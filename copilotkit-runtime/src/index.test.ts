/**
 * Property-Based Tests: CopilotKit Runtime — Authentication
 *
 * Property 17: Universal rejection of unauthenticated requests
 * Validates: Requirement 8.1
 *
 * For ANY request to the CopilotKit Runtime that does not include a valid
 * JWT token, the system MUST return HTTP 401 and MUST NOT execute any data
 * query.
 *
 * Strategy:
 *  - We test the `requireBearerToken` middleware directly via supertest
 *    against the Express app exported from index.ts.
 *  - We generate a wide variety of invalid / missing Authorization headers
 *    and verify that every single one is rejected with 401.
 *  - We also verify that a structurally valid Bearer token is accepted (200
 *    or 400/503 — anything other than 401), confirming the middleware does
 *    not over-reject.
 *
 * Note: Full cryptographic JWT verification against Cognito JWKS is
 * implemented in task 13.1. Here we test the structural validation layer
 * (presence and format of the Bearer token) as specified in Requirement 8.1.
 */

// Mock the AWS SDK to prevent network calls during tests
jest.mock("@aws-sdk/client-bedrock-agent-runtime", () => ({
  BedrockAgentRuntimeClient: jest.fn().mockImplementation(() => ({
    send: jest.fn().mockResolvedValue({
      completion: (async function* () {
        yield { chunk: { bytes: new TextEncoder().encode("test response") } };
      })(),
    }),
  })),
  InvokeAgentCommand: jest.fn().mockImplementation((input) => input),
}));

import request from "supertest";
import { app } from "./index";

// Set a reasonable timeout for all tests
jest.setTimeout(10000);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generates a random alphanumeric string of the given length. */
function randomString(length: number): string {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let result = "";
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/** Generates a random integer in [min, max]. */
function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Generates a structurally valid (but not cryptographically signed) JWT-like
 * token string: three base64url segments separated by dots.
 */
function fakeJwtToken(): string {
  const header = Buffer.from(
    JSON.stringify({ alg: "RS256", typ: "JWT" })
  ).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({
      sub: randomString(36),
      iss: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test",
      exp: Math.floor(Date.now() / 1000) + 3600,
    })
  ).toString("base64url");
  const signature = randomString(43); // fake signature
  return `${header}.${payload}.${signature}`;
}

// ---------------------------------------------------------------------------
// Corpus of invalid Authorization header values
// ---------------------------------------------------------------------------

/**
 * Returns an array of invalid Authorization header values that should all
 * trigger a 401 response.
 */
function buildInvalidAuthHeaders(): Array<string | undefined> {
  return [
    // Completely absent (represented as undefined — we omit the header)
    undefined,
    // Empty string
    "",
    // Whitespace only
    "   ",
    // Wrong scheme
    "Basic dXNlcjpwYXNz",
    "Token sometoken",
    "bearer", // scheme only, no token
    "BEARER", // uppercase scheme only
    // Bearer with empty token
    "Bearer ",
    "Bearer  ",
    // Bearer with whitespace token
    "Bearer    ",
    // Malformed: no space between scheme and token
    "Bearertoken123",
    // Multiple spaces
    "Bearer  token  extra",
    // Null-like strings
    "null",
    "undefined",
    // Only the word Bearer repeated
    "Bearer Bearer",
    // Non-ASCII characters
    "Bearer tëst",
    // Very short token (1 char)
    "Bearer x",
    // Scheme in wrong case with valid-looking token
    "bearer " + fakeJwtToken(),
    "BEARER " + fakeJwtToken(),
    // Extra prefix
    "X-Bearer " + fakeJwtToken(),
  ];
}

// ---------------------------------------------------------------------------
// Property 17: Universal rejection of unauthenticated requests
// ---------------------------------------------------------------------------

