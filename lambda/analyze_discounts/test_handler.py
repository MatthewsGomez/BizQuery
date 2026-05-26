"""
Unit tests for the analyze_discounts Lambda handler.

Covers
------
- No active discounts returns success with empty recommendations list
- Product with no sales history is excluded from recommendations
- Suggested discount never exceeds 80% (100 - MIN_PROFIT_MARGIN_PCT=20)
- Employee role returns ACCESS_DENIED
- DB unavailable returns DB_UNAVAILABLE error
- Valid owner request with recommendations returns success
"""

from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

# Ensure the lambda/ directory is on the path so shared imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyze_discounts.handler import handler
from analyze_discounts.analyzer import MIN_PROFIT_MARGIN_PCT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    product_id=None,
    category=None,
    analysis_period=None,
    user_id="owner-123",
    user_role="owner",
):
    params = {}
    if product_id is not None:
        params["product_id"] = product_id
    if category is not None:
        params["category"] = category
    if analysis_period is not None:
        params["analysis_period"] = analysis_period
    return {
        "tool_name": "analyze_discounts",
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


def _patch_db(active_discounts_rows, rotation_rows):
    """
    Context manager that patches get_db_connection with a mock connection.

    Handler call order:
      0 → get_active_discounts          (fetchall)
      1 → get_inventory_rotation_analysis (fetchall)
    """
    responses = [
        {"fetchall": active_discounts_rows},
        {"fetchall": rotation_rows},
    ]
    conn = MagicMock()
    conn.cursor.side_effect = _make_cursor_sequence(responses)

    @contextmanager
    def fake_get_db_connection():
        yield conn

    return patch(
        "analyze_discounts.handler.get_db_connection", fake_get_db_connection
    )


# ---------------------------------------------------------------------------
# Rotation row builder
# ---------------------------------------------------------------------------

def _rotation_row(
    product_id=1,
    name="Producto Test",
    unit_price=1000.0,
    category="Refrigeradores",
    quantity_available=50,
    units_sold=10,
    revenue=10000.0,
    days_of_stock=150.0,
):
    """Build a tuple matching the columns returned by get_inventory_rotation_analysis."""
    return (
        product_id,
        name,
        unit_price,
        category,
        quantity_available,
        units_sold,
        revenue,
        days_of_stock,
    )


# ---------------------------------------------------------------------------
# Test 1: No active discounts returns success with empty recommendations list
# ---------------------------------------------------------------------------

def test_no_active_discounts_returns_success_with_empty_recommendations():
    """
    When there are no active discounts and no rotation data, the handler
    should return success with an empty recommendations list.
    """
    with _patch_db(active_discounts_rows=[], rotation_rows=[]):
        response = handler(_make_event(), None)

    assert response["success"] is True
    data = response["data"]
    assert "recommendations" in data
    assert data["recommendations"] == []
    assert "summary" in data


# ---------------------------------------------------------------------------
# Test 2: Product with no sales history is excluded from recommendations
# ---------------------------------------------------------------------------

def test_product_with_no_sales_history_excluded_from_recommendations():
    """
    A product with units_sold=0 and days_of_stock=999 (sentinel) should be
    excluded from recommendations (Req 5.6: insufficient sales history).
    """
    # Product with no sales history: units_sold=0, days_of_stock=999
    no_history_row = _rotation_row(
        product_id=1,
        name="Producto Sin Historial",
        units_sold=0,
        days_of_stock=999.0,
    )

    with _patch_db(active_discounts_rows=[], rotation_rows=[no_history_row]):
        response = handler(_make_event(), None)

    assert response["success"] is True
    recommendations = response["data"]["recommendations"]
    # The product with no sales history must not appear in recommendations
    product_ids = [r["product_id"] for r in recommendations]
    assert 1 not in product_ids


# ---------------------------------------------------------------------------
# Test 3: Suggested discount never exceeds 80% (100 - MIN_PROFIT_MARGIN_PCT)
# ---------------------------------------------------------------------------

def test_suggested_discount_never_exceeds_max_allowed():
    """
    The suggested_discount_pct in any recommendation must never exceed
    (100 - MIN_PROFIT_MARGIN_PCT) = 80%, respecting the minimum profit margin.
    """
    max_allowed = 100.0 - MIN_PROFIT_MARGIN_PCT  # 80%

    # Create a product with extreme excess stock to try to push discount high
    extreme_stock_row = _rotation_row(
        product_id=2,
        name="Producto Exceso Stock",
        unit_price=500.0,
        category="Lavadoras",
        quantity_available=10000,  # extreme excess
        units_sold=1,              # very low rotation
        revenue=500.0,
        days_of_stock=300.0,
    )

    with _patch_db(active_discounts_rows=[], rotation_rows=[extreme_stock_row]):
        response = handler(_make_event(), None)

    assert response["success"] is True
    recommendations = response["data"]["recommendations"]

    for rec in recommendations:
        assert rec["suggested_discount_pct"] <= max_allowed, (
            f"Discount {rec['suggested_discount_pct']}% exceeds max allowed {max_allowed}%"
        )


# ---------------------------------------------------------------------------
# Test 4: Employee role returns ACCESS_DENIED
# ---------------------------------------------------------------------------

def test_employee_role_returns_access_denied():
    """
    A user with role 'employee' must receive ACCESS_DENIED without any
    DB query being executed (Req 5.7 / 8.6).
    """
    with patch("analyze_discounts.handler.get_db_connection") as mock_db:
        response = handler(
            _make_event(user_role="employee"),
            None,
        )

    assert response["success"] is False
    assert response["error"]["code"] == "ACCESS_DENIED"
    assert "Dueño" in response["error"]["message"] or "permisos" in response["error"]["message"]
    mock_db.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: DB unavailable returns DB_UNAVAILABLE error
# ---------------------------------------------------------------------------

def test_db_unavailable_returns_db_unavailable_error():
    """When the DB raises an exception, the handler must return DB_UNAVAILABLE."""

    @contextmanager
    def failing_db():
        raise Exception("Connection refused")
        yield  # makes it a generator

    with patch("analyze_discounts.handler.get_db_connection", failing_db):
        response = handler(_make_event(), None)

    assert response["success"] is False
    assert response["error"]["code"] == "DB_UNAVAILABLE"
    assert "base de datos" in response["error"]["message"]


# ---------------------------------------------------------------------------
# Test 6: Valid owner request with recommendations returns success
# ---------------------------------------------------------------------------

def test_valid_owner_request_returns_success_with_recommendations():
    """
    A valid owner request with products that qualify for discount
    recommendations should return success with a non-empty recommendations list.

    We set up two products in the same category so that category averages
    can be computed and the high-stock/low-rotation criterion can trigger.
    """
    # Product A: high stock, low rotation -> should get a recommendation
    product_a = _rotation_row(
        product_id=10,
        name="Refrigerador Samsung 400L",
        unit_price=1500.0,
        category="Refrigeradores",
        quantity_available=100,  # much higher than avg (avg will be ~55)
        units_sold=2,            # much lower than avg (avg will be ~11)
        revenue=3000.0,
        days_of_stock=150.0,
    )
    # Product B: normal stock and rotation (provides category average baseline)
    product_b = _rotation_row(
        product_id=11,
        name="Refrigerador LG 350L",
        unit_price=1200.0,
        category="Refrigeradores",
        quantity_available=10,   # low stock
        units_sold=20,           # high rotation
        revenue=24000.0,
        days_of_stock=15.0,
    )

    with _patch_db(active_discounts_rows=[], rotation_rows=[product_a, product_b]):
        response = handler(_make_event(), None)

    assert response["success"] is True
    data = response["data"]
    assert "recommendations" in data
    assert "summary" in data
    # At least product A should generate a recommendation
    assert len(data["recommendations"]) >= 1
    # Verify recommendation structure
    rec = data["recommendations"][0]
    assert "product_id" in rec
    assert "product_name" in rec
    assert "current_stock" in rec
    assert "days_of_stock_estimated" in rec
    assert "suggested_discount_pct" in rec
    assert "rationale" in rec
    assert "priority" in rec
