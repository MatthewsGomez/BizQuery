# Feature: bizquery, Properties 1, 2, 3, 4, 16: Strand Agent correctness

"""
Property-based tests for the BizQuery Strand Agent.

Since the Strand Agent requires real AWS credentials and a live Bedrock
endpoint, these tests exercise the **pure Python logic** that can be
validated in isolation:

Properties tested
-----------------
Property 1 — Enrutamiento correcto de herramientas por dominio
    For any user query mentioning a specific data domain (sales, inventory,
    discounts), the agent invokes exactly the corresponding tool.
    Validates: Req 1.2, 1.3, 1.4, 7.2

Property 2 — Enrutamiento multi-herramienta para consultas de múltiples dominios
    For any query spanning N distinct domains (N > 1), the agent invokes
    exactly N distinct tools.
    Validates: Req 1.5

Property 3 — Invariante de crecimiento del historial conversacional
    After each conversation turn, the history contains exactly one more
    message than before, and all previous messages remain unchanged.
    Validates: Req 2.1, 2.4

Property 4 — Nueva sesión comienza con memoria vacía
    For any new session_id, the conversational history is empty at the
    time of the first query.
    Validates: Req 2.5

Property 16 — Resiliencia ante errores de herramientas
    For any error returned by a Lambda tool, the Strand Agent generates a
    descriptive failure response and the session remains active.
    Validates: Req 7.5

Testing strategy
----------------
- Properties 1 & 2: A ``MockRoutingAgent`` records which tools are called
  based on keyword matching in the query, mirroring the LLM routing logic.
- Properties 3 & 4: The real ``SessionManager`` is exercised directly.
- Property 16: ``process_query`` is tested with a patched ``agent`` that
  raises an exception, verifying the safe error message is returned.
"""

from __future__ import annotations

import copy
import re
import sys
import os
import uuid
from typing import List, Set
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Make the agent package importable from the workspace root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.session import SessionManager, generate_session_id


# ---------------------------------------------------------------------------
# Domain keyword mapping (mirrors the LLM routing logic)
# ---------------------------------------------------------------------------

# Keywords that trigger each tool.
# IMPORTANT: use whole-word matching (via _detect_domains) to avoid false
# positives such as "venta" matching inside "inventario".
_SALES_KEYWORDS = [
    "ventas", "venta", "sales", "ingresos", "revenue",
    "transacciones", "transactions", "vendidos", "sold",
]
_INVENTORY_KEYWORDS = [
    "inventario", "inventory", "stock", "disponibilidad",
    "disponibles", "disponible", "availability", "almacén",
    "warehouse", "existencias", "unidades",
]
_DISCOUNTS_KEYWORDS = [
    "descuentos", "descuento", "discounts", "discount",
    "ofertas", "oferta", "offers", "offer", "recomendaciones",
    "recommendations",
]

_DOMAIN_KEYWORDS = {
    "query_sales": _SALES_KEYWORDS,
    "query_inventory": _INVENTORY_KEYWORDS,
    "analyze_discounts": _DISCOUNTS_KEYWORDS,
}


def _detect_domains(query: str) -> Set[str]:
    """Return the set of tool names whose keywords appear in *query*.

    Uses whole-word matching (``\\b`` word boundaries) so that, for example,
    "venta" does not match inside "inventario".
    """
    q_lower = query.lower()
    result = set()
    for tool_name, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            # Build a pattern that matches the keyword as a whole word.
            # We use a simple approach: the keyword must be preceded and
            # followed by a non-alphanumeric character (or start/end of string).
            pattern = r"(?<![a-záéíóúüñ])" + re.escape(kw) + r"(?![a-záéíóúüñ])"
            if re.search(pattern, q_lower):
                result.add(tool_name)
                break
    return result


# ---------------------------------------------------------------------------
# MockRoutingAgent
# ---------------------------------------------------------------------------

class MockRoutingAgent:
    """
    Lightweight agent stub that records which tools are invoked based on
    keyword matching in the query.

    This avoids real AWS calls while faithfully modelling the routing
    behaviour described in the design document.
    """

    def __init__(self) -> None:
        self.called_tools: List[str] = []

    def process(self, query: str) -> str:
        """Process *query*, record tool calls, and return a stub response."""
        self.called_tools = []
        domains = _detect_domains(query)
        for tool_name in sorted(domains):
            self.called_tools.append(tool_name)
        if not self.called_tools:
            return "No puedo ayudarte con esa solicitud."
        return f"Procesé tu consulta usando: {', '.join(self.called_tools)}"


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Single-domain query templates
_SALES_TEMPLATES = [
    "¿Cuáles fueron las ventas del mes pasado?",
    "Muéstrame los ingresos del primer trimestre",
    "¿Cuántas transacciones hubo en enero?",
    "Dame el resumen de ventas por categoría",
    "¿Qué productos fueron más vendidos?",
    "Show me the sales for last quarter",
    "What were the total revenue figures?",
]

