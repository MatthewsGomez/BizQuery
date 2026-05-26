/**
 * Integration Tests — BizQuery CopilotKit Runtime
 *
 * Verifies the end-to-end flow:
 *   autenticación → consulta → invocación de herramienta → respuesta en streaming
 *
 * Uses mocks for:
 *   - Bedrock AgentCore Runtime (BedrockAgentRuntimeClient)
 *   - Cognito JWKS (jwks-rsa) — skipped via COGNITO_USER_POOL_ID unset
 *
 * Requirements: 8.1, 8.2, 8.3
 */

// ---------------------------------------------------------------------------
// Mock AWS SDK before any imports
// ---------------------------------------------------------------------------

const mockSend = jest.fn();

jest.mock("@aws-sdk/client-bedrock-agent-runtime", () => ({
  BedrockAgentRuntimeClient: jest.fn().mockImplementation(() => ({
    send: mockSend,
  })),
  InvokeAgentCommand: jest.fn().mockImplementation((input) => ({ ...input, _type: "InvokeAgentCommand" })),
}));

// Mock jwks-rsa so no network calls are made
jest.mock("jwks-rsa", () =>
  jest.fn().mockReturnValue({
    getSigningKey: jest.fn().mockResolvedValue({
      getPublicKey: () => "mock-public-key",
    }),
  })
);

import request from "supertest";
import { app } from "./index";
import { InvokeAgentCommand } from "@aws-sdk/client-bedrock-agent-runtime";

jest.setTimeout(15000);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Creates a fake structurally-valid JWT with optional payload claims */
function makeFakeJwt(payload: Record<string, unknown> = {}): string {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", typ: "JWT", kid: "test-kid" })).toString("base64url");
  const body = Buffer.from(JSON.stringify({
    sub: "user-123",
    exp: Math.floor(Date.now() / 1000) + 3600,
    "cognito:groups": ["owners"],
    ...payload,
  })).toString("base64url");
  const sig = Buffer.from("fakesignature").toString("base64url");
  return `${header}.${body}.${sig}`;
}

/** Creates a mock Bedrock streaming response with the given text chunks */
function mockBedrockResponse(chunks: string[]) {
  async function* generator() {
    for (const chunk of chunks) {
      yield { chunk: { bytes: new TextEncoder().encode(chunk) } };
    }
  }
  mockSend.mockResolvedValueOnce({ completion: generator() });
}

// ---------------------------------------------------------------------------
// Test: Authentication flow
// ---------------------------------------------------------------------------

describe("Integration: Authentication flow", () => {
  test("rejects request without Authorization header with 401", async () => {
    const res = await request(app)
      .post("/copilotkit")
      .send({ messages: [{ role: "user", content: "test" }] });

    expect(res.status).toBe(401);
    expect(res.body.error).toBe("Unauthorized");
  });

  test("rejects request with invalid token format with 401", async () => {
    const res = await request(app)
      .post("/copilotkit")
      .set("Authorization", "Bearer not-a-jwt")
      .send({ messages: [{ role: "user", content: "test" }] });

    expect(res.status).toBe(401);
  });

  test("accepts request with valid Bearer JWT (passes auth middleware)", async () => {
    mockBedrockResponse(["Hola, soy BizQuery"]);
    process.env.BEDROCK_AGENT_ID = "test-agent-id";
    process.env.BEDROCK_AGENT_ALIAS_ID = "test-alias-id";

    const res = await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({
        messages: [{ role: "user", content: "¿Cuáles son las ventas?" }],
        session_id: "integration-session-001",
      });

    // Auth passed — response is not 401
    expect(res.status).not.toBe(401);

    delete process.env.BEDROCK_AGENT_ID;
    delete process.env.BEDROCK_AGENT_ALIAS_ID;
  });
});

// ---------------------------------------------------------------------------
// Test: Query → tool invocation → streaming response
// ---------------------------------------------------------------------------

