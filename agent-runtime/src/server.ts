import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { ROOT_CONVERSATION_ID, type ConversationId, type EntryId } from "@earendil-works/pi-durable";

import { requestQDashAuth } from "./auth.ts";
import { BRANCH_REFUSAL_STATUS, BranchError, parseDurableId } from "./branch.ts";
import { ActiveChat, type ChatTarget, type SteerOutcome } from "./chat-control.ts";
import { runChatTurn, toImageContent, type ImageBody, type TurnResponse } from "./chat-turn.ts";
import { parsePageContext } from "./page-context.ts";
import { encodeLine } from "./events.ts";
import { hasBearerToken, readJsonBody, RequestError, runtimeToken } from "./http.ts";
import { EvaluationError } from "./evaluate.ts";
import { TurnFeed } from "./turn-feed.ts";
import { claimStore, fenceSteer, steerFenced } from "./store-identity.ts";
import { stopStoredConversation } from "./stored-stop.ts";
import {
  BACKGROUND_CONTEXT,
  SharedRuntime,
  type SessionRequest,
  type StoreTarget,
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
// How long a stop of a chat whose work only the store remembers waits for that
// work to end, when it may start scheduling (see stored-stop.ts).
const STORED_STOP_SETTLE_MS = Number(process.env.STORED_STOP_SETTLE_MS ?? 5_000);
const RUNTIME_TOKEN = runtimeToken();

/**
 * Where a request's chat lives, resolved by QDash's API from the chat session it
 * stored: the store's session ID (unset, the chat's own) and the branch
 * conversation in it (unset, the root).
 */
interface StoreFields {
  store_session_id?: string;
  store_conversation_id?: string;
  /**
   * The incarnation of the store the request is about (see store-identity.ts):
   * QDash's API gives each one its own. Unset, a legacy request, which reaches
   * only a store without a generation.
   */
  store_generation?: string;
}

interface ChatBody extends StoreFields {
  owner_id?: string;
  conversation_id?: string;
  request_id?: string;
  message?: string;
  /** Replaces `message` when the conversation is new: an opening QDash wrote in full (an investigation). */
  initial_message?: string;
  /**
   * Goes before `message` when the conversation is new: a task result's context. The runtime
   * appends the user's message itself, after expanding a `/skill:name` command it starts with.
   */
  initial_context?: string;
  model?: { provider?: string; name?: string };
  thinking_level?: SessionRequest["thinkingLevel"];
  /** Figures attached to this turn's message. */
  images?: ImageBody[];
  /** Figures of the opening context; attached only when the conversation is new. */
  initial_images?: ImageBody[];
  /** The user's decision on a write call the previous turn asked approval for. */
  approval?: { id?: string; approve?: boolean };
  /** The user's own chat instructions, set in QDash's Settings. */
  user_instructions?: string;
  /** What the user has open in QDash: the page, and on the Workflow editor the flow's current code. */
  page_context?: unknown;
  /**
   * Continue the conversation's last run, which ended without an answer, instead of sending `message`: no user
   * message is added. Refused while something runs, after an answer, or while a question, an approval, or a proposed
   * edit waits for the user.
   */
  continue?: boolean;
  /**
   * Reattach to the turn `request_id` started, after its stream dropped: never submit anything. While the turn runs,
   * the request gets the turn's events from its start (see turn-feed.ts); after it ended, the turn's answer is read
   * from the store. A request ID the store has never seen is `404` with `reason: "turn_not_found"`.
   */
  reattach?: boolean;
  /** Where the turn starts in the transcript QDash saves (see TurnStart); reported, never interpreted. */
  turn_start?: unknown;
}

interface SteerBody extends StoreFields {
  owner_id?: string;
  conversation_id?: string;
  request_id?: string;
  message?: string;
  /** The request ID of the chat turn the steer was sent to; only that turn admits it. */
  turn_request_id?: string;
}

interface DeleteSessionBody extends StoreFields {
  owner_id?: string;
  conversation_id?: string;
}

interface AbortBody extends DeleteSessionBody {
  /**
   * When no turn of the chat runs, also stop the work the store holds for it
   * from before a restart (see stored-stop.ts). QDash's API asks this for a
   * deleted chat only, whose work no later turn would recover.
   */
  include_stored?: boolean;
  /**
   * Stop only the turn this request ID started: a stop that arrives after that turn
   * ended never stops a newer turn of the chat.
   */
  turn_request_id?: string;
}

interface BranchBody {
  owner_id?: string;
  store_session_id?: string;
  store_generation?: string;
  /** The conversation branched from; unset, the root. */
  source_conversation_id?: string;
  /** The answer's durable entry ID, as the chat stream reported it. */
  entry_id?: string;
  /** The QDash session the branch is for; the same one again returns the same branch. */
  target_session_id?: string;
}

interface EvaluateBody {
  task_id?: string;
  question?: string;
  max_figures?: number;
  /** "direct" (default) runs the two tools; "planner" runs a planner turn that calls them. */
  mode?: "direct" | "planner";
  /** The planner in planner mode; in direct mode only pi-qcaleval's fallback model. */
  model?: { provider?: string; name?: string };
  /** The model that qcal_evaluate must use, independent of the planner. */
  evaluation_model?: { provider?: string; name?: string };
  thinking_level?: SessionRequest["thinkingLevel"];
  /** Show the task's labeled example plots before the figure (in-context examples). */
  with_examples?: boolean;
  /** Read this uploaded knowledge draft instead of the task's shared knowledge. */
  knowledge_draft_id?: string;
}

interface PromptPreviewBody {
  task_name?: string;
  with_examples?: boolean;
  context?: string;
  question?: string;
  knowledge_draft_id?: string;
}

/** The knowledge draft a request names, if any. */
function draftIdOf(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Planner-less evaluations in flight, for /health. */
let evaluating = 0;

/** The prompts an evaluation of a task would send (see evaluate.ts); no model call. */
async function handleEvaluationPrompts(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<PromptPreviewBody>(req, MAX_BODY_BYTES);
  if (typeof body.task_name !== "string" || !body.task_name.trim()) {
    sendJson(res, 400, { error: "task_name is required" });
    return;
  }
  let auth;
  try {
    auth = requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return;
  }
  const controller = new AbortController();
  res.on("close", () => {
    if (!res.writableEnded) controller.abort();
  });
  try {
    const preview = await runtime.previewEvaluationPrompts(
      {
        taskName: body.task_name,
        withExamples: body.with_examples === true,
        context: typeof body.context === "string" ? body.context : undefined,
        question: typeof body.question === "string" ? body.question : undefined,
        knowledgeDraftId: draftIdOf(body.knowledge_draft_id),
      },
      auth,
      controller.signal,
    );
    sendJson(res, 200, preview);
  } catch (error) {
    if (controller.signal.aborted) return;
    if (error instanceof EvaluationError) {
      sendJson(res, error.status, { error: error.message, stage: error.stage });
      return;
    }
    throw error;
  }
}

/**
 * What holds each store, by owner and store session: a chat turn, a branch being
 * forked, or a deletion. One open writer per SQLite store: a store holds a chat
 * and every branch of it, so a turn of one branch, a fork, and a deletion of the
 * store wait for each other (`409`). A steer and a stop reach a turn through its
 * hold only when they name the turn's exact chat (`ActiveChat.runs`).
 */
type StoreHold =
  | {
      kind: "chat";
      active: ActiveChat;
      feed: TurnFeed;
      /** The turn adds no message of its own: a continue. */
      continuing: boolean;
      startedAt: number;
      /** Where the turn starts in the saved transcript, as its window sent it (see TurnStart). */
      turnStart: TurnStart | null;
    }
  | { kind: "branch" } | { kind: "delete" } | { kind: "stop" };
const stores = new Map<string, StoreHold>();

/**
 * Where a chat turn starts in the transcript QDash saves: how many messages precede it,
 * and a fingerprint the window that sent the turn computed. Opaque here: it is kept with
 * the running turn and reported to the user's other windows (`/chat/active`), which follow
 * the turn only from a saved transcript holding that start.
 */
type TurnStart = { index: number; digest: string };

function parseTurnStart(raw: unknown): TurnStart | null {
  if (!raw || typeof raw !== "object") return null;
  const { index, digest } = raw as { index?: unknown; digest?: unknown };
  if (typeof index !== "number" || !Number.isInteger(index) || index < 0) return null;
  if (typeof digest !== "string" || !/^[0-9a-f]{16}$/.test(digest)) return null;
  return { index, digest };
}

function storeKey(ownerId: string, storeSessionId: string): string {
  return `${ownerId}\0${storeSessionId}`;
}

/** The chat a request names: its QDash session, and its store and conversation there. */
interface RequestTarget {
  chat: ChatTarget;
  store: StoreTarget;
  key: string;
  /** The store's SQLite file. */
  path: string;
  generation: string | undefined;
}

/** The store generation a request names, or undefined for a legacy request. */
function generationOf(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

/** The target of a request, or undefined when its durable conversation ID is malformed. */
function requestTarget(ownerId: string, sessionId: string, body: StoreFields): RequestTarget | undefined {
  const storeSessionId = typeof body.store_session_id === "string" && body.store_session_id ? body.store_session_id : sessionId;
  let conversationId;
  if (body.store_conversation_id !== undefined && body.store_conversation_id !== null) {
    conversationId = parseDurableId<ConversationId>(body.store_conversation_id);
    if (conversationId === undefined) return undefined;
  }
  const generation = generationOf(body.store_generation);
  return {
    chat: {
      sessionId,
      conversation: conversationId === undefined ? "root" : String(conversationId),
      ...(generation === undefined ? {} : { generation }),
    },
    store: { storeSessionId, ...(conversationId === undefined ? {} : { conversationId }) },
    key: storeKey(ownerId, storeSessionId),
    path: runtime.storePath(ownerId, storeSessionId),
    generation,
  };
}

/** The turn running exactly this chat, if one does. */
function activeFor(target: RequestTarget): ActiveChat | undefined {
  const hold = stores.get(target.key);
  return hold?.kind === "chat" && hold.active.runs(target.chat) ? hold.active : undefined;
}

/** Why a store is held, for a `409` to a request about another of its chats. */
function storeBusy(hold: StoreHold): { error: string; reason: "store_busy" } {
  const error =
    hold.kind === "chat"
      ? "Another branch of this chat is answering. Wait for it to finish, or stop it, and try again."
      : hold.kind === "branch"
        ? "A branch of this chat is being created. Try again in a moment."
        : hold.kind === "stop"
          ? "A deleted branch of this chat is being stopped. Try again in a moment."
          : "This chat is being deleted.";
  return { error, reason: "store_busy" };
}

/** The reply to a request about an incarnation of the store that is gone. */
const STALE_STORE = {
  error: "This chat's runtime state belongs to an earlier chat of the same ID. Reload the chat and try again.",
  reason: "stale_store",
} as const;

/** The wire form of a steer outcome. */
function steerJson(outcome: SteerOutcome): Record<string, unknown> {
  switch (outcome.status) {
    case "applied":
      return { status: "applied", submission_id: outcome.submissionId, entry_id: String(outcome.entryId) };
    case "queued":
      return { status: "queued", submission_id: outcome.submissionId };
    case "withdrawn":
      return { status: "withdrawn", submission_id: outcome.submissionId, reason: outcome.reason };
    case "rejected":
      return { status: "rejected", reason: outcome.reason };
    case "not_found":
      return { status: "not_found" };
  }
}

const runtime = await SharedRuntime.create();
console.log(`[agent-runtime] tools: ${runtime.listToolNames().join(", ")}`);

/** Send one JSON response. */
function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

/** Open or recover a durable conversation and wait for one idempotent input, or a continue. */
async function handleChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<ChatBody>(req, MAX_BODY_BYTES);
  const ownerId = body.owner_id;
  const conversationId = body.conversation_id;
  const continuing = body.continue === true;
  // A reattach sends nothing: it only names the turn by its request ID.
  const reattach = body.reattach === true;
  if (!ownerId || !conversationId || (!continuing && !reattach && typeof body.message !== "string")) {
    sendJson(res, 400, {
      error: "owner_id, conversation_id and message are required",
    });
    return;
  }
  if (continuing && body.approval) {
    sendJson(res, 400, { error: "a continue cannot carry an approval decision" });
    return;
  }

  let auth;
  try {
    auth = requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return;
  }

  const target = requestTarget(ownerId, conversationId, body);
  if (!target) {
    sendJson(res, 400, { error: "store_conversation_id is not a conversation ID" });
    return;
  }
  if (reattach && !body.request_id) {
    sendJson(res, 400, { error: "a reattach needs the request_id of the turn" });
    return;
  }
  const hold = stores.get(target.key);
  if (
    reattach &&
    hold?.kind === "chat" &&
    hold.active.runs(target.chat) &&
    hold.active.turnRequestId === body.request_id
  ) {
    // The same user's same chat; the project must match too, as for a steer.
    if (hold.active.projectId !== auth.projectId) {
      sendJson(res, 403, { error: "the running answer belongs to another project" });
      return;
    }
    await attachTurn(res, hold.feed);
    return;
  }
  if (hold) {
    sendJson(
      res,
      409,
      hold.kind === "chat" && hold.active.runs(target.chat)
        ? { error: "conversation is already processing a request" }
        : storeBusy(hold),
    );
    return;
  }
  const active = new ActiveChat(auth.projectId, BACKGROUND_CONTEXT, target.chat, body.request_id, (fenceKey) =>
    steerFenced(target.path, target.chat.conversation, fenceKey),
  );
  // Every event the turn writes, for its own response and any request that reattaches.
  const feed = new TurnFeed();
  stores.set(target.key, {
    kind: "chat",
    active,
    feed,
    continuing,
    startedAt: Date.now(),
    turnStart: parseTurnStart(body.turn_start),
  });
  const pageContext = parsePageContext(body.page_context);

  let opened;
  try {
    // Held, so nothing creates or removes the store between this check and the open.
    if (claimStore(target.path, target.generation, true) === "stale") {
      active.failed();
      stores.delete(target.key);
      feed.end();
      sendJson(res, 409, STALE_STORE);
      return;
    }
    opened = await runtime.openSession(
      {
        ownerId,
        sessionId: conversationId,
        ...target.store,
        requestId: body.request_id,
        message: body.message ?? "",
        provider: body.model?.provider,
        modelName: body.model?.name,
        thinkingLevel: body.thinking_level,
        images: toImageContent(body.images),
        ...(typeof body.user_instructions === "string" ? { userInstructions: body.user_instructions } : {}),
        ...(pageContext ? { pageContext } : {}),
      },
      auth,
    );
  } catch (error) {
    active.failed();
    stores.delete(target.key);
    // A request that reattached meanwhile learns the turn never started.
    feed.end();
    if (error instanceof BranchError) {
      sendJson(res, BRANCH_REFUSAL_STATUS[error.reason], { error: error.message, reason: error.reason });
      return;
    }
    sendJson(res, 400, {
      error: error instanceof Error ? error.message : String(error),
    });
    return;
  }

  await runChatTurn(
    {
      request: body,
      opened,
      active,
      feed,
      storePath: target.path,
      release: () => stores.delete(target.key),
      timing: { wrapUpMs: CHAT_WRAP_UP_MS, timeoutMs: CHAT_TIMEOUT_MS, pingMs: CHAT_PING_MS },
      expandSkillCommand: (message) => runtime.expandSkillCommand(message),
    },
    chatResponse(res),
  );
}

/** The transport of a chat turn: a JSON refusal, or the turn's NDJSON stream. */
function chatResponse(res: ServerResponse): TurnResponse {
  return {
    refuse: (status, body) => sendJson(res, status, body),
    stream: (feed) => {
      res.writeHead(200, {
        "Content-Type": "application/x-ndjson",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
      });
      let connected = true;
      const detach = feed.subscribe((event) => {
        if (connected && !res.writableEnded) res.write(encodeLine(event));
      });
      res.on("close", () => {
        connected = false;
        detach();
      });
    },
    end: () => {
      if (!res.writableEnded) res.end();
    },
  };
}

/**
 * Stream a running turn to a request that reattached to it: the turn's events
 * so far, then its live ones, until it ends. A turn that ends without having
 * written a terminal event refused its request before streaming (it submitted
 * nothing); the reattached stream says so.
 */
async function attachTurn(res: ServerResponse, feed: TurnFeed): Promise<void> {
  res.writeHead(200, {
    "Content-Type": "application/x-ndjson",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
  });
  let connected = true;
  const detach = feed.subscribe((event) => {
    if (connected && !res.writableEnded) res.write(encodeLine(event));
  });
  res.on("close", () => {
    connected = false;
    detach();
  });
  await feed.closed;
  if (!feed.terminal && connected && !res.writableEnded) {
    res.write(
      encodeLine({
        type: "error",
        code: "turn_not_started",
        message: "The message was refused before the assistant started on it; send it again.",
      }),
    );
  }
  if (!res.writableEnded) res.end();
}

/**
 * Which turn, if any, runs exactly this chat now: read-only, from memory, so
 * another window of the same user's chat can follow it by reattaching with the
 * turn's request ID (which submits nothing). It opens no store and starts
 * nothing. It names the turn only to its own user (`owner_id`, set by the API
 * from the signed-in user) in the project the turn was sent from; for another
 * project it says only that a turn runs. A turn that already wrote its last
 * event is not reported: its end is being saved. The turn's start (`turn_start`)
 * lets that window place it only over a saved transcript that holds the start.
 */
async function handleActiveChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<StoreFields & { owner_id?: string; conversation_id?: string }>(
    req,
    MAX_BODY_BYTES,
  );
  if (!body.owner_id || !body.conversation_id) {
    sendJson(res, 400, { error: "owner_id and conversation_id are required" });
    return;
  }
  let auth;
  try {
    auth = requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return;
  }
  const target = requestTarget(body.owner_id, body.conversation_id, body);
  if (!target) {
    sendJson(res, 400, { error: "store_conversation_id is not a conversation ID" });
    return;
  }
  const hold = stores.get(target.key);
  if (hold?.kind !== "chat" || !hold.active.runs(target.chat) || !hold.active.turnRequestId || hold.feed.terminal) {
    sendJson(res, 200, { running: false });
    return;
  }
  if (hold.active.projectId !== auth.projectId) {
    sendJson(res, 200, { running: true, other_project: true });
    return;
  }
  sendJson(res, 200, {
    running: true,
    request_id: hold.active.turnRequestId,
    continuing: hold.continuing,
    started_at: hold.startedAt,
    turn_start: hold.turnStart,
  });
}

interface SteerRequest {
  ownerId: string;
  conversationId: string;
  requestId: string;
  projectId: string | undefined;
  target: RequestTarget;
  /** Names the steer within its chat: project and request ID. */
  fenceKey: string;
}

/** The fields every steer route takes, or a reply already sent for a bad request. */
function steerRequest(req: IncomingMessage, res: ServerResponse, body: SteerBody): SteerRequest | undefined {
  if (!body.owner_id || !body.conversation_id || !body.request_id) {
    sendJson(res, 400, { error: "owner_id, conversation_id and request_id are required" });
    return undefined;
  }
  let auth;
  try {
    auth = requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return undefined;
  }
  const target = requestTarget(body.owner_id, body.conversation_id, body);
  if (!target) {
    sendJson(res, 400, { error: "store_conversation_id is not a conversation ID" });
    return undefined;
  }
  // Only the turn of this exact chat: another branch of the store runs its own conversation.
  const active = activeFor(target);
  if (active && active.projectId !== auth.projectId) {
    sendJson(res, 403, { error: "the running answer belongs to another project" });
    return undefined;
  }
  return {
    ownerId: body.owner_id,
    conversationId: body.conversation_id,
    requestId: body.request_id,
    projectId: auth.projectId,
    target,
    fenceKey: `${auth.projectId ?? ""}\0${body.request_id}`,
  };
}

/** Where a steer stands in the durable store, or a reply already sent when it cannot say. */
async function storedSteer(res: ServerResponse, request: SteerRequest): Promise<SteerOutcome | undefined> {
  let receipt: SteerOutcome | "wrong_project";
  try {
    receipt = await runtime.steerReceipt(
      request.ownerId,
      request.conversationId,
      request.projectId,
      request.requestId,
      request.target.store,
    );
  } catch (error) {
    console.warn("[agent-runtime] could not read a steer receipt:", error);
    sendJson(res, 503, { error: "the conversation's store could not be read" });
    return undefined;
  }
  if (receipt === "wrong_project") {
    sendJson(res, 403, { error: "the message belongs to another project" });
    return undefined;
  }
  return receipt;
}

/**
 * Steer the turn a conversation is running with a message the user sent while
 * the answer was written.
 *
 * The steer goes to the harness the turn already has open, with that turn's
 * QDash credentials; it never opens the store a second time. It must come for
 * the same owner (the run key) and the same QDash project. When nothing runs
 * any more it is refused, so the user sends it as a new message instead of it
 * silently starting a run. A request ID already admitted, also by a turn that
 * ended or before a restart, reports that steer from the durable store.
 */
async function handleSteer(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<SteerBody>(req, MAX_BODY_BYTES);
  const message = typeof body.message === "string" ? body.message.trim() : "";
  const turnRequestId = typeof body.turn_request_id === "string" ? body.turn_request_id : "";
  if (!message || !turnRequestId) {
    sendJson(res, 400, {
      error: "owner_id, conversation_id, request_id, turn_request_id and message are required",
    });
    return;
  }
  const request = steerRequest(req, res, body);
  if (!request) return;
  const active = activeFor(request.target);
  // Only the turn the steer was sent to admits it, and only until a status
  // lookup said it was not sent (see ActiveChat.admits).
  let outcome: SteerOutcome = active?.admits(turnRequestId, request.fenceKey)
    ? await active.steer(request.requestId, message)
    : { status: "rejected", reason: "idle" };
  if (outcome.status === "rejected") {
    // A submit of the same request ID still in flight lands in the store first.
    await active?.drain();
    const stored = await storedSteer(res, request);
    if (!stored) return;
    if (stored.status !== "not_found") outcome = stored;
  }
  sendJson(res, outcome.status === "rejected" ? 409 : 200, steerJson(outcome));
}

/**
 * Where a steer stands, without sending it: it opens no harness, so it never
 * admits a steer or starts a run (SQLite may still lock the store briefly; a
 * lock held too long is a 503, never `not_found`). The chat asks after its
 * stream ended (stopped, or the connection dropped) before it saw where the
 * steer landed.
 *
 * `not_found` is final. A steer is admitted only by the turn it was sent to
 * (`turn_request_id`), and every turn has its own request ID. The same turn
 * may be requested again with that ID (a retry, or after a restart, to
 * recover it), so before it reads, the lookup fences the steer: durably,
 * beside the store (store-identity.ts `fenceSteer`), which every request of
 * the turn checks before it admits a steer, and in the turn running now.
 * A steer request still on its way then cannot admit it after the chat was
 * told it was not sent. The fence is written before the read whatever the
 * read finds: a steer the store already holds is reported from there anyway.
 */
async function handleSteerStatus(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<SteerBody>(req, MAX_BODY_BYTES);
  const request = steerRequest(req, res, body);
  if (!request) return;
  // Fence before reading, and let submits already in flight finish, so none lands after the read.
  try {
    fenceSteer(request.target.path, request.target.chat.conversation, request.fenceKey);
  } catch (error) {
    console.warn("[agent-runtime] could not fence a steer:", error);
    sendJson(res, 503, { error: "the conversation's store could not be written" });
    return;
  }
  const active = activeFor(request.target);
  active?.fence(request.fenceKey);
  await active?.drain();
  const stored = await storedSteer(res, request);
  if (!stored) return;
  sendJson(res, 200, steerJson(stored));
}

/**
 * Stop the turn a conversation is running, at the user's request.
 *
 * A dropped connection alone never cancels durable work (see handleChat), so
 * the chat's Stop button calls this explicitly. The turn then settles as
 * aborted and the next message can start a new one.
 *
 * With `include_stored`, a chat no turn runs has the work the store holds for
 * it from before a restart stopped (see stored-stop.ts), while the request
 * holds the store: `200` once stopped, `404` when there is none. It needs the
 * user's QDash credentials, like every request that opens a store.
 */
async function handleAbortChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<AbortBody>(req, MAX_BODY_BYTES);
  if (!body.owner_id || !body.conversation_id) {
    sendJson(res, 400, { error: "owner_id and conversation_id are required" });
    return;
  }
  const target = requestTarget(body.owner_id, body.conversation_id, body);
  if (!target) {
    sendJson(res, 400, { error: "store_conversation_id is not a conversation ID" });
    return;
  }
  // Only this exact chat's turn: a stop never reaches another branch of the store.
  // From the moment the turn holds the store, also before its input is
  // admitted: the turn applies the stop once it is (see ActiveChat.stop).
  const active = activeFor(target);
  if (active && body.turn_request_id && active.turnRequestId !== body.turn_request_id) {
    sendJson(res, 404, { error: "the named turn is not running" });
    return;
  }
  if (active) {
    await active.stop(BACKGROUND_CONTEXT);
    sendJson(res, 200, { aborted: true });
    return;
  }
  if (body.include_stored !== true) {
    sendJson(res, 404, { error: "conversation is not running" });
    return;
  }
  try {
    requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return;
  }
  const hold = stores.get(target.key);
  if (hold) {
    // A turn of this chat in a newer incarnation of the store: the one named is gone.
    if (hold.kind === "chat" && hold.active.target?.sessionId === target.chat.sessionId && hold.active.target.conversation === target.chat.conversation) {
      sendJson(res, 404, { error: "conversation is not running" });
      return;
    }
    sendJson(res, 409, storeBusy(hold));
    return;
  }
  stores.set(target.key, { kind: "stop" });
  try {
    // Held: nothing creates, opens, or removes the store meanwhile.
    if (claimStore(target.path, target.generation, false) !== "ok") {
      sendJson(res, 404, { error: "conversation is not running" });
      return;
    }
    const { harness, close } = await runtime.openStoreForCleanup(body.owner_id, target.store.storeSessionId ?? body.conversation_id);
    let stopped;
    try {
      stopped = await stopStoredConversation(
        harness,
        target.store.conversationId ?? ROOT_CONVERSATION_ID,
        BACKGROUND_CONTEXT,
        STORED_STOP_SETTLE_MS,
      );
    } finally {
      await close();
    }
    if (stopped === "none") {
      sendJson(res, 404, { error: "conversation is not running" });
      return;
    }
    sendJson(res, 200, { aborted: true, settled: stopped === "settled" });
  } finally {
    stores.delete(target.key);
  }
}

