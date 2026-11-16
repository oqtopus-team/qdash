import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { UserEntry, type ConversationId, type EntryId, type Submission } from "@earendil-works/pi-durable";

import { requestQDashAuth } from "./auth.ts";
import { BRANCH_REFUSAL_STATUS, BranchError, parseDurableId } from "./branch.ts";
import {
  ActiveChat,
  continueBlocker,
  settleChat,
  steerOutcomeOf,
  submissionByRequest,
  type ChatTarget,
  type ContinueBlocker,
  type SteerOutcome,
} from "./chat-control.ts";
import { parsePageContext } from "./page-context.ts";
import { WRAP_UP_MESSAGE } from "./budget.ts";
import { encodeLine, formatSettledDetail, toNdjsonEvents, type NdjsonEvent, type SessionEventLike } from "./events.ts";
import { hasBearerToken, readJsonBody, RequestError, runtimeToken } from "./http.ts";
import { decisionMessage, type ApprovalRequest } from "./durable-tools.ts";
import { EvaluationError } from "./evaluate.ts";
import { ViewEventStream } from "./view-events.ts";
import {
  answerText,
  pendingApproval,
  BACKGROUND_CONTEXT,
  SharedRuntime,
  type OpenDurableSession,
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
const RUNTIME_TOKEN = runtimeToken();

interface ImageBody {
  data: string;
  mimeType: string;
}

/**
 * Where a request's chat lives, resolved by QDash's API from the chat session it
 * stored: the store's session ID (unset, the chat's own) and the branch
 * conversation in it (unset, the root).
 */
interface StoreFields {
  store_session_id?: string;
  store_conversation_id?: string;
}

interface ChatBody extends StoreFields {
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
}

interface SteerBody extends StoreFields {
  owner_id?: string;
  conversation_id?: string;
  request_id?: string;
  message?: string;
}

interface DeleteSessionBody extends StoreFields {
  owner_id?: string;
  conversation_id?: string;
}

interface BranchBody {
  owner_id?: string;
  store_session_id?: string;
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

/** Convert wire images into Pi image-content blocks. */
function toImageContent(images: ImageBody[] | undefined) {
  return (images ?? []).map((image) => ({
    type: "image" as const,
    data: image.data,
    mimeType: image.mimeType,
  }));
}

/**
 * What holds each store, by owner and store session: a chat turn, a branch being
 * forked, or a deletion. One open writer per SQLite store: a store holds a chat
 * and every branch of it, so a turn of one branch, a fork, and a deletion of the
 * store wait for each other (`409`). A steer and a stop reach a turn through its
 * hold only when they name the turn's exact chat (`ActiveChat.runs`).
 */
type StoreHold = { kind: "chat"; active: ActiveChat } | { kind: "branch" } | { kind: "delete" };
const stores = new Map<string, StoreHold>();

function storeKey(ownerId: string, storeSessionId: string): string {
  return `${ownerId}\0${storeSessionId}`;
}

/** The chat a request names: its QDash session, and its store and conversation there. */
interface RequestTarget {
  chat: ChatTarget;
  store: StoreTarget;
  key: string;
}

/** The target of a request, or undefined when its durable conversation ID is malformed. */
function requestTarget(ownerId: string, sessionId: string, body: StoreFields): RequestTarget | undefined {
  const storeSessionId = typeof body.store_session_id === "string" && body.store_session_id ? body.store_session_id : sessionId;
  let conversationId;
  if (body.store_conversation_id !== undefined && body.store_conversation_id !== null) {
    conversationId = parseDurableId<ConversationId>(body.store_conversation_id);
    if (conversationId === undefined) return undefined;
  }
  return {
    chat: { sessionId, conversation: conversationId === undefined ? "root" : String(conversationId) },
    store: { storeSessionId, ...(conversationId === undefined ? {} : { conversationId }) },
    key: storeKey(ownerId, storeSessionId),
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
        : "This chat is being deleted.";
  return { error, reason: "store_busy" };
}

/**
 * Steer request IDs a status lookup found nowhere, by owner, conversation,
 * project and request ID. The lookup told the user the steer was not sent, so a
 * request with the same ID that was still on its way to this process is not
 * admitted after it.
 *
 * In memory only, for ten minutes. A restart drops every fence, and ends the
 * requests this process was still serving, but it does not discard a steer the
 * store already admitted: a queued one is placed when the conversation's run
 * is recovered (see CHAT_QUEUE_SETTINGS). A fence also does not hold against a
 * client that retries the same request ID after a restart or after it expired;
 * the chat never does, it only asks the status again.
 */
const fencedSteers = new Map<string, number>();
const STEER_FENCE_TTL_MS = 10 * 60_000;
const MAX_STEER_FENCES = 1000;

function fenceSteer(key: string): void {
  const now = Date.now();
  for (const [known, expires] of fencedSteers) {
    if (expires > now && fencedSteers.size < MAX_STEER_FENCES) break;
    fencedSteers.delete(known);
  }
  fencedSteers.set(key, now + STEER_FENCE_TTL_MS);
}

function isFenced(key: string): boolean {
  const expires = fencedSteers.get(key);
  return expires !== undefined && expires > Date.now();
}

/** What a refused continue tells the user. */
const CONTINUE_REFUSALS: Record<ContinueBlocker, string> = {
  busy: "The conversation is still answering.",
  nothing_to_continue: "There is nothing to continue: the last answer finished. Send a new message instead.",
  awaiting_user: "The assistant is waiting for your answer, approval, or decision on its proposal; answer it instead.",
};

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

/** Translate one committed durable event to the existing NDJSON bridge. */
function writeAgentEvent(event: SessionEventLike, write: (event: NdjsonEvent) => void): void {
  for (const line of toNdjsonEvents(event)) write(line);
}

/** Open or recover a durable conversation and wait for one idempotent input, or a continue. */
async function handleChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<ChatBody>(req, MAX_BODY_BYTES);
  const ownerId = body.owner_id;
  const conversationId = body.conversation_id;
  const continuing = body.continue === true;
  if (!ownerId || !conversationId || (!continuing && typeof body.message !== "string")) {
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
  const hold = stores.get(target.key);
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
  const active = new ActiveChat(auth.projectId, BACKGROUND_CONTEXT, target.chat);
  stores.set(target.key, { kind: "chat", active });
  const pageContext = parsePageContext(body.page_context);

  let opened;
  try {
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
    if (error instanceof BranchError) {
      sendJson(res, BRANCH_REFUSAL_STATUS[error.reason], { error: error.message, reason: error.reason });
      return;
    }
    sendJson(res, 400, {
      error: error instanceof Error ? error.message : String(error),
    });
    return;
  }

  const { conversation, harness } = opened;
  let settlement: Awaited<ReturnType<typeof settleChat>> | undefined;

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

    // A retried continue recovers the submission it made, before the gate below
    // reads a state that submission itself has changed.
    let own: Submission | undefined;
    if (continuing) {
      const known = body.request_id
        ? await submissionByRequest(harness, conversation, body.request_id, BACKGROUND_CONTEXT)
        : undefined;
      if (known && known.record.type !== "continue") {
        sendJson(res, 409, { error: "request_id already names another message" });
        return;
      }
      own = known?.submission;
      if (!own) {
        const blocker = await continueBlocker(conversation, BACKGROUND_CONTEXT);
        if (blocker) {
          sendJson(res, 409, { error: CONTINUE_REFUSALS[blocker], reason: blocker });
          return;
        }
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

    // Stream what changes in the conversation view; its first value is history.
    const events = await conversation.watch(BACKGROUND_CONTEXT);
    const stream = new ViewEventStream(
      conversation,
      events.value,
      (event) => writeAgentEvent(event, write),
      BACKGROUND_CONTEXT,
      // A run recovered from a runtime that died with a steer queued places that
      // steer before this turn's message, which waits for the run. A continue has
      // no message of its own: a steer streamed during it lands where it shows.
      continuing
        ? undefined
        : async (entryId) => {
            if (!own) return true;
            const record = await own.status(BACKGROUND_CONTEXT);
            return record.type !== "input" || record.entry === undefined || Number(record.entry) > entryId;
          },
    );
    events.start(async (call) => {
      if (call.kind !== "value") return;
      await stream.push(call.value).catch((error: unknown) => {
        console.warn("[agent-runtime] chat stream revision failed:", error);
      });
    });
    // Only now, with the conversation watched, may a run recovered from an
    // earlier request go on: every steer it places is streamed.
    harness.resume();

    try {
      if (!own && continuing) {
        own = await conversation.submit(
          { type: "continue", ...(body.request_id ? { requestId: body.request_id } : {}) },
          BACKGROUND_CONTEXT,
        );
      } else if (!own) {
        own = await submitInput(body, conversation, approval, opened.writeTools, write);
      }
      // Steers may follow from here: the turn's own input is admitted.
      active.ready(harness, conversation);
      // A steer is placed after the current tool round, so the model reads it
      // before deciding on more tools and answers in the same run.
      let wrapUp: Promise<Submission | undefined> | undefined;
      const wrapUpTimer =
        CHAT_WRAP_UP_MS > 0
          ? setTimeout(() => {
              wrapUp = active.steerInternal(WRAP_UP_MESSAGE);
              // Handled after the turn settles; keep the rejection from going unhandled meanwhile.
              wrapUp.catch(() => undefined);
            }, CHAT_WRAP_UP_MS)
          : null;
      const timeout =
        CHAT_TIMEOUT_MS > 0
          ? setTimeout(() => void conversation.abort(BACKGROUND_CONTEXT), CHAT_TIMEOUT_MS)
          : null;
      const ownSubmission = own;
      settlement = await settleChat(active, harness, ownSubmission, BACKGROUND_CONTEXT, async () => {
        // The turn answered: a wrap-up still queued would only start another run.
        await wrapUp
          ?.then((placed) => placed?.abort(BACKGROUND_CONTEXT))
          .catch((error: unknown) => console.warn("[agent-runtime] wrap-up steer failed:", error));
      }).finally(() => {
        if (wrapUpTimer) clearTimeout(wrapUpTimer);
        if (timeout) clearTimeout(timeout);
      });
      // Stream every commit of the turn, also those the watch had not delivered when it settled.
      await stream.finish(events);
      for (const [requestId, record] of settlement.steers) {
        const outcome = steerOutcomeOf(record);
        if (outcome.status === "withdrawn") {
          write({ type: "steer", request_id: requestId, status: "withdrawn", reason: outcome.reason });
        }
      }
      const settled = settlement.final;
      if (settled.status === "done" && settled.type !== "write") {
        write({
          type: "done",
          text: await answerText(conversation, settled.answer),
          entry_id: String(settled.answer),
        });
      } else if (settled.type === "continue" && settled.reason === "nothing_to_answer") {
        // Not a failure: the context ended in an answer, so nothing was asked of the model.
        write({ type: "noop", reason: "nothing_to_answer" });
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
    }
  } finally {
    // Refuse steers still waiting for the turn to be ready, and every later one.
    active.failed();
    await active.drain();
    try {
      await opened.close();
    } finally {
      stores.delete(target.key);
      // End the stream only once the conversation is free, so a client that
      // sends its next message as soon as the stream ends is not refused.
      if (!res.writableEnded) res.end();
    }
  }
}

/** Submit the turn's message: what the user typed, or the outcome of the write call they decided on. */
async function submitInput(
  body: ChatBody,
  conversation: OpenDurableSession["conversation"],
  approval: ApprovalRequest | undefined,
  writeTools: OpenDurableSession["writeTools"],
  write: (event: NdjsonEvent) => void,
): Promise<Submission> {
  const view = await conversation.context(BACKGROUND_CONTEXT);
  const isNew = !view.entries.some((entry) => UserEntry.is(entry));
  let message = isNew && body.initial_message ? body.initial_message : (body.message ?? "");
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
        const result = await writeTools.runApproved(approval);
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
  return conversation.submit(
    {
      type: "input",
      content,
      ...(body.request_id ? { requestId: body.request_id } : {}),
    },
    BACKGROUND_CONTEXT,
  );
}

interface SteerRequest {
  ownerId: string;
  conversationId: string;
  requestId: string;
  projectId: string | undefined;
  target: RequestTarget;
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
    fenceKey: `${body.owner_id}\0${body.conversation_id}\0${target.chat.conversation}\0${auth.projectId ?? ""}\0${body.request_id}`,
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
  if (!message) {
    sendJson(res, 400, { error: "owner_id, conversation_id, request_id and message are required" });
    return;
  }
  const request = steerRequest(req, res, body);
  if (!request) return;
  const active = activeFor(request.target);
  // A status lookup already said this request ID was not sent: never admit it now.
  let outcome: SteerOutcome =
    active && !isFenced(request.fenceKey)
      ? await active.steer(request.requestId, message)
      : { status: "rejected", reason: "idle" };
  if (outcome.status === "rejected") {
    // A submit of the same request ID still in flight lands in the store first.
    await active?.drain();
    const stored = await storedSteer(res, request);
    if (!stored) return;
    if (stored.status !== "not_found") outcome = stored;
  }
  // Told it was not sent: a copy of this request still on its way never steers a later turn.
  if (outcome.status === "rejected") fenceSteer(request.fenceKey);
  sendJson(res, outcome.status === "rejected" ? 409 : 200, steerJson(outcome));
}

/**
 * Where a steer stands, without sending it: it opens no harness, so it never
 * admits a steer or starts a run (SQLite may still lock the store briefly; a
 * lock held too long is a 503, never `not_found`). The chat asks after its stream ended (stopped, or the
 * connection dropped) before it saw where the steer landed. A request ID found
 * nowhere is fenced, so a request still on its way cannot admit it after the
 * chat was told it was not sent.
 */
async function handleSteerStatus(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<SteerBody>(req, MAX_BODY_BYTES);
  const request = steerRequest(req, res, body);
  if (!request) return;
  // Fence before reading, and let submits already in flight finish, so none lands after the read.
  fenceSteer(request.fenceKey);
  await activeFor(request.target)?.drain();
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
 */
async function handleAbortChat(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<DeleteSessionBody>(req, MAX_BODY_BYTES);
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
  const conversation = activeFor(target)?.conversation;
  if (!conversation) {
    sendJson(res, 404, { error: "conversation is not running" });
    return;
  }
  await conversation.abort(BACKGROUND_CONTEXT);
  sendJson(res, 200, { aborted: true });
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
 * refuses while the store is held.
 */
async function handleDeleteSession(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJsonBody<DeleteSessionBody>(req, MAX_BODY_BYTES);
  const storeSessionId = body.store_session_id || body.conversation_id;
  if (!body.owner_id || !storeSessionId) {
    sendJson(res, 400, { error: "owner_id and conversation_id are required" });
    return;
  }
  const key = storeKey(body.owner_id, storeSessionId);
  const hold = stores.get(key);
  if (hold) {
    sendJson(res, 409, hold.kind === "chat" ? { error: "conversation is still running" } : storeBusy(hold));
    return;
  }
  stores.set(key, { kind: "delete" });
  try {
    await runtime.deleteSessionState(body.owner_id, storeSessionId);
  } finally {
    stores.delete(key);
  }
  sendJson(res, 200, { deleted: true });
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
