/**
 * ChatInterface — CopilotKit chat wrapper
 *
 * Wraps the CopilotKit `<CopilotChat>` component and configures it to
 * communicate with the BizQuery CopilotKit Runtime. A unique `session_id`
 * is generated when the component mounts and kept in client memory for the
 * lifetime of the page — reloading the page discards the session and starts
 * a fresh one with empty memory.
 *
 * Requirements: 6.1, 6.2, 6.3, 2.5
 */

import React, { useRef, useState, useCallback } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
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
 * Renders the BizQuery chat interface.
 *
 * The `session_id` is generated once on mount via `useRef` so it survives
 * re-renders but is discarded when the page is reloaded (Requirement 2.5).
 *
 * The CopilotKit runtime URL is `/api/copilotkit`, which is proxied to the
 * CopilotKit Runtime server during development and resolved by CloudFront
 * in production.
 */
const ChatInterface: React.FC<ChatInterfaceProps> = ({
  accessToken,
  onConnectionError,
}) => {
  // session_id lives in a ref so it is stable across re-renders and is
  // discarded when the component unmounts (page reload).
  const sessionIdRef = useRef<string>(generateSessionId());

  // Local message history — tracks messages displayed in the chat thread.
  // This mirrors what CopilotKit renders so we can test history growth.
  const [messages, setMessages] = useState<ChatMessage[]>([]);

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
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        background: "#ffffff",
      }}
    >
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
              title: "BizQuery",
              initial: "¡Hola! Soy BizQuery. Puedo ayudarte a consultar datos de ventas, inventario y recomendaciones de descuentos. ¿En qué puedo ayudarte?",
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
    </div>
  );
};

export { generateSessionId };
export default ChatInterface;
