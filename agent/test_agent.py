"""
Tests unitarios para el Strand Agent de BizQuery.

Casos cubiertos
---------------
1. Consulta fuera de alcance — cuando el agente recibe una consulta fuera de
   su dominio, ``process_query`` retorna una respuesta (no lanza excepción,
   retorna un string).

2. Error en herramienta — cuando una herramienta lanza una excepción,
   ``process_query`` retorna un mensaje de error amigable para el usuario
   (no un stack trace ni el mensaje de excepción crudo).

3. Cambio de tema en la misma sesión — el ``SessionManager`` maneja
   correctamente múltiples mensajes en la misma sesión con diferentes temas.
"""

from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Make the agent package importable from the workspace root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.session import SessionManager, generate_session_id
from agent.agent import process_query


# ---------------------------------------------------------------------------
# Test Case 1: Consulta fuera de alcance
# ---------------------------------------------------------------------------

class TestOutOfScopeQuery(unittest.TestCase):
    """
    Verifica que process_query no lanza excepción cuando el agente recibe
    una consulta fuera de su dominio y retorna un string no vacío.
    """

    def test_out_of_scope_query_returns_string(self):
        """
        Cuando el agente recibe una consulta fuera de su dominio (e.g. receta
        de cocina), process_query debe retornar un string — no lanzar excepción.
        """
        # The stub Agent (used when strands is not installed) returns a fixed
        # message. We patch it to simulate an out-of-scope response.
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: (
            "Lo siento, no puedo ayudarte con eso. "
            "Estoy especializado en consultas sobre ventas, inventario y "
            "recomendaciones de descuentos de la empresa."
        )

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.return_value = mock_response

            result = process_query(
                query="¿Cuál es la receta del gazpacho?",
                user_id="user-001",
                user_role="employee",
                session_id=generate_session_id(),
            )

        self.assertIsInstance(result, str, "process_query debe retornar un str")
        self.assertGreater(len(result), 0, "La respuesta no debe estar vacía")

    def test_out_of_scope_query_does_not_raise(self):
        """
        process_query no debe propagar ninguna excepción para consultas
        fuera de alcance — el agente las maneja internamente.
        """
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "No puedo ayudarte con esa solicitud."

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.return_value = mock_response

            try:
                result = process_query(
                    query="¿Quién ganó el mundial de fútbol en 2022?",
                    user_id="user-002",
                    user_role="owner",
                    session_id=generate_session_id(),
                )
            except Exception as exc:  # noqa: BLE001
                self.fail(
                    f"process_query lanzó una excepción inesperada: {exc}"
                )

        self.assertIsInstance(result, str)

    def test_out_of_scope_query_returns_non_empty_response(self):
        """
        La respuesta para una consulta fuera de alcance debe ser un string
        con contenido (longitud > 0).
        """
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: (
            "Esa consulta está fuera de mi alcance. "
            "Puedo ayudarte con ventas, inventario y descuentos."
        )

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.return_value = mock_response

            result = process_query(
                query="Explícame la teoría de la relatividad",
                user_id="user-003",
                user_role="owner",
            )

        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


# ---------------------------------------------------------------------------
# Test Case 2: Error en herramienta
# ---------------------------------------------------------------------------

