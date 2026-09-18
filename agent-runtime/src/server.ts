import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { encodeLine, toNdjsonEvents, type NdjsonEvent } from "./events.ts";
import { SharedRuntime, type SessionRequest } from "./runtime.ts";

const PORT = Number(process.env.PORT ?? 8002);
const TIMEOUT_MS = Number(process.env.CHAT_TIMEOUT_MS ?? 180_000);

interface ChatBody {
  conversation_id?: string;
  message?: string;
  messages?: unknown[];
  model?: { provider?: string; name?: string };
  thinking_level?: SessionRequest["thinkingLevel"];
}

/** Conversations with a prompt in flight. Guards the stored history from concurrent writes. */
const running = new Set<string>();

const runtime = await SharedRuntime.create();
console.log(`[agent-runtime] tools: ${runtime.listToolNames().join(", ")}`);

async function readBody(req: IncomingMessage): Promise<ChatBody> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as ChatBody;
}

async function handleChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readBody(req);
  const conversationId = body.conversation_id;
  if (!conversationId || typeof body.message !== "string") {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "conversation_id and message are required" }));
    return;
  }

  if (running.has(conversationId)) {
    res.writeHead(409, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "conversation is already processing a request" }));
    return;
  }
  running.add(conversationId);

  res.writeHead(200, {
    "Content-Type": "application/x-ndjson",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
  });
  const write = (event: NdjsonEvent): void => {
    res.write(encodeLine(event));
  };

  const { session } = await runtime.createSession({
    sessionId: conversationId,
    messages: body.messages ?? [],
    provider: body.model?.provider,
    modelName: body.model?.name,
    thinkingLevel: body.thinking_level,
  });

  const timeout = setTimeout(() => void session.abort(), TIMEOUT_MS);
  const unsubscribe = session.subscribe((event) => {
    for (const line of toNdjsonEvents(event as never)) write(line);
  });

  try {
    await session.prompt(body.message);
    write({
      type: "done",
      text: session.getLastAssistantText() ?? "",
      messages: session.messages,
    });
  } catch (error) {
    write({ type: "error", message: error instanceof Error ? error.message : String(error) });
  } finally {
    clearTimeout(timeout);
    unsubscribe();
    session.dispose();
    running.delete(conversationId);
    res.end();
  }
}

const server = createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", running: running.size }));
    return;
  }
  if (req.method === "POST" && req.url === "/chat") {
    handleChat(req, res).catch((error: unknown) => {
      console.error("[agent-runtime] request failed:", error);
      if (res.headersSent) {
        res.write(encodeLine({ type: "error", message: String(error) }));
        res.end();
      } else {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: String(error) }));
      }
    });
    return;
  }
  res.writeHead(404).end();
});

server.listen(PORT, () => console.log(`[agent-runtime] listening on :${PORT}`));
