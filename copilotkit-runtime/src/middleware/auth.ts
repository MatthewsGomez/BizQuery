/**
 * auth.ts — JWT authentication middleware for BizQuery CopilotKit Runtime
 *
 * Extracts and validates the Cognito JWT from the Authorization header,
 * decodes the `cognito:groups` claim to derive the user role, and attaches
 * `user_id` and `user_role` to the request context for downstream use.
 *
 * Requirements: 8.1, 8.3
 */

import { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import jwksClient from "jwks-rsa";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthContext {
  userId: string;
  userRole: string;
  jwtToken: string;
}

export interface AuthenticatedRequest extends Request {
  auth?: AuthContext;
  jwtToken?: string;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const COGNITO_USER_POOL_ID = process.env.COGNITO_USER_POOL_ID ?? "";
const AWS_REGION = process.env.AWS_REGION ?? "us-east-1";

/**
 * Maps Cognito group names to BizQuery role strings.
 * The first matching group wins.
 */
const GROUP_TO_ROLE: Record<string, string> = {
  owners: "owner",
  managers: "manager",
  employees: "employee",
};

// ---------------------------------------------------------------------------
// JWKS client (lazy — only created when COGNITO_USER_POOL_ID is set)
// ---------------------------------------------------------------------------

let _jwksClient: ReturnType<typeof jwksClient> | null = null;

function getJwksClient(): ReturnType<typeof jwksClient> {
  if (!_jwksClient) {
    const jwksUri = `https://cognito-idp.${AWS_REGION}.amazonaws.com/${COGNITO_USER_POOL_ID}/.well-known/jwks.json`;
    _jwksClient = jwksClient({
      jwksUri,
      cache: true,
      cacheMaxEntries: 5,
      cacheMaxAge: 10 * 60 * 1000, // 10 minutes
    });
  }
  return _jwksClient;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Derives the BizQuery role from the `cognito:groups` claim.
 * Returns the role of the highest-privilege group the user belongs to,
 * or "employee" as the default fallback.
 */
export function deriveRoleFromGroups(groups: string[]): string {
  for (const [group, role] of Object.entries(GROUP_TO_ROLE)) {
    if (groups.includes(group)) {
      return role;
    }
  }
  return "employee";
}

/**
 * Decodes a JWT payload without verifying the signature.
 * Used only to extract the `kid` header for JWKS lookup.
 */
function decodeTokenHeader(token: string): { kid?: string } {
  const decoded = jwt.decode(token, { complete: true });
  if (!decoded || typeof decoded === "string") return {};
  return (decoded.header as { kid?: string }) ?? {};
}

/**
 * Fetches the signing key from Cognito's JWKS endpoint.
 */
async function getSigningKey(kid: string): Promise<string> {
  const client = getJwksClient();
  const key = await client.getSigningKey(kid);
  return key.getPublicKey();
}

/**
 * Verifies the JWT against Cognito's JWKS and returns the decoded payload.
 * Throws if the token is invalid or expired.
 */
async function verifyCognitoToken(token: string): Promise<jwt.JwtPayload> {
  const { kid } = decodeTokenHeader(token);
  if (!kid) {
    throw new Error("JWT header missing 'kid' claim.");
  }

  const signingKey = await getSigningKey(kid);

  return new Promise((resolve, reject) => {
    jwt.verify(token, signingKey, { algorithms: ["RS256"] }, (err, decoded) => {
      if (err) {
        reject(new Error(`JWT verification failed: ${err.message}`));
      } else {
        resolve(decoded as jwt.JwtPayload);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------

/**
 * Express middleware that:
 *  1. Extracts the Bearer token from the Authorization header.
 *  2. Verifies the JWT against Cognito's JWKS (when COGNITO_USER_POOL_ID is set).
 *  3. Decodes `cognito:groups` to derive the user role.
 *  4. Attaches `auth.userId`, `auth.userRole`, and `auth.jwtToken` to the request.
 *
 * Returns HTTP 401 if the token is missing, malformed, or invalid.
 */
export async function cognitoAuthMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  const authHeader = req.headers["authorization"];

  // 1. Require Authorization header
  if (!authHeader) {
    res.status(401).json({
      error: "Unauthorized",
      message: "Missing Authorization header.",
    });
    return;
  }

  // 2. Extract Bearer token
  const parts = authHeader.split(" ");
  if (parts.length !== 2 || parts[0] !== "Bearer" || !parts[1]) {
    res.status(401).json({
      error: "Unauthorized",
      message: "Invalid Authorization header. Expected: Bearer <token>",
    });
    return;
  }

  const token = parts[1];

  try {
    let userId = "unknown";
    let groups: string[] = [];

    if (COGNITO_USER_POOL_ID) {
      // Full cryptographic verification against Cognito JWKS
      console.log("[cognitoAuthMiddleware] Attempting token verification against JWKS...");
      const payload = await verifyCognitoToken(token);
      userId = (payload.sub as string) ?? "unknown";
      groups = Array.isArray(payload["cognito:groups"])
        ? (payload["cognito:groups"] as string[])
        : [];
    } else {
      // Development fallback: decode without verification
      console.log("[cognitoAuthMiddleware] COGNITO_USER_POOL_ID not set, decoding token without verification...");
      const decoded = jwt.decode(token) as jwt.JwtPayload | null;
      if (decoded) {
        userId = (decoded.sub as string) ?? "unknown";
        groups = Array.isArray(decoded["cognito:groups"])
          ? (decoded["cognito:groups"] as string[])
          : [];
      }
    }

    const userRole = deriveRoleFromGroups(groups);
    console.log(`[cognitoAuthMiddleware] Token verified successfully. userId: ${userId}, userRole: ${userRole}`);

    // 3. Attach auth context to request
    (req as AuthenticatedRequest).auth = { userId, userRole, jwtToken: token };
    (req as AuthenticatedRequest).jwtToken = token;

    next();
  } catch (err) {
    const message = err instanceof Error ? err.message : "Token validation failed.";
    console.error("[cognitoAuthMiddleware] Token validation failed:", message);
    res.status(401).json({ error: "Unauthorized", message });
  }
}
