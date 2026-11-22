"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ChatThinkingLevel } from "@/lib/chatThinking";
import type { ModelOverride } from "@/lib/copilotModels";
import {
  appendArgsDelta,
  appendDelta,
  appendLiveBlock,
  endTool,
  startDraft,
  startTool,
  stoppedBlocks,
  toPersistedTrace,
} from "@/lib/copilotChatStream";
import { buildHeaders, consumeSSEEvents, readErrorResponse } from "@/lib/sse-utils";
import { investigationFromStored, toInvestigationRequest } from "@/lib/copilotInvestigation";
import { createRequestId } from "@/lib/utils/requestId";
import {
  advanceSteer,
  patchSteer,
  placeLateSteer,
  settleOpenSteers,
  steerReplyStatus,
  type PendingSteer,
  type SteerAnchor,
  type SteerReply,
} from "@/lib/copilotSteer";
import {
  forgetOtherOwners,
  forgetStoredSessions,
  forgetStoredSteers,
  readStoredSteers,
  restoreSteer,
  storeSessionSteers,
} from "@/lib/copilotSteerStore";
import {
  forgetOtherTurnOwners,
  forgetStoredTurn,
  forgetStoredTurns,
  patchStoredTurn,
  readStoredTurns,
  storeTurn,
  type StoredTurn,
} from "@/lib/copilotTurnStore";
import { activitySnapshot, sameActivity } from "@/lib/chatActivity";
import type { CreateCopilotChatBranchRequest } from "@/schemas";
import type {
  TaskChatContext,
  AnswerFeedback,
  ChatBranchOrigin,
  ChatImageAttachment,
  ChatMessage,
  ChatEventKind,
  ChatTurnEvent,
  CopilotBlocksResult,
  DetachedTurn,
  InvestigationTarget,
  LiveTurn,
  PageContext,
  TurnActivitySnapshot,
  TurnConnection,
} from "@/types/copilotChat";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CopilotChatSession {
  id: string;
  title: string;
  /** Set when the chat is about one calibration result. */
  context: TaskChatContext | null;
  /**
   * Set when the chat investigates a failed execution or task. Every turn
   * names it, so a retried first turn still opens with the failure's logs.
   */
  investigation?: InvestigationTarget | null;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
  /** True once the server-stored messages have been fetched for this session. */
  messagesLoaded: boolean;
  /** Set on a chat branched from an answer of another one. */
  branch?: ChatBranchOrigin | null;
}

/** A turn that is streaming in one session. */
export interface SessionRun {
  turn: LiveTurn;
  /** One-line progress from backends that do not stream deltas. */
  statusMessage: string | null;
  /** Whether the turn's stream is live, and when the turn last sent something. */
  connection?: TurnConnection;
}

export interface SendOptions {
  sessionId?: string;
  /** Messages before this turn; a retry passes them without the replaced exchange. */
  history?: ChatMessage[];
  modelOverride?: ModelOverride | null;
  /** Thinking level for this turn; omitted to keep the model's configured default. */
  thinkingLevel?: ChatThinkingLevel;
  /** Figures the user attached to this message. */
  images?: ChatImageAttachment[];
  /** The user's decision on the write operation the last answer asked approval for. */
  approval?: { id: string; approve: boolean };
  /** The page the user has open, from the chat dock; the assistant is told every turn. */
  page?: PageContext | null;
  /**
   * Continue the last run, which ended without an answer, instead of sending `text`: no
   * user message is added. `history` is what stays shown before the continuation.
   */
  continueRun?: boolean;
}

export interface NewSessionOptions {
  title?: string;
  investigation?: InvestigationTarget | null;
}

interface CopilotChatSessionContextValue {
  sessions: CopilotChatSession[];
  isLoadingSessions: boolean;
  activeSessionId: string | null;
  activeSession: CopilotChatSession | null;
  runs: Record<string, SessionRun>;

  switchSession: (sessionId: string | null) => void;
  createNewSession: (context?: TaskChatContext | null, options?: NewSessionOptions) => string;
  /** Whether the session exists now, including one created in this same event handler. */
  hasSession: (sessionId: string) => boolean;
  deleteSession: (sessionId: string) => void;
  renameSession: (sessionId: string, title: string) => void;
  /** Rate the assistant message at `index`; null clears the rating. */
  setMessageFeedback: (sessionId: string, index: number, feedback: AnswerFeedback | null) => void;
  findSessionByContext: (context: TaskChatContext) => CopilotChatSession | null;

  sendMessage: (text: string, options?: SendOptions) => boolean;
  stop: (sessionId: string) => void;

  /** Messages sent while an answer was streaming, until the stream says where they landed. */
  steers: Record<string, PendingSteer[]>;
  /** Send `text` to the answer streaming in this session; false when none is. */
  steer: (sessionId: string, text: string) => boolean;
  /** Ask the runtime again where an unconfirmed steer stands; never sends it. */
  checkSteer: (sessionId: string, requestId: string) => void;
  dismissSteer: (sessionId: string, requestId: string) => void;
  /**
   * Whether the steers a reload left unresolved are restored. Until then the chat
   * cannot tell whether one is hidden, so it does not offer Continue.
   */
  steersReady: boolean;
  /** A one-line notice for the session, such as a continue that found nothing to do. */
  notices: Record<string, string>;
  dismissNotice: (sessionId: string) => void;
  /**
   * Start a new chat from the saved answer `entryId` of this session and switch to
   * it. Resolves with the new session's ID, or null when it failed; the reason is
   * the session's notice. A second call while one runs joins it.
   */
  branchFrom: (sessionId: string, entryId: string) => Promise<string | null>;
  /** The answer being branched from, by session, while its request runs. */
  branching: Record<string, string>;
  /**
   * Turns of this tab the chat does not stream now, by session: being restored after a
   * reload or a remount, or sent from another project. Each says what the chat last saw.
   */
  detachedTurns: Record<string, DetachedTurn>;
  /**
   * Hear the notable moments of turns this tab streams (an answer ready, input needed, an
   * expert awaited, a failure), each once per turn, also across reattaches and restores.
   * Never raised for history loaded from the server. Returns the unsubscribe function.
   */
  subscribeChatEvents: (listener: (event: ChatTurnEvent) => void) => () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const SESSIONS_PATH = "/copilot/chat/sessions";

/**
 * How long a turn's stream may stay silent before the chat takes it for dropped.
 * The runtime sends a heartbeat every 15 seconds (`CHAT_PING_MS`), also while a
 * tool waits on an expert or a measurement, so silence this long is a connection
 * a proxy or the network stopped, not a quiet turn.
 */
export const STREAM_SILENCE_MS = 60_000;
/** The abort reason of a stream that went silent; the chat then reattaches. */
const STALE_STREAM = "stale";
/** The abort reason when the provider unmounts: nothing is shown or saved any more. */
const UNMOUNTED = "unmounted";
/**
 * The abort reason when the user switched to another project: the chat stops showing the
 * turn, which runs on, and follows it again once the user is back in its project.
 */
const DETACHED = "detached";
/** How often a quiet turn's pointer is told its last update time again. */
const POINTER_REFRESH_MS = 15_000;
const RESTORE_UNPLACEABLE_MESSAGE =
  "An answer to this chat was still running when the page reloaded, but its message was not saved, so it cannot be shown here.";
/** Answers a proxy or a restarting API gives while the turn may run on. */
const STREAM_LOST_STATUS = new Set([502, 503, 504]);
/** Reattach attempts before the chat stops trying and says so (about 10 minutes). */
const MAX_REATTACH_ATTEMPTS = 25;
const TURN_NOT_FOUND_MESSAGE =
  "The connection dropped before the assistant received this message. Send it again.";
const CONNECTION_LOST_MESSAGE =
  "Lost the connection to the assistant. It may still be working on this message: reopen the chat later, or stop it before sending again.";

/** Where one turn's stream starts, for `runTurn`. */
interface TurnPlan {
  sessionId: string;
  controller: AbortController;
  /** The turn's own request ID: every stream of the turn, and its Stop, names it. */
  requestId: string;
  /** The project the turn was sent from. */
  projectId: string | null;
  /** The messages before the turn. */
  history: ChatMessage[];
  /** What precedes the live answer when the turn starts: the history and the user's message. */
  shown: ChatMessage[];
  /** Where the turn's own message is in `shown`; -1 for a continue. */
  userAt: number;
  continuing: boolean;
  /** The chat as it was, shown again when a continue or a restore changes nothing. */
  original: ChatMessage[];
  startedAt: number;
  lastUpdateAt: number;
  url: string;
  body: Record<string, unknown>;
  /** The first stream is a reattach: nothing is submitted. */
  reattach: boolean;
  /** Restored from the turn's pointer after a reload, a remount, or a project switch. */
  restored: boolean;
  /** Notifications the turn already raised (from its pointer), so a replay raises none again. */
  notified?: ChatEventKind[];
}

/** Tools whose call means the turn now waits for an expert. */
const EXPERT_WAIT_TOOL = "qdash_wait_agent_intervention";
const EXPERT_REQUEST_TOOL = "qdash_request_agent_human";

/** What a final answer asks of the user, from its blocks: the one notification it raises. */
function answerEventKind(result: CopilotBlocksResult): ChatEventKind {
  const types = new Set(result.blocks.map((b) => b.type));
  if (types.has("approval")) return "approval";
  if (types.has("ask")) return "question";
  if (types.has("edit")) return "edit";
  return "answer";
}

/** Wait before reattach attempt `attempt`: none for the first, then 1, 2, 4, 8, 16, and 30 seconds. */
function reattachDelay(attempt: number): number {
  return attempt <= 1 ? 0 : Math.min(30_000, 1_000 * 2 ** (attempt - 2));
}

/** Resolve after `ms`, or reject with the signal's reason once it aborts. */
function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
const DEFAULT_TITLE = "New Chat";

function withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  if (!(key in record)) return record;
  const { [key]: _removed, ...rest } = record;
  return rest;
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toTimestamp(iso: string | undefined | null): number {
  if (!iso) return Date.now();
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? Date.now() : t;
}

function sameContext(a: TaskChatContext | null, b: TaskChatContext): boolean {
  return a !== null && a.taskId === b.taskId && a.executionId === b.executionId && a.qid === b.qid;
}

function contextTitle(context: TaskChatContext): string {
  return `${context.taskName} / ${context.qid}`;
}

interface ServerMessage {
  role: string;
  content: string;
  /**
   * Server-side this is base64 image data, but the frontend only carries a
   * boolean indicator (the image bytes are not retained client side after
   * send). We round-trip presence-only via the truthy-string trick.
   */
  attached_image?: string | null;
  steer?: {
    request_id: string;
    entry_id?: string | null;
    placement?: "exact" | "approximate";
  } | null;
  /** An assistant answer's runtime entry; only such an answer can be branched from. */
  entry_id?: string | null;
  created_at?: string | null;
}

interface ServerSessionSummary {
  session_id: string;
  title: string;
  /** A task chat's context, or `{ investigation }` for an investigation. */
  context?: TaskChatContext | { investigation: InvestigationTarget } | null;
  message_count: number;
  branch?: { source_session_id: string; source_entry_id: string } | null;
  created_at: string;
  updated_at: string;
}

interface ServerSessionDetail extends ServerSessionSummary {
  messages: ServerMessage[];
}

function serverMessageToLocal(m: ServerMessage): ChatMessage {
  return {
    role: m.role as ChatMessage["role"],
    content: m.content,
    attachedImage: Boolean(m.attached_image),
    ...(m.steer
      ? {
          steer: {
            requestId: m.steer.request_id,
            entryId: m.steer.entry_id ?? null,
            placement: m.steer.placement ?? "exact",
          },
        }
      : {}),
    ...(m.role === "assistant" && m.entry_id ? { entryId: m.entry_id } : {}),
  };
}

/**
 * The assistant message with its rating set or cleared. Plain-text answers
 * (older sessions, error-free fallbacks) are wrapped into the blocks form so
 * the rating has a place to live. Error messages are not ratable.
 */
function withFeedback(message: ChatMessage, feedback: AnswerFeedback | null): ChatMessage | null {
  if (message.content.startsWith("Error: ")) return null;
  let payload: CopilotBlocksResult;
  try {
    const parsed = JSON.parse(message.content) as CopilotBlocksResult;
    if (!Array.isArray(parsed.blocks)) throw new Error("not blocks");
    payload = parsed;
  } catch {
    payload = {
      blocks: [{ type: "text", content: message.content, chart: null }],
      assessment: null,
    };
  }
  const { feedback: _previous, ...rest } = payload;
  const next: CopilotBlocksResult = feedback ? { ...rest, feedback } : rest;
  return { ...message, content: JSON.stringify(next) };
}

function localMessageToServer(m: ChatMessage): ServerMessage {
  return {
    role: m.role,
    content: m.content,
    attached_image: m.attachedImage ? "1" : null,
    ...(m.steer
      ? {
          steer: {
            request_id: m.steer.requestId,
            entry_id: m.steer.entryId,
            placement: m.steer.placement,
          },
        }
      : {}),
    ...(m.entryId ? { entry_id: m.entryId } : {}),
  };
}

/** Split a stored context into the task chat context and the investigation target. */
function fromServerContext(raw: ServerSessionSummary["context"]): {
  context: TaskChatContext | null;
  investigation: InvestigationTarget | null;
} {
  const investigation = investigationFromStored(raw);
  if (investigation || (raw && "investigation" in raw)) return { context: null, investigation };
  return {
    context: (raw as TaskChatContext | null | undefined) ?? null,
    investigation: null,
  };
}

function toServerContext(session: CopilotChatSession): ServerSessionSummary["context"] {
  return session.investigation ? { investigation: session.investigation } : session.context;
}

function fromServerBranch(raw: ServerSessionSummary["branch"]): ChatBranchOrigin | null {
  return raw
    ? { sourceSessionId: raw.source_session_id, sourceEntryId: raw.source_entry_id }
    : null;
}

function summaryToSession(s: ServerSessionSummary): CopilotChatSession {
  return {
    id: s.session_id,
    title: s.title,
    ...fromServerContext(s.context),
    messages: [],
    createdAt: toTimestamp(s.created_at),
    updatedAt: toTimestamp(s.updated_at),
    messagesLoaded: false,
    branch: fromServerBranch(s.branch),
  };
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiListSessions(): Promise<ServerSessionSummary[]> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}`, {
    headers: buildHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  const data = (await res.json()) as { sessions: ServerSessionSummary[] };
  return data.sessions;
}

async function apiGetSession(sessionId: string): Promise<ServerSessionDetail> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`, {
    headers: buildHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to get session: ${res.status}`);
  return (await res.json()) as ServerSessionDetail;
}

async function apiCreateSession(session: CopilotChatSession): Promise<void> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({
      session_id: session.id,
      title: session.title,
      context: toServerContext(session),
      messages: [],
    }),
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
}

async function apiUpdateSession(
  sessionId: string,
  patch: { title?: string; messages?: ServerMessage[] },
): Promise<void> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: buildHeaders(),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`Failed to update session: ${res.status}`);
}

async function apiDeleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete session: ${res.status}`);
  }
}

