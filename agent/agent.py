"""
BizQuery Strand Agent — instancia principal del agente conversacional.

Este módulo configura el Strand Agent con:
  - Modelo Claude de Amazon Bedrock (configurable vía variables de entorno)
  - Las tres herramientas registradas: query_sales, query_inventory, analyze_discounts
  - System prompt en español que define el comportamiento del agente

Variables de entorno:
    BEDROCK_MODEL_ID   ID del modelo de Bedrock (default: anthropic.claude-3-5-sonnet-20241022-v2:0)
    AWS_REGION         Región de AWS (default: us-east-1)

Uso::

    from agent.agent import agent, process_query

    response = process_query(
        query="¿Cuáles fueron las ventas del mes pasado?",
        user_id="cognito-sub-uuid",
        user_role="owner",
        session_id="uuid-v4",
    )
"""

from __future__ import annotations

import logging
import os
from typing import Optional

# ---------------------------------------------------------------------------
# Optional strands import — fall back to minimal stubs so the module is
# importable in environments where the `strands` package is not installed
# (e.g. unit-test runners, CI pipelines).
# ---------------------------------------------------------------------------
try:
    from strands import Agent  # type: ignore[import]
    from strands.models import BedrockModel  # type: ignore[import]
    _STRANDS_AVAILABLE = True
except ImportError:
    _STRANDS_AVAILABLE = False

    class BedrockModel:  # type: ignore[no-redef]
        """Stub for BedrockModel when strands is not installed."""

        def __init__(self, model_id: str, region_name: str, **kwargs):
            self.model_id = model_id
            self.region_name = region_name

    class Agent:  # type: ignore[no-redef]
        """Stub for Agent when strands is not installed."""

        def __init__(self, model=None, tools=None, system_prompt: str = "", **kwargs):
            self.model = model
            self.tools = tools or []
            self.system_prompt = system_prompt

        def __call__(self, query: str, **kwargs) -> "AgentResponse":
            return AgentResponse(
                message="strands package not installed — cannot process queries."
            )

    class AgentResponse:  # type: ignore[misc]
        """Minimal response stub."""

        def __init__(self, message: str):
            self.message = message

        def __str__(self) -> str:
            return self.message


