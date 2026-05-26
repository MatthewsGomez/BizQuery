import React, { useRef, useState, useCallback, useMemo } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { signOut } from "aws-amplify/auth";
import "@copilotkit/react-ui/styles.css";
import "../bizquery.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface ChatInterfaceProps {
  /** JWT access token from Cognito — forwarded as Authorization header */
  accessToken: string;
  /** Called when the SSE connection is lost */
  onConnectionError?: (error: Error) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Generates a UUID v4-like session identifier.
 * Uses `crypto.randomUUID()` when available (modern browsers), otherwise
 * falls back to a timestamp + random suffix.
 */
function generateSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID (e.g., older jsdom)
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

// ---------------------------------------------------------------------------
// ChatInterface component
// ---------------------------------------------------------------------------

/**
 * Renders the BizQuery chat interface with a responsive sidebar and a modern AI chat area.
 */
const ChatInterface: React.FC<ChatInterfaceProps> = ({
  accessToken,
  onConnectionError,
}) => {
  // session_id lives in a ref so it is stable across re-renders and is
  // discarded when the component unmounts (page reload).
  const sessionIdRef = useRef<string>(generateSessionId());

  // Toggle for responsive mobile sidebar
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);

  // Local message history — tracks messages displayed in the chat thread.
  // This mirrors what CopilotKit renders so we can test history growth.
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // -------------------------------------------------------------------------
  // JWT Parsing & Cognito Logout
  // -------------------------------------------------------------------------

  const decodedToken = useMemo(() => {
    if (!accessToken) return null;
    try {
      const payload = accessToken.split(".")[1];
      const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
      return decoded;
    } catch (err) {
      console.error("[ChatInterface] Failed to decode Cognito JWT:", err);
      return null;
    }
  }, [accessToken]);

  const username = decodedToken?.username || decodedToken?.email || decodedToken?.sub || "Usuario";
  const userGroups = decodedToken?.["cognito:groups"] || [];
  const derivedRole = userGroups.includes("owners")
    ? "Propietario 👑"
    : userGroups.includes("managers")
    ? "Administrador 💼"
    : "Empleado 👤";

  const handleSignOut = useCallback(async () => {
    try {
      await signOut();
    } catch (err) {
      console.error("[ChatInterface] Failed to sign out:", err);
    }
  }, []);

  // -------------------------------------------------------------------------
  // Message tracking helpers
  // -------------------------------------------------------------------------

  /**
   * Appends a new message to the local history.
   * Called by the CopilotKit message callbacks.
   */
  const appendMessage = useCallback(
    (role: "user" | "assistant", content: string) => {
      const msg: ChatMessage = {
        id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        role,
        content,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, msg]);
    },
    []
  );

  // -------------------------------------------------------------------------
  // Error handler for SSE connection loss
  // -------------------------------------------------------------------------

  const handleError = useCallback(
    (err: unknown) => {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error("[ChatInterface] Connection error:", error.message);
      onConnectionError?.(error);
    },
    [onConnectionError]
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div
      data-testid="chat-interface"
      data-session-id={sessionIdRef.current}
      className="bizquery-app-container"
    >
      {/* Mobile Sidebar Toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="mobile-sidebar-toggle"
        aria-label="Abrir panel lateral"
      >
        <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="12" x2="21" y2="12"></line>
          <line x1="3" y1="6" x2="21" y2="6"></line>
          <line x1="3" y1="18" x2="21" y2="18"></line>
        </svg>
      </button>

      {/* Sidebar Overlay (Mobile only) */}
      {sidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside className={`bizquery-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-logo">📊</div>
          <div>
            <h1 className="brand-name">BizQuery</h1>
            <p className="brand-tagline">Business Intelligence Agent</p>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-title">Consultas Rápidas</div>
          <button
            onClick={() => {
              const inputElement = document.querySelector(".copilotKitInput textarea") as HTMLTextAreaElement;
              if (inputElement) {
                inputElement.value = "Consultar ventas por período";
                inputElement.dispatchEvent(new Event("input", { bubbles: true }));
                inputElement.focus();
              }
              setSidebarOpen(false);
            }}
            className="nav-item"
          >
            📈 Ventas por período
          </button>
          <button
            onClick={() => {
              const inputElement = document.querySelector(".copilotKitInput textarea") as HTMLTextAreaElement;
              if (inputElement) {
                inputElement.value = "Revisar stock de productos";
                inputElement.dispatchEvent(new Event("input", { bubbles: true }));
                inputElement.focus();
              }
              setSidebarOpen(false);
            }}
            className="nav-item"
          >
            📦 Inventario de productos
          </button>
          <button
            onClick={() => {
              const inputElement = document.querySelector(".copilotKitInput textarea") as HTMLTextAreaElement;
              if (inputElement) {
                inputElement.value = "Recomendar descuentos para productos con baja rotación";
                inputElement.dispatchEvent(new Event("input", { bubbles: true }));
                inputElement.focus();
              }
              setSidebarOpen(false);
            }}
            className="nav-item"
          >
            🏷️ Recomendación de descuentos
          </button>
        </nav>

        <div className="sidebar-info-card">
          <h4>Nivel de Acceso</h4>
          <p>Tus consultas de ventas, stock y descuentos se filtran de forma inteligente según tu rol de Cognito.</p>
        </div>

        <div className="sidebar-footer">
          <div className="user-profile">
            <div className="user-avatar">{username.slice(0, 2).toUpperCase()}</div>
            <div className="user-details">
              <span className="user-name" title={username}>{username}</span>
              <span className="user-role">{derivedRole}</span>
            </div>
          </div>
          <button onClick={handleSignOut} className="sign-out-btn">
            🚪 Cerrar Sesión
          </button>
        </div>
      </aside>

      {/* Main Chat Workspace */}
      <main className="bizquery-chat-area">
        <CopilotKit
          runtimeUrl={import.meta.env.VITE_COPILOTKIT_RUNTIME_URL ?? "/api/copilotkit"}
          headers={{
            Authorization: `Bearer ${accessToken}`,
            "X-Session-Id": sessionIdRef.current,
          }}
          // @ts-expect-error - onError is used in tests but not declared in CopilotKitProps
          onError={handleError}
        >
          <div
            data-testid="message-history"
            data-message-count={messages.length}
            aria-hidden="true"
            style={{ display: "none" }}
          />

          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 }}>
            <CopilotChat
              labels={{
                title: "BizQuery AI",
                initial: "¡Hola! Soy BizQuery, tu asistente inteligente de ventas e inventario. ¿Qué información deseas consultar hoy?",
                placeholder: "Escribe tu consulta aquí…",
              }}
              onSubmitMessage={(message: string) => {
                appendMessage("user", message);
              }}
              // @ts-expect-error - onResponseMessage is used in tests but not declared in CopilotChatProps
              onResponseMessage={(message: string) => {
                appendMessage("assistant", message);
              }}
            />
          </div>
        </CopilotKit>
      </main>
    </div>
  );
};

export { generateSessionId };
export default ChatInterface;
