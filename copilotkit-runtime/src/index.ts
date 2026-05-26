/**
 * BizQuery CopilotKit Runtime
 */

import * as dotenv from "dotenv";
dotenv.config();

import express, { Request, Response, NextFunction } from "express";
import cors from "cors";
import {
  BedrockAgentRuntimeClient,
  InvokeAgentCommand,
  InvokeAgentCommandInput,
} from "@aws-sdk/client-bedrock-agent-runtime";
import { cognitoAuthMiddleware, AuthenticatedRequest as AuthMiddlewareRequest } from "./middleware/auth";
import { AuthenticatedRequest } from "./types";

const PORT = parseInt(process.env.PORT ?? "3000", 10);
const BEDROCK_AGENT_ID = process.env.BEDROCK_AGENT_ID ?? "";
const BEDROCK_AGENT_ALIAS_ID = process.env.BEDROCK_AGENT_ALIAS_ID ?? "";
const AWS_REGION = process.env.AWS_REGION ?? "us-east-1";

const bedrockClient = new BedrockAgentRuntimeClient({
  region: AWS_REGION,
  ...(process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        credentials: {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
          ...(process.env.AWS_SESSION_TOKEN ? { sessionToken: process.env.AWS_SESSION_TOKEN } : {}),
        },
      }
    : {}),
});

function extractSessionId(body: Record<string, unknown>, req?: Request): string {
  if (body.variables && typeof body.variables === "object") {
    const vars = body.variables as Record<string, unknown>;
    if (vars.data && typeof vars.data === "object") {
      const data = vars.data as Record<string, unknown>;
      if (typeof data.threadId === "string" && data.threadId.trim()) {
        return data.threadId.trim().replace(/[^a-zA-Z0-9_-]/g, "-");
      }
    }
  }
  const headerSessionId = req?.headers["x-session-id"];
  if (typeof headerSessionId === "string" && headerSessionId.trim()) {
    return headerSessionId.trim().replace(/[^a-zA-Z0-9_-]/g, "-");
  }
  return `session-${Date.now()}`;
}

function extractUserMessage(body: Record<string, unknown>): string {
  let messages: unknown = undefined;
  if (body.variables && typeof body.variables === "object") {
    const vars = body.variables as Record<string, unknown>;
    if (vars.data && typeof vars.data === "object") {
      messages = (vars.data as Record<string, unknown>).messages;
    }
  }
  if (!messages) messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0) return "";

  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i] as Record<string, unknown>;
    if (msg.textMessage && typeof msg.textMessage === "object") {
      const tm = msg.textMessage as Record<string, unknown>;
      if (tm.role === "user" && typeof tm.content === "string" && tm.content.trim()) {
        return tm.content.trim();
      }
    }
    if (msg.role === "user") {
      if (typeof msg.content === "string") return msg.content;
      if (Array.isArray(msg.content)) {
        return (msg.content as Array<Record<string, unknown>>)
          .filter((p) => p.type === "text")
          .map((p) => String(p.text ?? ""))
          .join(" ");
      }
    }
  }
  return "";
}

export const app = express();

app.use(express.json({ limit: "10mb" }));

const corsOptions = {
  origin: (origin: string | undefined, callback: (err: Error | null, allow?: boolean) => void) => {
    const allowed = (process.env.FRONTEND_URL ?? "http://localhost:5173").split(",").map(u => u.trim());
    // Allow requests with no origin (e.g. curl, Postman) and whitelisted origins
    if (!origin || allowed.some(u => origin.startsWith(u))) {
      callback(null, true);
    } else {
      callback(new Error(`CORS: origin ${origin} not allowed`));
    }
  },
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization", "X-Session-Id", "x-copilotkit-runtime-client-gql-version"],
  credentials: true,
};
app.use(cors(corsOptions));
app.options("*", cors(corsOptions));

app.use((req, _res, next) => {
  console.log(`[BizQuery Runtime] [${new Date().toISOString()}] ${req.method} ${req.path}`);
  if (req.method !== "OPTIONS") {
    console.log(`[BizQuery Runtime] Auth: ${req.headers["authorization"] ? "Present" : "Missing"}`);
  }
  next();
});

app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok", service: "bizquery-copilotkit-runtime" });
});