from agent.tools import query_sales, query_inventory, analyze_discounts  # noqa: E402

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
_BEDROCK_MODEL_ID: str = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
)
_AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """Eres BizQuery, un asistente inteligente de consulta de datos para una empresa de electrodomésticos.

## Tu rol y capacidades

Puedes responder preguntas sobre:
- **Ventas**: totales por período, rendimiento por producto o categoría, comparaciones entre períodos, productos más vendidos.
- **Inventario**: disponibilidad de productos, niveles de stock, productos con bajo stock, inventario por categoría.
- **Recomendaciones de descuentos**: análisis de rotación de inventario y velocidad de ventas para sugerir descuentos óptimos (solo disponible para usuarios con rol Dueño).

## Idioma de respuesta

Responde siempre en el mismo idioma en que el usuario formuló su pregunta. Si la pregunta está en español, responde en español. Si está en inglés, responde en inglés.

## Consultas fuera de alcance

Si el usuario hace una pregunta que no está relacionada con ventas, inventario o recomendaciones de descuentos de la empresa, explica amablemente que no puedes ayudar con esa solicitud y describe qué tipo de preguntas sí puedes responder. Por ejemplo:
- "Lo siento, no puedo ayudarte con eso. Estoy especializado en consultas sobre ventas, inventario y recomendaciones de descuentos de la empresa. ¿Puedo ayudarte con alguna de estas áreas?"

## Manejo de errores

- Nunca expongas detalles técnicos al usuario: no muestres errores SQL, stack traces, nombres de tablas, nombres de funciones Lambda ni mensajes de error internos.
- Si ocurre un error al consultar los datos, informa al usuario de forma comprensible: "No pude obtener los datos en este momento. Por favor, intenta de nuevo más tarde."
- Si el usuario no tiene permisos para acceder a cierta información, explícalo de forma clara y respetuosa.

## Formato de respuestas

- Cuando los datos sean tabulares (listas de productos, ventas por categoría, etc.), preséntelos en formato de tabla Markdown para facilitar la lectura.
- Cuando presentes recomendaciones de descuentos, destaca claramente el producto, el descuento sugerido y la justificación.
- Usa lenguaje natural y amigable; evita jerga técnica innecesaria.
- Sé conciso pero completo: incluye los datos relevantes sin sobrecargar al usuario con información innecesaria.

## Contexto del negocio

La empresa vende electrodomésticos (refrigeradores, lavadoras, televisores, aires acondicionados, etc.). Los usuarios pueden ser Dueños (acceso completo) o Empleados (acceso restringido a datos operativos).
"""


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_agent() -> Agent:
    """
    Crea y retorna una instancia configurada del Strand Agent.

    El agente usa el modelo Claude de Amazon Bedrock especificado en la
    variable de entorno ``BEDROCK_MODEL_ID`` y tiene registradas las tres
    herramientas de BizQuery: ``query_sales``, ``query_inventory`` y
    ``analyze_discounts``.

    Returns
    -------
    Agent
        Instancia del Strand Agent lista para procesar consultas.
    """
    model = BedrockModel(
        model_id=_BEDROCK_MODEL_ID,
        region_name=_AWS_REGION,
    )

    return Agent(
        model=model,
        tools=[query_sales, query_inventory, analyze_discounts],
        system_prompt=_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Module-level agent instance (convenience)
# ---------------------------------------------------------------------------

#: Instancia del agente a nivel de módulo para uso directo.
agent: Agent = create_agent()


# ---------------------------------------------------------------------------
# process_query helper
# ---------------------------------------------------------------------------

def process_query(
    query: str,
    user_id: str,
    user_role: str,
    session_id: Optional[str] = None,
) -> str:
    """
    Procesa una consulta del usuario y retorna la respuesta en texto.

    Invoca el agente con la consulta proporcionada y extrae el texto de la
    respuesta. Los parámetros ``user_id``, ``user_role`` y ``session_id``
    se incluyen en el contexto para que las herramientas puedan aplicar
    el control de acceso basado en roles.

    Parameters
    ----------
    query:
        Pregunta o instrucción en lenguaje natural del usuario.
    user_id:
        Identificador del usuario autenticado (Cognito ``sub``).
    user_role:
        Rol del usuario: ``"owner"`` o ``"employee"``.
    session_id:
        Identificador de sesión para mantener el contexto conversacional
        (opcional; si se omite, el agente no asocia la consulta a una sesión).

    Returns
    -------
    str
        Respuesta del agente en lenguaje natural.

    Examples
    --------
    >>> response = process_query(
    ...     query="¿Cuáles son los productos con bajo stock?",
    ...     user_id="user-123",
    ...     user_role="owner",
    ...     session_id="session-abc",
    ... )
    >>> print(response)
    """
    logger.info(
        "process_query | user_id=%s user_role=%s session_id=%s query_len=%d",
        user_id,
        user_role,
        session_id,
        len(query),
    )

    # Build the full query with user context so the tools can use it
    # The agent will pass user_id and user_role when invoking tools
    contextual_query = (
        f"[user_id={user_id}, user_role={user_role}"
        + (f", session_id={session_id}" if session_id else "")
        + f"]\n\n{query}"
    )

    try:
        response = agent(contextual_query)
        response_text = str(response)
        logger.info(
            "process_query completed | user_id=%s response_len=%d",
            user_id,
            len(response_text),
        )
        return response_text
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "process_query error | user_id=%s error=%s",
            user_id,
            exc,
            exc_info=True,
        )
        return (
            "Lo siento, ocurrió un error al procesar tu consulta. "
            "Por favor, intenta de nuevo más tarde."
        )
