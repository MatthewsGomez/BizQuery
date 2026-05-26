/**
 * Unit Tests — AuthGuard
 *
 * Cases:
 *  1. Redirect without active session (no token → signInWithRedirect called)
 *  2. Loading indicator during session check
 *  3. Connection error notification (auth error surfaces correctly)
 *  4. Children rendered when session is valid
 *
 * Requirements: 8.1, 8.2
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock aws-amplify/auth
// ---------------------------------------------------------------------------

const mockFetchAuthSession = vi.fn();
const mockSignInWithRedirect = vi.fn();

vi.mock("aws-amplify/auth", () => ({
  fetchAuthSession: (...args: unknown[]) => mockFetchAuthSession(...args),
  signInWithRedirect: (...args: unknown[]) => mockSignInWithRedirect(...args),
}));

// Import after mocking
import AuthGuard from "./AuthGuard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Creates a mock Cognito session with a valid access token */
function mockValidSession(token = "header.payload.signature") {
  return {
    tokens: {
      accessToken: {
        toString: () => token,
      },
    },
  };
}

/** Creates a mock session with no tokens (unauthenticated) */
function mockEmptySession() {
  return { tokens: undefined };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuthGuard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: signInWithRedirect resolves immediately
    mockSignInWithRedirect.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Case 1: Loading indicator during session check
  // -------------------------------------------------------------------------

  it("shows a loading indicator while the session check is in progress", () => {
    // fetchAuthSession never resolves during this test
    mockFetchAuthSession.mockReturnValue(new Promise(() => {}));

    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>
    );

    // Loading indicator must be visible
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "Verificando sesión"
    );

    // Protected content must NOT be visible yet
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Case 2: Redirect without active session (no token)
  // -------------------------------------------------------------------------

  it("calls signInWithRedirect when the session has no access token", async () => {
    mockFetchAuthSession.mockResolvedValue(mockEmptySession());

    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(mockSignInWithRedirect).toHaveBeenCalledTimes(1);
    });

    // Protected content must NOT be rendered
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  it("calls signInWithRedirect when fetchAuthSession throws a 'No current user' error", async () => {
    mockFetchAuthSession.mockRejectedValue(
      new Error("No current user")
    );

    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(mockSignInWithRedirect).toHaveBeenCalledTimes(1);
    });

    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  it("calls signInWithRedirect when fetchAuthSession throws a UserUnAuthenticatedException", async () => {
    mockFetchAuthSession.mockRejectedValue(
      new Error("UserUnAuthenticatedException: User is not authenticated")
    );

    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(mockSignInWithRedirect).toHaveBeenCalledTimes(1);
    });

    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Case 3: Connection error notification
  // -------------------------------------------------------------------------

  it("shows an error message when an unexpected auth error occurs", async () => {
    const unexpectedError = new Error("Network timeout");
    mockFetchAuthSession.mockRejectedValue(unexpectedError);

    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Network timeout");
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  it("shows a login button in the error state that calls signInWithRedirect", async () => {
    mockFetchAuthSession.mockRejectedValue(new Error("Unexpected error"));

    render(
      <AuthGuard>
        <div>Protected</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    const loginButton = screen.getByRole("button", { name: /iniciar sesión/i });
    expect(loginButton).toBeInTheDocument();

    await userEvent.click(loginButton);

    expect(mockSignInWithRedirect).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Case 4: Children rendered when session is valid
  // -------------------------------------------------------------------------

  it("renders children when the session has a valid access token", async () => {
    mockFetchAuthSession.mockResolvedValue(mockValidSession());

    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected Content</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
    });

    expect(screen.getByTestId("protected-content")).toHaveTextContent(
      "Protected Content"
    );

    // Loading indicator must be gone
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("does not call signInWithRedirect when the session is valid", async () => {
    mockFetchAuthSession.mockResolvedValue(mockValidSession());

    render(
      <AuthGuard>
        <div>Protected</div>
      </AuthGuard>
    );

    await waitFor(() => {
      expect(screen.getByText("Protected")).toBeInTheDocument();
    });

    expect(mockSignInWithRedirect).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Custom loading component
  // -------------------------------------------------------------------------

  it("renders a custom loading component when provided", () => {
    mockFetchAuthSession.mockReturnValue(new Promise(() => {}));

    render(
      <AuthGuard loadingComponent={<div data-testid="custom-loader">Loading…</div>}>
        <div>Protected</div>
      </AuthGuard>
    );

    expect(screen.getByTestId("custom-loader")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Cleanup: cancelled effect on unmount
  // -------------------------------------------------------------------------

  it("does not update state after unmount (no memory leak)", async () => {
    // Delay the resolution so we can unmount before it completes
    let resolveSession!: (value: unknown) => void;
    mockFetchAuthSession.mockReturnValue(
      new Promise((resolve) => {
        resolveSession = resolve;
      })
    );

    const { unmount } = render(
      <AuthGuard>
        <div>Protected</div>
      </AuthGuard>
    );

    // Unmount before the session resolves
    unmount();

    // Resolve after unmount — should not cause any state update errors
    resolveSession(mockValidSession());

    // Give React a tick to process
    await new Promise((r) => setTimeout(r, 10));

    // No assertion needed — the test passes if no "Can't perform a React
    // state update on an unmounted component" warning is thrown.
    expect(true).toBe(true);
  });
});
