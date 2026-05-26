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
"""

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
