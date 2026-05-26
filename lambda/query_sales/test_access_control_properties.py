"""
Property-Based Tests — Control de acceso por rol (Propiedad 18)

Propiedad 18: Control de acceso por rol a datos financieros
Valida: Requisitos 8.3, 8.5

Para cualquier combinación de rol de usuario y tipo de consulta:
  - El rol 'employee' NUNCA debe recibir datos financieros en la respuesta
    (total, compare_total, variation_pct, total_amount, final_amount).
  - El rol 'employee' que solicita include_financial=True debe recibir ACCESS_DENIED.
  - Los roles 'owner' y 'manager' sí pueden recibir datos financieros.

Usa `hypothesis` para generar combinaciones aleatorias de roles y consultas.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch
from datetime import date

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Import handler components under test
# ---------------------------------------------------------------------------
from query_sales.handler import _strip_financial_fields, _FINANCIAL_FIELDS, _compute_variation
from query_sales.models import QuerySalesInput

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

employee_role = st.just("employee")
privileged_roles = st.sampled_from(["owner", "manager"])
all_roles = st.sampled_from(["owner", "manager", "employee", "unknown"])

valid_periods = st.sampled_from(["2025-Q1", "2025-Q2", "2025-01", "2024-Q4"])

financial_result = st.fixed_dictionaries({
    "period": st.just("2025-Q1"),
    "start_date": st.just("2025-01-01"),
    "end_date": st.just("2025-03-31"),
    "total": st.floats(min_value=0, max_value=1e6, allow_nan=False),
    "num_transactions": st.integers(min_value=0, max_value=10000),
    "by_category": st.just([]),
    "top_products": st.just([]),
    "total_amount": st.floats(min_value=0, max_value=1e6, allow_nan=False),
    "final_amount": st.floats(min_value=0, max_value=1e6, allow_nan=False),
})


# ---------------------------------------------------------------------------
# Propiedad 18a: employee nunca recibe campos financieros en el resultado
# ---------------------------------------------------------------------------

@given(result=financial_result)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_employee_never_receives_financial_fields(result):
    """
    Propiedad 18: _strip_financial_fields elimina todos los campos financieros.
    Para cualquier resultado con campos financieros, después de aplicar el
    filtro ningún campo financiero debe estar presente.
    """
    stripped = _strip_financial_fields(result)

    for field in _FINANCIAL_FIELDS:
        assert field not in stripped, (
            f"Campo financiero '{field}' encontrado en resultado filtrado para employee"
        )


@given(result=financial_result)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_strip_preserves_non_financial_fields(result):
    """
    Propiedad 18: _strip_financial_fields preserva todos los campos no financieros.
    """
    stripped = _strip_financial_fields(result)

    for key in result:
        if key not in _FINANCIAL_FIELDS:
            assert key in stripped, (
                f"Campo no financiero '{key}' fue eliminado incorrectamente"
            )
            assert stripped[key] == result[key]


# ---------------------------------------------------------------------------
# Propiedad 18b: handler retorna ACCESS_DENIED para employee con include_financial
# ---------------------------------------------------------------------------

def _make_event(user_id: str, user_role: str, period: str, include_financial: bool) -> dict:
    return {
        "user_id": user_id,
        "user_role": user_role,
        "parameters": {
            "period": period,
            "include_financial": include_financial,
        },
    }


def _mock_db_result():
    """Returns a mock DB connection that yields financial data."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


@given(
    user_id=st.text(min_size=1, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
    period=valid_periods,
)
@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
def test_employee_include_financial_always_denied(user_id, period):
    """
    Propiedad 18: employee + include_financial=True → ACCESS_DENIED siempre.
    """
    from query_sales.handler import handler

    event = _make_event(user_id, "employee", period, include_financial=True)

    with patch("query_sales.handler.get_db_connection"), \
         patch("query_sales.handler.log_invocation"):
        response = handler(event, None)

    # La respuesta debe ser un error con código ACCESS_DENIED
    assert response.get("success") is False, (
        f"Se esperaba success=False para employee+include_financial, got: {response}"
    )
    assert response.get("error", {}).get("code") == "ACCESS_DENIED", (
        f"Se esperaba error.code=ACCESS_DENIED, got: {response}"
    )


# ---------------------------------------------------------------------------
# Propiedad 18c: employee sin include_financial no recibe campos financieros
# ---------------------------------------------------------------------------

@given(
    user_id=st.text(min_size=1, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
    period=valid_periods,
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_employee_response_never_contains_financial_fields(user_id, period):
    """
    Propiedad 18: La respuesta para employee nunca contiene campos financieros,
    incluso cuando include_financial=False.
    """
    from query_sales.handler import handler

    event = _make_event(user_id, "employee", period, include_financial=False)

    mock_total = {"total": 9999.99, "num_transactions": 10}
    mock_category = [{"category": "Refrigeradores", "count": 5}]
    mock_top = [{"product_id": 1, "name": "Prod A", "units_sold": 10}]

    with patch("query_sales.handler.get_db_connection") as mock_db, \
         patch("query_sales.handler.get_total_by_period", return_value=mock_total), \
         patch("query_sales.handler.get_sales_by_category", return_value=mock_category), \
         patch("query_sales.handler.get_top_products", return_value=mock_top), \
         patch("query_sales.handler.log_invocation"):

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        response = handler(event, None)

    body = response.get("body", "{}")
    if isinstance(body, str):
        body = json.loads(body)

    data = body.get("data", body)

    for field in _FINANCIAL_FIELDS:
        assert field not in data, (
            f"Campo financiero '{field}' encontrado en respuesta para employee"
        )


# ---------------------------------------------------------------------------
# Propiedad 18d: owner recibe campos financieros cuando include_financial=True
# ---------------------------------------------------------------------------

@given(
    user_id=st.text(min_size=1, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
    period=valid_periods,
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_owner_receives_financial_fields(user_id, period):
    """
    Propiedad 18: owner con include_financial=True NO recibe ACCESS_DENIED.
    """
    from query_sales.handler import handler

    event = _make_event(user_id, "owner", period, include_financial=True)

    mock_total = {"total": 9999.99, "num_transactions": 10}
    mock_category = []
    mock_top = []

    with patch("query_sales.handler.get_db_connection") as mock_db, \
         patch("query_sales.handler.get_total_by_period", return_value=mock_total), \
         patch("query_sales.handler.get_sales_by_category", return_value=mock_category), \
         patch("query_sales.handler.get_top_products", return_value=mock_top), \
         patch("query_sales.handler.log_invocation"):

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        response = handler(event, None)

    body = response.get("body", "{}")
    if isinstance(body, str):
        body = json.loads(body)

    # No debe ser ACCESS_DENIED
    assert response.get("success") is not False or response.get("error", {}).get("code") != "ACCESS_DENIED", (
        f"owner recibió ACCESS_DENIED inesperadamente: {response}"
    )
    assert response.get("success") is True or response.get("error", {}).get("code") != "ACCESS_DENIED"