app.post(
  "/copilotkit",
  cognitoAuthMiddleware,
  async (req: Request, res: Response): Promise<void> => {
    const authenticatedReq = req as AuthMiddlewareRequest;
    const jwtToken = authenticatedReq.auth?.jwtToken ?? (req as AuthenticatedRequest).jwtToken ?? "";
    const userId = authenticatedReq.auth?.userId ?? "unknown";
    const userRole = authenticatedReq.auth?.userRole ?? "employee";
    const body = req.body as Record<string, unknown>;
    const operationName = body.operationName as string | undefined;

    console.log(`[BizQuery Runtime] Operation: ${operationName} userId: ${userId} role: ${userRole}`);

    if (operationName === "availableAgents") {
      res.json({
        data: {
          availableAgents: {
            agents: [],
            __typename: "AvailableAgents",
          },
        },
      });
      return;
    }

    if (operationName === "generateCopilotResponse") {
      const sessionId = extractSessionId(body, req);
      const userMessage = extractUserMessage(body);

      console.log(`[BizQuery Runtime] sessionId: ${sessionId} message: "${userMessage}"`);

      if (!userMessage) {
        res.status(400).json({ errors: [{ message: "No user message found." }] });
        return;
      }

      if (!BEDROCK_AGENT_ID || !BEDROCK_AGENT_ALIAS_ID) {
        res.status(503).json({ errors: [{ message: "Bedrock agent not configured." }] });
        return;
      }

      const boundary = "graphql";
      res.setHeader("Content-Type", `multipart/mixed; boundary="${boundary}"`);
      res.setHeader("Transfer-Encoding", "chunked");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");

      const threadId = sessionId;
      const messageId = `msg-${Date.now()}`;

      let fullText = "";

      try {
        const input: InvokeAgentCommandInput = {
          agentId: BEDROCK_AGENT_ID,
          agentAliasId: BEDROCK_AGENT_ALIAS_ID,
          sessionId,
          inputText: userMessage,
          sessionState: {
            sessionAttributes: {
              jwt_token: jwtToken,
              user_id: userId,
              user_role: userRole,
            },
          },
        };

        const command = new InvokeAgentCommand(input);
        const response = await bedrockClient.send(command);

        if (response.completion) {
          for await (const event of response.completion) {
            if (event.chunk?.bytes) {
              fullText += new TextDecoder().decode(event.chunk.bytes);
            }
          }
        }
      } catch (error) {
        const err = error as Error;
        console.error("[BizQuery Runtime] Bedrock error:", err.message);
        fullText = "Lo siento, ocurrió un error al procesar tu consulta. Por favor intenta de nuevo.";
      }

      const part = JSON.stringify({
        data: {
          generateCopilotResponse: {
            threadId,
            runId: `run-${Date.now()}`,
            extensions: null,
            status: { code: "SUCCESS", __typename: "BaseResponseStatus" },
            messages: [
              {
                id: messageId,
                createdAt: new Date().toISOString(),
                role: "assistant",
                content: [fullText],
                parentMessageId: null,
                __typename: "TextMessageOutput",
                status: { code: "SUCCESS", __typename: "SuccessMessageStatus" },
              },
            ],
            metaEvents: [],
            __typename: "CopilotResponse",
          },
        },
        hasNext: false,
      });

      res.write(`\r\n--${boundary}\r\nContent-Type: application/json\r\n\r\n${part}\r\n`);
      res.write(`\r\n--${boundary}--\r\n`);
      res.end();

      console.log(`[BizQuery Runtime] Response sent. Length: ${fullText.length}`);
      return;
    }

    res.status(400).json({ errors: [{ message: `Unknown operation: ${operationName}` }] });
  }
);

app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error("[BizQuery Runtime] Unhandled error:", err.message);
  res.status(500).json({ error: "Internal Server Error" });
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`[BizQuery Runtime] Server listening on http://localhost:${PORT}`);
    console.log(`[BizQuery Runtime] CopilotKit endpoint: POST http://localhost:${PORT}/copilotkit`);
    console.log(`[BizQuery Runtime] Bedrock Agent ID: ${BEDROCK_AGENT_ID || "(not set)"}`);
    console.log(`[BizQuery Runtime] Bedrock Agent Alias ID: ${BEDROCK_AGENT_ALIAS_ID || "(not set)"}`);
    console.log(`[BizQuery Runtime] AWS Region: ${AWS_REGION}`);
  });
}