describe("Property 17: Universal rejection of unauthenticated requests", () => {
  /**
   * Core property: every request without a valid Bearer token MUST receive
   * HTTP 401. We test this against the POST /copilotkit endpoint.
   *
   * Validates: Requirement 8.1
   */
  describe("POST /copilotkit — rejects all invalid/missing Authorization headers", () => {
    const invalidHeaders = buildInvalidAuthHeaders();

    test.each(
      invalidHeaders.map((h, i) => [
        h === undefined ? "(no Authorization header)" : JSON.stringify(h),
        h,
        i,
      ])
    )(
      "returns 401 for Authorization: %s",
      async (_label: string, headerValue: string | undefined, _idx: number) => {
        const req = request(app)
          .post("/copilotkit")
          .send({ messages: [{ role: "user", content: "test" }] });

        if (headerValue !== undefined) {
          req.set("Authorization", headerValue);
        }

        const response = await req;

        expect(response.status).toBe(401);
        expect(response.body).toHaveProperty("error", "Unauthorized");
      }
    );
  });

  /**
   * Randomised sub-property: generate N random strings that are NOT valid
   * Bearer tokens and verify each one is rejected.
   *
   * This covers the "for any" quantifier of Property 17 by sampling the
   * space of possible invalid inputs.
   *
   * Validates: Requirement 8.1
   */
  test("rejects 50 randomly generated invalid Authorization headers", async () => {
    const iterations = 50;

    for (let i = 0; i < iterations; i++) {
      // Generate a random string that is NOT a valid "Bearer <token>" header
      const invalidHeader = randomString(randomInt(0, 30));

      const response = await request(app)
        .post("/copilotkit")
        .set("Authorization", invalidHeader)
        .send({ messages: [{ role: "user", content: "test" }] });

      expect(response.status).toBe(401);
      expect(response.body).toHaveProperty("error", "Unauthorized");
    }
  });

  /**
   * Inverse property: a structurally valid Bearer token MUST NOT be rejected
   * with 401 by the authentication middleware. The request may fail for other
   * reasons (missing Bedrock config, missing message body, etc.) but the
   * middleware itself must pass it through.
   *
   * Validates: Requirement 8.1 (the middleware must not over-reject)
   */
  test("accepts a structurally valid Bearer token (does not return 401)", async () => {
    const validToken = fakeJwtToken();

    const response = await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${validToken}`)
      .send({
        messages: [{ role: "user", content: "¿Cuáles son las ventas de hoy?" }],
        session_id: "test-session-001",
      });

    // The middleware should pass the request through.
    // The response may be 400 (bad request), 503 (Bedrock not configured),
    // or even 200 — but it MUST NOT be 401.
    expect(response.status).not.toBe(401);
  });

  /**
   * Randomised inverse property: generate N valid-looking Bearer tokens and
   * verify none of them are rejected by the auth middleware with 401.
   *
   * Validates: Requirement 8.1
   */
  test("accepts 20 randomly generated valid-looking Bearer tokens", async () => {
    const iterations = 20;

    for (let i = 0; i < iterations; i++) {
      const token = fakeJwtToken();

      const response = await request(app)
        .post("/copilotkit")
        .set("Authorization", `Bearer ${token}`)
        .send({
          messages: [{ role: "user", content: "test query" }],
          session_id: `session-${i}`,
        });

      expect(response.status).not.toBe(401);
    }
  });
});

// ---------------------------------------------------------------------------
// Additional unit tests for the requireBearerToken middleware
// ---------------------------------------------------------------------------

describe("requireBearerToken middleware — unit tests", () => {
  test("returns 401 with descriptive message when Authorization header is missing", async () => {
    const response = await request(app)
      .post("/copilotkit")
      .send({ messages: [] });

    expect(response.status).toBe(401);
    expect(response.body.message).toMatch(/Missing Authorization header/i);
  });

  test("returns 401 with descriptive message for wrong scheme (Basic)", async () => {
    const response = await request(app)
      .post("/copilotkit")
      .set("Authorization", "Basic dXNlcjpwYXNz")
      .send({ messages: [] });

    expect(response.status).toBe(401);
    expect(response.body.message).toMatch(/Invalid Authorization header format/i);
  });

  test("returns 401 with descriptive message for empty Bearer token", async () => {
    const response = await request(app)
      .post("/copilotkit")
      .set("Authorization", "Bearer ")
      .send({ messages: [] });

    expect(response.status).toBe(401);
  });

  test("health endpoint does not require authentication", async () => {
    const response = await request(app).get("/health");

    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty("status", "ok");
  });
});
