"""
Lambda handler for the query_sales tool.

Entry point: handler(event, context)

Expected event shape
--------------------
{
    "tool_name":  "query_sales",
    "parameters": {
        "period":            "2025-Q1",          # required
        "product_id":        42,                 # optional int
        "category":          "Refrigeradores",   # optional str
        "compare_period":    "2024-Q1",          # optional str
        "include_financial": false               # optional bool, default false
    },
    "user_id":   "cognito-sub-uuid",
    "user_role": "owner" | "employee"
}
"""

from __future__ import annotations

import logging
import os
import sys

# Allow importing from the sibling `shared` package when running inside Lambda
# (where the working directory is /var/task/lambda or similar).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.audit import log_invocation
from shared.db import get_db_connection
from shared.response import error_response, success_response

from models import QuerySalesInput, parse_period
from queries import get_sales_by_category, get_top_products, get_total_by_period

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _compute_variation(v1: float, v2: float) -> float:
    """
    Compute percentage variation between two period totals.

    variation = (V2 - V1) / V1 * 100

    Returns 0.0 when V1 is zero to avoid division by zero.
    """
    if v1 == 0:
        return 0.0
    return (v2 - v1) / v1 * 100


# Fields that contain financial data and must never be exposed to 'employee'
_FINANCIAL_FIELDS = frozenset({
    "total",
    "compare_total",
    "variation_pct",
    "total_amount",
    "final_amount",
})


def _strip_financial_fields(data: dict) -> dict:
    """Remove financial fields from a result dict for non-privileged roles."""
    return {k: v for k, v in data.items() if k not in _FINANCIAL_FIELDS}


def handler(event: dict, context: object) -> dict:
    """
    AWS Lambda handler for the query_sales tool.

    Parameters
    ----------
    event:
        Lambda invocation payload (see module docstring for shape).
    context:
        Lambda context object (unused).

    Returns
    -------
    dict
        Standard BizQuery response envelope produced by
        ``success_response`` or ``error_response``.
    """
    # ------------------------------------------------------------------
    # 1. Extract identity / role
    # ------------------------------------------------------------------
    user_id: str = event.get("user_id", "")
    user_role: str = event.get("user_role", "")

    logger.info(
        "query_sales invoked | user_id=%s user_role=%s",
        user_id,
        user_role,
    )

    # ------------------------------------------------------------------
    # 2. Parse and validate input
    # ------------------------------------------------------------------
    raw_params: dict = event.get("parameters", {})

    try:
        params = QuerySalesInput.from_dict(raw_params)
    except (ValueError, KeyError) as exc:
        logger.warning("Invalid parameters: %s", exc)
        result = error_response("INVALID_PARAMS", str(exc))
        log_invocation(user_id, user_role, "query_sales", raw_params, result)
        return result

    # ------------------------------------------------------------------
    # 3. Role-based access control for financial data
    #
    # Rules (Requisitos 8.3, 8.5):
    #   - Only 'owner' may request include_financial=True.
    #   - 'employee' role never receives financial fields in the response
    #     (total_amount, final_amount, compare_total, variation_pct).
    #     Requesting include_financial=True as employee is an explicit denial.
    # ------------------------------------------------------------------
    if params.include_financial and user_role == "employee":
        logger.warning(
            "ACCESS_DENIED: user_role=%s attempted include_financial=True",
            user_role,
        )
        result = error_response(
            "ACCESS_DENIED",
            "No tienes permisos para acceder a datos financieros.",
        )
        log_invocation(user_id, user_role, "query_sales", raw_params, result)
        return result

    if params.include_financial and user_role not in ("owner", "manager"):
        logger.warning(
            "ACCESS_DENIED: user_role=%s attempted include_financial=True",
            user_role,
        )
        result = error_response(
            "ACCESS_DENIED",
            "No tienes permisos para acceder a datos financieros.",
        )
        log_invocation(user_id, user_role, "query_sales", raw_params, result)
        return result

    # ------------------------------------------------------------------
    # 4. Execute queries
    # ------------------------------------------------------------------
    try:
        with get_db_connection() as conn:
            start_date, end_date = parse_period(params.period)

            # Always run all three queries; category/product_id act as filters
            total_data = get_total_by_period(conn, start_date, end_date)
            category_data = get_sales_by_category(
                conn, start_date, end_date, category=params.category
            )
            top_products = get_top_products(
                conn, start_date, end_date, product_id=params.product_id
            )

            result: dict = {
                "period": params.period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total": total_data["total"],
                "num_transactions": total_data["num_transactions"],
                "by_category": category_data,
                "top_products": top_products,
            }

            # ----------------------------------------------------------
            # 5. Compare period (optional)
            # ----------------------------------------------------------
            if params.compare_period:
                cmp_start, cmp_end = parse_period(params.compare_period)
                cmp_total_data = get_total_by_period(conn, cmp_start, cmp_end)
                cmp_category_data = get_sales_by_category(
                    conn, cmp_start, cmp_end, category=params.category
                )
                cmp_top_products = get_top_products(
                    conn, cmp_start, cmp_end, product_id=params.product_id
                )

                v1 = cmp_total_data["total"]
                v2 = total_data["total"]
                variation_pct = _compute_variation(v1, v2)

                result["compare_period"] = params.compare_period
                result["compare_start_date"] = cmp_start.isoformat()
                result["compare_end_date"] = cmp_end.isoformat()
                result["compare_total"] = v1
                result["compare_num_transactions"] = cmp_total_data["num_transactions"]
                result["compare_by_category"] = cmp_category_data
                result["compare_top_products"] = cmp_top_products
                result["variation_pct"] = round(variation_pct, 4)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("DB error in query_sales: %s", exc, exc_info=True)
        result = error_response(
            "DB_UNAVAILABLE",
            "No se pudo conectar a la base de datos o ejecutar la consulta.",
        )
        log_invocation(user_id, user_role, "query_sales", raw_params, result)
        return result

    logger.info(
        "query_sales success | user_id=%s period=%s",
        user_id,
        params.period,
    )
    # Strip financial fields for employee role (Requisitos 8.3, 8.5)
    if user_role == "employee":
        result = _strip_financial_fields(result)

    final_response = success_response(result)
    log_invocation(user_id, user_role, "query_sales", raw_params, final_response)
    return final_response
