"""
Lambda handler for the analyze_discounts tool.

Entry point: handler(event, context)

Expected event shape
--------------------
{
    "tool_name":  "analyze_discounts",
    "parameters": {
        "product_id":        null,              # optional int
        "category":          "refrigeradores",  # optional str
        "analysis_period":   "30d"              # optional str, default "30d"
    },
    "user_id":   "cognito-sub-uuid",
    "user_role": "owner" | "employee"
}

Access control
--------------
* Only users with role ``"owner"`` may access discount recommendations.
* Users with role ``"employee"`` receive an ``ACCESS_DENIED`` error
  (Req 5.7 / 8.6).
"""

from __future__ import annotations

import logging
import os
import sys

# Allow importing from the sibling `shared` package when running inside Lambda
# (where the working directory is /var/task/lambda or similar).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.audit import log_invocation                       # noqa: E402
from shared.db import get_db_connection                       # noqa: E402
from shared.response import error_response, success_response  # noqa: E402

from models import AnalyzeDiscountsInput, parse_analysis_period
from queries import get_active_discounts, get_inventory_rotation_analysis
from analyzer import generate_recommendations, generate_summary

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """
    AWS Lambda handler for the analyze_discounts tool.

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

        On success::

            {
                "success": true,
                "data": {
                    "recommendations": [...],
                    "summary": "..."
                },
                "error": null
            }
    """
    # ------------------------------------------------------------------
    # 1. Extract identity / role
    # ------------------------------------------------------------------
    user_id: str = event.get("user_id", "")
    user_role: str = event.get("user_role", "")

    logger.info(
        "analyze_discounts invoked | user_id=%s user_role=%s",
        user_id,
        user_role,
    )

    # ------------------------------------------------------------------
    # 2. Role-based access control (Req 5.7 / 8.6)
    #    Only owners may access discount recommendations.
    # ------------------------------------------------------------------
    if user_role != "owner":
        logger.warning(
            "ACCESS_DENIED: user_role=%s attempted analyze_discounts",
            user_role,
        )
        result = error_response(
            "ACCESS_DENIED",
            "Las recomendaciones de descuentos están reservadas para el rol Dueño. "
            "No tienes permisos para acceder a esta funcionalidad.",
        )
        log_invocation(user_id, user_role, "analyze_discounts", event.get("parameters", {}), result)
        return result

    # ------------------------------------------------------------------
    # 3. Parse and validate input
    # ------------------------------------------------------------------
    raw_params = event.get("parameters", {})

    # Guard: Strands/Claude sometimes serialises parameters as a list with a
    # single dict element instead of a plain dict.  Normalise it here so
    # from_dict always receives a dict.
    if isinstance(raw_params, list):
        raw_params = raw_params[0] if raw_params else {}
    if not isinstance(raw_params, dict):
        raw_params = {}

    try:
        params = AnalyzeDiscountsInput.from_dict(raw_params)
    except (ValueError, KeyError) as exc:
        logger.warning("Invalid parameters: %s", exc)
        result = error_response("VALIDATION_ERROR", str(exc))
        log_invocation(user_id, user_role, "analyze_discounts", raw_params, result)
        return result

    # Resolve the numeric period (days) from the validated model
    analysis_period_days: int = parse_analysis_period(
        params.analysis_period or "30d"
    )

    # ------------------------------------------------------------------
    # 4. Execute queries and generate recommendations
    # ------------------------------------------------------------------
    try:
        with get_db_connection() as conn:
            # 4a. Fetch currently active discounts (context for the analyzer)
            active_discounts = get_active_discounts(
                conn,
                product_id=params.product_id,
                category=params.category,
            )

            # 4b. Fetch inventory rotation analysis vs. recent sales
            rotation_data = get_inventory_rotation_analysis(
                conn,
                product_id=params.product_id,
                category=params.category,
                analysis_period_days=analysis_period_days,
            )

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("DB error in analyze_discounts: %s", exc, exc_info=True)
        result = error_response(
            "DB_UNAVAILABLE",
            "No se pudo conectar a la base de datos o ejecutar la consulta.",
        )
        log_invocation(user_id, user_role, "analyze_discounts", raw_params, result)
        return result

    # ------------------------------------------------------------------
    # 5. Generate recommendations and summary (pure Python, no DB)
    # ------------------------------------------------------------------
    recommendations = generate_recommendations(rotation_data, active_discounts)
    summary = generate_summary(recommendations)

    result = {
        "recommendations": recommendations,
        "summary": summary,
    }

    logger.info(
        "analyze_discounts success | user_id=%s product_id=%s category=%s "
        "period_days=%s num_recommendations=%s",
        user_id,
        params.product_id,
        params.category,
        analysis_period_days,
        len(recommendations),
    )

    final_response = success_response(result)
    log_invocation(user_id, user_role, "analyze_discounts", raw_params, final_response)
    return final_response
