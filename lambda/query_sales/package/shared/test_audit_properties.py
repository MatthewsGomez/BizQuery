"""
Property-Based Tests — Auditoría de invocaciones (Propiedad 19)

Propiedad 19: Auditoría completa de invocaciones
Valida: Requisito 8.4

Para toda invocación de `log_invocation` (exitosa o fallida), se debe generar
exactamente un registro de log con los campos requeridos:
  - audit: True
  - user_id, user_role, tool_name, timestamp, success, status_code
  - Sin datos financieros sensibles en los parámetros

Usa `hypothesis` para generar combinaciones aleatorias de inputs.
"""

import json
import logging
import sys
import os
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.audit import log_invocation, _sanitize_parameters, _SENSITIVE_PARAM_KEYS

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_ids = st.text(min_size=1, max_size=64, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"))
user_roles = st.sampled_from(["owner", "manager", "employee", "admin"])
tool_names = st.sampled_from(["query_sales", "query_inventory", "analyze_discounts"])
status_codes = st.sampled_from([200, 400, 401, 403, 500])

safe_param_keys = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_")
safe_param_values = st.one_of(st.text(max_size=50), st.integers(), st.none())

parameters_strategy = st.dictionaries(safe_param_keys, safe_param_values, max_size=8)

sensitive_parameters_strategy = st.fixed_dictionaries({
    "total_amount": st.floats(min_value=0, max_value=1e6),
    "final_amount": st.floats(min_value=0, max_value=1e6),
    "period": st.just("2025-Q1"),
})


def make_result(status_code: int) -> dict:
    if status_code < 400:
        return {"statusCode": status_code, "body": json.dumps({"success": True, "data": {}})}
    return {"statusCode": status_code, "body": json.dumps({"error": {"code": "ERR", "message": "error"}})}


# ---------------------------------------------------------------------------
# Propiedad 19a: log_invocation emite exactamente un registro por llamada
# ---------------------------------------------------------------------------

@given(
    user_id=user_ids,
    user_role=user_roles,
    tool_name=tool_names,
    parameters=parameters_strategy,
    status_code=status_codes,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_log_invocation_emits_exactly_one_record(user_id, user_role, tool_name, parameters, status_code):
    """
    Propiedad 19: Toda invocación genera exactamente un registro de log.
    """
    result = make_result(status_code)
    log_records = []

    handler = logging.handlers_list = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    capturing = CapturingHandler()

    import shared.audit as audit_module
    original_handlers = audit_module.logger.handlers[:]
    audit_module.logger.handlers = [capturing]
    audit_module.logger.propagate = False

    try:
        log_invocation(user_id, user_role, tool_name, parameters, result)
    finally:
        audit_module.logger.handlers = original_handlers
        audit_module.logger.propagate = True

    # Propiedad: exactamente un registro emitido
    assert len(log_records) == 1


# ---------------------------------------------------------------------------
# Propiedad 19b: el registro contiene todos los campos requeridos
# ---------------------------------------------------------------------------

@given(
    user_id=user_ids,
    user_role=user_roles,
    tool_name=tool_names,
    parameters=parameters_strategy,
    status_code=status_codes,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_log_record_contains_required_fields(user_id, user_role, tool_name, parameters, status_code):
    """
    Propiedad 19: El registro contiene user_id, tool_name, timestamp, success/error.
    """
    result = make_result(status_code)
    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    capturing = CapturingHandler()

    import shared.audit as audit_module
    original_handlers = audit_module.logger.handlers[:]
    audit_module.logger.handlers = [capturing]
    audit_module.logger.propagate = False

    try:
        log_invocation(user_id, user_role, tool_name, parameters, result)
    finally:
        audit_module.logger.handlers = original_handlers
        audit_module.logger.propagate = True

    record = json.loads(log_records[0].getMessage())

    # Campos requeridos
    assert record["audit"] is True
    assert record["user_id"] == user_id
    assert record["user_role"] == user_role
    assert record["tool_name"] == tool_name
    assert "timestamp" in record
    assert "success" in record
    assert "status_code" in record
    assert record["status_code"] == status_code
    assert record["success"] == (status_code < 400)


# ---------------------------------------------------------------------------
# Propiedad 19c: datos financieros sensibles nunca aparecen en el log
# ---------------------------------------------------------------------------

@given(
    user_id=user_ids,
    user_role=user_roles,
    tool_name=tool_names,
    parameters=sensitive_parameters_strategy,
    status_code=st.just(200),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_sensitive_fields_are_redacted_in_log(user_id, user_role, tool_name, parameters, status_code):
    """
    Propiedad 19: Los campos financieros sensibles se redactan antes de loguear.
    """
    result = make_result(status_code)
    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    capturing = CapturingHandler()

    import shared.audit as audit_module
    original_handlers = audit_module.logger.handlers[:]
    audit_module.logger.handlers = [capturing]
    audit_module.logger.propagate = False

    try:
        log_invocation(user_id, user_role, tool_name, parameters, result)
    finally:
        audit_module.logger.handlers = original_handlers
        audit_module.logger.propagate = True

    record = json.loads(log_records[0].getMessage())
    logged_params = record["parameters"]

    for sensitive_key in _SENSITIVE_PARAM_KEYS:
        if sensitive_key in parameters:
            assert logged_params[sensitive_key] == "[REDACTED]", (
                f"Campo sensible '{sensitive_key}' no fue redactado"
            )


# ---------------------------------------------------------------------------
# Propiedad 19d: _sanitize_parameters es idempotente
# ---------------------------------------------------------------------------

@given(parameters=parameters_strategy)
@settings(max_examples=100)
def test_sanitize_parameters_idempotent(parameters):
    """
    Sanitizar dos veces produce el mismo resultado que sanitizar una vez.
    """
    once = _sanitize_parameters(parameters)
    twice = _sanitize_parameters(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Propiedad 19e: invocaciones fallidas también generan exactamente un registro
# ---------------------------------------------------------------------------

@given(
    user_id=user_ids,
    user_role=user_roles,
    tool_name=tool_names,
    parameters=parameters_strategy,
    status_code=st.sampled_from([400, 401, 403, 500]),
)
@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
def test_failed_invocations_also_produce_one_audit_record(user_id, user_role, tool_name, parameters, status_code):
    """
    Propiedad 19: Las invocaciones fallidas también generan exactamente un registro.
    """
    result = make_result(status_code)
    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    capturing = CapturingHandler()

    import shared.audit as audit_module
    original_handlers = audit_module.logger.handlers[:]
    audit_module.logger.handlers = [capturing]
    audit_module.logger.propagate = False

    try:
        log_invocation(user_id, user_role, tool_name, parameters, result)
    finally:
        audit_module.logger.handlers = original_handlers
        audit_module.logger.propagate = True

    assert len(log_records) == 1
    record = json.loads(log_records[0].getMessage())
    assert record["success"] is False