type BranchReply =
  | { ok: true; session: ServerSessionDetail }
  | {
      ok: false;
      message: string;
      /**
       * No answer from the server, a server error, or a conflict (the branch is still
       * being created, or the chat is busy): the branch may have been made or may still
       * be, so a retry sends the same target ID and gets that branch. Otherwise nothing
       * was made.
       */
      retryable: boolean;
    };

/** Branch `sessionId` at its saved answer `entryId` into the new session `targetId`. */
async function apiBranchSession(
  sessionId: string,
  entryId: string,
  targetId: string,
): Promise<BranchReply> {
  let res: Response;
  const request: CreateCopilotChatBranchRequest = {
    entry_id: entryId,
    target_session_id: targetId,
  };
  try {
    res = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}/branches`, {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(request),
    });
  } catch {
    return { ok: false, message: "The connection failed. Try again.", retryable: true };
  }
  if (res.ok) {
    try {
      return { ok: true, session: (await res.json()) as ServerSessionDetail };
    } catch {
      // The branch was made, but its reply was lost on the way: the retry, under
      // the same target ID, gets that branch.
      return { ok: false, message: "The connection failed. Try again.", retryable: true };
    }
  }
  return {
    ok: false,
    message: await readErrorResponse(res),
    retryable: res.status >= 500 || res.status === 409,
  };
}

/** Request for one turn; a chat about a task result names it in `task`. */
function buildTurnRequest(
  session: CopilotChatSession | undefined,
  sessionId: string,
  message: string,
  history: ChatMessage[],
  modelOverride: ModelOverride | null,
  approval: SendOptions["approval"],
  images: ChatImageAttachment[] = [],
  thinkingLevel?: ChatThinkingLevel,
  page?: PageContext | null,
  continueRun = false,
  requestId: string = createRequestId(),
): { url: string; body: Record<string, unknown> } {
  const context = session?.context;
  const investigation = session?.investigation;
  return {
    url: `${BASE_URL}/copilot/chat/stream`,
    body: {
      ...(investigation && !history.some((message) => message.role === "user")
        ? { investigation: toInvestigationRequest(investigation) }
        : {}),
      ...(approval ? { approval } : {}),
      ...(images.length ? { images } : {}),
      ...(page
        ? {
            page: {
              path: page.path,
              title: page.title,
              ...(page.flow
                ? {
                    flow: {
                      name: page.flow.name,
                      chip_id: page.flow.chipId ?? null,
                      code: page.flow.code,
                      dirty: page.flow.dirty,
                    },
                  }
                : {}),
              ...(page.metricScript
                ? {
                    metric_script: {
                      script_id: page.metricScript.scriptId,
                      name: page.metricScript.name,
                      code: page.metricScript.code,
                      dirty: page.metricScript.dirty ?? false,
                    },
                  }
                : {}),
              ...(page.dashboard
                ? {
                    dashboard: {
                      dashboard_id: page.dashboard.dashboardId,
                      name: page.dashboard.name,
                      description: page.dashboard.description || null,
                      visibility: page.dashboard.visibility ?? null,
                      chip_id: page.dashboard.chipId ?? null,
                      version: page.dashboard.version ?? null,
                      code: page.dashboard.code,
                      dirty: page.dashboard.dirty ?? false,
                    },
                  }
                : {}),
            },
          }
        : {}),
      ...(context
        ? {
            task: {
              task_name: context.taskName,
              chip_id: context.chipId,
              qid: context.qid,
              execution_id: context.executionId,
              task_id: context.taskId,
            },
          }
        : {}),
      message,
      // Required by the Pi backend, which restores conversation state from the
      // persisted session rather than from the request body.
      session_id: sessionId,
      request_id: requestId,
      conversation_history: history.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      model_override: modelOverride,
      ...(thinkingLevel ? { thinking_level: thinkingLevel } : {}),
      ...(continueRun ? { continue_run: true } : {}),
    },
  };
}

/** The request headers, naming `projectId` (the one a steer was sent from) as the project. */
function headersFor(projectId: string | null | undefined): Record<string, string> {
  const headers = buildHeaders();
  delete headers["X-Project-Id"];
  return projectId ? { ...headers, "X-Project-Id": projectId } : headers;
}

/**
 * A steer request's reply. Only a reply from the runtime settles where the steer
 * stands; a request refused before it got there (a bad request, a lost session)
 * failed. A request that got no answer, or that the API could not pass on, may
 * still have been admitted, so it is unconfirmed until a status lookup says.
 */
async function readSteerReply(response: Response): Promise<SteerReply> {
  if (response.ok || response.status === 409) {
    try {
      return steerReplyStatus(await response.json());
    } catch {
      return { status: "unconfirmed" };
    }
  }
  if (response.status >= 500) return { status: "unconfirmed" };
  return { status: "failed", reason: await readErrorResponse(response) };
}

/**
 * Send a steer to the runtime. A request that fails on the network is retried
 * once with the same request ID, so the steer is admitted at most once.
 */
async function apiSteer(
  sessionId: string,
  requestId: string,
  turnRequestId: string,
  message: string,
  projectId: string | null | undefined,
): Promise<SteerReply> {
  const send = () =>
    fetch(`${BASE_URL}/copilot/chat/steer`, {
      method: "POST",
      headers: headersFor(projectId),
      // Only the turn it is sent to admits it: a copy that arrives later never
      // steers another turn.
      body: JSON.stringify({
        session_id: sessionId,
        request_id: requestId,
        turn_request_id: turnRequestId,
        message,
      }),
    });
  let response: Response;
  try {
    response = await send();
  } catch {
    try {
      response = await send();
    } catch {
      return { status: "unconfirmed" };
    }
  }
  return readSteerReply(response);
}

/** Where a steer stands, read from the runtime's store. Read-only: it never sends the steer. */
async function apiSteerStatus(
  sessionId: string,
  requestId: string,
  projectId: string | null | undefined,
): Promise<SteerReply> {
  try {
    const response = await fetch(`${BASE_URL}/copilot/chat/steer/status`, {
      method: "POST",
      headers: headersFor(projectId),
      body: JSON.stringify({ session_id: sessionId, request_id: requestId }),
    });
    if (!response.ok) return { status: "unconfirmed" };
    return steerReplyStatus(await response.json());
  } catch {
    return { status: "unconfirmed" };
  }
}

/** How long to wait before asking again about a steer the runtime still holds queued. */
const STEER_CHECK_DELAYS_MS = [300, 1000, 2000, 4000, 8000];

function resultToBlocks(payload: Record<string, unknown>): CopilotBlocksResult {
  if (Array.isArray(payload.blocks)) return payload as unknown as CopilotBlocksResult;
  const text =
    typeof payload.explanation === "string" ? payload.explanation : JSON.stringify(payload);
  return {
    blocks: [{ type: "text", content: text, chart: null }],
    assessment: null,
  };
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const CopilotChatSessionCtx = createContext<CopilotChatSessionContextValue | null>(null);

export function CopilotChatSessionProvider({
  children,
  owner,
  project,
}: {
  children: React.ReactNode;
  /**
   * The signed-in user, to keep unresolved steers and running turns across a reload
   * for them only: null while not known yet, undefined to keep them in memory only.
   */
  owner?: string | null;
  /**
   * The project the user has open. A turn is followed only in the project it was sent
   * from: null while not known yet (nothing is restored), undefined to follow every turn.
   */
  project?: string | null;
}) {
  const [sessions, setSessions] = useState<CopilotChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [runs, setRuns] = useState<Record<string, SessionRun>>({});
  const [steers, setSteers] = useState<Record<string, PendingSteer[]>>({});
  const [notices, setNotices] = useState<Record<string, string>>({});
  // The user whose stored steers were restored into `steers`.
  const [restoredFor, setRestoredFor] = useState<string | null>(null);
  const restoredForRef = useRef<string | null>(null);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const projectRef = useRef(project);
  projectRef.current = project;
  // Whether the session list came from the server: only then is a session missing from it gone.
  const sessionsListed = useRef(false);

  // Mirrors readable from async stream code without stale closures.
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  // Sessions whose messages have already been fetched (or are in flight).
  const messagesFetched = useRef<Set<string>>(new Set());
  // POST /sessions in-flight per id. PATCH/DELETE await this so we never
  // hit a 404 from racing against the create.
  const pendingCreates = useRef<Map<string, Promise<void>>>(new Map());
  const controllers = useRef<Map<string, AbortController>>(new Map());
  // The project each streaming turn was sent from.
  const turnProjects = useRef<Map<string, string | null>>(new Map());
  // Turns whose stream ended, by session: their pointer goes once a save holding the end lands.
  const endedTurns = useRef<Map<string, { requestId: string; seq: number }>>(new Map());
  // How many transcript updates each session had; a save reports the one it holds.
  const transcriptSeq = useRef<Map<string, number>>(new Map());
  // Turns of this tab not streamed now (see DetachedTurn).
  const [detachedTurns, setDetachedTurns] = useState<Record<string, DetachedTurn>>({});
  const detachedRef = useRef(detachedTurns);
  detachedRef.current = detachedTurns;
  // Bumped when a detached stream has ended, so the restore runs again.
  const [resumeTick, setResumeTick] = useState(0);
  // Who hears the turns' notable moments (see subscribeChatEvents).
  const chatEventListeners = useRef<Set<(event: ChatTurnEvent) => void>>(new Set());
  const subscribeChatEvents = useCallback((listener: (event: ChatTurnEvent) => void) => {
    chatEventListeners.current.add(listener);
    return () => {
      chatEventListeners.current.delete(listener);
    };
  }, []);
  // Unmounted (signed out, layout gone): stop watching every turn, so no stream
  // keeps reconnecting with nobody to show it. The turns themselves run on.
  useEffect(() => {
    const live = controllers.current;
    return () => {
      for (const controller of live.values()) controller.abort(UNMOUNTED);
    };
  }, []);

  const awaitCreate = useCallback(async (sessionId: string) => {
    const promise = pendingCreates.current.get(sessionId);
    if (promise) {
      try {
        await promise;
      } catch {
        // create errored; rollback happens in createNewSession's catch
      }
    }
  }, []);

  // ------- initial load -------

  useEffect(() => {
    let cancelled = false;
    apiListSessions()
      .then((list) => {
        if (cancelled) return;
        sessionsListed.current = true;
        // Keep sessions created locally before the list arrived.
        setSessions((prev) => {
          const serverIds = new Set(list.map((s) => s.session_id));
          return [...prev.filter((s) => !serverIds.has(s.id)), ...list.map(summaryToSession)];
        });
      })
      .catch(() => {
        // Network/auth failure — start empty. Errors surface on next CRUD.
      })
      .finally(() => {
        if (!cancelled) setIsLoadingSessions(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ------- lazy load active session messages -------

  // Detail requests in flight, by session, so the active chat and a restore share one.
  const messageLoads = useRef<Map<string, Promise<ChatMessage[]>>>(new Map());

  /** The session's saved messages: the ones loaded, or fetched now and kept. */
  const loadSessionMessages = useCallback((sessionId: string): Promise<ChatMessage[]> => {
    const loaded = sessionsRef.current.find((s) => s.id === sessionId);
    if (loaded?.messagesLoaded) return Promise.resolve(loaded.messages);
    const inFlight = messageLoads.current.get(sessionId);
    if (inFlight) return inFlight;
    messagesFetched.current.add(sessionId);
    const load = apiGetSession(sessionId)
      .then((detail) => {
        const messages = detail.messages.map(serverMessageToLocal);
        const update = (s: CopilotChatSession): CopilotChatSession =>
          // Never over what the chat already shows: a turn may have updated it meanwhile.
          s.id === sessionId && !s.messagesLoaded
            ? {
                ...s,
                title: detail.title,
                ...(detail.context
                  ? fromServerContext(detail.context)
                  : {
                      context: s.context,
                      investigation: s.investigation ?? null,
                    }),
                messages,
                updatedAt: toTimestamp(detail.updated_at),
                messagesLoaded: true,
                branch: fromServerBranch(detail.branch),
              }
            : s;
        sessionsRef.current = sessionsRef.current.map(update);
        setSessions((prev) => prev.map(update));
        return sessionsRef.current.find((s) => s.id === sessionId)?.messages ?? messages;
      })
      .catch((error: unknown) => {
        messagesFetched.current.delete(sessionId);
        throw error;
      })
      .finally(() => {
        messageLoads.current.delete(sessionId);
      });
    messageLoads.current.set(sessionId, load);
    return load;
  }, []);

  useEffect(() => {
    if (!activeSessionId) return;
    if (messagesFetched.current.has(activeSessionId)) return;
    loadSessionMessages(activeSessionId).catch(() => {
      // Asked again the next time the chat is opened.
    });
  }, [activeSessionId, loadSessionMessages]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );

  // ------- pending steers -------

  // Readable from stream code, which outlives the render that started it.
  const steersRef = useRef(steers);
  steersRef.current = steers;
  // The stream each steer was sent to, by request ID: a reply after it ended has no stream to report it.
  const steerStreams = useRef<Map<string, AbortController>>(new Map());
  // Steer requests whose reply has not come back yet.
  const steerPosts = useRef<Set<string>>(new Set());
  // Where the turn streaming in each session starts in its conversation.
  const turnAnchors = useRef<Map<string, SteerAnchor>>(new Map());
  // The request ID of the turn streaming in each session; a steer names it.
  const turnRequests = useRef<Map<string, string>>(new Map());

  const updateSteers = useCallback(
    (sessionId: string, update: (list: PendingSteer[]) => PendingSteer[]) => {
      const apply = (prev: Record<string, PendingSteer[]>) => {
        const list = update(prev[sessionId] ?? []);
        if (list.length === 0) {
          if (!(sessionId in prev)) return prev;
          const { [sessionId]: _removed, ...rest } = prev;
          return rest;
        }
        return { ...prev, [sessionId]: list };
      };
      steersRef.current = apply(steersRef.current);
      setSteers(apply);
      // Stored before any request about it is sent, so a reload finds it.
      const who = ownerRef.current;
      if (typeof who === "string") {
        storeSessionSteers(
          who,
          sessionId,
          steersRef.current[sessionId] ?? [],
          restoredForRef.current !== who,
        );
      }
    },
    [],
  );
  // Steers restored after a reload, by session and request ID, to ask about once the session's messages load.
  const toReconcile = useRef<Set<string>>(new Set());

  // ------- session CRUD -------

  const switchSession = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
  }, []);

  const createNewSession = useCallback(
    (context: TaskChatContext | null = null, options: NewSessionOptions = {}): string => {
      const id = generateId();
      const ts = Date.now();
      const local: CopilotChatSession = {
        id,
        title: options.title ?? (context ? contextTitle(context) : DEFAULT_TITLE),
        context,
        investigation: options.investigation ?? null,
        messages: [],
        createdAt: ts,
        updatedAt: ts,
        messagesLoaded: true,
      };
      messagesFetched.current.add(id);
      sessionsRef.current = [local, ...sessionsRef.current];
      setSessions((prev) => [local, ...prev]);
      setActiveSessionId(id);
      const createPromise = apiCreateSession(local)
        .then(() => {
          pendingCreates.current.delete(id);
        })
        .catch((err) => {
          pendingCreates.current.delete(id);
          // Roll back if the server refused (e.g. duplicate id).
          setSessions((prev) => prev.filter((s) => s.id !== id));
          messagesFetched.current.delete(id);
          setActiveSessionId((current) => (current === id ? null : current));
          throw err;
        });
      pendingCreates.current.set(id, createPromise);
      return id;
    },
    [],
  );

  const hasSession = useCallback(
    (sessionId: string) => sessionsRef.current.some((s) => s.id === sessionId),
    [],
  );

  const findSessionByContext = useCallback(
    (context: TaskChatContext) => sessions.find((s) => sameContext(s.context, context)) ?? null,
    [sessions],
  );

  const deleteSession = useCallback(
    (sessionId: string) => {
      controllers.current.get(sessionId)?.abort();
      // The API stops the deleted chat's turn; nothing of it is restored.
      if (typeof ownerRef.current === "string") forgetStoredTurn(ownerRef.current, sessionId);
      endedTurns.current.delete(sessionId);
      setDetachedTurns((prev) => withoutKey(prev, sessionId));
      // Its steers go with it, also from the tab's storage.
      updateSteers(sessionId, () => []);
      for (const key of toReconcile.current) {
        if (key.startsWith(`${sessionId}\0`)) toReconcile.current.delete(key);
      }
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      setActiveSessionId((current) => (current === sessionId ? null : current));
      messagesFetched.current.delete(sessionId);
      (async () => {
        try {
          await awaitCreate(sessionId);
          await apiDeleteSession(sessionId);
        } catch {
          // If delete failed, the session may still exist server-side. Reload.
          apiListSessions().then((list) => {
            setSessions(list.map(summaryToSession));
          });
        }
      })();
    },
    [awaitCreate, updateSteers],
  );

  const renameSession = useCallback(
    (sessionId: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return;
      const update = (s: CopilotChatSession): CopilotChatSession =>
        s.id === sessionId ? { ...s, title: trimmed } : s;
      sessionsRef.current = sessionsRef.current.map(update);
      setSessions((prev) => prev.map(update));
      (async () => {
        await awaitCreate(sessionId);
        apiUpdateSession(sessionId, { title: trimmed }).catch(() => {
          /* swallow — local state is the source of truth until reload */
        });
      })();
    },
    [awaitCreate],
  );

  // Transcript saves by session: at most one PATCH in flight, and the newest
  // snapshot waiting behind it. Each save replaces the whole transcript and the
  // server keeps no version, so an older snapshot must never land after a newer
  // one; one still waiting is replaced by the newer, which holds what it held.
  const saveQueues = useRef<
    Map<
      string,
      {
        running: boolean;
        next: {
          owner: string | null | undefined;
          messages: ChatMessage[];
          seq: number;
          patch: { messages: ServerMessage[]; title?: string };
        } | null;
      }
    >
  >(new Map());

  /** A save of `messages` was acknowledged: the steers it holds are saved with it. */
  const savedTranscript = useRef<(sessionId: string, messages: ChatMessage[], seq: number) => void>(
    () => {},
  );

  const saveTranscript = useCallback(
    (
      sessionId: string,
      messages: ChatMessage[],
      patch: { messages: ServerMessage[]; title?: string },
      seq: number,
    ) => {
      let queue = saveQueues.current.get(sessionId);
      if (!queue) {
        queue = { running: false, next: null };
        saveQueues.current.set(sessionId, queue);
      }
      const owner = ownerRef.current;
      const waiting = queue.next;
      // A derived title the waiting snapshot carried goes with the one replacing it.
      const title = patch.title ?? (waiting?.owner === owner ? waiting?.patch.title : undefined);
      queue.next = {
        owner,
        messages,
        seq,
        patch: title === undefined ? patch : { ...patch, title },
      };
      if (queue.running) return;
      const q = queue;
      q.running = true;
      void (async () => {
        try {
          while (q.next) {
            const job = q.next;
            q.next = null;
            // Saved only for the user who wrote it: never under another sign-in.
            if (job.owner !== ownerRef.current) continue;
            try {
              await awaitCreate(sessionId);
              if (job.owner !== ownerRef.current) continue;
              await apiUpdateSession(sessionId, job.patch);
            } catch {
              // Local state is the source of truth until reload; a steer this save
              // held stays recoverable (see PendingSteer.saving).
              continue;
            }
            savedTranscript.current(sessionId, job.messages, job.seq);
          }
        } finally {
          q.running = false;
          if (!q.next && saveQueues.current.get(sessionId) === q) {
            saveQueues.current.delete(sessionId);
          }
        }
      })();
    },
    [awaitCreate],
  );

  const updateSessionMessages = useCallback(
    (sessionId: string, messages: ChatMessage[], options: { save?: boolean } = {}) => {
      // Derive a sidebar title from the first user message while the session
      // still has the default placeholder, and send it in the same PATCH.
      const session = sessionsRef.current.find((s) => s.id === sessionId);
      let derivedTitle: string | undefined;
      if (session?.title === DEFAULT_TITLE) {
        const firstUser = messages.find((m) => m.role === "user");
        if (firstUser?.content) derivedTitle = firstUser.content.slice(0, 50);
      }
      const update = (s: CopilotChatSession): CopilotChatSession =>
        s.id === sessionId
          ? {
              ...s,
              title: derivedTitle ?? s.title,
              messages,
              updatedAt: Date.now(),
              messagesLoaded: true,
            }
          : s;
      sessionsRef.current = sessionsRef.current.map(update);
      setSessions((prev) => prev.map(update));
      // Shown only: a restore folds the turn over the saved chat and saves once it can.
      if (options.save === false) return;

      const seq = (transcriptSeq.current.get(sessionId) ?? 0) + 1;
      transcriptSeq.current.set(sessionId, seq);
      const patch: { messages: ServerMessage[]; title?: string } = {
        messages: messages.map(localMessageToServer),
      };
      if (derivedTitle !== undefined) patch.title = derivedTitle;
      saveTranscript(sessionId, messages, patch, seq);
    },
    [saveTranscript],
  );

  const setMessageFeedback = useCallback(
    (sessionId: string, index: number, feedback: AnswerFeedback | null) => {
      const session = sessionsRef.current.find((s) => s.id === sessionId);
      const message = session?.messages[index];
      if (!session || !message || message.role !== "assistant") return;
      const updated = withFeedback(message, feedback);
      if (!updated) return;
      updateSessionMessages(
        sessionId,
        session.messages.map((m, i) => (i === index ? updated : m)),
      );
    },
    [updateSessionMessages],
  );

  // ------- streaming -------

  const setRun = useCallback(
    (sessionId: string, update: ((run: SessionRun) => SessionRun) | null) => {
      setRuns((prev) => {
        if (update === null) {
          if (!(sessionId in prev)) return prev;
          const { [sessionId]: _removed, ...rest } = prev;
          return rest;
        }
        const run = prev[sessionId];
        return run ? { ...prev, [sessionId]: update(run) } : prev;
      });
    },
    [],
  );

  /**
   * Stream one turn into its session: the turn's own request, or a reattach to a
   * turn this tab started before the provider watched it (a reload, a remount, a
   * project switch back). Every stream of the turn names the project it was sent
   * from, so a reattach after the user switched projects is never sent under the
   * other project.
   */
  const runTurn = useCallback(
    (plan: TurnPlan) => {
      const { sessionId, controller, history, continuing, original } = plan;
      const turnRequestId = plan.requestId;
      // What precedes the live answer: the history, the user's message, and the parts of
      // the answer that steers closed off, each followed by the steer, in transcript order.
      let shown = plan.shown;
      // Where this turn's user message is in `shown`; steers of earlier turns go before it.
      let userAt = plan.userAt;
      turnAnchors.current.set(sessionId, {
        start: history.length,
        userText: continuing ? null : (shown[userAt]?.content ?? null),
      });
      turnRequests.current.set(sessionId, turnRequestId);
      turnProjects.current.set(sessionId, plan.projectId);
      // The user the turn's pointer is stored for; nothing is written for anyone else.
      const owner = ownerRef.current;

      // The live turn is folded locally and mirrored into state, so the final
      // message is built from what was streamed even if renders lag behind.
      let turn: LiveTurn = { steps: [], startedAt: plan.startedAt };
      let connection: TurnConnection = {
        state: plan.reattach ? "reconnecting" : "live",
        lastUpdateAt: plan.lastUpdateAt,
        attempt: 0,
      };
      let statusMessage: string | null = null;
      setRuns((prev) => ({
        ...prev,
        [sessionId]: { turn, statusMessage: null, connection },
      }));

      // Keep the turn's pointer told what it last did, for a chat restored after a
      // reload: only when the activity changes, or every POINTER_REFRESH_MS.
      let storedActivity: TurnActivitySnapshot | null = null;
      let storedAt = 0;
      const remember = () => {
        if (typeof owner !== "string" || owner !== ownerRef.current) return;
        const activity = activitySnapshot(turn.steps, statusMessage);
        if (
          sameActivity(activity, storedActivity) &&
          connection.lastUpdateAt - storedAt < POINTER_REFRESH_MS
        ) {
          return;
        }
        storedActivity = activity;
        storedAt = connection.lastUpdateAt;
        patchStoredTurn(owner, sessionId, turnRequestId, {
          activity,
          lastUpdateAt: connection.lastUpdateAt,
        });
      };
      // Each notable moment is raised once per turn: a reattach or a restore replays the
      // turn's events from its start, and the pointer remembers what was raised before.
      const notified = new Set<ChatEventKind>(plan.notified ?? []);
      const notify = (kind: ChatEventKind, detail?: string) => {
        if (notified.has(kind) || owner !== ownerRef.current) return;
        notified.add(kind);
        if (typeof owner === "string") {
          patchStoredTurn(owner, sessionId, turnRequestId, { notified: [...notified] });
        }
        const event: ChatTurnEvent = {
          kind,
          sessionId,
          requestId: turnRequestId,
          owner,
          projectId: plan.projectId,
          chatTitle: sessionsRef.current.find((s) => s.id === sessionId)?.title ?? "Chat",
          ...(detail ? { detail } : {}),
        };
        for (const listener of [...chatEventListeners.current]) listener(event);
      };
      const setConnection = (patch: Partial<TurnConnection>) => {
        connection = { ...connection, ...patch };
        const next = connection;
        setRun(sessionId, (run) => ({ ...run, connection: next }));
        if (patch.lastUpdateAt !== undefined) remember();
      };
      const updateTurn = (fold: (t: LiveTurn) => LiveTurn) => {
        turn = fold(turn);
        const next = turn;
        statusMessage = null;
        // New streamed activity supersedes a status such as context compaction.
        setRun(sessionId, (run) => ({ ...run, turn: next, statusMessage: null }));
        remember();
      };

      const finish = (result: CopilotBlocksResult, entryId?: string) => {
        const trace = toPersistedTrace(turn, Date.now());
        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: JSON.stringify(trace ? { ...result, trace } : result),
          // The answer's runtime entry, kept with the message so it can be branched from.
          ...(entryId ? { entryId } : {}),
        };
        updateSessionMessages(sessionId, [...shown, assistantMsg]);
      };

      // Where the answer of a run recovered from an earlier request goes: after
      // the last steer it placed before this turn's message, or (none) right
      // before that message.
      let recoveredAt: number | null = null;

      /**
       * A steer landed in the transcript: the answer so far becomes a message, the
       * steer follows it, and the answer goes on from there. Once per request ID.
       */
      const placeSteer = (payload: {
        request_id?: unknown;
        text?: unknown;
        result?: unknown;
        entry_id?: unknown;
        before_turn?: unknown;
      }) => {
        if (typeof payload.request_id !== "string") return;
        const requestId = payload.request_id;
        if (placedSteers.has(requestId) || shown.some((m) => m.steer?.requestId === requestId)) {
          return;
        }
        placedSteers.add(requestId);
        const pending = (steersRef.current[sessionId] ?? []).find((s) => s.requestId === requestId);
        const text =
          typeof payload.text === "string" && payload.text ? payload.text : pending?.text;
        const entryId = typeof payload.entry_id === "string" ? payload.entry_id : null;
        const now = Date.now();
        const trace = toPersistedTrace(turn, now);
        const segment = payload.result
          ? resultToBlocks(payload.result as Record<string, unknown>)
          : { blocks: [], assessment: null };
        const before: ChatMessage[] =
          segment.blocks.length || trace
            ? [
                {
                  role: "assistant",
                  content: JSON.stringify(trace ? { ...segment, trace } : segment),
                },
              ]
            : [];
        if (payload.before_turn === true && userAt >= 0) {
          // A run recovered after the runtime died placed this steer before this
          // turn's message: it belongs to an earlier turn. Put it in the turn it was
          // sent to if the chat remembers it, else just before this turn's message.
          // Either way the answer it interrupted is not split here: approximate.
          // What that run streamed before it goes before it, in the same turn.
          const anchor =
            pending?.anchor && pending.anchor.start < history.length ? pending.anchor : undefined;
          const placed =
            anchor && text ? placeLateSteer(shown, { requestId, text, entryId, anchor }) : null;
          if (placed) {
            userAt += placed.length - shown.length;
            shown = placed;
          } else if (text) {
            const steerMessage: ChatMessage = {
              role: "user",
              content: text,
              steer: { requestId, entryId, placement: "approximate" },
            };
            shown = [...shown.slice(0, userAt), steerMessage, ...shown.slice(userAt)];
            userAt += 1;
          }
          const at = shown.findIndex((m) => m.steer?.requestId === requestId);
          const into = at >= 0 ? at : userAt;
          shown = [...shown.slice(0, into), ...before, ...shown.slice(into)];
          if (into <= userAt) userAt += before.length;
          // The recovered run's answer to it follows it, up to this turn's own message.
          recoveredAt = (at >= 0 ? at + before.length : into + before.length - 1) + 1;
        } else {
          shown = [...shown, ...before];
          if (text) {
            shown = [
              ...shown,
              {
                role: "user",
                content: text,
                steer: { requestId, entryId, placement: "exact" },
              },
            ];
          }
        }
        // Kept, out of sight, until a save holding it is acknowledged.
        updateSteers(sessionId, (list) =>
          patchSteer(advanceSteer(list, requestId, "delivered", undefined, entryId), requestId, {
            saving: true,
          }),
        );
        updateSessionMessages(sessionId, shown);
        turn = { steps: [], startedAt: now };
        const next = turn;
        setRun(sessionId, (run) => ({ ...run, turn: next }));
        steerStreams.current.delete(requestId);
        toReconcile.current.delete(`${sessionId}\0${requestId}`);
      };
      const placedSteers = new Set<string>();
      // Where the turn began, for a reattached stream that replays it from there.
      const turnStart = { shown, userAt };

      /**
       * A reattached stream replays the turn from its start: fold it again from
       * there. Steers it places are placed again; nothing is saved until it does.
       */
      const restartFold = () => {
        shown = turnStart.shown;
        userAt = turnStart.userAt;
        recoveredAt = null;
        placedSteers.clear();
        turn = { steps: [], startedAt: turn.startedAt };
        const next = turn;
        setRun(sessionId, (run) => ({ ...run, turn: next, statusMessage: null }));
      };

      /**
       * This turn's own message was placed: what streamed so far was a run
       * recovered from an earlier request, answering a steer of an earlier turn.
       * It is closed off and kept with that turn, before this turn's message.
       */
      const startTurn = (payload: { result?: unknown }) => {
        if (userAt < 0) return;
        const now = Date.now();
        const trace = toPersistedTrace(turn, now);
        const segment = payload.result
          ? resultToBlocks(payload.result as Record<string, unknown>)
          : { blocks: [], assessment: null };
        if (!segment.blocks.length && !trace) return;
        const into = Math.min(recoveredAt ?? userAt, userAt);
        const message: ChatMessage = {
          role: "assistant",
          content: JSON.stringify(trace ? { ...segment, trace } : segment),
        };
        shown = [...shown.slice(0, into), message, ...shown.slice(into)];
        userAt += 1;
        recoveredAt = null;
        updateSessionMessages(sessionId, shown);
        turn = { steps: [], startedAt: now };
        const next = turn;
        setRun(sessionId, (run) => ({ ...run, turn: next }));
      };

      (async () => {
        // What the turn's pointer becomes when this stream ends: `ended` once the
        // turn's end is saved; kept while the turn may run on unwatched.
        // `forget`: a restored turn the chat cannot follow; it is not tried again.
        let outcome: "ended" | "not_found" | "watching" | "lost" | "forget" = "ended";
        try {
          await awaitCreate(sessionId);
          const { url, body } = plan;
          let gotResult = false;

          /**
           * One stream of the turn: the request itself, or a reattach after the
           * last one dropped. Resolves `lost` when the stream ended or went silent
           * before the turn did, so the turn may still be running; throws for an
           * answer that failed, and when the user stopped the turn.
           */
          const streamOnce = async (reattach: boolean): Promise<"done" | "lost"> => {
            const attempt = new AbortController();
            const forward = () => attempt.abort(controller.signal.reason);
            controller.signal.addEventListener("abort", forward, { once: true });
            // The runtime sends a heartbeat every few seconds, also while a tool
            // waits: a stream that stays silent past STREAM_SILENCE_MS is dead.
            let silence: ReturnType<typeof setTimeout> | undefined;
            const heard = () => {
              clearTimeout(silence);
              silence = setTimeout(() => attempt.abort(STALE_STREAM), STREAM_SILENCE_MS);
            };
            const lost = (): "lost" => {
              if (controller.signal.aborted) throw controller.signal.reason;
              return "lost";
            };
            try {
              heard();
              let response: Response;
              try {
                response = await fetch(url, {
                  method: "POST",
                  headers: headersFor(plan.projectId),
                  body: JSON.stringify(reattach ? { ...body, reattach: true } : body),
                  signal: attempt.signal,
                });
              } catch {
                return lost();
              }
              if (!response.ok) {
                // A proxy or the API restarting: the turn may well run on.
                if (STREAM_LOST_STATUS.has(response.status)) return lost();
                throw new Error(await readErrorResponse(response));
              }
              const reader = response.body?.getReader();
              if (!reader) throw new Error("No response body");
              if (reattach) restartFold();
              setConnection({ state: "live", attempt: 0 });

              const decoder = new TextDecoder();
              let buffer = "";
              while (true) {
                let chunk: ReadableStreamReadResult<Uint8Array>;
                try {
                  chunk = await reader.read();
                } catch {
                  return lost();
                }
                const { done, value } = chunk;
                if (done) break;
                heard();
                buffer += decoder.decode(value, { stream: true });
                const { events, remainder } = consumeSSEEvents(buffer);
                buffer = remainder;
                // Heartbeats carry no event: only the turn's own events count as an update.
                if (events.length > 0) setConnection({ lastUpdateAt: Date.now() });

                for (const evt of events) {
                  const payload = JSON.parse(evt.data);
                  if (evt.event === "delta") {
                    updateTurn((t) => ({
                      ...t,
                      steps: appendDelta(t.steps, "text", payload.text),
                    }));
                  } else if (evt.event === "thinking") {
                    updateTurn((t) => ({
                      ...t,
                      steps: appendDelta(t.steps, "thinking", payload.text),
                    }));
                  } else if (evt.event === "tool_draft") {
                    updateTurn((t) => ({
                      ...t,
                      steps: startDraft(t.steps, payload),
                    }));
                  } else if (evt.event === "tool_args_delta") {
                    updateTurn((t) => ({
                      ...t,
                      steps: appendArgsDelta(t.steps, payload),
                    }));
                  } else if (evt.event === "tool_start") {
                    updateTurn((t) => ({
                      ...t,
                      steps: startTool(t.steps, payload),
                    }));
                    if (payload.tool === EXPERT_WAIT_TOOL) notify("expert");
                  } else if (evt.event === "tool_end") {
                    updateTurn((t) => ({ ...t, steps: endTool(t.steps, payload) }));
                    if (payload.tool === EXPERT_REQUEST_TOOL && payload.is_error === false) {
                      notify("expert");
                    }
                  } else if (evt.event === "ui") {
                    updateTurn((t) => appendLiveBlock(t, payload));
                  } else if (evt.event === "status") {
                    statusMessage = payload.message ?? null;
                    const status = statusMessage;
                    setRun(sessionId, (run) => ({ ...run, statusMessage: status }));
                    remember();
                  } else if (evt.event === "turn_start") {
                    startTurn(payload);
                  } else if (evt.event === "steer") {
                    if (payload.status === "applied") placeSteer(payload);
                    else if (typeof payload.request_id === "string") {
                      const requestId = payload.request_id;
                      updateSteers(sessionId, (list) =>
                        advanceSteer(list, requestId, "withdrawn", payload.reason || undefined),
                      );
                    }
                  } else if (evt.event === "noop") {
                    // The last answer was complete: nothing was asked of the model or added.
                    gotResult = true;
                    updateSessionMessages(sessionId, original);
                    setNotices((prev) => ({
                      ...prev,
                      [sessionId]: "Nothing to continue: the last answer is complete.",
                    }));
                  } else if (evt.event === "result") {
                    gotResult = true;
                    const { entry_id: entryId, ...result } = payload as Record<string, unknown>;
                    const blocks = resultToBlocks(result);
                    finish(blocks, typeof entryId === "string" && entryId ? entryId : undefined);
                    notify(answerEventKind(blocks));
                  } else if (evt.event === "error") {
                    // Lost, or a turn whose end the store does not settle yet: attach again.
                    if (
                      payload.code === "stream_lost" ||
                      payload.code === "turn_boundary_unknown"
                    ) {
                      return lost();
                    }
                    if (payload.code === "turn_not_found") throw new Error(TURN_NOT_FOUND_MESSAGE);
                    throw new Error(payload.detail);
                  }
                }
              }
              return gotResult ? "done" : lost();
            } finally {
              clearTimeout(silence);
              controller.signal.removeEventListener("abort", forward);
            }
          };

          // Reattach after a dropped stream, never resending: the runtime replays
          // the turn from its start, or says it never got the message.
          let reattach = plan.reattach;
          for (let attempt = 1; (await streamOnce(reattach)) === "lost"; attempt++) {
            if (attempt > MAX_REATTACH_ATTEMPTS) {
              outcome = "lost";
              throw new Error(CONNECTION_LOST_MESSAGE);
            }
            setConnection({ state: "reconnecting", attempt });
            await abortableDelay(reattachDelay(attempt), controller.signal);
            reattach = true;
          }
        } catch (err) {
          if (controller.signal.aborted) {
            // Keep whatever had streamed, like ChatGPT/Claude do on Stop.
            if (controller.signal.reason === "stop") {
              finish({
                blocks: stoppedBlocks(turn),
                assessment: null,
                stopped: true,
              });
            } else {
              // Nobody watches here any more (signed out, another project, the
              // provider gone), but the turn runs on: its pointer stays.
              outcome = "watching";
            }
            return;
          }
          const message = err instanceof Error ? err.message : "Request failed";
          if (message === TURN_NOT_FOUND_MESSAGE) outcome = "not_found";
          if (continuing && turn.steps.length === 0 && shown.length === history.length) {
            // A refused continue changed nothing: show the chat as it was, and why.
            updateSessionMessages(sessionId, original);
            setNotices((prev) => ({ ...prev, [sessionId]: message }));
            return;
          }
          if (plan.restored && outcome !== "not_found" && outcome !== "lost") {
            // A restored turn the chat could not follow: the saved chat stays as it
            // was, nothing is claimed about the turn, and the notice says why.
            updateSessionMessages(sessionId, original, { save: false });
            outcome = "forget";
            setNotices((prev) => ({
              ...prev,
              [sessionId]: `Could not reconnect to the answer: ${message}`,
            }));
            return;
          }
          updateSessionMessages(sessionId, [
            ...shown,
            { role: "assistant", content: `Error: ${message}` },
          ]);
          notify("failed", message);
        } finally {
          if (controllers.current.get(sessionId) === controller) {
            controllers.current.delete(sessionId);
            setRun(sessionId, null);
          }
          if (turnRequests.current.get(sessionId) === turnRequestId) {
            turnRequests.current.delete(sessionId);
            turnAnchors.current.delete(sessionId);
            turnProjects.current.delete(sessionId);
          }
          // The stream ended without saying where these steers landed: a stop or a dropped
          // connection may have come just after the answer read one. Ask the runtime.
          updateSteers(sessionId, settleOpenSteers);
          afterStream.current(sessionId, controller);
          if (typeof owner === "string" && owner === ownerRef.current) {
            if (outcome === "not_found" || outcome === "forget") {
              forgetStoredTurn(owner, sessionId, turnRequestId);
            } else if (outcome === "ended") {
              // Forgotten once the transcript holding the turn's end is saved.
              patchStoredTurn(owner, sessionId, turnRequestId, { ended: true });
              endedTurns.current.set(sessionId, {
                requestId: turnRequestId,
                seq: transcriptSeq.current.get(sessionId) ?? 0,
              });
            }
          }
          // Followed again once the user is back in the turn's project.
          if (outcome === "watching" && controller.signal.reason === DETACHED) {
            setResumeTick((tick) => tick + 1);
          }
        }
      })();
    },
    [awaitCreate, setRun, updateSessionMessages, updateSteers],
  );

  const sendMessage = useCallback(
    (text: string, options?: SendOptions) => {
      const sessionId = options?.sessionId ?? activeSessionId ?? createNewSession(null);
      if (controllers.current.has(sessionId)) return false;
      // A turn of this chat still runs unwatched (another project, or being restored):
      // a new message would be refused by the runtime, or race the turn.
      if (detachedRef.current[sessionId]) return false;
      const session = sessionsRef.current.find((s) => s.id === sessionId);
      // A session restored from the list has no local history until its detail
      // request completes. Sending from that placeholder would replace the
      // persisted conversation with only the new turn.
      if (session && !session.messagesLoaded && !options?.history) return false;
      const history = options?.history ?? session?.messages ?? [];
      const continuing = options?.continueRun === true;
      // Shown again if a continue is refused before it streamed anything.
      const original = session?.messages ?? history;

      const controller = new AbortController();
      controllers.current.set(sessionId, controller);
      setNotices((prev) => {
        if (!(sessionId in prev)) return prev;
        const { [sessionId]: _cleared, ...rest } = prev;
        return rest;
      });
      // Only the first turn of a task chat carries the result figures; the
      // user's own attachments go with whichever turn they were staged for.
      const images = options?.images ?? [];
      const userMsg: ChatMessage = {
        role: "user",
        content: text,
        attachedImage:
          images.length > 0 ||
          (Boolean(session?.context) && !history.some((m) => m.role === "user")),
        // An empty local list distinguishes server-provided task figures
        // from user attachments whose bytes were lost after a reload.
        attachments: images.map((i) => `data:${i.mimeType};base64,${i.data}`),
      };
      const shown: ChatMessage[] = continuing ? [...history] : [...history, userMsg];
      // Saved before the request goes out, so a reload finds the turn's message.
      updateSessionMessages(sessionId, shown);
      const turnRequestId = createRequestId();
      // Every request of the turn, a reattach included, names the project it was sent from.
      const projectId = buildHeaders()["X-Project-Id"] ?? null;
      const { url, body } = buildTurnRequest(
        session,
        sessionId,
        text,
        history,
        options?.modelOverride ?? null,
        options?.approval,
        images,
        options?.thinkingLevel,
        options?.page,
        continuing,
        turnRequestId,
      );
      const startedAt = Date.now();
      const who = ownerRef.current;
      endedTurns.current.delete(sessionId);
      // The turn's pointer, so a reload or a remount reattaches to it instead of forgetting it.
      if (typeof who === "string") {
        storeTurn(who, {
          sessionId,
          requestId: turnRequestId,
          projectId,
          start: history.length,
          continuing,
          startedAt,
          lastUpdateAt: startedAt,
        });
      }
      runTurn({
        sessionId,
        controller,
        requestId: turnRequestId,
        projectId,
        history,
        shown,
        userAt: continuing ? -1 : history.length,
        continuing,
        original,
        startedAt,
        lastUpdateAt: startedAt,
        url,
        body,
        reattach: false,
        restored: false,
      });
      return true;
    },
    [activeSessionId, createNewSession, runTurn, updateSessionMessages],
  );

  const findSteer = useCallback(
    (sessionId: string, requestId: string) =>
      (steersRef.current[sessionId] ?? []).find((s) => s.requestId === requestId),
    [],
  );

  /** Whether the stream a steer was sent to still runs, and so will report where it landed. */
  const streamLive = useCallback((sessionId: string, requestId: string) => {
    const sentTo = steerStreams.current.get(requestId);
    return sentTo !== undefined && controllers.current.get(sessionId) === sentTo;
  }, []);

  /**
   * Put a steer the runtime read into the saved conversation, once, if no stream
   * placed it. While a stream runs in the session it waits for that stream's end:
   * the stream rewrites the conversation from what it started with.
   */
  const placeDelivered = useCallback(
    (sessionId: string, requestId: string) => {
      if (controllers.current.has(sessionId)) return;
      const pending = findSteer(sessionId, requestId);
      if (!pending || pending.status !== "delivered" || pending.unplaced || pending.saving) return;
      const session = sessionsRef.current.find((s) => s.id === sessionId);
      const placed = session ? placeLateSteer(session.messages, pending) : null;
      if (!placed) {
        updateSteers(sessionId, (list) => patchSteer(list, requestId, { unplaced: true }));
        return;
      }
      // Kept until a save holding it is acknowledged; saved also when the chat
      // already shows it, which may not be saved yet.
      updateSteers(sessionId, (list) => patchSteer(list, requestId, { saving: true }));
      steerStreams.current.delete(requestId);
      updateSessionMessages(sessionId, placed);
    },
    [findSteer, updateSessionMessages, updateSteers],
  );

  savedTranscript.current = (sessionId, messages, seq) => {
    // The turn's end is saved: a reload has nothing of it left to restore.
    const ended = endedTurns.current.get(sessionId);
    if (ended && seq >= ended.seq && !controllers.current.has(sessionId)) {
      endedTurns.current.delete(sessionId);
      const who = ownerRef.current;
      if (typeof who === "string") forgetStoredTurn(who, sessionId, ended.requestId);
    }
    const saved = new Set(messages.flatMap((m) => (m.steer ? [m.steer.requestId] : [])));
    if (!(steersRef.current[sessionId] ?? []).some((s) => s.saving && saved.has(s.requestId))) {
      return;
    }
    updateSteers(sessionId, (list) => list.filter((s) => !(s.saving && saved.has(s.requestId))));
  };

  /**
   * What a steer request or a status lookup reported. While the steer's stream runs,
   * it reports where the steer lands; after it ended, queued means the runtime has
   * not settled it yet, so the chat asks again.
   */
  const applyReply = useCallback(
    (sessionId: string, requestId: string, reply: SteerReply, attempt: number) => {
      const live = streamLive(sessionId, requestId);
      let { status } = reply;
      if (status === "queued" && !live) status = "unconfirmed";
      if (status === "unconfirmed" && live) status = "sending";
      updateSteers(sessionId, (list) =>
        patchSteer(advanceSteer(list, requestId, status, reply.reason, reply.entryId), requestId, {
          checking: false,
        }),
      );
      if (status === "delivered") {
        if (!live) placeDelivered(sessionId, requestId);
      } else if (reply.status === "queued" && !live) {
        if (attempt < STEER_CHECK_DELAYS_MS.length) {
          updateSteers(sessionId, (list) => patchSteer(list, requestId, { checking: true }));
          setTimeout(
            () => checkSteerRef.current(sessionId, requestId, attempt + 1),
            STEER_CHECK_DELAYS_MS[attempt],
          );
        }
      } else if (reply.status === "unconfirmed" && attempt === 0) {
        // The request got no answer: ask the store, which fences the request ID if it never landed.
        checkSteerRef.current(sessionId, requestId, 1);
      }
    },
    [placeDelivered, streamLive, updateSteers],
  );

  /** Ask the runtime's store where a steer stands. Never sends it, and never starts a run. */
  const checkSteerAt = useCallback(
    (sessionId: string, requestId: string, attempt: number) => {
      const pending = findSteer(sessionId, requestId);
      if (!pending || (pending.status !== "unconfirmed" && pending.status !== "sending")) return;
      updateSteers(sessionId, (list) => patchSteer(list, requestId, { checking: true }));
      void apiSteerStatus(sessionId, requestId, pending.projectId).then((reply) =>
        applyReply(sessionId, requestId, reply, Math.max(attempt, 1)),
      );
    },
    [applyReply, findSteer, updateSteers],
  );
  const checkSteerRef = useRef(checkSteerAt);
  checkSteerRef.current = checkSteerAt;

  const checkSteer = useCallback(
    (sessionId: string, requestId: string) => checkSteerAt(sessionId, requestId, 1),
    [checkSteerAt],
  );

  // After a stream ended: ask about the steers it left unconfirmed, and place the
  // ones the runtime read that no stream placed (also those that waited for it).
  const afterStream = useRef<(sessionId: string, controller: AbortController) => void>(() => {});
  afterStream.current = (sessionId, controller) => {
    for (const pending of steersRef.current[sessionId] ?? []) {
      const sentHere = steerStreams.current.get(pending.requestId) === controller;
      if (pending.status === "delivered") placeDelivered(sessionId, pending.requestId);
      else if (
        sentHere &&
        (pending.status === "unconfirmed" || pending.status === "sending") &&
        !pending.checking &&
        !steerPosts.current.has(pending.requestId)
      ) {
        // A steer whose request is still on its way is settled by its reply instead.
        checkSteerAt(sessionId, pending.requestId, 0);
      }
    }
  };

  // Another user signed in, or the user signed out: nothing of theirs stays here.
  const previousOwner = useRef(owner);
  useEffect(() => {
    const previous = previousOwner.current;
    previousOwner.current = owner;
    if (previous === owner || typeof previous !== "string") return;
    restoredForRef.current = null;
    setRestoredFor(null);
    steersRef.current = {};
    setSteers({});
    steerStreams.current.clear();
    toReconcile.current.clear();
    // No stream of theirs goes on showing; their turns run on in the runtime.
    for (const controller of controllers.current.values()) controller.abort(UNMOUNTED);
    endedTurns.current.clear();
    restoredTurnsFor.current = null;
    resuming.current.clear();
    setDetachedTurns({});
    if (owner === null) {
      forgetStoredSteers(previous);
      forgetStoredTurns(previous);
    }
  }, [owner]);

  // Restore the steers a reload left unresolved, once the user and their sessions are known.
  useEffect(() => {
    if (typeof owner !== "string" || isLoadingSessions || restoredForRef.current === owner) return;
    forgetOtherOwners(owner);
    const stored = readStoredSteers(owner);
    const listed = new Set(sessionsRef.current.map((s) => s.id));
    const gone: string[] = [];
    for (const [sessionId, list] of Object.entries(stored)) {
      // Only into a session this user's list holds; one the server no longer lists is gone.
      if (!listed.has(sessionId)) {
        if (sessionsListed.current) gone.push(sessionId);
        continue;
      }
      const restored = list.map(restoreSteer);
      updateSteers(sessionId, (current) => {
        const known = new Set(current.map((s) => s.requestId));
        return [...restored.filter((s) => !known.has(s.requestId)), ...current];
      });
      for (const s of restored) toReconcile.current.add(`${sessionId}\0${s.requestId}`);
    }
    if (gone.length) forgetStoredSessions(owner, gone);
    restoredForRef.current = owner;
    // Steers sent before this kept in memory only, or merged with the stored ones: store them now.
    for (const sessionId of Object.keys(steersRef.current)) updateSteers(sessionId, (list) => list);
    setRestoredFor(owner);
  }, [owner, isLoadingSessions, updateSteers]);

  // ------- running turns across reloads, remounts, and projects -------

  // The user whose other users' stored turns were removed.
  const restoredTurnsFor = useRef<string | null>(null);
  // Sessions whose stored turn is being restored now.
  const resuming = useRef<Set<string>>(new Set());

  /**
   * Follow a turn this tab started, from its pointer, over the session's saved
   * messages: reattach with its request ID, which submits nothing. The runtime
   * streams a running turn from its start, replays an ended one from its store,
   * or says it never got the message.
   */
  const resumeTurn = useCallback(
    (stored: StoredTurn, messages: ChatMessage[]) => {
      const { sessionId } = stored;
      if (controllers.current.has(sessionId)) return;
      const who = ownerRef.current;
      const placeable = stored.continuing
        ? messages.length >= stored.start
        : messages.length > stored.start &&
          messages[stored.start].role === "user" &&
          !messages[stored.start].steer;
      if (!placeable) {
        // The turn's message was never saved: there is nowhere to show its answer.
        if (typeof who === "string") forgetStoredTurn(who, sessionId, stored.requestId);
        setNotices((prev) => ({ ...prev, [sessionId]: RESTORE_UNPLACEABLE_MESSAGE }));
        return;
      }
      const history = messages.slice(0, stored.start);
      const shown = stored.continuing ? history : messages.slice(0, stored.start + 1);
      // What a failed attempt saved after the turn's message (an error) is not shown
      // under the live answer; nothing is saved until the turn's stream says more.
      if (shown.length !== messages.length) {
        updateSessionMessages(sessionId, shown, { save: false });
      }
      const controller = new AbortController();
      controllers.current.set(sessionId, controller);
      runTurn({
        sessionId,
        controller,
        requestId: stored.requestId,
        projectId: stored.projectId,
        history,
        shown,
        userAt: stored.continuing ? -1 : stored.start,
        continuing: stored.continuing,
        original: messages,
        startedAt: stored.startedAt,
        lastUpdateAt: stored.lastUpdateAt ?? stored.startedAt,
        url: `${BASE_URL}/copilot/chat/stream`,
        body: {
          session_id: sessionId,
          request_id: stored.requestId,
          message: "",
          conversation_history: [],
        },
        reattach: true,
        restored: true,
        notified: stored.notified,
      });
    },
    [runTurn, updateSessionMessages],
  );

  // Switched to another project: stop showing turns sent from the previous one. They
  // run on, and the restore below follows them again once the user is back.
  useEffect(() => {
    if (typeof project !== "string" || typeof owner !== "string") return;
    const stored = readStoredTurns(owner);
    for (const [sessionId, controller] of controllers.current) {
      const sentFrom = turnProjects.current.get(sessionId);
      // Only a turn the chat can find again: one whose pointer is stored.
      if (
        sentFrom !== undefined &&
        sentFrom !== project &&
        stored[sessionId]?.requestId === turnRequests.current.get(sessionId)
      ) {
        controller.abort(DETACHED);
      }
    }
    setResumeTick((tick) => tick + 1);
  }, [project, owner]);

  // Restore the turns this tab started that no stream follows now, once the user,
  // their sessions, and the open project are known: after a reload, a remount, a
  // project switch back, or a detached stream's end.
  useEffect(() => {
    if (typeof owner !== "string" || isLoadingSessions || project === null) return;
    if (restoredTurnsFor.current !== owner) {
      forgetOtherTurnOwners(owner);
      restoredTurnsFor.current = owner;
    }
    const stored = readStoredTurns(owner);
    const listed = new Set(sessionsRef.current.map((s) => s.id));
    const parked: Record<string, DetachedTurn> = {};
    const detachedFor = (turn: StoredTurn, reason: DetachedTurn["reason"]): DetachedTurn => ({
      reason,
      requestId: turn.requestId,
      projectId: turn.projectId,
      startedAt: turn.startedAt,
      activity: turn.activity ?? null,
      lastUpdateAt: turn.lastUpdateAt ?? null,
    });
    for (const turn of Object.values(stored)) {
      const { sessionId } = turn;
      // Only into a session this user's list holds; one the server no longer lists is gone.
      if (!listed.has(sessionId)) {
        if (sessionsListed.current) forgetStoredTurn(owner, sessionId, turn.requestId);
        continue;
      }
      if (controllers.current.has(sessionId)) continue;
      // Ended here, its end shown and being saved: nothing to restore.
      if (endedTurns.current.get(sessionId)?.requestId === turn.requestId) continue;
      if (project !== undefined && turn.projectId !== project) {
        parked[sessionId] = detachedFor(turn, "other_project");
        continue;
      }
      if (resuming.current.has(sessionId)) continue;
      resuming.current.add(sessionId);
      parked[sessionId] = detachedFor(turn, "restoring");
      void loadSessionMessages(sessionId)
        .then((messages) => {
          if (!resuming.current.delete(sessionId) || ownerRef.current !== owner) return;
          if (projectRef.current !== undefined && projectRef.current !== turn.projectId) {
            setDetachedTurns((prev) => ({
              ...prev,
              [sessionId]: detachedFor(turn, "other_project"),
            }));
            return;
          }
          setDetachedTurns((prev) => withoutKey(prev, sessionId));
          // Still this turn's pointer: a newer turn, a deletion, or a sign-out wins.
          if (readStoredTurns(owner)[sessionId]?.requestId !== turn.requestId) return;
          resumeTurn(turn, messages);
        })
        .catch(() => {
          // The chat could not be loaded: the pointer stays for the next attempt.
          resuming.current.delete(sessionId);
          setDetachedTurns((prev) => withoutKey(prev, sessionId));
        });
    }
    setDetachedTurns((prev) => {
      const next: Record<string, DetachedTurn> = { ...parked };
      // A restore still loading keeps its entry until it streams.
      for (const [sessionId, turn] of Object.entries(prev)) {
        if (turn.reason === "restoring" && resuming.current.has(sessionId) && !next[sessionId]) {
          next[sessionId] = turn;
        }
      }
      const same =
        Object.keys(next).length === Object.keys(prev).length &&
        Object.entries(next).every(
          ([id, turn]) =>
            prev[id]?.requestId === turn.requestId && prev[id]?.reason === turn.reason,
        );
      return same ? prev : next;
    });
  }, [owner, project, isLoadingSessions, resumeTick, loadSessionMessages, resumeTurn]);

  // Ask where each restored steer stands once its session's messages are loaded and
  // no stream runs there: status only, never sent again. One already in the saved
  // conversation is done; one the runtime read is placed there, approximately.
  useEffect(() => {
    for (const key of [...toReconcile.current]) {
      const [sessionId, requestId] = key.split("\0");
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) {
        toReconcile.current.delete(key);
        continue;
      }
      if (!session.messagesLoaded || controllers.current.has(sessionId)) continue;
      toReconcile.current.delete(key);
      const pending = findSteer(sessionId, requestId);
      if (!pending) continue;
      if (session.messages.some((m) => m.steer?.requestId === requestId)) {
        updateSteers(sessionId, (list) => list.filter((s) => s.requestId !== requestId));
      } else if (pending.status === "delivered") {
        placeDelivered(sessionId, requestId);
      } else if (pending.status === "unconfirmed" && !pending.checking) {
        checkSteerAt(sessionId, requestId, 1);
      }
    }
  }, [sessions, steers, restoredFor, findSteer, placeDelivered, checkSteerAt, updateSteers]);

  const steer = useCallback(
    (sessionId: string, text: string) => {
      const trimmed = text.trim();
      const controller = controllers.current.get(sessionId);
      const turnRequestId = turnRequests.current.get(sessionId);
      if (!trimmed || !controller || !turnRequestId) return false;
      const requestId = createRequestId();
      // Every later request about this steer names the project it was sent from.
      const projectId = buildHeaders()["X-Project-Id"] ?? null;
      steerStreams.current.set(requestId, controller);
      updateSteers(sessionId, (list) => [
        ...list,
        {
          requestId,
          text: trimmed,
          status: "sending",
          projectId,
          anchor: turnAnchors.current.get(sessionId),
        },
      ]);
      steerPosts.current.add(requestId);
      void apiSteer(sessionId, requestId, turnRequestId, trimmed, projectId).then((reply) => {
        steerPosts.current.delete(requestId);
        applyReply(sessionId, requestId, reply, 0);
      });
      return true;
    },
    [applyReply, updateSteers],
  );

  const dismissSteer = useCallback(
    (sessionId: string, requestId: string) => {
      steerStreams.current.delete(requestId);
      updateSteers(sessionId, (list) => list.filter((s) => s.requestId !== requestId));
    },
    [updateSteers],
  );

  const dismissNotice = useCallback((sessionId: string) => {
    setNotices((prev) => {
      if (!(sessionId in prev)) return prev;
      const { [sessionId]: _removed, ...rest } = prev;
      return rest;
    });
  }, []);

  /** Stop streaming and keep the partial answer. */
  const stop = useCallback((sessionId: string) => {
    const controller = controllers.current.get(sessionId);
    if (!controller) return;
    const turnRequestId = turnRequests.current.get(sessionId);
    const projectId = turnProjects.current.get(sessionId);
    controller.abort("stop");
    // Closing the stream keeps the partial answer here, but the runtime keeps
    // working on the turn until told otherwise. The stop names the turn, so a
    // late one never stops a newer turn of the chat.
    fetch(`${BASE_URL}/copilot/chat/stop`, {
      method: "POST",
      headers: projectId === undefined ? buildHeaders() : headersFor(projectId),
      body: JSON.stringify({
        session_id: sessionId,
        ...(turnRequestId ? { turn_request_id: turnRequestId } : {}),
      }),
      keepalive: true,
    }).catch(() => {
      /* best effort: the next message reports if the turn is still running */
    });
  }, []);

  // ------- branches -------

  // Branch requests in flight, by session and answer: a second click joins the first.
  const branchRequests = useRef<Map<string, Promise<string | null>>>(new Map());
  // The new session's ID for a branch request that may have been made, reused by its retry.
  const branchTargets = useRef<Map<string, string>>(new Map());
  const [branching, setBranching] = useState<Record<string, string>>({});

  const branchFrom = useCallback(
    (sessionId: string, entryId: string): Promise<string | null> => {
      const key = `${sessionId}\0${entryId}`;
      const inFlight = branchRequests.current.get(key);
      if (inFlight) return inFlight;
      const targetId = branchTargets.current.get(key) ?? generateId();
      branchTargets.current.set(key, targetId);
      setBranching((prev) => ({ ...prev, [sessionId]: entryId }));
      dismissNotice(sessionId);
      const work = (async () => {
        try {
          await awaitCreate(sessionId);
          let reply: BranchReply;
          try {
            reply = await apiBranchSession(sessionId, entryId, targetId);
          } catch {
            // Whatever failed, the branch may have been made: keep the target for the retry.
            reply = { ok: false, message: "Something went wrong. Try again.", retryable: true };
          }
          if (!reply.ok) {
            if (!reply.retryable) branchTargets.current.delete(key);
            setNotices((prev) => ({
              ...prev,
              [sessionId]: `Could not branch from this answer: ${reply.message}`,
            }));
            return null;
          }
          branchTargets.current.delete(key);
          const detail = reply.session;
          const local: CopilotChatSession = {
            ...summaryToSession(detail),
            messages: detail.messages.map(serverMessageToLocal),
            messagesLoaded: true,
          };
          messagesFetched.current.add(local.id);
          const add = (list: CopilotChatSession[]) => [
            local,
            ...list.filter((s) => s.id !== local.id),
          ];
          sessionsRef.current = add(sessionsRef.current);
          setSessions(add);
          setActiveSessionId(local.id);
          return local.id;
        } finally {
          branchRequests.current.delete(key);
          setBranching((prev) => {
            if (prev[sessionId] !== entryId) return prev;
            const { [sessionId]: _done, ...rest } = prev;
            return rest;
          });
        }
      })();
      branchRequests.current.set(key, work);
      return work;
    },
    [awaitCreate, dismissNotice],
  );

  const steersReady = owner === undefined || (owner !== null && restoredFor === owner);

  const value = useMemo(
    () => ({
      sessions,
      isLoadingSessions,
      activeSessionId,
      activeSession,
      runs,
      switchSession,
      createNewSession,
      hasSession,
      deleteSession,
      renameSession,
      setMessageFeedback,
      findSessionByContext,
      sendMessage,
      stop,
      steers,
      steer,
      checkSteer,
      dismissSteer,
      steersReady,
      notices,
      dismissNotice,
      branchFrom,
      branching,
      detachedTurns,
      subscribeChatEvents,
    }),
    [
      sessions,
      isLoadingSessions,
      activeSessionId,
      activeSession,
      runs,
      switchSession,
      createNewSession,
      hasSession,
      deleteSession,
      renameSession,
      setMessageFeedback,
      findSessionByContext,
      sendMessage,
      stop,
      steers,
      steer,
      checkSteer,
      dismissSteer,
      steersReady,
      notices,
      dismissNotice,
      branchFrom,
      branching,
      detachedTurns,
      subscribeChatEvents,
    ],
  );

  return <CopilotChatSessionCtx.Provider value={value}>{children}</CopilotChatSessionCtx.Provider>;
}

export function useCopilotChatSessionContext() {
  const ctx = useContext(CopilotChatSessionCtx);
  if (!ctx) {
    throw new Error("useCopilotChatSessionContext must be used within CopilotChatSessionProvider");
  }
  return ctx;
}