/**
 * Evaluate one task result's figure without a planner (see evaluate.ts).
 *
 * Synchronous: the response is the evaluation record, after the calibration
 * VLM has answered. A caller that gives up closes the connection, which
 * aborts the evaluation; concurrency is the caller's to limit.
 */
async function handleEvaluate(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<EvaluateBody>(req, MAX_BODY_BYTES);
  if (typeof body.task_id !== "string" || !body.task_id.trim()) {
    sendJson(res, 400, { error: "task_id is required" });
    return;
  }
  let auth;
  try {
    auth = requestQDashAuth(req.headers);
  } catch {
    sendJson(res, 401, { error: "QDash user authentication is required" });
    return;
  }
  const controller = new AbortController();
  res.on("close", () => {
    if (!res.writableEnded) controller.abort();
  });
  if (body.mode !== undefined && body.mode !== "direct" && body.mode !== "planner") {
    sendJson(res, 400, { error: "mode must be direct or planner" });
    return;
  }
  evaluating += 1;
  try {
    const request = {
      taskId: body.task_id,
      question: typeof body.question === "string" ? body.question : undefined,
      maxFigures: body.max_figures,
      withExamples: body.with_examples === true,
      knowledgeDraftId: draftIdOf(body.knowledge_draft_id),
      provider: body.model?.provider,
      modelName: body.model?.name,
      evaluationProvider: body.evaluation_model?.provider,
      evaluationModelName: body.evaluation_model?.name,
      thinkingLevel: body.thinking_level,
    };
    const result =
      body.mode === "planner"
        ? await runtime.evaluateWithPlanner(request, auth, controller.signal)
        : await runtime.evaluateTask(request, auth, controller.signal);
    sendJson(res, 200, result);
  } catch (error) {
    if (controller.signal.aborted) {
      console.warn(`[agent-runtime] evaluation of ${body.task_id} abandoned by the caller`);
      return;
    }
    if (error instanceof EvaluationError) {
      console.warn(`[agent-runtime] evaluation of ${body.task_id} failed at ${error.stage}: ${error.message}`);
      sendJson(res, error.status, { error: error.message, stage: error.stage });
      return;
    }
    throw error;
  } finally {
    evaluating -= 1;
  }
}

