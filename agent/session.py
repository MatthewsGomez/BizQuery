"""
BizQuery — Gestión de sesiones conversacionales.

Este módulo provee la lógica de gestión de sesión para el agente BizQuery:
generación de identificadores de sesión únicos y mantenimiento del historial
conversacional en memoria.

Cada sesión almacena:
  - ``session_id``: UUID v4 único de la sesión.
  - ``user_id``: Identificador del usuario autenticado (Cognito ``sub``).
  - ``user_role``: Rol del usuario (``"owner"`` o ``"employee"``).
  - ``created_at``: Timestamp ISO-8601 de creación de la sesión.
  - ``messages``: Lista de mensajes con ``role``, ``content`` y ``timestamp``.

Requisitos satisfechos:
  - Req 2.1: Mantiene el contexto conversacional con todos los mensajes desde
    el inicio de la sesión.
  - Req 2.4: Retiene un mínimo de 20 turnos de conversación anteriores
    (sin límite de mensajes en esta implementación).
  - Req 2.5: Nueva sesión comienza con historial vacío, independiente de
    sesiones anteriores.
  - Req 2.6: Cada sesión está asociada exclusivamente al ``session_id`` del
    usuario autenticado; dos usuarios concurrentes no comparten contexto.

Uso::

    from agent.session import session_manager, generate_session_id

    # Crear una nueva sesión
    session_id = generate_session_id()
    session = session_manager.create_session(
        user_id="cognito-sub-uuid",
        user_role="owner",
    )

    # Agregar mensajes
    session_manager.add_message(session["session_id"], "user", "¿Cuáles son las ventas del mes?")
    session_manager.add_message(session["session_id"], "assistant", "Las ventas del mes fueron...")

    # Recuperar historial
    history = session_manager.get_history(session["session_id"])
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def generate_session_id() -> str:
    """
    Genera un identificador de sesión único como UUID v4.

    Returns
    -------
    str
        Cadena UUID v4 en formato estándar (e.g. ``"550e8400-e29b-41d4-a716-446655440000"``).

    Examples
    --------
    >>> sid = generate_session_id()
    >>> len(sid)
    36
    >>> sid.count("-")
    4
    """
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """
    Gestiona sesiones conversacionales en memoria.

    Mantiene un diccionario interno de sesiones indexado por ``session_id``.
    Cada sesión almacena el identificador de usuario, su rol, la marca de
    tiempo de creación y la lista de mensajes del historial conversacional.

    Esta implementación satisface los requisitos de memoria conversacional
    (Req 2.1, 2.4, 2.5, 2.6): el historial crece con cada mensaje, nunca
    pierde mensajes durante la sesión, y cada sesión es completamente
    independiente de las demás.

    Notes
    -----
    El almacenamiento es en memoria (``dict``). Los datos se pierden al
    reiniciar el proceso. Para persistencia entre reinicios se requeriría
    integración con un backend externo (e.g. DynamoDB, Redis).
    """

    def __init__(self) -> None:
        # Diccionario principal: session_id → session dict
        self._sessions: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self, user_id: str, user_role: str) -> dict:
        """
        Crea una nueva sesión con historial vacío.

        Genera un ``session_id`` único, registra el usuario y su rol, y
        almacena la sesión en memoria. El historial comienza vacío,
        independientemente de si el mismo usuario tiene sesiones anteriores
        (Req 2.5).

        Parameters
        ----------
        user_id:
            Identificador del usuario autenticado (Cognito ``sub``).
        user_role:
            Rol del usuario: ``"owner"`` o ``"employee"``.

        Returns
        -------
        dict
            Diccionario de sesión con las claves ``session_id``, ``user_id``,
            ``user_role``, ``created_at`` y ``messages``.

        Examples
        --------
        >>> sm = SessionManager()
        >>> session = sm.create_session("user-123", "owner")
        >>> session["user_id"]
        'user-123'
        >>> session["messages"]
        []
        """
        session_id = generate_session_id()
        session: dict = {
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "created_at": _now_iso(),
            "messages": [],
        }
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Recupera una sesión por su identificador.

        Parameters
        ----------
        session_id:
            Identificador UUID v4 de la sesión.

        Returns
        -------
        dict or None
            Diccionario de sesión si existe, ``None`` en caso contrario.
        """
        return self._sessions.get(session_id)

    def session_exists(self, session_id: str) -> bool:
        """
        Comprueba si una sesión existe en memoria.

        Parameters
        ----------
        session_id:
            Identificador UUID v4 de la sesión.

        Returns
        -------
        bool
            ``True`` si la sesión existe, ``False`` en caso contrario.
        """
        return session_id in self._sessions

    def clear_session(self, session_id: str) -> None:
        """
        Elimina una sesión de memoria.

        Si la sesión no existe, la operación no tiene efecto (no lanza
        excepción).

        Parameters
        ----------
        session_id:
            Identificador UUID v4 de la sesión a eliminar.
        """
        self._sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Agrega un mensaje al historial de una sesión.

        El mensaje se añade al final de la lista ``messages`` de la sesión,
        preservando todos los mensajes anteriores (Req 2.1). El historial
        nunca pierde mensajes durante la sesión activa (Req 2.4).

        Parameters
        ----------
        session_id:
            Identificador UUID v4 de la sesión.
        role:
            Rol del emisor del mensaje: ``"user"`` o ``"assistant"``.
        content:
            Texto del mensaje.

        Raises
        ------
        KeyError
            Si la sesión no existe.

        Examples
        --------
        >>> sm = SessionManager()
        >>> session = sm.create_session("user-123", "owner")
        >>> sm.add_message(session["session_id"], "user", "Hola")
        >>> len(sm.get_history(session["session_id"]))
        1
        """
        session = self._sessions[session_id]
        message = {
            "role": role,
            "content": content,
            "timestamp": _now_iso(),
        }
        session["messages"].append(message)

    def get_history(self, session_id: str) -> List[dict]:
        """
        Retorna el historial de mensajes de una sesión.

        Parameters
        ----------
        session_id:
            Identificador UUID v4 de la sesión.

        Returns
        -------
        list
            Lista de mensajes de la sesión. Retorna una lista vacía si la
            sesión no existe (comportamiento seguro para evitar excepciones
            en el flujo del agente).

        Examples
        --------
        >>> sm = SessionManager()
        >>> sm.get_history("nonexistent-id")
        []
        """
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return session["messages"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Retorna el timestamp actual en formato ISO-8601 con zona horaria UTC."""
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

#: Instancia de ``SessionManager`` a nivel de módulo para uso directo.
session_manager: SessionManager = SessionManager()
