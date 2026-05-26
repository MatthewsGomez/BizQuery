"""
Unit tests for the query_sales Lambda handler.

Covers
------
- Period with no sales returns empty/zero result
- Filter by non-existent category returns empty list
- compare_period returns both period data and percentage variation
- Employee role with include_financial=True returns ACCESS_DENIED
- DB exception returns DB_UNAVAILABLE error
"""

from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Ensure the lambda/ directory is on the path so shared imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from query_sales.handler import handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    period="2025-Q1",
    product_id=None,
    category=None,
    compare_period=None,
    include_financial=False,
    user_id="user-123",
    user_role="owner",
):
    params = {"period": period, "include_financial": include_financial}
    if product_id is not None:
        params["product_id"] = product_id
    if category is not None:
        params["category"] = category
    if compare_period is not None:
        params["compare_period"] = compare_period
    return {
        "tool_name": "query_sales",
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

    Handler call order (no compare_period):
      0 → get_total_by_period   (fetchone)
      1 → get_sales_by_category (fetchall)
      2 → get_top_products      (fetchall)

    Handler call order (with compare_period):
      0 → get_total_by_period   main  (fetchone)
      1 → get_sales_by_category main  (fetchall)
      2 → get_top_products      main  (fetchall)
      3 → get_total_by_period   cmp   (fetchone)
      4 → get_sales_by_category cmp   (fetchall)
      5 → get_top_products      cmp   (fetchall)
    """
    conn = MagicMock()
    conn.cursor.side_effect = _make_cursor_sequence(responses)

    @contextmanager
    def fake_get_db_connection():
        yield conn

    return patch("query_sales.handler.get_db_connection", fake_get_db_connection)


# ---------------------------------------------------------------------------
# Test 1: Period with no sales returns zero total and empty lists
# ---------------------------------------------------------------------------

def test_period_with_no_sales_returns_zero_result():
    """A period that has no sales should return total=0 and empty lists."""
    responses = [
        {"fetchone": (Decimal("0"), 0)},   # get_total_by_period
        {"fetchall": []},                   # get_sales_by_category
        {"fetchall": []},                   # get_top_products
    ]
    with _patch_db(responses):
        response = handler(_make_event(period="2020-Q1"), None)

    assert response["success"] is True
    data = response["data"]
    assert data["total"] == 0.0
    assert data["num_transactions"] == 0
    assert data["by_category"] == []
    assert data["top_products"] == []


# ---------------------------------------------------------------------------
# Test 2: Filter by non-existent category returns empty list
# ---------------------------------------------------------------------------

def test_filter_by_nonexistent_category_returns_empty_list():
    """Querying a category that has no sales should return an empty list."""
    responses = [
        {"fetchone": (Decimal("0"), 0)},
        {"fetchall": []},
        {"fetchall": []},
    ]
    with _patch_db(responses):
        response = handler(_make_event(period="2025-Q1", category="Drones"), None)

    assert response["success"] is True
    assert response["data"]["by_category"] == []


# ---------------------------------------------------------------------------
# Test 3: compare_period returns both period data and percentage variation
# ---------------------------------------------------------------------------

def test_compare_period_returns_variation():
    """
    When compare_period is provided, the response must include both period
    totals and the computed percentage variation.

    Main period total: 2000.00
    Compare period total: 1000.00
    Expected variation: (2000 - 1000) / 1000 * 100 = 100.0%
    """
    category_rows = [("Refrigeradores", Decimal("2000.00"), 2)]
    product_rows = [("Refrigerador Samsung", 2, Decimal("2000.00"))]

    responses = [
        # Main period
        {"fetchone": (Decimal("2000.00"), 10)},  # total
        {"fetchall": category_rows},              # by_category
        {"fetchall": product_rows},               # top_products
        # Compare period
        {"fetchone": (Decimal("1000.00"), 5)},   # total
        {"fetchall": category_rows},              # by_category
        {"fetchall": product_rows},               # top_products
    ]

    with _patch_db(responses):
        response = handler(
            _make_event(period="2025-Q1", compare_period="2024-Q1"), None
        )

    assert response["success"] is True
    data = response["data"]

    assert "compare_period" in data
    assert "compare_total" in data
    assert "variation_pct" in data

    # variation = (V2 - V1) / V1 * 100 = (2000 - 1000) / 1000 * 100 = 100.0
    assert abs(data["variation_pct"] - 100.0) < 0.01, (
        f"Expected variation ~100.0%, got {data['variation_pct']}"
    )
    assert data["compare_total"] == 1000.0
    assert data["total"] == 2000.0


# ---------------------------------------------------------------------------
# Test 4: Employee role with include_financial=True returns ACCESS_DENIED
# ---------------------------------------------------------------------------

def test_employee_with_include_financial_returns_access_denied():
    """
    An employee requesting financial data must receive ACCESS_DENIED
    without any DB query being executed.
    """
    with patch("query_sales.handler.get_db_connection") as mock_db:
        response = handler(
            _make_event(period="2025-Q1", include_financial=True, user_role="employee"),
            None,
        )

    assert response["success"] is False
    assert response["error"]["code"] == "ACCESS_DENIED"
    assert "financieros" in response["error"]["message"]
    mock_db.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: DB exception returns DB_UNAVAILABLE error
# ---------------------------------------------------------------------------

def test_db_exception_returns_db_unavailable():
    """When the DB raises an exception, the handler must return DB_UNAVAILABLE."""

    @contextmanager
    def failing_db():
        raise Exception("Connection refused")
        yield  # makes it a generator

    with patch("query_sales.handler.get_db_connection", failing_db):
        response = handler(_make_event(period="2025-Q1"), None)

    assert response["success"] is False
    assert response["error"]["code"] == "DB_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Test 6: Owner role with include_financial=True is allowed
# ---------------------------------------------------------------------------

def test_owner_with_include_financial_is_allowed():
    """An owner requesting financial data must not be blocked."""
    responses = [
        {"fetchone": (Decimal("5000.00"), 20)},
        {"fetchall": [("Lavadoras", Decimal("5000.00"), 10)]},
        {"fetchall": [("Lavadora Samsung", 10, Decimal("5000.00"))]},
    ]
    with _patch_db(responses):
        response = handler(
            _make_event(period="2025-Q1", include_financial=True, user_role="owner"),
            None,
        )

    assert response["success"] is True
    assert response["data"]["total"] == 5000.0


# ---------------------------------------------------------------------------
# Test 7: Missing period returns INVALID_PARAMS
# ---------------------------------------------------------------------------

def test_missing_period_returns_invalid_params():
    """A request without a period must return INVALID_PARAMS."""
    event = {
        "tool_name": "query_sales",
        "parameters": {},
        "user_id": "user-1",
        "user_role": "owner",
    }
    response = handler(event, None)
    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_PARAMS"
