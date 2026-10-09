import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import {
  UserEntry,
  watchEvents,
  type AgentEvent,
  type Conversation,
} from "@earendil-works/pi-durable";

import { requestQDashAuth } from "./auth.ts";
import { WRAP_UP_MESSAGE } from "./budget.ts";
import { encodeLine, formatSettledDetail, toNdjsonEvents, type NdjsonEvent } from "./events.ts";
import { hasBearerToken, readJsonBody, RequestError } from "./http.ts";
import { decisionMessage, type ApprovalRequest } from "./durable-tools.ts";
import {
  answerText,
  pendingApproval,
  BACKGROUND_CONTEXT,
  SharedRuntime,
  type SessionRequest,
} from "./runtime.ts";

const PORT = Number(process.env.PORT ?? 8002);
// Optional turn budgets, both off by default: a turn runs until it answers or
// the user stops it (POST /chat/abort). Calibrations take as long as they take,
// and a tool waiting on one must not be cut off by the clock. Set
// CHAT_WRAP_UP_MS to steer the model to answer with what it has after that
// long, and CHAT_TIMEOUT_MS to abort a turn outright.
const CHAT_WRAP_UP_MS = Number(process.env.CHAT_WRAP_UP_MS ?? 0);
const CHAT_TIMEOUT_MS = Number(process.env.CHAT_TIMEOUT_MS ?? 0);
// A quiet turn (a tool polling an execution) sends a ping this often so the
// proxies between here and the browser do not take silence for a dead stream.
const CHAT_PING_MS = Number(process.env.CHAT_PING_MS ?? 15_000);
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
  /** Figures attached to this turn's message. */
  images?: ImageBody[];
  /** Figures of the opening context; attached only when the conversation is new. */
  initial_images?: ImageBody[];
  /** The user's decision on a write call the previous turn asked approval for. */
  approval?: { id?: string; approve?: boolean };
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
/**
 * Turns in flight by owner and conversation. The value is the conversation to
 * abort on a stop request, or null while the session is still being opened.
 */
const running = new Map<string, Conversation | null>();

const runtime = await SharedRuntime.create();
console.log(`[agent-runtime] tools: ${runtime.listToolNames().join(", ")}`);

