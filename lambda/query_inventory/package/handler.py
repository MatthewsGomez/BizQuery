"""
Lambda handler for the query_inventory tool.

Entry point: handler(event, context)

Expected event shape
--------------------
{
    "tool_name":  "query_inventory",
    "parameters": {
        "product_id":          42,          # optional int
        "sku":                 "REF-SAM-400L",  # optional str
        "category":            "Refrigeradores",  # optional str
        "low_stock_threshold": 10           # optional int
    },
    "user_id":   "cognito-sub-uuid",
    "user_role": "owner" | "employee"
}

Routing logic
-------------
* If ``product_id`` or ``sku`` is provided → call ``get_product_stock``.
  Returns a not-found message when the product does not exist.
* Otherwise → call both ``get_low_stock_products`` and
  ``get_inventory_by_category`` and return the combined result.
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
from shared.response import (
    bedrock_response,
    error_response,
    extract_bedrock_params,
    is_bedrock_event,
    success_response,
)

from models import QueryInventoryInput
from queries import get_inventory_by_category, get_low_stock_products, get_product_stock

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """
    AWS Lambda handler for the query_inventory tool.

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
    # 1. Detect invocation source and extract identity / role
    # ------------------------------------------------------------------
    from_bedrock = is_bedrock_event(event)

    if from_bedrock:
        session_attrs = (
            event.get("sessionAttributes") or
            event.get("agent", {}).get("sessionAttributes") or
            {}
        )
        user_id = session_attrs.get("user_id", "")
        user_role = session_attrs.get("user_role", "employee")
    else:
        user_id = event.get("user_id", "")
        user_role = event.get("user_role", "")

    logger.info(
        "query_inventory invoked | source=%s user_id=%s user_role=%s",
        "bedrock" if from_bedrock else "direct",
        user_id,
        user_role,
    )

    # ------------------------------------------------------------------
    # 2. Parse and validate input
    # ------------------------------------------------------------------
    if from_bedrock:
        raw_params = extract_bedrock_params(event)
    else:
        raw_params = event.get("parameters", {})

    # Guard: Strands/Claude sometimes serialises parameters as a list with a
    # single dict element instead of a plain dict.  Normalise it here so
    # from_dict always receives a dict.
    if isinstance(raw_params, list):
        raw_params = raw_params[0] if raw_params else {}
    if not isinstance(raw_params, dict):
        raw_params = {}

    try:
        params = QueryInventoryInput.from_dict(raw_params)
    except (ValueError, KeyError) as exc:
        logger.warning("Invalid parameters: %s", exc)
        result = error_response("INVALID_PARAMS", str(exc))
        log_invocation(user_id, user_role, "query_inventory", raw_params, result)
        return bedrock_response(event, result) if from_bedrock else result

    # ------------------------------------------------------------------
    # 3. Execute queries
    # ------------------------------------------------------------------
    try:
        with get_db_connection() as conn:

            # ----------------------------------------------------------
            # 3a. Specific product lookup (by product_id or sku)
            # ----------------------------------------------------------
            if params.product_id is not None or params.sku is not None:
                product = get_product_stock(
                    conn,
                    product_id=params.product_id,
                    sku=params.sku,
                )

                if product is None:
                    identifier = (
                        f"product_id={params.product_id}"
                        if params.product_id is not None
                        else f"sku='{params.sku}'"
                    )
                    logger.info(
                        "query_inventory: product not found | %s", identifier
                    )
                    not_found = success_response(
                        {
                            "found": False,
                            "message": (
                                f"No se encontró ningún producto con {identifier} "
                                "en el inventario."
                            ),
                        }
                    )
                    log_invocation(user_id, user_role, "query_inventory", raw_params, not_found)
                    return bedrock_response(event, not_found) if from_bedrock else not_found

                result = {"found": True, "product": product}

            # ----------------------------------------------------------
            # 3b. General inventory overview (low-stock + by-category)
            # ----------------------------------------------------------
            else:
                low_stock = get_low_stock_products(
                    conn,
                    threshold=params.low_stock_threshold,
                )
                by_category = get_inventory_by_category(
                    conn,
                    category=params.category,
                )

                result = {
                    "low_stock_products": low_stock,
                    "inventory_by_category": by_category,
                }

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("DB error in query_inventory: %s", exc, exc_info=True)
        result = error_response(
            "DB_UNAVAILABLE",
            "No se pudo conectar a la base de datos o ejecutar la consulta.",
        )
        log_invocation(user_id, user_role, "query_inventory", raw_params, result)
        return bedrock_response(event, result) if from_bedrock else result

    logger.info(
        "query_inventory success | user_id=%s product_id=%s sku=%s",
        user_id,
        params.product_id,
        params.sku,
    )
    final_response = success_response(result)
    log_invocation(user_id, user_role, "query_inventory", raw_params, final_response)
    return bedrock_response(event, final_response) if from_bedrock else final_response
