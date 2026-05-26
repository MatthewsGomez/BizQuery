/**
 * amplify.ts — AWS Amplify configuration for BizQuery
 *
 * Configures Amplify with Cognito credentials sourced from Vite environment
 * variables. Import and call `configureAmplify()` once at app startup
 * (before any auth calls) — `main.tsx` is the right place.
 *
 * Required environment variables (set in .env or injected at build time):
 *   VITE_COGNITO_USER_POOL_ID  – e.g. "us-east-1_AbCdEfGhI"
 *   VITE_COGNITO_CLIENT_ID     – App Client ID (no secret)
 *   VITE_COGNITO_DOMAIN        – Hosted UI domain, e.g. "auth.example.com"
 *
 * Requirements: 8.1, 8.2
 */

import { Amplify } from "aws-amplify";

// ---------------------------------------------------------------------------
// Read Vite env vars (injected at build time via import.meta.env)
// ---------------------------------------------------------------------------

const userPoolId: string = import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "";
const userPoolClientId: string = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";
const cognitoDomain: string = import.meta.env.VITE_COGNITO_DOMAIN ?? "";

// ---------------------------------------------------------------------------
// Amplify resource config
// ---------------------------------------------------------------------------

/**
 * Configures AWS Amplify with the Cognito User Pool settings.
 * Must be called once before any `aws-amplify/auth` calls.
 */
export function configureAmplify(): void {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        loginWith: {
          oauth: {
            domain: cognitoDomain,
            scopes: ["openid", "email", "profile"],
            redirectSignIn: [window.location.origin],
            redirectSignOut: [window.location.origin],
            responseType: "code",
          },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Exported config values (useful for debugging / testing)
// ---------------------------------------------------------------------------

export const amplifyConfig = {
  userPoolId,
  userPoolClientId,
  cognitoDomain,
} as const;
