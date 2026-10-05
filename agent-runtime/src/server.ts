import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { UserEntry, watchEvents, type AgentEvent } from "@earendil-works/pi-durable";

import { encodeLine, toNdjsonEvents, type NdjsonEvent } from "./events.ts";
import { hasBearerToken, readJsonBody, RequestError } from "./http.ts";
import {
  answerText,
  BACKGROUND_CONTEXT,
  SharedRuntime,
  type SessionRequest,
} from "./runtime.ts";

const PORT = Number(process.env.PORT ?? 8002);
const CHAT_TIMEOUT_MS = Number(process.env.CHAT_TIMEOUT_MS ?? 180_000);
const REVIEW_CONCURRENCY = Number(process.env.REVIEW_CONCURRENCY ?? 2);
const REVIEW_QUEUE_TIMEOUT_MS = Number(process.env.REVIEW_QUEUE_TIMEOUT_MS ?? 30_000);
const MAX_BODY_BYTES = Number(process.env.MAX_REQUEST_BODY_BYTES ?? 20 * 1024 * 1024);
const RUNTIME_TOKEN = process.env.AGENT_RUNTIME_TOKEN;

interface ImageBody {
  data: string;
  mimeType: string;
}

interface ChatBody {
  owner_id?: string;
  conversation_id?: string;
  request_id?: string;
  message?: string;
  initial_message?: string;
  model?: { provider?: string; name?: string };
  thinking_level?: SessionRequest["thinkingLevel"];
  images?: ImageBody[];
}

interface ReviewBody {
  prompt?: string;
  images?: ImageBody[];
  model?: { provider?: string; name?: string };
}

interface DeleteSessionBody {
  owner_id?: string;
  conversation_id?: string;
}

/** Convert wire images into Pi image-content blocks. */
function toImageContent(images: ImageBody[] | undefined) {
  return (images ?? []).map((image) => ({
    type: "image" as const,
    data: image.data,
    mimeType: image.mimeType,
  }));
}

/** One active writer per user/session storage file. */
const running = new Set<string>();

/** Bound local-model review concurrency across API and worker callers. */
const reviewQueue: Array<() => void> = [];
let reviewsInFlight = 0;

