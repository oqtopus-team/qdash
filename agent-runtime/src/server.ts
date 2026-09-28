import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { randomUUID } from "node:crypto";

import { encodeLine, toNdjsonEvents, type NdjsonEvent } from "./events.ts";
import { SharedRuntime, type SessionRequest } from "./runtime.ts";

const PORT = Number(process.env.PORT ?? 8002);
const TIMEOUT_MS = Number(process.env.CHAT_TIMEOUT_MS ?? 180_000);
const REVIEW_TIMEOUT_MS = Number(process.env.REVIEW_TIMEOUT_MS ?? 300_000);
const REVIEW_CONCURRENCY = Number(process.env.REVIEW_CONCURRENCY ?? 2);

interface ImageBody {
  data: string;
  mimeType: string;
}

interface ChatBody {
  conversation_id?: string;
  message?: string;
  messages?: unknown[];
  model?: { provider?: string; name?: string };
  thinking_level?: SessionRequest["thinkingLevel"];
  images?: ImageBody[];
}

interface ReviewBody {
  prompt?: string;
  images?: ImageBody[];
  model?: { provider?: string; name?: string };
}

/** Pi's prompt() image attachments, from the wire shape both endpoints use. */
function toImageContent(images: ImageBody[] | undefined) {
  return (images ?? []).map((image) => ({
    type: "image" as const,
    data: image.data,
    mimeType: image.mimeType,
  }));
}

/** Conversations with a prompt in flight. Guards the stored history from concurrent writes. */
const running = new Set<string>();

/**
 * Caps how many reviews hit the model at once.
 *
 * Reviews arrive from two Python thread pools that do not know about each other,
 * and they all land on one local VLM. Callers wait instead of being rejected.
 * See .agents/sessions/2026-09-28-ai-review-pi-agent/adr/0004-*.md
 */
const reviewQueue: (() => void)[] = [];
let reviewsInFlight = 0;

async function acquireReviewSlot(): Promise<() => void> {
  if (reviewsInFlight >= REVIEW_CONCURRENCY) {
    await new Promise<void>((resolve) => reviewQueue.push(resolve));
  }
  reviewsInFlight++;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    reviewsInFlight--;
    reviewQueue.shift()?.();
  };
}

const runtime = await SharedRuntime.create();
console.log(`[agent-runtime] tools: ${runtime.listToolNames().join(", ")}`);

async function readBody<T>(req: IncomingMessage): Promise<T> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as T;
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

/**
 * Run one AI review and return the verdict as a single JSON response.
 *
 * Unlike /chat this does not stream: the caller only ever uses the finished
 * verdict, and the Python side turns it into the stored markdown note.
 */
async function handleReview(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readBody<ReviewBody>(req);
  if (typeof body.prompt !== "string" || !body.prompt) {
    sendJson(res, 400, { error: "prompt is required" });
    return;
  }

  const release = await acquireReviewSlot();
  try {
    let session;
    try {
      ({ session } = await runtime.createReviewSession({
        sessionId: randomUUID(),
        provider: body.model?.provider,
        modelName: body.model?.name,
      }));
    } catch (error) {
      sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
      return;
    }

    let review: unknown;
    const unsubscribe = session.subscribe((event) => {
      const settled = event as { type: string; result?: { details?: { review?: unknown } } };
      if (settled.type === "tool_execution_end" && settled.result?.details?.review) {
        review = settled.result.details.review;
      }
    });
    const timeout = setTimeout(() => void session.abort(), REVIEW_TIMEOUT_MS);

    try {
      await session.prompt(body.prompt, { images: toImageContent(body.images) });
      if (review) {
        sendJson(res, 200, { review });
      } else {
        sendJson(res, 200, {
          error: session.state.errorMessage ?? "submit_review was not called",
          text: session.getLastAssistantText() ?? "",
        });
      }
    } finally {
      clearTimeout(timeout);
      unsubscribe();
      session.dispose();
    }
  } finally {
    release();
  }
}

async function handleChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readBody<ChatBody>(req);
  const conversationId = body.conversation_id;
  if (!conversationId || typeof body.message !== "string") {
    sendJson(res, 400, { error: "conversation_id and message are required" });
    return;
  }

  if (running.has(conversationId)) {
    sendJson(res, 409, { error: "conversation is already processing a request" });
    return;
  }
  running.add(conversationId);

  // Created before writeHead: unknown models throw here, and once NDJSON starts
  // flowing an HTTP status can no longer be set.
  let session;
  try {
    ({ session } = await runtime.createSession({
      sessionId: conversationId,
      messages: body.messages ?? [],
      provider: body.model?.provider,
      modelName: body.model?.name,
      thinkingLevel: body.thinking_level,
    }));
  } catch (error) {
    running.delete(conversationId);
    sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
    return;
  }

  res.writeHead(200, {
    "Content-Type": "application/x-ndjson",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
  });
  const write = (event: NdjsonEvent): void => {
    res.write(encodeLine(event));
  };

  const timeout = setTimeout(() => void session.abort(), TIMEOUT_MS);
  const unsubscribe = session.subscribe((event) => {
    for (const line of toNdjsonEvents(event as never)) write(line);
  });

  try {
    await session.prompt(body.message, { images: toImageContent(body.images) });
    const text = session.getLastAssistantText() ?? "";
    // A failed turn resolves normally with an empty assistant message, so
    // without this the caller renders a blank reply and no error anywhere.
    if (!text && session.state.errorMessage) {
      write({ type: "error", message: session.state.errorMessage });
    } else {
      write({ type: "done", text, messages: session.messages });
    }
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
    sendJson(res, 200, { status: "ok", running: running.size, reviews: reviewsInFlight });
    return;
  }
  if (req.method === "POST" && req.url === "/chat") {
    handleChat(req, res).catch((error: unknown) => {
      console.error("[agent-runtime] request failed:", error);
      if (res.headersSent) {
        res.write(encodeLine({ type: "error", message: String(error) }));
        res.end();
      } else {
        sendJson(res, 500, { error: String(error) });
      }
    });
    return;
  }
  if (req.method === "POST" && req.url === "/review") {
    handleReview(req, res).catch((error: unknown) => {
      console.error("[agent-runtime] review failed:", error);
      if (!res.headersSent) sendJson(res, 500, { error: String(error) });
    });
    return;
  }
  res.writeHead(404).end();
});

server.listen(PORT, () => console.log(`[agent-runtime] listening on :${PORT}`));