/**
 * Remove a store and its workspace after the last QDash session that uses it
 * has been deleted: `store_session_id`, or `conversation_id` for a chat that
 * was never branched. QDash's API decides when that is; the runtime only
 * refuses while the store is held. Only the incarnation `store_generation`
 * names is removed (see store-identity.ts): a request that arrives after the
 * chat was created again under the same ID removes nothing, and says so.
 */
async function handleDeleteSession(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<DeleteSessionBody>(req, MAX_BODY_BYTES);
  const storeSessionId = body.store_session_id || body.conversation_id;
  if (!body.owner_id || !storeSessionId) {
    sendJson(res, 400, { error: "owner_id and conversation_id are required" });
    return;
  }
  const generation = generationOf(body.store_generation);
  const key = storeKey(body.owner_id, storeSessionId);
  const hold = stores.get(key);
  if (hold) {
    // A turn of a newer incarnation of the store holds it: the one named is gone already.
    if (hold.kind === "chat" && generation !== undefined && hold.active.target?.generation !== generation) {
      sendJson(res, 200, { deleted: true, outcome: "stale" });
      return;
    }
    sendJson(res, 409, hold.kind === "chat" ? { error: "conversation is still running" } : storeBusy(hold));
    return;
  }
  stores.set(key, { kind: "delete" });
  let outcome;
  try {
    // Checked and removed while held: no request creates or opens the store in between.
    outcome = await runtime.deleteSessionState(body.owner_id, storeSessionId, generation);
  } finally {
    stores.delete(key);
  }
  if (outcome === "stale" && generation === undefined) {
    sendJson(res, 409, STALE_STORE);
    return;
  }
  // `stale`: the store is a newer incarnation; the one named was removed before.
  sendJson(res, 200, { deleted: true, outcome });
}