class TestToolError(unittest.TestCase):
    """
    Verifica que cuando una herramienta lanza una excepción, process_query
    retorna un mensaje de error amigable — no un stack trace ni el mensaje
    de excepción crudo.
    """

    def _assert_safe_error_response(self, response: str, raw_error: str) -> None:
        """Helper: verifica que la respuesta es segura y amigable."""
        self.assertIsInstance(response, str, "La respuesta debe ser un str")
        self.assertGreater(len(response), 0, "La respuesta no debe estar vacía")
        self.assertNotIn(
            raw_error, response,
            "La respuesta no debe exponer el mensaje de error crudo"
        )
        self.assertNotIn(
            "Traceback", response,
            "La respuesta no debe exponer un stack trace"
        )
        self.assertNotIn(
            "Exception", response,
            "La respuesta no debe exponer nombres de clases de excepción"
        )

    def test_tool_exception_returns_friendly_message(self):
        """
        Cuando el agente lanza una excepción (simulando un error de Lambda),
        process_query debe retornar un mensaje amigable para el usuario.
        """
        raw_error = "Connection timeout to Lambda bizquery-query-sales"

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.side_effect = Exception(raw_error)

            result = process_query(
                query="¿Cuáles fueron las ventas del mes pasado?",
                user_id="user-010",
                user_role="owner",
                session_id=generate_session_id(),
            )

        self._assert_safe_error_response(result, raw_error)

    def test_db_unavailable_error_returns_friendly_message(self):
        """
        Cuando la Lambda retorna un error de base de datos no disponible,
        process_query debe retornar un mensaje amigable.
        """
        raw_error = "DB_UNAVAILABLE: could not connect to server"

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.side_effect = RuntimeError(raw_error)

            result = process_query(
                query="¿Qué productos tienen bajo stock?",
                user_id="user-011",
                user_role="employee",
                session_id=generate_session_id(),
            )

        self._assert_safe_error_response(result, raw_error)

    def test_lambda_function_error_returns_friendly_message(self):
        """
        Cuando la Lambda retorna un FunctionError (excepción interna),
        process_query debe retornar un mensaje amigable.
        """
        raw_error = "Lambda bizquery-analyze-discounts returned an error: {'errorMessage': 'Task timed out'}"

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.side_effect = RuntimeError(raw_error)

            result = process_query(
                query="¿Qué descuentos debería aplicar este mes?",
                user_id="user-012",
                user_role="owner",
                session_id=generate_session_id(),
            )

        self._assert_safe_error_response(result, raw_error)

    def test_sql_error_does_not_expose_internals(self):
        """
        Un error SQL interno no debe filtrarse al usuario en la respuesta.
        """
        raw_error = "SQL syntax error near 'SELECT * FROM sales WHERE'"

        with patch("agent.agent.agent") as mock_agent:
            mock_agent.side_effect = Exception(raw_error)

            result = process_query(
                query="Dame el resumen de ventas por categoría",
                user_id="user-013",
                user_role="owner",
            )

        self._assert_safe_error_response(result, raw_error)
        # Also verify no SQL keywords leak through
        self.assertNotIn("SELECT", result)
        self.assertNotIn("FROM", result)

    def test_error_response_is_meaningful(self):
        """
        El mensaje de error retornado debe tener una longitud mínima para
        ser considerado un mensaje significativo (no una cadena vacía o
        un solo carácter).
        """
        with patch("agent.agent.agent") as mock_agent:
            mock_agent.side_effect = Exception("Internal server error")

            result = process_query(
                query="¿Cuántas unidades de lavadoras hay en stock?",
                user_id="user-014",
                user_role="employee",
                session_id=generate_session_id(),
            )

        self.assertGreaterEqual(
            len(result), 10,
            "El mensaje de error debe ser suficientemente descriptivo"
        )


# ---------------------------------------------------------------------------
# Test Case 3: Cambio de tema en la misma sesión
# ---------------------------------------------------------------------------

