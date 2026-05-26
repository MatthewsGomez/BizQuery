/**
 * App — Root component
 *
 * Composes `<AuthGuard>` and `<ChatInterface>`, managing global
 * authentication state. Handles SSE connection loss by showing an error
 * notification with a retry option.
 *
 * Requirements: 6.3, 6.5
 */

import React, { useState, useCallback } from "react";
import { fetchAuthSession } from "aws-amplify/auth";
import AuthGuard from "./components/AuthGuard";
import ChatInterface from "./components/ChatInterface";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConnectionErrorState {
  hasError: boolean;
  message: string;
  retryCount: number;
}

// ---------------------------------------------------------------------------
// App component
// ---------------------------------------------------------------------------

const App: React.FC = () => {
  // Access token is fetched once the AuthGuard confirms authentication.
  // It is stored in state so it can be refreshed on retry.
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // SSE connection error state
  const [connectionError, setConnectionError] = useState<ConnectionErrorState>({
    hasError: false,
    message: "",
    retryCount: 0,
  });

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /**
   * Called by AuthGuard once the Cognito session is confirmed.
   * Fetches the current access token and stores it in state.
   */
  const handleAuthenticated = useCallback(async () => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.accessToken?.toString() ?? null;
      setAccessToken(token);
    } catch (err) {
      console.error("[App] Failed to fetch access token:", err);
    }
  }, []);

  /**
   * Called by ChatInterface when the SSE connection is lost.
   * Shows an error notification with a retry option.
   */
  const handleConnectionError = useCallback((error: Error) => {
    setConnectionError((prev) => ({
      hasError: true,
      message: error.message || "Se perdió la conexión con el servidor.",
      retryCount: prev.retryCount + 1,
    }));
  }, []);

  /**
   * Retries the connection by clearing the error state.
   * The ChatInterface will re-mount and attempt a new SSE connection.
   */
  const handleRetry = useCallback(() => {
    setConnectionError((prev) => ({
      ...prev,
      hasError: false,
      message: "",
    }));
  }, []);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        fontFamily: "sans-serif",
      }}
    >
      {/* Connection error notification */}
      {connectionError.hasError && (
        <div
          role="alert"
          data-testid="connection-error-notification"
          style={{
            backgroundColor: "#fff3cd",
            border: "1px solid #ffc107",
            borderRadius: "4px",
            padding: "0.75rem 1rem",
            margin: "0.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
          }}
        >
          <span>
            ⚠️ Se perdió la conexión con el servidor.{" "}
            {connectionError.message && `(${connectionError.message})`}
          </span>
          <button
            onClick={handleRetry}
            data-testid="retry-button"
            style={{
              padding: "0.25rem 0.75rem",
              cursor: "pointer",
              backgroundColor: "#ffc107",
              border: "none",
              borderRadius: "4px",
              fontWeight: "bold",
            }}
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Protected content — only rendered when authenticated */}
      <AuthGuard>
        <AuthenticatedContent
          accessToken={accessToken}
          onAuthenticated={handleAuthenticated}
          onConnectionError={handleConnectionError}
        />
      </AuthGuard>
    </div>
  );
};

// ---------------------------------------------------------------------------
// AuthenticatedContent — rendered inside AuthGuard
// ---------------------------------------------------------------------------

interface AuthenticatedContentProps {
  accessToken: string | null;
  onAuthenticated: () => Promise<void>;
  onConnectionError: (error: Error) => void;
}

/**
 * Inner component rendered once the user is authenticated.
 * Fetches the access token on mount and renders the ChatInterface.
 */
const AuthenticatedContent: React.FC<AuthenticatedContentProps> = ({
  accessToken,
  onAuthenticated,
  onConnectionError,
}) => {
  // Trigger token fetch on first render inside the auth guard
  React.useEffect(() => {
    void onAuthenticated();
  }, [onAuthenticated]);

  if (!accessToken) {
    return (
      <div
        role="status"
        aria-label="Cargando interfaz de chat"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flex: 1,
          color: "#555",
        }}
      >
        <span>Cargando…</span>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflow: "hidden" }}>
      <ChatInterface
        accessToken={accessToken}
        onConnectionError={onConnectionError}
      />
    </div>
  );
};

export default App;