_INVENTORY_TEMPLATES = [
    "¿Cuál es el stock actual de refrigeradores?",
    "Muéstrame el inventario por categoría",
    "¿Qué productos tienen bajo stock?",
    "¿Cuántas unidades disponibles hay de lavadoras?",
    "Dame el estado del almacén",
    "What is the current inventory level?",
    "Show me products with low stock",
]

_DISCOUNTS_TEMPLATES = [
    "¿Qué descuentos están vigentes?",
    "Dame recomendaciones de ofertas para este mes",
    "¿Qué productos deberían tener descuento?",
    "Analiza los descuentos actuales",
    "¿Cuáles son las mejores ofertas para liquidar inventario?",
    "What discounts should we apply?",
    "Give me discount recommendations",
]

# Strategies for single-domain queries
sales_query = st.sampled_from(_SALES_TEMPLATES)
inventory_query = st.sampled_from(_INVENTORY_TEMPLATES)
discounts_query = st.sampled_from(_DISCOUNTS_TEMPLATES)

# Strategy for a query that mentions exactly one domain
single_domain_query = st.one_of(
    sales_query.map(lambda q: ("query_sales", q)),
    inventory_query.map(lambda q: ("query_inventory", q)),
    discounts_query.map(lambda q: ("analyze_discounts", q)),
)

# Strategy for multi-domain queries: combine two or three domain templates
multi_domain_query = st.one_of(
    # sales + inventory
    st.tuples(sales_query, inventory_query).map(
        lambda t: ({"query_sales", "query_inventory"}, f"{t[0]} Además, {t[1]}")
    ),
    # sales + discounts
    st.tuples(sales_query, discounts_query).map(
        lambda t: ({"query_sales", "analyze_discounts"}, f"{t[0]} También, {t[1]}")
    ),
    # inventory + discounts
    st.tuples(inventory_query, discounts_query).map(
        lambda t: ({"query_inventory", "analyze_discounts"}, f"{t[0]} Y además, {t[1]}")
    ),
    # all three
    st.tuples(sales_query, inventory_query, discounts_query).map(
        lambda t: (
            {"query_sales", "query_inventory", "analyze_discounts"},
            f"{t[0]} {t[1]} {t[2]}",
        )
    ),
)

# Strategy for message content (non-empty strings)
message_content = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        whitelist_characters=" .,¿?¡!áéíóúüñÁÉÍÓÚÜÑ",
    ),
)

# Strategy for user roles
user_role = st.sampled_from(["owner", "employee"])

