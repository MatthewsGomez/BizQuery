"""
Parameterized SQL queries for the analyze_discounts Lambda function.

All queries use ``%s`` placeholders (psycopg2 style) -- never string
interpolation -- to prevent SQL injection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Query 1: Active discounts (optionally filtered by product or category)
# ---------------------------------------------------------------------------

_SQL_ACTIVE_DISCOUNTS = """
SELECT d.id, d.name, d.discount_pct, d.start_date, d.end_date,
       d.is_active, d.product_id, d.category_id,
       p.name AS product_name, c.name AS category_name
FROM discounts d
LEFT JOIN products p ON d.product_id = p.id
LEFT JOIN categories c ON d.category_id = c.id
WHERE d.is_active = TRUE
  AND d.end_date >= CURRENT_DATE
ORDER BY d.end_date ASC;
"""

_SQL_ACTIVE_DISCOUNTS_BY_PRODUCT = """
SELECT d.id, d.name, d.discount_pct, d.start_date, d.end_date,
       d.is_active, d.product_id, d.category_id,
       p.name AS product_name, c.name AS category_name
FROM discounts d
LEFT JOIN products p ON d.product_id = p.id
LEFT JOIN categories c ON d.category_id = c.id
WHERE d.is_active = TRUE
  AND d.end_date >= CURRENT_DATE
  AND d.product_id = %s
ORDER BY d.end_date ASC;
"""

_SQL_ACTIVE_DISCOUNTS_BY_CATEGORY = """
SELECT d.id, d.name, d.discount_pct, d.start_date, d.end_date,
       d.is_active, d.product_id, d.category_id,
       p.name AS product_name, c.name AS category_name
FROM discounts d
LEFT JOIN products p ON d.product_id = p.id
LEFT JOIN categories c ON d.category_id = c.id
WHERE d.is_active = TRUE
  AND d.end_date >= CURRENT_DATE
  AND c.name = %s
ORDER BY d.end_date ASC;
"""

_SQL_ACTIVE_DISCOUNTS_BY_PRODUCT_AND_CATEGORY = """
SELECT d.id, d.name, d.discount_pct, d.start_date, d.end_date,
       d.is_active, d.product_id, d.category_id,
       p.name AS product_name, c.name AS category_name
FROM discounts d
LEFT JOIN products p ON d.product_id = p.id
LEFT JOIN categories c ON d.category_id = c.id
WHERE d.is_active = TRUE
  AND d.end_date >= CURRENT_DATE
  AND (d.product_id = %s OR c.name = %s)
