/**
 * AuthGuard — Higher-Order Component for Cognito session protection
 *
 * Verifies that the user has an active Cognito session before rendering
 * the protected content. If no valid session is found, the user is
 * redirected to the Cognito Hosted UI for authentication.
 *
 * Requirements: 8.1, 8.2
 */

import React, { useEffect, useState, ReactNode } from "react";
import { fetchAuthSession, signInWithRedirect } from "aws-amplify/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthState {
  /** Whether the auth check has completed */
  isLoading: boolean;
  /** Whether the user is authenticated */
  isAuthenticated: boolean;
  /** The raw JWT access token, available when authenticated */
  accessToken: string | null;
  /** Any error that occurred during the auth check */
  error: Error | null;
}

interface AuthGuardProps {
  children: ReactNode;
  /** Optional custom loading component */
  loadingComponent?: ReactNode;
}

// ---------------------------------------------------------------------------
// AuthGuard component
// ---------------------------------------------------------------------------

/**
 * Wraps protected content and ensures the user is authenticated.
 *
 * Behaviour:
 *  1. On mount, calls `fetchAuthSession()` to check for an active Cognito session.
 *  2. If a valid session with an access token exists → renders children.
 *  3. If no session or the token is missing → redirects to Cognito Hosted UI
 *     via `signInWithRedirect()`.
 *  4. While the check is in progress → renders a loading indicator.
 */
const AuthGuard: React.FC<AuthGuardProps> = ({
  children,
  loadingComponent,
}) => {
  const [authState, setAuthState] = useState<AuthState>({
    isLoading: true,
    isAuthenticated: false,
    accessToken: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    const checkSession = async () => {
      try {
        const session = await fetchAuthSession();
        const token = session.tokens?.accessToken?.toString() ?? null;

        if (cancelled) return;

        if (token) {
          setAuthState({
            isLoading: false,
            isAuthenticated: true,
            accessToken: token,
            error: null,
          });
        } else {
          // No valid token — redirect to Cognito Hosted UI
          await signInWithRedirect();
        }
      } catch (err) {
        if (cancelled) return;

        const error = err instanceof Error ? err : new Error(String(err));

        // If the error indicates no session, redirect to login
        if (
          error.message.includes("No current user") ||
          error.message.includes("not authenticated") ||
          error.message.includes("UserUnAuthenticatedException")
        ) {
          try {
            await signInWithRedirect();
          } catch {
            // signInWithRedirect itself failed — surface the error
            setAuthState({
              isLoading: false,
              isAuthenticated: false,
              accessToken: null,
              error,
            });
          }
        } else {
          setAuthState({
            isLoading: false,
            isAuthenticated: false,
            accessToken: null,
            error,
          });
        }
      }
    };

    void checkSession();

    return () => {
      cancelled = true;
    };
  }, []);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (authState.isLoading) {
    return (
      <>
        {loadingComponent ?? (
          <div
            role="status"
            aria-label="Verificando sesión"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100vh",
              fontFamily: "sans-serif",
              color: "#555",
            }}
          >
            <span>Cargando…</span>
          </div>
        )}
      </>
    );
  }

  if (authState.error) {
    return (
      <div
        role="alert"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          fontFamily: "sans-serif",
          color: "#c00",
          gap: "1rem",
        }}
      >
        <p>Error de autenticación: {authState.error.message}</p>
        <button
          onClick={() => void signInWithRedirect()}
          style={{ padding: "0.5rem 1rem", cursor: "pointer" }}
        >
          Iniciar sesión
        </button>
      </div>
    );
  }

  if (!authState.isAuthenticated) {
    // Redirect is in progress — render nothing
    return null;
  }

  return <>{children}</>;
};

export default AuthGuard;
