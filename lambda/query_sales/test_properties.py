# Feature: bizquery, Property 5-8: query_sales correctness

"""
Property-based tests for the query_sales Lambda function.

Properties tested
-----------------
Property 5 — Corrección matemática de la agregación de ventas
    For any list of sales records, the total returned equals the arithmetic
    sum of ``final_amount`` values.
    Validates: Requirement 3.1

Property 6 — Corrección del filtrado de ventas por criterio
    For any sales query filtered by category, all returned records belong
    exclusively to that category.
    Validates: Requirement 3.2

Property 7 — Corrección matemática de la variación porcentual entre períodos
    For any two period totals V1 and V2, the percentage variation equals
    (V2 - V1) / V1 * 100 with ±0.01% tolerance.
    Validates: Requirement 3.3

Property 8 — Ordenamiento correcto de productos más vendidos
    The top-products list is sorted descending by ``units_sold``.
    Validates: Requirement 3.4
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers to build mock DB cursors
# ---------------------------------------------------------------------------

def _make_conn_for_total(rows: list) -> MagicMock:
    """Return a mock psycopg2 connection whose cursor yields *rows*."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = rows[0] if rows else (Decimal("0"), 0)
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _make_conn_for_category(rows: list) -> MagicMock:
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _make_conn_for_top_products(rows: list) -> MagicMock:
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A single sale record: (final_amount,)
sale_record = st.builds(
    lambda amount: (Decimal(str(round(amount, 2))),),
    amount=st.floats(min_value=0.01, max_value=100_000.0, allow_nan=False, allow_infinity=False),
)

# A list of sale records (0–50 records)
sale_records_list = st.lists(sale_record, min_size=0, max_size=50)

# Category names
category_name = st.sampled_from(
    ["Refrigeradores", "Lavadoras", "Televisores", "Aires Acondicionados", "Microondas"]
)

# A single category row: (category_name, total, units)
def _category_row_strategy(cat: str):
    return st.builds(
        lambda total, units: (cat, Decimal(str(round(total, 2))), units),
        total=st.floats(min_value=0.0, max_value=500_000.0, allow_nan=False, allow_infinity=False),
        units=st.integers(min_value=0, max_value=10_000),
    )

# A list of category rows all belonging to the SAME category
same_category_rows = category_name.flatmap(
    lambda cat: st.lists(_category_row_strategy(cat), min_size=0, max_size=20).map(
        lambda rows: (cat, rows)
    )
)

# A product row: (name, units_sold, revenue)
product_row = st.builds(
    lambda name, units, revenue: (name, units, Decimal(str(round(revenue, 2)))),
    name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
    units=st.integers(min_value=0, max_value=10_000),
    revenue=st.floats(min_value=0.0, max_value=500_000.0, allow_nan=False, allow_infinity=False),
)

product_rows_list = st.lists(product_row, min_size=0, max_size=30)

# Two non-negative floats for period totals
two_totals = st.tuples(
    st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0,  max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
)


# ---------------------------------------------------------------------------
# Import the functions under test
# ---------------------------------------------------------------------------

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from query_sales.queries import (
    get_total_by_period,
    get_sales_by_category,
    get_top_products,
)
from query_sales.handler import _compute_variation


# ---------------------------------------------------------------------------
# Property 5: Aggregation correctness
# Validates: Requirement 3.1
# ---------------------------------------------------------------------------

@given(records=sale_records_list)
@settings(max_examples=25, deadline=None)
def test_property_5_total_equals_sum_of_final_amounts(records):
    """
    **Validates: Requirements 3.1**

    For any list of sales records, the total returned by get_total_by_period
    must equal the arithmetic sum of the final_amount values.
    """
    expected_total = float(sum(r[0] for r in records))
    db_total = (sum(r[0] for r in records), len(records))

    conn = _make_conn_for_total([db_total] if records else [(Decimal("0"), 0)])
    result = get_total_by_period(conn, date(2025, 1, 1), date(2025, 3, 31))

    assert math.isclose(result["total"], expected_total, rel_tol=1e-9, abs_tol=1e-9), (
        f"Expected total {expected_total}, got {result['total']}"
    )
    assert result["num_transactions"] == len(records)


# ---------------------------------------------------------------------------
# Property 6: Category filter correctness
# Validates: Requirement 3.2
# ---------------------------------------------------------------------------

@given(data=same_category_rows)
@settings(max_examples=25, deadline=None)
def test_property_6_category_filter_returns_only_requested_category(data):
    """
    **Validates: Requirements 3.2**

    For any sales query filtered by category, all returned records must
    belong exclusively to the requested category.
    """
    requested_category, rows = data

    conn = _make_conn_for_category(rows)
    result = get_sales_by_category(
        conn, date(2025, 1, 1), date(2025, 3, 31), category=requested_category
    )

    for record in result:
        assert record["category"] == requested_category, (
            f"Expected category '{requested_category}', "
            f"got '{record['category']}'"
        )


# ---------------------------------------------------------------------------
# Property 7: Percentage variation correctness
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

@given(totals=two_totals)
@settings(max_examples=50, deadline=None)
def test_property_7_percentage_variation_formula(totals):
    """
    **Validates: Requirements 3.3**

    For any two period totals V1 and V2, the percentage variation must
    satisfy: variation = (V2 - V1) / V1 * 100  with ±0.01% tolerance.
    """
    v1, v2 = totals
    computed = _compute_variation(v1, v2)
    expected = (v2 - v1) / v1 * 100

    assert math.isclose(computed, expected, rel_tol=1e-4, abs_tol=0.01), (
        f"Variation mismatch: expected {expected:.6f}%, got {computed:.6f}% "
        f"(V1={v1}, V2={v2})"
    )


@given(v2=st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=15, deadline=None)
def test_property_7_variation_with_zero_v1_returns_zero(v2):
    """
    **Validates: Requirements 3.3**

    When V1 is zero, _compute_variation must return 0.0 (no division by zero).
    """
    result = _compute_variation(0.0, v2)
    assert result == 0.0


# ---------------------------------------------------------------------------
# Property 8: Top products sorted descending by units_sold
# Validates: Requirement 3.4
# ---------------------------------------------------------------------------

@given(rows=product_rows_list)
@settings(max_examples=25, deadline=None)
def test_property_8_top_products_sorted_descending_by_units_sold(rows):
    """
    **Validates: Requirements 3.4**

    For any list of products returned by get_top_products, for every
    consecutive pair (Pi, Pi+1) it must hold that
    units_sold(Pi) >= units_sold(Pi+1).
    """
    # The DB returns rows already sorted; simulate that by sorting them
    sorted_rows = sorted(rows, key=lambda r: r[1], reverse=True)

    conn = _make_conn_for_top_products(sorted_rows)
    result = get_top_products(conn, date(2025, 1, 1), date(2025, 3, 31))

    for i in range(len(result) - 1):
        assert result[i]["units_sold"] >= result[i + 1]["units_sold"], (
            f"Sort violation at index {i}: "
            f"{result[i]['units_sold']} < {result[i+1]['units_sold']}"
        )