ORDER BY d.end_date ASC;
"""


def get_active_discounts(
    conn: Any,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return currently active discounts.

    A discount is considered active when ``is_active = TRUE`` and
    ``end_date >= CURRENT_DATE``.  Results can be optionally filtered by
    ``product_id``, ``category`` name, or both (OR logic).

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    product_id:
        Optional product ID to restrict results to discounts that apply to
        that specific product.
    category:
        Optional category name to restrict results to discounts that apply
        to that category.

    Returns
    -------
    list of dict
        Each element: ``{"id": int, "name": str, "discount_pct": float,
        "start_date": date, "end_date": date, "is_active": bool,
        "product_id": int | None, "category_id": int | None,
        "product_name": str | None, "category_name": str | None}``
        Sorted ascending by ``end_date``.
    """
    with conn.cursor() as cur:
        if product_id is not None and category is not None:
            cur.execute(
                _SQL_ACTIVE_DISCOUNTS_BY_PRODUCT_AND_CATEGORY,
                (product_id, category),
            )
        elif product_id is not None:
            cur.execute(_SQL_ACTIVE_DISCOUNTS_BY_PRODUCT, (product_id,))
        elif category is not None:
            cur.execute(_SQL_ACTIVE_DISCOUNTS_BY_CATEGORY, (category,))
        else:
            cur.execute(_SQL_ACTIVE_DISCOUNTS)
        rows = cur.fetchall()

    return [
        {
            "id": int(row[0]),
            "name": row[1],
            "discount_pct": float(row[2]),
            "start_date": row[3],
            "end_date": row[4],
            "is_active": bool(row[5]),
            "product_id": int(row[6]) if row[6] is not None else None,
            "category_id": int(row[7]) if row[7] is not None else None,
            "product_name": row[8],
            "category_name": row[9],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Query 2: Inventory rotation analysis vs. sales
# ---------------------------------------------------------------------------

_SQL_ROTATION_ANALYSIS = """
SELECT p.id, p.name, p.unit_price, c.name AS category,
       i.quantity_available,
       COALESCE(SUM(si.quantity), 0) AS units_sold,
       COALESCE(SUM(si.subtotal), 0.0) AS revenue,
       CASE WHEN COALESCE(SUM(si.quantity), 0) > 0
            THEN (i.quantity_available / (SUM(si.quantity) / %s::float))
            ELSE 999
       END AS days_of_stock
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
LEFT JOIN sale_items si ON si.product_id = p.id
LEFT JOIN sales s ON si.sale_id = s.id
    AND s.sale_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
    AND s.status = 'completed'
GROUP BY p.id, p.name, p.unit_price, c.name, i.quantity_available
ORDER BY days_of_stock DESC;
"""

_SQL_ROTATION_ANALYSIS_BY_PRODUCT = """
SELECT p.id, p.name, p.unit_price, c.name AS category,
       i.quantity_available,
       COALESCE(SUM(si.quantity), 0) AS units_sold,
       COALESCE(SUM(si.subtotal), 0.0) AS revenue,
       CASE WHEN COALESCE(SUM(si.quantity), 0) > 0
            THEN (i.quantity_available / (SUM(si.quantity) / %s::float))
            ELSE 999
       END AS days_of_stock
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
LEFT JOIN sale_items si ON si.product_id = p.id
LEFT JOIN sales s ON si.sale_id = s.id
    AND s.sale_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
    AND s.status = 'completed'
WHERE p.id = %s
GROUP BY p.id, p.name, p.unit_price, c.name, i.quantity_available
ORDER BY days_of_stock DESC;
"""

_SQL_ROTATION_ANALYSIS_BY_CATEGORY = """
SELECT p.id, p.name, p.unit_price, c.name AS category,
       i.quantity_available,
       COALESCE(SUM(si.quantity), 0) AS units_sold,
       COALESCE(SUM(si.subtotal), 0.0) AS revenue,
       CASE WHEN COALESCE(SUM(si.quantity), 0) > 0
            THEN (i.quantity_available / (SUM(si.quantity) / %s::float))
            ELSE 999
       END AS days_of_stock
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
LEFT JOIN sale_items si ON si.product_id = p.id
LEFT JOIN sales s ON si.sale_id = s.id
    AND s.sale_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
    AND s.status = 'completed'
WHERE c.name = %s
GROUP BY p.id, p.name, p.unit_price, c.name, i.quantity_available
ORDER BY days_of_stock DESC;
"""

_SQL_ROTATION_ANALYSIS_BY_PRODUCT_AND_CATEGORY = """
SELECT p.id, p.name, p.unit_price, c.name AS category,
       i.quantity_available,
       COALESCE(SUM(si.quantity), 0) AS units_sold,
       COALESCE(SUM(si.subtotal), 0.0) AS revenue,
       CASE WHEN COALESCE(SUM(si.quantity), 0) > 0
            THEN (i.quantity_available / (SUM(si.quantity) / %s::float))
            ELSE 999
       END AS days_of_stock
FROM inventory i
JOIN products p ON i.product_id = p.id
JOIN categories c ON p.category_id = c.id
LEFT JOIN sale_items si ON si.product_id = p.id
LEFT JOIN sales s ON si.sale_id = s.id
    AND s.sale_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
    AND s.status = 'completed'
WHERE p.id = %s AND c.name = %s
GROUP BY p.id, p.name, p.unit_price, c.name, i.quantity_available
ORDER BY days_of_stock DESC;
"""


def get_inventory_rotation_analysis(
    conn: Any,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
    analysis_period_days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Return inventory rotation analysis compared to recent sales.

    For each product, computes the number of units sold and an estimate of
    how many days of stock remain based on the sales velocity observed during
    the analysis period.  Products with no sales in the period receive a
    ``days_of_stock`` value of 999 (sentinel for "no rotation").

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    product_id:
        Optional product ID to restrict results to a single product.
    category:
        Optional category name to restrict results to products in that
        category.
    analysis_period_days:
        Number of past days to consider for the sales velocity calculation
        (default 30).

    Returns
    -------
    list of dict
        Each element: ``{"id": int, "name": str, "unit_price": float,
        "category": str, "quantity_available": int, "units_sold": int,
        "revenue": float, "days_of_stock": float}``
        Sorted descending by ``days_of_stock`` (highest rotation risk first).
    """
    period = float(analysis_period_days)

    with conn.cursor() as cur:
        if product_id is not None and category is not None:
            cur.execute(
                _SQL_ROTATION_ANALYSIS_BY_PRODUCT_AND_CATEGORY,
                (period, analysis_period_days, product_id, category),
            )
        elif product_id is not None:
            cur.execute(
                _SQL_ROTATION_ANALYSIS_BY_PRODUCT,
                (period, analysis_period_days, product_id),
            )
        elif category is not None:
            cur.execute(
                _SQL_ROTATION_ANALYSIS_BY_CATEGORY,
                (period, analysis_period_days, category),
            )
        else:
            cur.execute(
                _SQL_ROTATION_ANALYSIS,
                (period, analysis_period_days),
            )
        rows = cur.fetchall()

    return [
        {
            "id": int(row[0]),
            "name": row[1],
            "unit_price": float(row[2]),
            "category": row[3],
            "quantity_available": int(row[4]),
            "units_sold": int(row[5]),
            "revenue": float(row[6]),
            "days_of_stock": float(row[7]),
        }
        for row in rows
    ]
