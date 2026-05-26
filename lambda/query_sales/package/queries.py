"""
Parameterized SQL queries for the query_sales Lambda function.

All queries use ``%s`` placeholders (psycopg2 style) — never string
interpolation — to prevent SQL injection.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Query 1: Total sales for a period
# ---------------------------------------------------------------------------

_SQL_TOTAL_BY_PERIOD = """
SELECT
    COALESCE(SUM(final_amount), 0.0)  AS total,
    COUNT(*)                           AS num_transactions
FROM sales
WHERE sale_date BETWEEN %s AND %s
  AND status = 'completed';
"""


def get_total_by_period(
    conn: Any,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Return the total revenue and transaction count for a date range.

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    start_date:
        Inclusive start of the period.
    end_date:
        Inclusive end of the period.

    Returns
    -------
    dict
        ``{"total": float, "num_transactions": int}``
    """
    with conn.cursor() as cur:
        cur.execute(_SQL_TOTAL_BY_PERIOD, (start_date, end_date))
        row = cur.fetchone()

    total = float(row[0]) if row and row[0] is not None else 0.0
    num_transactions = int(row[1]) if row and row[1] is not None else 0
    return {"total": total, "num_transactions": num_transactions}


# ---------------------------------------------------------------------------
# Query 2: Sales broken down by category
# ---------------------------------------------------------------------------

_SQL_SALES_BY_CATEGORY = """
SELECT
    c.name                  AS category,
    COALESCE(SUM(si.subtotal), 0.0) AS total,
    COALESCE(SUM(si.quantity), 0)   AS units
FROM sale_items si
JOIN products  p  ON si.product_id = p.id
JOIN categories c ON p.category_id = c.id
JOIN sales      s  ON si.sale_id   = s.id
WHERE s.sale_date BETWEEN %s AND %s
  AND s.status = 'completed'
  {category_filter}
GROUP BY c.name
ORDER BY total DESC;
"""

_SQL_SALES_BY_CATEGORY_FILTERED = """
SELECT
    c.name                  AS category,
    COALESCE(SUM(si.subtotal), 0.0) AS total,
    COALESCE(SUM(si.quantity), 0)   AS units
FROM sale_items si
JOIN products  p  ON si.product_id = p.id
JOIN categories c ON p.category_id = c.id
JOIN sales      s  ON si.sale_id   = s.id
WHERE s.sale_date BETWEEN %s AND %s
  AND s.status = 'completed'
  AND c.name = %s
GROUP BY c.name
ORDER BY total DESC;
"""


def get_sales_by_category(
    conn: Any,
    start_date: date,
    end_date: date,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return sales aggregated by product category for a date range.

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    start_date:
        Inclusive start of the period.
    end_date:
        Inclusive end of the period.
    category:
        Optional category name to restrict results to a single category.

    Returns
    -------
    list of dict
        Each element: ``{"category": str, "total": float, "units": int}``
    """
    with conn.cursor() as cur:
        if category:
            cur.execute(
                _SQL_SALES_BY_CATEGORY_FILTERED,
                (start_date, end_date, category),
            )
        else:
            cur.execute(
                _SQL_SALES_BY_CATEGORY.format(category_filter=""),
                (start_date, end_date),
            )
        rows = cur.fetchall()

    return [
        {
            "category": row[0],
            "total": float(row[1]),
            "units": int(row[2]),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Query 3: Top products by units sold
# ---------------------------------------------------------------------------

_SQL_TOP_PRODUCTS = """
SELECT
    p.name                          AS name,
    COALESCE(SUM(si.quantity), 0)   AS units_sold,
    COALESCE(SUM(si.subtotal), 0.0) AS revenue
FROM sale_items si
JOIN products p ON si.product_id = p.id
JOIN sales    s ON si.sale_id    = s.id
WHERE s.sale_date BETWEEN %s AND %s
  AND s.status = 'completed'
  {product_filter}
GROUP BY p.id, p.name
ORDER BY units_sold DESC
LIMIT %s;
"""

_SQL_TOP_PRODUCTS_FILTERED = """
SELECT
    p.name                          AS name,
    COALESCE(SUM(si.quantity), 0)   AS units_sold,
    COALESCE(SUM(si.subtotal), 0.0) AS revenue
FROM sale_items si
JOIN products p ON si.product_id = p.id
JOIN sales    s ON si.sale_id    = s.id
WHERE s.sale_date BETWEEN %s AND %s
  AND s.status = 'completed'
  AND p.id = %s
GROUP BY p.id, p.name
ORDER BY units_sold DESC
LIMIT %s;
"""


def get_top_products(
    conn: Any,
    start_date: date,
    end_date: date,
    limit: int = 10,
    product_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Return the top-selling products by units sold for a date range.

    Parameters
    ----------
    conn:
        An open psycopg2 connection.
    start_date:
        Inclusive start of the period.
    end_date:
        Inclusive end of the period.
    limit:
        Maximum number of products to return (default 10).
    product_id:
        Optional product ID to restrict results to a single product.

    Returns
    -------
    list of dict
        Each element: ``{"name": str, "units_sold": int, "revenue": float}``
        Sorted descending by ``units_sold``.
    """
    with conn.cursor() as cur:
        if product_id is not None:
            cur.execute(
                _SQL_TOP_PRODUCTS_FILTERED,
                (start_date, end_date, product_id, limit),
            )
        else:
            cur.execute(
                _SQL_TOP_PRODUCTS.format(product_filter=""),
                (start_date, end_date, limit),
            )
        rows = cur.fetchall()

    return [
        {
            "name": row[0],
            "units_sold": int(row[1]),
            "revenue": float(row[2]),
        }
        for row in rows
    ]