/** Wait for a review slot, rejecting before the caller's HTTP timeout. */
async function acquireReviewSlot(): Promise<() => void> {
  if (reviewsInFlight >= REVIEW_CONCURRENCY) {
    await new Promise<void>((resolve, reject) => {
      const resume = (): void => {
        clearTimeout(timeout);
        resolve();
      };
      const timeout = setTimeout(() => {
        const index = reviewQueue.indexOf(resume);
        if (index >= 0) reviewQueue.splice(index, 1);
        reject(new RequestError(503, "review queue is busy; retry later"));
      }, REVIEW_QUEUE_TIMEOUT_MS);
      reviewQueue.push(resume);
    });
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

/** Send one JSON response. */
function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

/** Run one automatic review and return its structured verdict. */
async function handleReview(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<ReviewBody>(req, MAX_BODY_BYTES);
  if (typeof body.prompt !== "string" || !body.prompt) {
    sendJson(res, 400, { error: "prompt is required" });
    return;
  }

  const release = await acquireReviewSlot();
  try {
    const result = await runtime.runReview({
      prompt: body.prompt,
      provider: body.model?.provider,
      modelName: body.model?.name,
      images: toImageContent(body.images),
    });
    if (result.review) {
      sendJson(res, 200, { review: result.review });
    } else {
      sendJson(res, 200, { error: "submit_review was not called", text: result.text });
    }
  } finally {
    release();
  }
}

/** Translate one committed durable event to the existing NDJSON bridge. */
function writeAgentEvent(event: AgentEvent, write: (event: NdjsonEvent) => void): void {
  for (const line of toNdjsonEvents(event)) write(line);
}

/** Open or recover a durable conversation and wait for one idempotent input. */
async function handleChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<ChatBody>(req, MAX_BODY_BYTES);
  const ownerId = body.owner_id;
  const conversationId = body.conversation_id;
  if (!ownerId || !conversationId || typeof body.message !== "string") {
    sendJson(res, 400, { error: "owner_id, conversation_id and message are required" });
    return;
  }

  const runKey = `${ownerId}\0${conversationId}`;
  if (running.has(runKey)) {
    sendJson(res, 409, { error: "conversation is already processing a request" });
    return;
  }
  running.add(runKey);

  let opened;
  try {
    opened = await runtime.openSession({
      ownerId,
      sessionId: conversationId,
      requestId: body.request_id,
      message: body.message,
      provider: body.model?.provider,
      modelName: body.model?.name,
      thinkingLevel: body.thinking_level,
      images: toImageContent(body.images),
    });
  } catch (error) {
    running.delete(runKey);
    sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
    return;
  }

  const { harness, conversation } = opened;
  res.writeHead(200, {
    "Content-Type": "application/x-ndjson",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
  });
  let connected = true;
  res.on("close", () => {
    // A dropped browser connection does not cancel durable work. Retrying with
    // the same request_id recovers the committed answer instead of paying for
    // a second model turn.
    connected = false;
  });
  const write = (event: NdjsonEvent): void => {
    if (connected && !res.writableEnded) res.write(encodeLine(event));
  };

  const events = await watchEvents(harness, conversation.id, BACKGROUND_CONTEXT);
  events.start(async (batch) => {
    for (const event of batch) writeAgentEvent(event, write);
  });

  try {
    const view = await conversation.context(BACKGROUND_CONTEXT);
    const isNew = !view.entries.some((entry) => UserEntry.is(entry));
    const message = isNew && body.initial_message ? body.initial_message : body.message;
    const images = isNew ? toImageContent(body.images) : [];
    const content = images.length
      ? [{ type: "text" as const, text: message }, ...images]
      : message;
    const submission = await conversation.submit(
      {
        type: "input",
        content,
        ...(body.request_id ? { requestId: body.request_id } : {}),
      },
      BACKGROUND_CONTEXT,
    );
    const timeout = setTimeout(
      () => void conversation.abort(BACKGROUND_CONTEXT),
      CHAT_TIMEOUT_MS,
    );
    const settled = await submission.wait(BACKGROUND_CONTEXT).finally(() => clearTimeout(timeout));
    await events.stop();
    if (settled.status === "done" && settled.type === "input") {
      write({ type: "done", text: await answerText(conversation, settled.answer) });
    } else {
      write({ type: "error", message: `conversation was not answered: ${settled.reason}` });
    }
  } catch (error) {
    write({ type: "error", message: error instanceof Error ? error.message : String(error) });
  } finally {
    await events.stop();
    await harness.close(BACKGROUND_CONTEXT);
    running.delete(runKey);
    if (connected && !res.writableEnded) res.end();
  }
}

/** Remove durable state after the owning QDash session has been deleted. */
async function handleDeleteSession(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<DeleteSessionBody>(req, MAX_BODY_BYTES);
  if (!body.owner_id || !body.conversation_id) {
    sendJson(res, 400, { error: "owner_id and conversation_id are required" });
    return;
  }
  const runKey = `${body.owner_id}\0${body.conversation_id}`;
  if (running.has(runKey)) {
    sendJson(res, 409, { error: "conversation is still running" });
    return;
  }
  runtime.deleteSessionState(body.owner_id, body.conversation_id);
  sendJson(res, 200, { deleted: true });
}

/** Require the shared internal bearer secret for every mutating runtime route. */
function authorized(req: IncomingMessage): boolean {
  return hasBearerToken(req.headers.authorization, RUNTIME_TOKEN);
}

const server = createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { status: "ok", running: running.size, reviews: reviewsInFlight });
    return;
  }
  if (req.method === "POST" && req.url === "/chat") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleChat(req, res).catch((error: unknown) => handleRouteError(res, error, "request"));
    return;
  }
  if (req.method === "POST" && req.url === "/review") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleReview(req, res).catch((error: unknown) => handleRouteError(res, error, "review"));
    return;
  }
  if (req.method === "DELETE" && req.url === "/session") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleDeleteSession(req, res).catch((error: unknown) =>
      handleRouteError(res, error, "session delete"),
    );
    return;
  }
  res.writeHead(404).end();
});

/** Map route failures without exposing internal exception details. */
function handleRouteError(res: ServerResponse, error: unknown, route: string): void {
  console.error(`[agent-runtime] ${route} failed:`, error);
  if (res.headersSent) {
    if (!res.writableEnded) res.end();
    return;
  }
  if (error instanceof RequestError) {
    sendJson(res, error.status, { error: error.message });
  } else {
    sendJson(res, 500, { error: "internal server error" });
  }
}

server.listen(PORT, () => console.log(`[agent-runtime] listening on :${PORT}`));