/**
 * Branch a chat at one of its answers: fork the conversation in the chat's
 * store (see branch.ts). The store is held for the whole open, fork, and close,
 * so no turn of the chat or of another branch, no other fork, and no deletion
 * runs meanwhile, and nothing is scheduled. Idempotent by `target_session_id`.
 */
async function handleBranch(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<BranchBody>(req, MAX_BODY_BYTES);
  const at = parseDurableId<EntryId>(body.entry_id);
  const hasSource = body.source_conversation_id !== undefined && body.source_conversation_id !== null;
  const source = hasSource ? parseDurableId<ConversationId>(body.source_conversation_id) : undefined;
  if (
    !body.owner_id ||
    !body.store_session_id ||
    !body.target_session_id ||
    at === undefined ||
    (hasSource && source === undefined)
  ) {
    sendJson(res, 400, {
      error: "owner_id, store_session_id, target_session_id and a durable entry_id are required",
      reason: "invalid_request",
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
  const key = storeKey(body.owner_id, body.store_session_id);
  const hold = stores.get(key);
  if (hold) {
    const busy = storeBusy(hold);
    sendJson(res, 409, {
      error: hold.kind === "chat" ? "This chat or one of its branches is answering. Try again when it has finished." : busy.error,
      reason: "busy",
    });
    return;
  }
  stores.set(key, { kind: "branch" });
  try {
    if (claimStore(runtime.storePath(body.owner_id, body.store_session_id), generationOf(body.store_generation), false) === "stale") {
      sendJson(res, 409, STALE_STORE);
      return;
    }
    const result = await runtime.forkSession(
      {
        ownerId: body.owner_id,
        storeSessionId: body.store_session_id,
        ...(source === undefined ? {} : { sourceConversationId: source }),
        at,
        targetSessionId: body.target_session_id,
      },
      auth,
    );
    sendJson(res, 200, { conversation_id: String(result.conversationId), created: result.created });
  } catch (error) {
    if (error instanceof BranchError) {
      sendJson(res, BRANCH_REFUSAL_STATUS[error.reason], { error: error.message, reason: error.reason });
      return;
    }
    throw error;
  } finally {
    stores.delete(key);
  }
}

/** Require the shared internal bearer secret for every mutating runtime route. */
function authorized(req: IncomingMessage): boolean {
  return hasBearerToken(req.headers.authorization, RUNTIME_TOKEN);
}

const server = createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, {
      status: "ok",
      running: [...stores.values()].filter((hold) => hold.kind === "chat").length,
      evaluating,
    });
    return;
  }
  if (req.method === "POST" && req.url === "/evaluate") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleEvaluate(req, res).catch((error: unknown) => handleRouteError(res, error, "evaluate"));
    return;
  }
  if (req.method === "POST" && req.url === "/evaluation-prompts") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleEvaluationPrompts(req, res).catch((error: unknown) => handleRouteError(res, error, "evaluation-prompts"));
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
  if (req.method === "POST" && req.url === "/system-prompt") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    readJsonBody<{ user_instructions?: unknown }>(req, MAX_BODY_BYTES)
      .then((body) =>
        sendJson(
          res,
          200,
          runtime.chatSystemPrompt(
            typeof body.user_instructions === "string" ? body.user_instructions : undefined,
          ),
        ),
      )
      .catch((error: unknown) => handleRouteError(res, error, "system prompt"));
    return;
  }
  if (req.method === "GET" && req.url === "/skills") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    sendJson(res, 200, { skills: runtime.chatSkills() });
    return;
  }
  if (req.method === "GET" && req.url === "/chat-models") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    runtime
      .chatModels()
      .then((chatModels) => sendJson(res, 200, { chat_models: chatModels }))
      .catch((error: unknown) => handleRouteError(res, error, "chat models"));
    return;
  }
  if (req.method === "POST" && req.url === "/chat/active") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleActiveChat(req, res).catch((error: unknown) => handleRouteError(res, error, "active turn"));
    return;
  }
  if (req.method === "POST" && req.url === "/chat/steer/status") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleSteerStatus(req, res).catch((error: unknown) => handleRouteError(res, error, "steer status"));
    return;
  }
  if (req.method === "POST" && req.url === "/chat/steer") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleSteer(req, res).catch((error: unknown) => handleRouteError(res, error, "steer"));
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
  if (req.method === "POST" && req.url === "/chat/branch") {
    if (!authorized(req)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    handleBranch(req, res).catch((error: unknown) => handleRouteError(res, error, "branch"));
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