describe("Integration: Query → Bedrock invocation → streaming response", () => {
  beforeEach(() => {
    process.env.BEDROCK_AGENT_ID = "agent-abc123";
    process.env.BEDROCK_AGENT_ALIAS_ID = "alias-xyz789";
  });

  afterEach(() => {
    delete process.env.BEDROCK_AGENT_ID;
    delete process.env.BEDROCK_AGENT_ALIAS_ID;
    mockSend.mockReset();
  });

  test("invokes Bedrock agent with correct agentId and aliasId", async () => {
    mockBedrockResponse(["Las ventas del Q1 fueron $50,000"]);

    await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({
        messages: [{ role: "user", content: "¿Cuáles son las ventas del Q1?" }],
        session_id: "session-001",
      });

    expect(mockSend).toHaveBeenCalledTimes(1);
    const callArg = mockSend.mock.calls[0][0] as Record<string, unknown>;
    expect(callArg.agentId).toBe("agent-abc123");
    expect(callArg.agentAliasId).toBe("alias-xyz789");
  });

  test("propagates session_id to Bedrock sessionState", async () => {
    mockBedrockResponse(["respuesta"]);

    await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({
        messages: [{ role: "user", content: "consulta" }],
        session_id: "my-session-42",
      });

    const callArg = mockSend.mock.calls[0][0] as Record<string, unknown>;
    expect(callArg.sessionId).toBe("my-session-42");
    const attrs = (callArg.sessionState as Record<string, unknown>)?.sessionAttributes as Record<string, string>;
    expect(attrs.session_id).toBe("my-session-42");
  });

  test("propagates user_id and user_role to Bedrock sessionState", async () => {
    mockBedrockResponse(["respuesta"]);

    const token = makeFakeJwt({ sub: "user-abc", "cognito:groups": ["owners"] });

    await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${token}`)
      .send({
        messages: [{ role: "user", content: "consulta financiera" }],
        session_id: "session-role-test",
      });

    const callArg = mockSend.mock.calls[0][0] as Record<string, unknown>;
    const attrs = (callArg.sessionState as Record<string, unknown>)?.sessionAttributes as Record<string, string>;

    // user_id and user_role must be propagated
    expect(attrs).toHaveProperty("user_id");
    expect(attrs).toHaveProperty("user_role");
  });

  test("streams SSE response back to client", async () => {
    mockBedrockResponse(["Las ventas ", "fueron $50,000"]);

    const res = await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({
        messages: [{ role: "user", content: "ventas" }],
        session_id: "sse-session",
      });

    expect(res.headers["content-type"]).toMatch(/text\/event-stream/);
    expect(res.text).toContain("data:");
    expect(res.text).toContain("[DONE]");
  });

  test("returns 400 when no user message is found in the body", async () => {
    const res = await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({ messages: [], session_id: "empty-session" });

    expect(res.status).toBe(400);
    expect(res.body.error).toBe("Bad Request");
  });

  test("returns 503 when Bedrock agent is not configured", async () => {
    delete process.env.BEDROCK_AGENT_ID;
    delete process.env.BEDROCK_AGENT_ALIAS_ID;

    const res = await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({
        messages: [{ role: "user", content: "consulta" }],
        session_id: "no-agent-session",
      });

    expect(res.status).toBe(503);
  });

  test("handles Bedrock error gracefully and sends SSE error event", async () => {
    mockSend.mockRejectedValueOnce(new Error("Bedrock timeout"));
    process.env.BEDROCK_AGENT_ID = "agent-abc123";
    process.env.BEDROCK_AGENT_ALIAS_ID = "alias-xyz789";

    const res = await request(app)
      .post("/copilotkit")
      .set("Authorization", `Bearer ${makeFakeJwt()}`)
      .send({
        messages: [{ role: "user", content: "consulta" }],
        session_id: "error-session",
      });

    expect(res.headers["content-type"]).toMatch(/text\/event-stream/);
    expect(res.text).toContain("error");
    expect(res.text).toContain("[DONE]");
  });
});

// ---------------------------------------------------------------------------
// Test: Health endpoint
// ---------------------------------------------------------------------------

describe("Integration: Health endpoint", () => {
  test("GET /health returns 200 without authentication", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("ok");
  });
});
