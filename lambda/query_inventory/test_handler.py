"""
Unit tests for the query_inventory Lambda handler.

Covers
------
- Non-existent product returns descriptive not-found message
- Category with no products returns empty list
- Custom low_stock_threshold is applied correctly
- DB unavailable returns DB_UNAVAILABLE error
- Successful product stock query returns correct data
"""

from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

# Ensure the lambda/ directory is on the path so shared imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from query_inventory.handler import handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    product_id=None,
    sku=None,
    category=None,
    low_stock_threshold=None,
    user_id="user-123",
    user_role="employee",
):
    params = {}
    if product_id is not None:
        params["product_id"] = product_id
    if sku is not None:
        params["sku"] = sku
    if category is not None:
        params["category"] = category
    if low_stock_threshold is not None:
        params["low_stock_threshold"] = low_stock_threshold
    return {
        "tool_name": "query_inventory",
        "parameters": params,
        "user_id": user_id,
        "user_role": user_role,
    }


def _make_cursor_sequence(responses):
    """
    Return a side_effect function for conn.cursor that yields cursors
    returning values from *responses* in order.

    Each element of *responses* is a dict with optional keys:
      - "fetchone": value for cur.fetchone()
      - "fetchall": value for cur.fetchall()
    """
    call_count = [0]

    def cursor_factory():
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(responses):
            resp = responses[idx]
            if "fetchone" in resp:
                cur.fetchone.return_value = resp["fetchone"]
            if "fetchall" in resp:
                cur.fetchall.return_value = resp["fetchall"]
        return cur

    return cursor_factory


def _patch_db(responses):
    """
    Context manager that patches get_db_connection with a mock connection
    whose cursors return values from *responses* in sequence.

    Handler call order for product lookup:
      0 → get_product_stock (fetchone)

    Handler call order for general overview:
      0 → get_low_stock_products  (fetchall)
      1 → get_inventory_by_category (fetchall)
    """
    conn = MagicMock()
    conn.cursor.side_effect = _make_cursor_sequence(responses)

    @contextmanager
    def fake_get_db_connection():
        yield conn

    return patch("query_inventory.handler.get_db_connection", fake_get_db_connection)


# ---------------------------------------------------------------------------
# Test 1: Non-existent product returns descriptive not-found message
# ---------------------------------------------------------------------------

def test_nonexistent_product_returns_not_found_message():
    """
    Querying a product_id that does not exist in inventory should return
    a success response with found=False and a descriptive message.
    """
    responses = [
        {"fetchone": None},  # get_product_stock → not found
    ]
    with _patch_db(responses):
        response = handler(_make_event(product_id=9999), None)

    assert response["success"] is True
    data = response["data"]
    assert data["found"] is False
    assert "9999" in data["message"] or "product_id" in data["message"]
    assert "No se encontró" in data["message"]


def test_nonexistent_sku_returns_not_found_message():
    """
    Querying a SKU that does not exist in inventory should return
    a success response with found=False and a descriptive message.
    """
    responses = [
        {"fetchone": None},  # get_product_stock → not found
    ]
    with _patch_db(responses):
        response = handler(_make_event(sku="SKU-NONEXISTENT"), None)

    assert response["success"] is True
    data = response["data"]
    assert data["found"] is False
    assert "SKU-NONEXISTENT" in data["message"]
    assert "No se encontró" in data["message"]


# ---------------------------------------------------------------------------
# Test 2: Category with no products returns empty list
# ---------------------------------------------------------------------------

def test_category_with_no_products_returns_empty_list():
    """
    Querying a category that has no products should return empty lists
    for both low_stock_products and inventory_by_category.
    """
    responses = [
        {"fetchall": []},  # get_low_stock_products
        {"fetchall": []},  # get_inventory_by_category
    ]
    with _patch_db(responses):
        response = handler(_make_event(category="Drones"), None)

    assert response["success"] is True
    data = response["data"]
    assert data["low_stock_products"] == []
    assert data["inventory_by_category"] == []


# ---------------------------------------------------------------------------
# Test 3: Custom low_stock_threshold is applied correctly
# ---------------------------------------------------------------------------