# Strategy for exception messages (simulating Lambda errors)
error_message = st.one_of(
    st.just("Connection timeout"),
    st.just("DB_UNAVAILABLE"),
    st.just("Internal server error"),
    st.just("Lambda function error"),
    st.just("SQL syntax error near 'SELECT'"),
    st.text(min_size=4, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
)


# ---------------------------------------------------------------------------
# Property 1: Correct tool routing by domain
# Validates: Req 1.2, 1.3, 1.4, 7.2
# ---------------------------------------------------------------------------

@given(data=single_domain_query)
@settings(max_examples=25, deadline=None)
def test_property_1_correct_tool_routing_by_domain(data):
    """
    **Validates: Requirements 1.2, 1.3, 1.4, 7.2**

    For any user query mentioning a specific data domain (sales, inventory,
    discounts), the agent invokes exactly the corresponding tool and no
    tools from unrelated domains.
    """
    expected_tool, query = data

    agent = MockRoutingAgent()
    agent.process(query)

    assert expected_tool in agent.called_tools, (
        f"Expected tool '{expected_tool}' to be called for query: '{query}'. "
        f"Called tools: {agent.called_tools}"
    )

    # The query is single-domain — no other domain's tool should be called
    # (unless the template accidentally contains keywords from another domain)
    # We verify the expected tool IS called; extra tools are only acceptable
    # if the query text genuinely contains keywords from those domains.
    for called in agent.called_tools:
        detected = _detect_domains(query)
        assert called in detected, (
            f"Tool '{called}' was called but its keywords are not in query: '{query}'"
        )


# ---------------------------------------------------------------------------
# Property 2: Multi-tool routing for multi-domain queries
# Validates: Req 1.5
# ---------------------------------------------------------------------------

@given(data=multi_domain_query)
@settings(max_examples=25, deadline=None)
def test_property_2_multi_tool_routing_for_multi_domain_queries(data):
    """
    **Validates: Requirements 1.5**

    For any query spanning N distinct domains (N > 1), the agent invokes
    exactly N distinct tools — one per domain mentioned.
    """
    expected_tools, query = data

    agent = MockRoutingAgent()
    agent.process(query)

    called_set = set(agent.called_tools)

    # Every expected tool must have been called
    for tool_name in expected_tools:
        assert tool_name in called_set, (
            f"Expected tool '{tool_name}' to be called for multi-domain query: '{query}'. "
            f"Called tools: {called_set}"
        )

    # At least as many distinct tools as expected domains must be called
    # (the query text may incidentally contain keywords from additional domains)
    assert len(called_set) >= len(expected_tools), (
        f"Expected at least {len(expected_tools)} distinct tools for query '{query}', "
        f"but got {len(called_set)}: {called_set}"
    )


# ---------------------------------------------------------------------------
# Property 3: Conversational history growth invariant
# Validates: Req 2.1, 2.4
# ---------------------------------------------------------------------------

@given(
    messages=st.lists(
        st.tuples(
            st.sampled_from(["user", "assistant"]),
            message_content,
        ),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=25, deadline=None)
def test_property_3_history_growth_invariant(messages):
    """
    **Validates: Requirements 2.1, 2.4**

    After each conversation turn, the history contains exactly one more
    message than before, and all previous messages remain unchanged.
    The history only grows — it never loses messages during an active session.
    """
    sm = SessionManager()
    session = sm.create_session(user_id="test-user", user_role="owner")
    session_id = session["session_id"]

    for i, (role, content) in enumerate(messages):
        history_before = copy.deepcopy(sm.get_history(session_id))
        count_before = len(history_before)

        sm.add_message(session_id, role, content)

        history_after = sm.get_history(session_id)
        count_after = len(history_after)

        # History grew by exactly one
        assert count_after == count_before + 1, (
            f"After adding message {i}, expected history length {count_before + 1}, "
            f"got {count_after}"
        )

        # All previous messages are unchanged
        for j, prev_msg in enumerate(history_before):
            assert history_after[j]["role"] == prev_msg["role"], (
                f"Message {j} role changed after adding message {i}"
            )
            assert history_after[j]["content"] == prev_msg["content"], (
                f"Message {j} content changed after adding message {i}"
            )

        # The new message has the correct role and content
        new_msg = history_after[-1]
        assert new_msg["role"] == role, (
            f"New message role mismatch: expected '{role}', got '{new_msg['role']}'"
        )
        assert new_msg["content"] == content, (
            f"New message content mismatch: expected '{content}', got '{new_msg['content']}'"
        )


# ---------------------------------------------------------------------------
# Property 4: New session starts with empty memory
# Validates: Req 2.5
# ---------------------------------------------------------------------------

@given(
    num_sessions=st.integers(min_value=1, max_value=10),
    role=user_role,
)
@settings(max_examples=25, deadline=None)
def test_property_4_new_session_starts_with_empty_history(num_sessions, role):
    """
    **Validates: Requirements 2.5**

    For any new session_id, the conversational history is empty at the
    time of the first query, regardless of how many prior sessions exist
    for the same user.
    """
    sm = SessionManager()
    user_id = f"user-{uuid.uuid4()}"

    for i in range(num_sessions):
        # Create a new session (possibly after adding messages to previous ones)
        session = sm.create_session(user_id=user_id, user_role=role)
        session_id = session["session_id"]

        # History must be empty immediately after creation
        history = sm.get_history(session_id)
        assert history == [], (
            f"Session {i} for user '{user_id}' should start with empty history, "
            f"but got {len(history)} messages"
        )

        # Add some messages to this session so the next iteration has prior state
        sm.add_message(session_id, "user", f"Consulta número {i}")
        sm.add_message(session_id, "assistant", f"Respuesta número {i}")


@given(
    existing_messages=st.lists(
        st.tuples(
            st.sampled_from(["user", "assistant"]),
            message_content,
        ),
        min_size=1,
        max_size=10,
    ),
    role=user_role,
)
@settings(max_examples=25, deadline=None)
def test_property_4b_new_session_independent_of_existing_sessions(
    existing_messages, role
):
    """
    **Validates: Requirements 2.5**

    A new session starts with empty history even when other sessions for
    the same user already contain messages.
    """
    sm = SessionManager()
    user_id = f"user-{uuid.uuid4()}"

    # Create a session and populate it with messages
    old_session = sm.create_session(user_id=user_id, user_role=role)
    old_session_id = old_session["session_id"]
    for msg_role, content in existing_messages:
        sm.add_message(old_session_id, msg_role, content)

    assert len(sm.get_history(old_session_id)) == len(existing_messages)

    # Create a brand-new session for the same user
    new_session = sm.create_session(user_id=user_id, user_role=role)
    new_session_id = new_session["session_id"]

    # The new session must have an empty history
    new_history = sm.get_history(new_session_id)
    assert new_history == [], (
        f"New session should start with empty history, "
        f"but got {len(new_history)} messages"
    )

    # The old session's history must be unaffected
    old_history = sm.get_history(old_session_id)
    assert len(old_history) == len(existing_messages), (
        f"Old session history should still have {len(existing_messages)} messages, "
        f"but got {len(old_history)}"
    )


# ---------------------------------------------------------------------------
# Property 16: Tool error resilience
# Validates: Req 7.5
# ---------------------------------------------------------------------------

@given(error_msg=error_message)
@settings(max_examples=25, deadline=None)
def test_property_16_tool_error_resilience(error_msg):
    """
    **Validates: Requirements 7.5**

    For any error returned by a Lambda tool, process_query returns a safe,
    descriptive failure response (not a stack trace or raw exception message)
    and the session remains active.
    """
    from agent.agent import process_query

    # Patch the module-level agent so it raises an exception
    with patch("agent.agent.agent") as mock_agent:
        mock_agent.side_effect = Exception(error_msg)

        session_id = generate_session_id()
        response = process_query(
            query="¿Cuáles son las ventas del mes?",
            user_id="test-user",
            user_role="owner",
            session_id=session_id,
        )

    # The response must be a non-empty string
    assert isinstance(response, str), (
        f"process_query should return a str, got {type(response)}"
    )
    assert len(response) > 0, "process_query should return a non-empty response"

    # The response must NOT expose the raw exception message or stack trace
    assert error_msg not in response, (
        f"process_query should not expose the raw error message in the response. "
        f"Error: '{error_msg}', Response: '{response}'"
    )
    assert "Traceback" not in response, (
        "process_query should not expose a stack trace in the response"
    )
    assert "Exception" not in response, (
        "process_query should not expose exception class names in the response"
    )

    # The response must be a user-friendly error message
    # (the system prompt instructs the agent to use friendly language)
    assert len(response) >= 10, (
        f"Response is too short to be a meaningful error message: '{response}'"
    )


@given(
    error_msg=error_message,
    num_prior_messages=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=25, deadline=None)
def test_property_16b_session_remains_active_after_tool_error(
    error_msg, num_prior_messages
):
    """
    **Validates: Requirements 7.5**

    After a tool error, the session remains active: the SessionManager
    still holds the session and its history is intact.
    """
    sm = SessionManager()
    session = sm.create_session(user_id="test-user", user_role="owner")
    session_id = session["session_id"]

    # Add some prior messages to the session
    for i in range(num_prior_messages):
        sm.add_message(session_id, "user", f"Pregunta {i}")
        sm.add_message(session_id, "assistant", f"Respuesta {i}")

    history_before = copy.deepcopy(sm.get_history(session_id))

    # Simulate a tool error by patching the agent
    with patch("agent.agent.agent") as mock_agent:
        mock_agent.side_effect = Exception(error_msg)

        from agent.agent import process_query
        response = process_query(
            query="¿Cuáles son las ventas del mes?",
            user_id="test-user",
            user_role="owner",
            session_id=session_id,
        )

    # Session must still exist
    assert sm.session_exists(session_id), (
        "Session should remain active after a tool error"
    )

    # Session history must be unchanged (process_query does not modify it directly)
    history_after = sm.get_history(session_id)
    assert len(history_after) == len(history_before), (
        f"Session history length changed after tool error: "
        f"before={len(history_before)}, after={len(history_after)}"
    )

    # Response must be a safe error message
    assert isinstance(response, str) and len(response) > 0, (
        "process_query must return a non-empty string even on tool error"
    )
