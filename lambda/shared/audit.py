"""
audit.py — Auditoría de invocaciones de Lambda tools

Escribe registros de auditoría en CloudWatch Logs usando el módulo `logging`
estándar de Python. Lambda captura automáticamente la salida de `logging` en
CloudWatch Logs.

Campos registrados: user_id, user_role, tool_name, timestamp, success/error.
Los datos financieros sensibles NO se incluyen en los parámetros auditados.

Requisito: 8.4
"""

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Campos de parámetros que contienen datos financieros sensibles y deben
# ser omitidos del registro de auditoría.
_SENSITIVE_PARAM_KEYS = frozenset({
    "total_amount",
    "final_amount",
    "unit_price",
    "discount_amount",
    "revenue",
    "profit",
    "cost",
})


def _sanitize_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Elimina campos financieros sensibles de los parámetros antes de loguear."""
    return {
        k: "[REDACTED]" if k in _SENSITIVE_PARAM_KEYS else v
        for k, v in parameters.items()
    }


def log_invocation(
    user_id: str,
    user_role: str,
    tool_name: str,
    parameters: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """
    Registra una invocación de herramienta Lambda en CloudWatch Logs.

    Args:
        user_id:    Identificador del usuario que realizó la invocación.
        user_role:  Rol del usuario (e.g. 'admin', 'manager', 'employee').
        tool_name:  Nombre de la herramienta invocada (e.g. 'query_sales').
        parameters: Parámetros de entrada de la invocación (se sanitizan).
        result:     Resultado retornado por la herramienta.
    """
    success = result.get("statusCode", 500) < 400

    record = {
        "audit": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_id": user_id,
        "user_role": user_role,
        "tool_name": tool_name,
        "parameters": _sanitize_parameters(parameters),
        "success": success,
        "status_code": result.get("statusCode"),
    }

    if not success:
        # Incluir el código de error pero no datos sensibles del body
        body = result.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                body = {}
        if isinstance(body, dict):
            record["error_code"] = body.get("error", {}).get("code") if isinstance(body.get("error"), dict) else body.get("code")
            record["error_message"] = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")

    logger.info(json.dumps(record))