def test_custom_low_stock_threshold_is_applied():
    """
    When low_stock_threshold is provided, the handler should pass it to
    get_low_stock_products and return only products below that threshold.
    """
    # Simulate DB returning products that satisfy quantity_available <= 20
    low_stock_rows = [
        ("Refrigerador Mabe 300L", "REF-MBE-300L", "Refrigeradores", 3, 5),
        ("Lavadora Mabe 10kg",     "LAV-MBE-10KG", "Lavadoras",       4, 8),
        ("Microondas Mabe 20L",    "MIC-MBE-20L",  "Microondas",      2, 15),
    ]
    category_rows = [
        ("Refrigeradores", 3, 1),
        ("Lavadoras", 4, 1),
        ("Microondas", 2, 1),
    ]
    responses = [
        {"fetchall": low_stock_rows},  # get_low_stock_products
        {"fetchall": category_rows},   # get_inventory_by_category
    ]
    with _patch_db(responses):
        response = handler(_make_event(low_stock_threshold=20), None)

    assert response["success"] is True
    data = response["data"]
    assert len(data["low_stock_products"]) == 3
    # All returned products must satisfy quantity_available <= 20
    for product in data["low_stock_products"]:
        assert product["quantity_available"] <= 20


# ---------------------------------------------------------------------------
# Test 4: DB unavailable returns DB_UNAVAILABLE error
# ---------------------------------------------------------------------------

def test_db_unavailable_returns_db_unavailable_error():
    """When the DB raises an exception, the handler must return DB_UNAVAILABLE."""

    @contextmanager
    def failing_db():
        raise Exception("Connection refused")
        yield  # makes it a generator

    with patch("query_inventory.handler.get_db_connection", failing_db):
        response = handler(_make_event(product_id=1), None)

    assert response["success"] is False
    assert response["error"]["code"] == "DB_UNAVAILABLE"
    assert "base de datos" in response["error"]["message"]


# ---------------------------------------------------------------------------
# Test 5: Successful product stock query returns correct data
# ---------------------------------------------------------------------------

def test_successful_product_stock_query_returns_correct_data():
    """
    A valid product_id query should return found=True with the correct
    product stock data.
    """
    db_row = (
        "Refrigerador Samsung No Frost 400L",  # name
        "REF-SAM-400L",                         # sku
        25,                                     # quantity_available
        5,                                      # min_stock_threshold
    )
    responses = [
        {"fetchone": db_row},  # get_product_stock
    ]
    with _patch_db(responses):
        response = handler(_make_event(product_id=1), None)

    assert response["success"] is True
    data = response["data"]
    assert data["found"] is True
    product = data["product"]
    assert product["name"] == "Refrigerador Samsung No Frost 400L"
    assert product["sku"] == "REF-SAM-400L"
    assert product["quantity_available"] == 25
    assert product["min_stock_threshold"] == 5


# ---------------------------------------------------------------------------
# Test 6: General overview (no product_id/sku) returns both sections
# ---------------------------------------------------------------------------

def test_general_overview_returns_low_stock_and_by_category():
    """
    When no product_id or sku is provided, the handler should return
    both low_stock_products and inventory_by_category.
    """
    low_stock_rows = [
        ("Refrigerador Mabe 300L", "REF-MBE-300L", "Refrigeradores", 3, 5),
    ]
    category_rows = [
        ("Refrigeradores", 58, 4),
        ("Lavadoras", 71, 4),
    ]
    responses = [
        {"fetchall": low_stock_rows},
        {"fetchall": category_rows},
    ]
    with _patch_db(responses):
        response = handler(_make_event(), None)

    assert response["success"] is True
    data = response["data"]
    assert "low_stock_products" in data
    assert "inventory_by_category" in data
    assert len(data["low_stock_products"]) == 1
    assert len(data["inventory_by_category"]) == 2


# ---------------------------------------------------------------------------
# Test 7: Invalid product_id returns INVALID_PARAMS
# ---------------------------------------------------------------------------

def test_invalid_product_id_returns_invalid_params():
    """A negative product_id must return INVALID_PARAMS without hitting the DB."""
    with patch("query_inventory.handler.get_db_connection") as mock_db:
        response = handler(_make_event(product_id=-1), None)

    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_PARAMS"
    mock_db.assert_not_called()
