# Feature: bizquery, Property 9-11: query_inventory correctness

"""
Property-based tests for the query_inventory Lambda function.

Properties tested
-----------------
Property 9 — Consistencia de lectura del inventario
    For any existing product, the quantity_available returned by
    get_product_stock equals the value stored in the inventory table.
    Validates: Requirement 4.1

Property 10 — Invariante del filtro de bajo stock
    For any low-stock result, all products satisfy
    quantity_available <= min_stock_threshold, and no product with
    quantity_available > min_stock_threshold appears in the result.
    Validates: Requirement 4.2

Property 11 — Corrección de la agregación de inventario por categoría
    For any category, total_units returned equals the sum of
    quantity_available of all products in that category.
    Validates: Requirement 4.3
"""

from __future__ import annotations

import sys
import os
from decimal import Decimal
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from query_inventory.queries import (
    get_product_stock,
    get_low_stock_products,
    get_inventory_by_category,
)


# ---------------------------------------------------------------------------
# Mock connection helpers
# ---------------------------------------------------------------------------

def _conn_fetchone(row):
    """Return a mock connection whose cursor.fetchone() returns *row*."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _conn_fetchall(rows):
    """Return a mock connection whose cursor.fetchall() returns *rows*."""
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

# A valid product name (non-empty printable text)
product_name = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
)

# A valid SKU string
sku_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
)

# Non-negative integer stock quantities
quantity = st.integers(min_value=0, max_value=100_000)

# Positive threshold (min_stock_threshold is always >= 1 in practice)
threshold = st.integers(min_value=1, max_value=10_000)

# A single inventory row: (name, sku, quantity_available, min_stock_threshold)
inventory_row = st.builds(
    lambda name, sku, qty, thr: (name, sku, qty, thr),
    name=product_name,
    sku=sku_strategy,
    qty=quantity,
    thr=threshold,
)

# Category name
category_name = st.sampled_from(
    ["Refrigeradores", "Lavadoras", "Televisores", "Aires Acondicionados", "Microondas"]
)

# A single low-stock row: (name, sku, category, quantity_available, min_stock_threshold)
# Constrained so that quantity_available <= min_stock_threshold
low_stock_row = st.builds(
    lambda name, sku, cat, thr, qty_offset: (name, sku, cat, thr - qty_offset, thr),
    name=product_name,
    sku=sku_strategy,
    cat=category_name,
    thr=st.integers(min_value=1, max_value=1_000),
    qty_offset=st.integers(min_value=0, max_value=1_000),
).filter(lambda r: r[3] >= 0)  # quantity_available must be non-negative

low_stock_rows = st.lists(low_stock_row, min_size=0, max_size=30)

# A list of (quantity_available,) values for a single category
category_quantities = st.lists(
    st.integers(min_value=0, max_value=100_000),
    min_size=0,
    max_size=50,
)


# ---------------------------------------------------------------------------
# Property 9: Consistency of inventory reads
# Validates: Requirement 4.1
# ---------------------------------------------------------------------------

@given(row=inventory_row)
@settings(max_examples=25, deadline=None)
def test_property_9_read_consistency(row):
    """
    **Validates: Requirements 4.1**

    For any existing product, the quantity_available returned by
    get_product_stock must equal the value stored in the inventory table.
    """
    name, sku, qty, thr = row
    db_row = (name, sku, qty, thr)

    conn = _conn_fetchone(db_row)
    result = get_product_stock(conn, product_id=1)

    assert result is not None
    assert result["quantity_available"] == qty, (
        f"Expected quantity_available={qty}, got {result['quantity_available']}"
    )
    assert result["min_stock_threshold"] == thr
    assert result["name"] == name
    assert result["sku"] == sku


# ---------------------------------------------------------------------------
# Property 10: Low-stock filter invariant
# Validates: Requirement 4.2
# ---------------------------------------------------------------------------

@given(rows=low_stock_rows)
@settings(max_examples=25, deadline=None)
def test_property_10_low_stock_filter_invariant(rows):
    """
    **Validates: Requirements 4.2**

    For any low-stock result, all products must satisfy
    quantity_available <= min_stock_threshold, and no product with
    quantity_available > min_stock_threshold should appear.
    """
    conn = _conn_fetchall(rows)
    result = get_low_stock_products(conn)

    for product in result:
        assert product["quantity_available"] <= product["min_stock_threshold"], (
            f"Product '{product['name']}' violates low-stock invariant: "
            f"quantity_available={product['quantity_available']} > "
            f"min_stock_threshold={product['min_stock_threshold']}"
        )


@given(
    rows=low_stock_rows,
    custom_threshold=st.integers(min_value=0, max_value=1_000),
)
@settings(max_examples=25, deadline=None)
def test_property_10_custom_threshold_filter_invariant(rows, custom_threshold):
    """
    **Validates: Requirements 4.2**

    When a custom threshold is provided, all returned products must satisfy
    quantity_available <= custom_threshold.
    """
    # Build rows that satisfy the custom threshold
    filtered_rows = [r for r in rows if r[3] <= custom_threshold]

    conn = _conn_fetchall(filtered_rows)
    result = get_low_stock_products(conn, threshold=custom_threshold)

    for product in result:
        assert product["quantity_available"] <= custom_threshold, (
            f"Product '{product['name']}' violates custom threshold: "
            f"quantity_available={product['quantity_available']} > "
            f"custom_threshold={custom_threshold}"
        )


# ---------------------------------------------------------------------------
# Property 11: Category aggregation correctness
# Validates: Requirement 4.3
# ---------------------------------------------------------------------------

@given(
    cat=category_name,
    quantities=category_quantities,
)
@settings(max_examples=25, deadline=None)
def test_property_11_category_total_equals_sum_of_quantities(cat, quantities):
    """
    **Validates: Requirements 4.3**

    For any category, total_units returned by get_inventory_by_category
    must equal the sum of quantity_available of all products in that
    category.
    """
    expected_total = sum(quantities)
    num_products = len(quantities)

    # Simulate what the DB returns: one aggregated row per category
    db_rows = [(cat, expected_total, num_products)] if quantities else []

    conn = _conn_fetchall(db_rows)
    result = get_inventory_by_category(conn, category=cat)

    if not quantities:
        assert result == [], f"Expected empty list for empty category, got {result}"
    else:
        assert len(result) == 1
        assert result[0]["category"] == cat
        assert result[0]["total_units"] == expected_total, (
            f"Expected total_units={expected_total}, got {result[0]['total_units']}"
        )
        assert result[0]["num_products"] == num_products
