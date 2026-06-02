"""
Standard HTTP-style response helpers for Lambda functions.

All Lambda tools in BizQuery return a consistent JSON envelope so that the
Strand Agent and callers can handle success and error cases uniformly.

Response envelope schema
------------------------
Success::

    {
        "success": true,
        "data": <any>,
        "error": null
    }

Error::

    {
        "success": false,
        "data": null,
        "error": {
            "code": "<ERROR_CODE>",
            "message": "<human-readable description>"
        }
    }

Bedrock Agent responses use a different envelope — use ``bedrock_response``
when the Lambda is invoked by a Bedrock Agent action group.
"""

import json
from typing import Any, Dict


def success_response(data: Any) -> Dict[str, Any]:
    """
    Build a successful response envelope.

    Parameters
    ----------
    data:
        The payload to return to the caller.  Can be any JSON-serialisable
        value (dict, list, str, number, ``None``).

    Returns
    -------
    dict
        ``{"success": True, "data": data, "error": None}``

    Examples
    --------
    >>> success_response({"total": 1500.0})
    {'success': True, 'data': {'total': 1500.0}, 'error': None}
    >>> success_response([])
    {'success': True, 'data': [], 'error': None}
    """
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def error_response(code: str, message: str) -> Dict[str, Any]:
    """
    Build an error response envelope.

    Parameters
    ----------
    code:
        A machine-readable error code (e.g. ``"ACCESS_DENIED"``,
        ``"DB_UNAVAILABLE"``, ``"INVALID_PARAMS"``).
    message:
        A human-readable description of the error, suitable for logging
        and for the Strand Agent to relay to the user.

    Returns
    -------
    dict
        ``{"success": False, "data": None, "error": {"code": code, "message": message}}``

    Examples
    --------
    >>> error_response("ACCESS_DENIED", "No tienes permisos para acceder a datos financieros.")
    {'success': False, 'data': None, 'error': {'code': 'ACCESS_DENIED', 'message': 'No tienes permisos para acceder a datos financieros.'}}
    >>> error_response("DB_UNAVAILABLE", "No se pudo conectar a la base de datos.")
    {'success': False, 'data': None, 'error': {'code': 'DB_UNAVAILABLE', 'message': 'No se pudo conectar a la base de datos.'}}
    """
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


# ---------------------------------------------------------------------------
# Bedrock Agent response helpers
# ---------------------------------------------------------------------------

def is_bedrock_event(event: dict) -> bool:
    """Return True if the Lambda was invoked by a Bedrock Agent action group."""
    return "actionGroup" in event or "agent" in event


def extract_bedrock_params(event: dict) -> dict:
    """
    Extract parameters from a Bedrock Agent event into a plain dict.

    Bedrock sends parameters as a list of {"name": ..., "value": ...} dicts
    under event["parameters"], or as a requestBody for API-schema actions.
    This normalises both into a single flat dict.
    """
    params: dict = {}

    # Function-type action group: parameters is a list of {name, value} dicts
    raw = event.get("parameters") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "name" in item:
                params[item["name"]] = item.get("value")

    # API-schema action group: parameters may be in requestBody
    request_body = event.get("requestBody", {})
    if isinstance(request_body, dict):
        content = request_body.get("content", {})
        if isinstance(content, dict):
            body_str = (
                content.get("application/json", {})
                .get("properties") or []
            )
            if isinstance(body_str, list):
                for item in body_str:
                    if isinstance(item, dict) and "name" in item:
                        params[item["name"]] = item.get("value")

    # Coerce numeric strings to int/float where possible,
    # but skip fields that are always expected to be strings.
    _STRING_FIELDS = {"period", "compare_period", "category", "sku", "analysis_period"}
    coerced: dict = {}
    for k, v in params.items():
        if k in _STRING_FIELDS:
            # Keep as string — these fields must not be coerced to numbers
            coerced[k] = str(v) if v is not None else v
            continue
        if isinstance(v, str):
            try:
                coerced[k] = int(v)
                continue
            except ValueError:
                pass
            try:
                coerced[k] = float(v)
                continue
            except ValueError:
                pass
            # Coerce boolean strings
            if v.lower() == "true":
                coerced[k] = True
                continue
            if v.lower() == "false":
                coerced[k] = False
                continue
            if v.lower() in ("null", "none", ""):
                coerced[k] = None
                continue
        coerced[k] = v

    return coerced


def bedrock_response(event: dict, biz_response: dict) -> dict:
    """
    Wrap a BizQuery response dict into the Bedrock Agent response envelope.

    Bedrock Agents require this exact shape::

        {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": "<actionGroup>",
                "function": "<function>",
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {"body": "<string>"}
                    }
                }
            }
        }

    Parameters
    ----------
    event:
        The original Lambda event from Bedrock (used to echo back
        ``actionGroup`` and ``function``).
    biz_response:
        The standard BizQuery response dict produced by ``success_response``
        or ``error_response``.

    Returns
    -------
    dict
        Bedrock-compatible response envelope.
    """
    body_text = json.dumps(biz_response, ensure_ascii=False, default=str)
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "function": event.get("function", ""),
            "functionResponse": {
                "responseBody": {
                    "TEXT": {"body": body_text}
                }
            },
        },
    }
