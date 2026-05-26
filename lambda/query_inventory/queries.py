"""
Parameterized SQL queries for the query_inventory Lambda function.

All queries use ``%s`` placeholders (psycopg2 style) — never string
interpolation — to prevent SQL injection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Query 1: Stock for a specific product (by product_id or SKU)
# ---------------------------------------------------------------------------

_SQL_PRODUCT_STOCK_BY_ID = """
SELECT p.name, p.sku, i.quantity_available, i.min_stock_threshold
FROM inventory i
JOIN products p ON i.product_id = p.id
WHERE p.id = %s;
"""

_SQL_PRODUCT_STOCK_BY_SKU = """
SELECT p.name, p.sku, i.quantity_available, i.min_stock_threshold
FROM inventory i
JOIN products p ON i.product_id = p.id
WHERE p.sku = %s;
"""

_SQL_PRODUCT_STOCK_BY_ID_OR_SKU = """
SELECT p.name, p.sku, i.quantity_available, i.min_stock_threshold
FROM inventory i
JOIN products p ON i.product_id = p.id
WHERE p.id = %s OR p.sku = %s;
"""


def get_product_stock(
    conn: Any,
    product_id: Optional[int] = None,
    sku: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Return stock information for a specific product.

    Looks up by ``product_id``, ``sku``, or both (OR logic).  At least one
    of the two parameters must be provided.

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    product_id:
        Optional product ID.
    sku:
        Optional product SKU.

    Returns
    -------
    dict or None
        ``{"name": str, "sku": str, "quantity_available": int,
        "min_stock_threshold": int}`` or ``None`` if the product is not
        found.

    Raises
    ------
    ValueError
        If neither ``product_id`` nor ``sku`` is provided.
    """
    if product_id is None and sku is None:
        raise ValueError("At least one of 'product_id' or 'sku' must be provided.")

    with conn.cursor() as cur:
        if product_id is not None and sku is not None:
            cur.execute(_SQL_PRODUCT_STOCK_BY_ID_OR_SKU, (product_id, sku))
        elif product_id is not None:
            cur.execute(_SQL_PRODUCT_STOCK_BY_ID, (product_id,))
        else:
            cur.execute(_SQL_PRODUCT_STOCK_BY_SKU, (sku,))
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "name": row[0],
        "sku": row[1],
        "quantity_available": int(row[2]),
        "min_stock_threshold": int(row[3]),
    }


# ---------------------------------------------------------------------------
# Query 2: Products with low stock
# ---------------------------------------------------------------------------

_SQL_LOW_STOCK_DEFAULT = """
SELECT p.name, p.sku, c.name AS category,
       i.quantity_available, i.min_stock_threshold
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
WHERE i.quantity_available <= i.min_stock_threshold
ORDER BY i.quantity_available ASC;
"""

_SQL_LOW_STOCK_CUSTOM_THRESHOLD = """
SELECT p.name, p.sku, c.name AS category,
       i.quantity_available, i.min_stock_threshold
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
WHERE i.quantity_available <= %s
ORDER BY i.quantity_available ASC;
"""


def get_low_stock_products(
    conn: Any,
    threshold: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Return products whose available stock is at or below the threshold.

    When *threshold* is ``None``, the per-product ``min_stock_threshold``
    column is used as the comparison value.  When *threshold* is provided,
    it overrides the per-product threshold for all products.

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    threshold:
        Optional custom threshold.  Products with
        ``quantity_available <= threshold`` are returned.

    Returns
    -------
    list of dict
        Each element: ``{"name": str, "sku": str, "category": str,
        "quantity_available": int, "min_stock_threshold": int}``
        Sorted ascending by ``quantity_available``.
    """
    with conn.cursor() as cur:
        if threshold is not None:
            cur.execute(_SQL_LOW_STOCK_CUSTOM_THRESHOLD, (threshold,))
        else:
            cur.execute(_SQL_LOW_STOCK_DEFAULT)
        rows = cur.fetchall()

    return [
        {
            "name": row[0],
            "sku": row[1],
            "category": row[2],
            "quantity_available": int(row[3]),
            "min_stock_threshold": int(row[4]),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Query 3: Inventory summary by category
# ---------------------------------------------------------------------------

_SQL_INVENTORY_BY_CATEGORY = """
SELECT c.name AS category,
       SUM(i.quantity_available) AS total_units,
       COUNT(p.id) AS num_products
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY c.name;
"""

_SQL_INVENTORY_BY_CATEGORY_FILTERED = """
SELECT c.name AS category,
       SUM(i.quantity_available) AS total_units,
       COUNT(p.id) AS num_products
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
WHERE c.name = %s
GROUP BY c.name;
"""


def get_inventory_by_category(
    conn: Any,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return inventory totals grouped by product category.

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    category:
        Optional category name to restrict results to a single category.

    Returns
    -------
    list of dict
        Each element: ``{"category": str, "total_units": int,
        "num_products": int}``
    """
    with conn.cursor() as cur:
        if category is not None:
            cur.execute(_SQL_INVENTORY_BY_CATEGORY_FILTERED, (category,))
        else:
            cur.execute(_SQL_INVENTORY_BY_CATEGORY)
        rows = cur.fetchall()

    return [
        {
            "category": row[0],
            "total_units": int(row[1]),
            "num_products": int(row[2]),
        }
        for row in rows
    ]