class TestTopicChangeInSession(unittest.TestCase):
    """
    Verifica que el SessionManager maneja correctamente múltiples mensajes
    en la misma sesión con diferentes temas.
    """

    def setUp(self):
        """Crea un SessionManager fresco para cada test."""
        self.sm = SessionManager()

    def test_session_handles_multiple_topics(self):
        """
        Una sesión puede contener mensajes sobre diferentes temas (ventas,
        inventario, descuentos) y el historial los preserva todos en orden.
        """
        session = self.sm.create_session(user_id="user-020", user_role="owner")
        session_id = session["session_id"]

        # Turno 1: consulta sobre ventas
        self.sm.add_message(session_id, "user", "¿Cuáles fueron las ventas del mes pasado?")
        self.sm.add_message(session_id, "assistant", "Las ventas del mes pasado fueron $50,000.")

        # Turno 2: cambio de tema a inventario
        self.sm.add_message(session_id, "user", "¿Qué productos tienen bajo stock?")
        self.sm.add_message(session_id, "assistant", "Los siguientes productos tienen bajo stock: ...")

        # Turno 3: cambio de tema a descuentos
        self.sm.add_message(session_id, "user", "¿Qué descuentos debería aplicar?")
        self.sm.add_message(session_id, "assistant", "Recomiendo aplicar un 15% de descuento en refrigeradores.")

        history = self.sm.get_history(session_id)

        # Debe haber exactamente 6 mensajes (3 turnos × 2 mensajes por turno)
        self.assertEqual(len(history), 6)

        # Verificar el orden y contenido de los mensajes
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("ventas", history[0]["content"])

        self.assertEqual(history[2]["role"], "user")
        self.assertIn("stock", history[2]["content"])

        self.assertEqual(history[4]["role"], "user")
        self.assertIn("descuentos", history[4]["content"])

    def test_session_preserves_message_order_across_topics(self):
        """
        El historial preserva el orden cronológico de los mensajes
        independientemente del tema de cada uno.
        """
        session = self.sm.create_session(user_id="user-021", user_role="employee")
        session_id = session["session_id"]

        messages = [
            ("user", "¿Cuántas lavadoras hay en stock?"),
            ("assistant", "Hay 15 lavadoras disponibles."),
            ("user", "¿Y refrigeradores?"),
            ("assistant", "Hay 8 refrigeradores disponibles."),
            ("user", "¿Cuáles tienen bajo stock?"),
            ("assistant", "Los refrigeradores están por debajo del umbral mínimo."),
        ]

        for role, content in messages:
            self.sm.add_message(session_id, role, content)

        history = self.sm.get_history(session_id)

        self.assertEqual(len(history), len(messages))
        for i, (expected_role, expected_content) in enumerate(messages):
            self.assertEqual(history[i]["role"], expected_role)
            self.assertEqual(history[i]["content"], expected_content)

    def test_session_history_grows_with_each_topic_change(self):
        """
        El historial crece exactamente en 1 con cada mensaje agregado,
        incluso cuando los mensajes son de temas distintos.
        """
        session = self.sm.create_session(user_id="user-022", user_role="owner")
        session_id = session["session_id"]

        topics = [
            ("user", "Consulta sobre ventas"),
            ("assistant", "Respuesta sobre ventas"),
            ("user", "Consulta sobre inventario"),
            ("assistant", "Respuesta sobre inventario"),
            ("user", "Consulta sobre descuentos"),
            ("assistant", "Respuesta sobre descuentos"),
        ]

        for i, (role, content) in enumerate(topics):
            count_before = len(self.sm.get_history(session_id))
            self.sm.add_message(session_id, role, content)
            count_after = len(self.sm.get_history(session_id))

            self.assertEqual(
                count_after, count_before + 1,
                f"El historial debe crecer en 1 al agregar el mensaje {i}"
            )

    def test_two_sessions_same_user_are_independent(self):
        """
        Dos sesiones del mismo usuario son completamente independientes:
        los mensajes de una no afectan a la otra.
        """
        user_id = "user-023"

        session_a = self.sm.create_session(user_id=user_id, user_role="owner")
        session_b = self.sm.create_session(user_id=user_id, user_role="owner")

        sid_a = session_a["session_id"]
        sid_b = session_b["session_id"]

        # Agregar mensajes solo a la sesión A
        self.sm.add_message(sid_a, "user", "¿Cuáles son las ventas del trimestre?")
        self.sm.add_message(sid_a, "assistant", "Las ventas del trimestre fueron $150,000.")

        # La sesión B debe seguir vacía
        history_b = self.sm.get_history(sid_b)
        self.assertEqual(
            len(history_b), 0,
            "La sesión B no debe verse afectada por los mensajes de la sesión A"
        )

        # La sesión A debe tener exactamente 2 mensajes
        history_a = self.sm.get_history(sid_a)
        self.assertEqual(len(history_a), 2)

    def test_new_session_starts_empty_after_topic_changes(self):
        """
        Una nueva sesión comienza con historial vacío, incluso si la sesión
        anterior tenía múltiples temas.
        """
        # Sesión anterior con múltiples temas
        old_session = self.sm.create_session(user_id="user-024", user_role="owner")
        old_sid = old_session["session_id"]

        self.sm.add_message(old_sid, "user", "Ventas del mes")
        self.sm.add_message(old_sid, "assistant", "Respuesta ventas")
        self.sm.add_message(old_sid, "user", "Inventario actual")
        self.sm.add_message(old_sid, "assistant", "Respuesta inventario")

        # Nueva sesión para el mismo usuario
        new_session = self.sm.create_session(user_id="user-024", user_role="owner")
        new_sid = new_session["session_id"]

        new_history = self.sm.get_history(new_sid)
        self.assertEqual(
            len(new_history), 0,
            "La nueva sesión debe comenzar con historial vacío"
        )


if __name__ == "__main__":
    unittest.main()