/** Send one JSON response. */
function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
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
    sendJson(res, 400, {
      error: "owner_id, conversation_id and message are required",
    });
    return;
  }

  let auth;
  try {
    auth = requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return;
  }

  const runKey = `${ownerId}\0${conversationId}`;
  if (running.has(runKey)) {
    sendJson(res, 409, {
      error: "conversation is already processing a request",
    });
    return;
  }
  running.set(runKey, null);

  let opened;
  try {
    opened = await runtime.openSession(
      {
        ownerId,
        sessionId: conversationId,
        requestId: body.request_id,
        message: body.message,
        provider: body.model?.provider,
        modelName: body.model?.name,
        thinkingLevel: body.thinking_level,
        images: toImageContent(body.images),
      },
      auth,
    );
  } catch (error) {
    running.delete(runKey);
    sendJson(res, 400, {
      error: error instanceof Error ? error.message : String(error),
    });
    return;
  }

  const { harness, conversation } = opened;
  running.set(runKey, conversation);

  try {
    let approval: ApprovalRequest | undefined;
    if (body.approval) {
      approval = body.approval.id
        ? await pendingApproval(conversation, body.approval.id)
        : undefined;
      if (!approval) {
        sendJson(res, 400, {
          error: "This approval is no longer pending; ask the assistant again.",
        });
        return;
      }
    }

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
    const ping = CHAT_PING_MS > 0 ? setInterval(() => write({ type: "ping" }), CHAT_PING_MS) : null;

    const events = await watchEvents(harness, conversation.id, BACKGROUND_CONTEXT);
    events.start(async (batch) => {
      for (const event of batch) writeAgentEvent(event, write);
    });

    try {
      const view = await conversation.context(BACKGROUND_CONTEXT);
      const isNew = !view.entries.some((entry) => UserEntry.is(entry));
      let message = isNew && body.initial_message ? body.initial_message : body.message;
      if (approval) {
        // The runtime, not the model, runs the call the user approved, with the
        // exact arguments the user saw. The model only learns the outcome.
        if (body.approval?.approve === true) {
          const id = `${approval.id}:approved`;
          write({
            type: "tool_start",
            name: approval.tool,
            id,
            args: approval.args,
          });
          try {
            const result = await opened.writeTools.runApproved(approval);
            write({
              type: "tool_end",
              name: approval.tool,
              id,
              isError: false,
            });
            message = decisionMessage(approval, { approved: true, result });
          } catch (error) {
            write({ type: "tool_end", name: approval.tool, id, isError: true });
            const reason = error instanceof Error ? error.message : String(error);
            message = decisionMessage(approval, {
              approved: true,
              error: reason,
            });
          }
        } else {
          message = decisionMessage(approval, { approved: false });
        }
      }
      // Opening figures go with the first turn only; attachments go with every turn.
      const images = [
        ...(isNew ? toImageContent(body.initial_images) : []),
        ...toImageContent(body.images),
      ];
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
      // A steer is placed after the current tool round, so the model reads it
      // before deciding on more tools and answers in the same run.
      let wrapUp: ReturnType<typeof conversation.submit> | undefined;
      const wrapUpTimer =
        CHAT_WRAP_UP_MS > 0
          ? setTimeout(() => {
              wrapUp = conversation.submit(
                { type: "input", content: WRAP_UP_MESSAGE, whenBusy: "steer" },
                BACKGROUND_CONTEXT,
              );
              // Handled after the turn settles; keep the rejection from going unhandled meanwhile.
              wrapUp.catch(() => undefined);
            }, CHAT_WRAP_UP_MS)
          : null;
      const timeout =
        CHAT_TIMEOUT_MS > 0
          ? setTimeout(() => void conversation.abort(BACKGROUND_CONTEXT), CHAT_TIMEOUT_MS)
          : null;
      const settled = await submission.wait(BACKGROUND_CONTEXT).finally(() => {
        if (wrapUpTimer) clearTimeout(wrapUpTimer);
        if (timeout) clearTimeout(timeout);
      });
      // A steer still queued when the run answered would start a new run.
      await wrapUp
        ?.then((placed) => placed.abort(BACKGROUND_CONTEXT))
        .catch((error: unknown) => console.warn("[agent-runtime] wrap-up steer failed:", error));
      await events.stop();
      if (settled.status === "done" && settled.type === "input") {
        write({
          type: "done",
          text: await answerText(conversation, settled.answer),
        });
      } else {
        // `detail` carries the provider's error text (HTTP status, vLLM message).
        const detail = formatSettledDetail(settled.detail);
        console.error(`[agent-runtime] chat not answered: ${settled.reason}${detail}`);
        write({
          type: "error",
          message: `conversation was not answered: ${settled.reason}${detail}`,
        });
      }
    } catch (error) {
      write({
        type: "error",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      if (ping) clearInterval(ping);
      await events.stop();
      if (connected && !res.writableEnded) res.end();
    }
  } finally {
    try {
      await opened.close();
    } finally {
      running.delete(runKey);
    }
  }
}

/**
 * Stop the turn a conversation is running, at the user's request.
 *
 * A dropped connection alone never cancels durable work (see handleChat), so
 * the chat's Stop button calls this explicitly. The turn then settles as
 * aborted and the next message can start a new one.
 */
async function handleAbortChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<DeleteSessionBody>(req, MAX_BODY_BYTES);
  if (!body.owner_id || !body.conversation_id) {
    sendJson(res, 400, { error: "owner_id and conversation_id are required" });
    return;
  }
  const conversation = running.get(`${body.owner_id}\0${body.conversation_id}`);
  if (!conversation) {
    sendJson(res, 404, { error: "conversation is not running" });
    return;
  }
  await conversation.abort(BACKGROUND_CONTEXT);
  sendJson(res, 200, { aborted: true });
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
    sendJson(res, 200, {
      status: "ok",
      running: running.size,
    });
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
  if (req.method === "POST" && req.url === "/chat/abort") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleAbortChat(req, res).catch((error: unknown) => handleRouteError(res, error, "abort"));
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
