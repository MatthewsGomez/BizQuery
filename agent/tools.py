"""
BizQuery Strand Agent tools.

Defines three tools that the Strand Agent can invoke:
  - query_sales       → Lambda ``bizquery-query-sales``
  - query_inventory   → Lambda ``bizquery-query-inventory``
  - analyze_discounts → Lambda ``bizquery-analyze-discounts``

Each tool builds the standard BizQuery Lambda payload::

    {
        "tool_name":  "<name>",
        "parameters": { ... },
        "user_id":    "<cognito-sub>",
        "user_role":  "owner" | "employee"
    }

and returns the parsed JSON response from the Lambda.

Lambda function names are read from environment variables with sensible
defaults so the module works out-of-the-box in a local dev environment:

    LAMBDA_QUERY_SALES          (default: "bizquery-query-sales")
    LAMBDA_QUERY_INVENTORY      (default: "bizquery-query-inventory")
    LAMBDA_ANALYZE_DISCOUNTS    (default: "bizquery-analyze-discounts")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import boto3

# ---------------------------------------------------------------------------
# Optional strands import — fall back to a minimal stub so the module is
# importable in environments where the `strands` package is not installed
# (e.g. unit-test runners, CI pipelines).
# ---------------------------------------------------------------------------
try:
    from strands import tool  # type: ignore[import]
except ImportError:
    def tool(fn=None, **kwargs):  # type: ignore[misc]
        """Minimal @tool stub used when the strands package is unavailable."""
        if fn is not None:
            return fn
        return lambda f: f

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Lambda function name resolution
# ---------------------------------------------------------------------------
_LAMBDA_QUERY_SALES = os.environ.get(
    "LAMBDA_QUERY_SALES", "bizquery-query-sales"
)
_LAMBDA_QUERY_INVENTORY = os.environ.get(
    "LAMBDA_QUERY_INVENTORY", "bizquery-query-inventory"
)
_LAMBDA_ANALYZE_DISCOUNTS = os.environ.get(
    "LAMBDA_ANALYZE_DISCOUNTS", "bizquery-analyze-discounts"
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _invoke_lambda(function_name: str, payload: dict) -> dict:
    """
    Invoke an AWS Lambda function synchronously and return the parsed response.

    Parameters
    ----------
    function_name:
        The name or ARN of the Lambda function to invoke.
    payload:
        The JSON-serialisable payload to send as the Lambda event.

    Returns
    -------
    dict
        Parsed JSON body from the Lambda response.

    Raises
    ------
    RuntimeError
        If the Lambda invocation returns a ``FunctionError`` header, indicating
        an unhandled exception inside the function.
    """
    client = boto3.client("lambda")

    logger.info("Invoking Lambda %s", function_name)

    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    # Surface Lambda-level errors (unhandled exceptions, OOM, etc.)
    if response.get("FunctionError"):
        error_detail = response["Payload"].read().decode("utf-8")
        logger.error(
            "Lambda %s returned FunctionError: %s", function_name, error_detail
        )
        raise RuntimeError(
            f"Lambda {function_name} returned an error: {error_detail}"
        )

    raw_payload = response["Payload"].read()
    return json.loads(raw_payload)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@tool
def query_sales(
    period: str,
    user_id: str,
    user_role: str,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
    compare_period: Optional[str] = None,
    include_financial: bool = False,
) -> dict:
    """
    Consulta datos de ventas por período, producto o categoría.

    Invoca la Lambda ``query_sales`` con los parámetros proporcionados y
    retorna el resultado en formato estándar BizQuery.

    Parameters
    ----------
    period:
        Período de tiempo para la consulta (e.g. ``"2025-Q1"``, ``"2025-01"``).
    user_id:
        Identificador del usuario autenticado (Cognito ``sub``).
    user_role:
        Rol del usuario: ``"owner"`` o ``"employee"``.
    product_id:
        ID del producto para filtrar las ventas (opcional).
    category:
        Nombre de la categoría para filtrar las ventas (opcional).
    compare_period:
        Período de comparación para calcular variaciones (opcional).
    include_financial:
        Si es ``True``, incluye datos financieros detallados.
        Solo disponible para usuarios con rol ``"owner"``.

    Returns
    -------
    dict
        Respuesta estándar BizQuery con los datos de ventas solicitados::

            {
                "success": true,
                "data": {
                    "period": "...",
                    "total": ...,
                    "num_transactions": ...,
                    "by_category": [...],
                    "top_products": [...]
                },
                "error": null
            }
    """
    parameters: dict = {"period": period, "include_financial": include_financial}

    if product_id is not None:
        parameters["product_id"] = product_id
    if category is not None:
        parameters["category"] = category
    if compare_period is not None:
        parameters["compare_period"] = compare_period

    payload = {
        "tool_name": "query_sales",
        "parameters": parameters,
        "user_id": user_id,
        "user_role": user_role,
    }

    logger.info(
        "query_sales tool | user_id=%s user_role=%s period=%s",
        user_id,
        user_role,
        period,
    )

    return _invoke_lambda(_LAMBDA_QUERY_SALES, payload)


@tool
def query_inventory(
    user_id: str,
    user_role: str,
    product_id: Optional[int] = None,
    sku: Optional[str] = None,
    category: Optional[str] = None,
    low_stock_threshold: Optional[int] = None,
) -> dict:
    """
    Consulta disponibilidad y niveles de stock de productos.

    Invoca la Lambda ``query_inventory`` con los parámetros proporcionados y
    retorna el resultado en formato estándar BizQuery.

    Parameters
    ----------
    user_id:
        Identificador del usuario autenticado (Cognito ``sub``).
    user_role:
        Rol del usuario: ``"owner"`` o ``"employee"``.
    product_id:
        ID del producto para consultar su stock específico (opcional).
    sku:
        SKU del producto para consultar su stock específico (opcional).
    category:
        Nombre de la categoría para filtrar el inventario (opcional).
    low_stock_threshold:
        Umbral personalizado para considerar un producto con bajo stock
        (opcional; si se omite, se usa el umbral configurado por producto).

    Returns
    -------
    dict
        Respuesta estándar BizQuery con los datos de inventario::

            {
                "success": true,
                "data": {
                    "low_stock_products": [...],
                    "inventory_by_category": [...]
                },
                "error": null
            }

        O, si se especificó ``product_id`` o ``sku``::

            {
                "success": true,
                "data": {
                    "found": true,
                    "product": { "name": "...", "quantity_available": ..., ... }
                },
                "error": null
            }
    """
    parameters: dict = {}

    if product_id is not None:
        parameters["product_id"] = product_id
    if sku is not None:
        parameters["sku"] = sku
    if category is not None:
        parameters["category"] = category
    if low_stock_threshold is not None:
        parameters["low_stock_threshold"] = low_stock_threshold

    payload = {
        "tool_name": "query_inventory",
        "parameters": parameters,
        "user_id": user_id,
        "user_role": user_role,
    }

    logger.info(
        "query_inventory tool | user_id=%s user_role=%s product_id=%s sku=%s",
        user_id,
        user_role,
        product_id,
        sku,
    )

    return _invoke_lambda(_LAMBDA_QUERY_INVENTORY, payload)


@tool
def analyze_discounts(
    user_id: str,
    user_role: str,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
    analysis_period: Optional[str] = None,
) -> dict:
    """
    Analiza inventario y ventas para recomendar descuentos óptimos.

    Invoca la Lambda ``analyze_discounts`` con los parámetros proporcionados y
    retorna las recomendaciones de descuentos en formato estándar BizQuery.

    Solo disponible para usuarios con rol ``"owner"``.

    Parameters
    ----------
    user_id:
        Identificador del usuario autenticado (Cognito ``sub``).
    user_role:
        Rol del usuario: ``"owner"`` o ``"employee"``.
        Los usuarios con rol ``"employee"`` recibirán un error ``ACCESS_DENIED``.
    product_id:
        ID del producto para limitar el análisis (opcional).
    category:
        Nombre de la categoría para limitar el análisis (opcional).
    analysis_period:
        Período de análisis histórico (e.g. ``"30d"``, ``"90d"``).
        Por defecto ``"30d"`` si se omite.

    Returns
    -------
    dict
        Respuesta estándar BizQuery con las recomendaciones de descuentos::

            {
                "success": true,
                "data": {
                    "recommendations": [
                        {
                            "product_id": 42,
                            "product_name": "...",
                            "suggested_discount_pct": 15,
                            "rationale": "...",
                            "priority": "high"
                        }
                    ],
                    "summary": "..."
                },
                "error": null
            }
    """
    parameters: dict = {}

    if product_id is not None:
        parameters["product_id"] = product_id
    if category is not None:
        parameters["category"] = category
    if analysis_period is not None:
        parameters["analysis_period"] = analysis_period

    payload = {
        "tool_name": "analyze_discounts",
        "parameters": parameters,
        "user_id": user_id,
        "user_role": user_role,
    }

    logger.info(
        "analyze_discounts tool | user_id=%s user_role=%s product_id=%s category=%s",
        user_id,
        user_role,
        product_id,
        category,
    )

    return _invoke_lambda(_LAMBDA_ANALYZE_DISCOUNTS, payload)
