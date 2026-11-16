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
import type {
  TaskChatContext,
  AnswerFeedback,
  ChatBranchOrigin,
  ChatImageAttachment,
  ChatMessage,
  CopilotBlocksResult,
  InvestigationTarget,
  LiveTurn,
  PageContext,
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
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const SESSIONS_PATH = "/copilot/chat/sessions";
const DEFAULT_TITLE = "New Chat";

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
  try {
    res = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}/branches`, {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify({ entry_id: entryId, target_session_id: targetId }),
    });
  } catch {
    return { ok: false, message: "The connection failed. Try again.", retryable: true };
  }
  if (res.ok) return { ok: true, session: (await res.json()) as ServerSessionDetail };
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
      request_id: createRequestId(),
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
  message: string,
  projectId: string | null | undefined,
): Promise<SteerReply> {
  const send = () =>
    fetch(`${BASE_URL}/copilot/chat/steer`, {
      method: "POST",
      headers: headersFor(projectId),
      body: JSON.stringify({
        session_id: sessionId,
        request_id: requestId,
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
}: {
  children: React.ReactNode;
  /**
   * The signed-in user, to keep unresolved steers across a reload for them
   * only: null while not known yet, undefined to keep steers in memory only.
   */
  owner?: string | null;
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

  useEffect(() => {
    if (!activeSessionId) return;
    if (messagesFetched.current.has(activeSessionId)) return;
    messagesFetched.current.add(activeSessionId);

    let cancelled = false;
    apiGetSession(activeSessionId)
      .then((detail) => {
        if (cancelled) return;
        setSessions((prev) =>
          prev.map((s) =>
            s.id === activeSessionId
              ? {
                  ...s,
                  title: detail.title,
                  ...(detail.context
                    ? fromServerContext(detail.context)
                    : {
                        context: s.context,
                        investigation: s.investigation ?? null,
                      }),
                  messages: detail.messages.map(serverMessageToLocal),
                  updatedAt: toTimestamp(detail.updated_at),
                  messagesLoaded: true,
                  branch: fromServerBranch(detail.branch),
                }
              : s,
          ),
        );
      })
      .catch(() => {
        messagesFetched.current.delete(activeSessionId);
      });
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

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

  const updateSessionMessages = useCallback(
    (sessionId: string, messages: ChatMessage[]) => {
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

      const patch: { messages: ServerMessage[]; title?: string } = {
        messages: messages.map(localMessageToServer),
      };
      if (derivedTitle !== undefined) patch.title = derivedTitle;
      (async () => {
        await awaitCreate(sessionId);
        apiUpdateSession(sessionId, patch).catch(() => {
          /* swallow — local state is the source of truth until reload */
        });
      })();
    },
    [awaitCreate],
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

  const sendMessage = useCallback(
    (text: string, options?: SendOptions) => {
      const sessionId = options?.sessionId ?? activeSessionId ?? createNewSession(null);
      if (controllers.current.has(sessionId)) return false;
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
      // What precedes the live answer: the history, the user's message, and the parts of
      // the answer that steers closed off, each followed by the steer, in transcript order.
      let shown: ChatMessage[] = continuing ? [...history] : [...history, userMsg];
      // Where this turn's user message is in `shown`; steers of earlier turns go before it.
      let userAt = continuing ? -1 : history.length;
      updateSessionMessages(sessionId, shown);
      turnAnchors.current.set(sessionId, {
        start: history.length,
        userText: continuing ? null : text,
      });

      // The live turn is folded locally and mirrored into state, so the final
      // message is built from what was streamed even if renders lag behind.
      let turn: LiveTurn = { steps: [], startedAt: Date.now() };
      setRuns((prev) => ({
        ...prev,
        [sessionId]: { turn, statusMessage: null },
      }));
      const updateTurn = (fold: (t: LiveTurn) => LiveTurn) => {
        turn = fold(turn);
        const next = turn;
        setRun(sessionId, (run) => ({ ...run, turn: next }));
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
        shown = [...shown, ...before];
        if (payload.before_turn === true && userAt >= 0) {
          // A run recovered after the runtime died placed this steer before this
          // turn's message: it belongs to an earlier turn. Put it in the turn it was
          // sent to if the chat remembers it, else just before this turn's message.
          // Either way the answer it interrupted is not split here: approximate.
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
        } else if (text) {
          shown = [
            ...shown,
            {
              role: "user",
              content: text,
              steer: { requestId, entryId, placement: "exact" },
            },
          ];
        }
        updateSessionMessages(sessionId, shown);
        turn = { steps: [], startedAt: now };
        const next = turn;
        setRun(sessionId, (run) => ({ ...run, turn: next }));
        updateSteers(sessionId, (list) => list.filter((s) => s.requestId !== requestId));
        steerStreams.current.delete(requestId);
        toReconcile.current.delete(`${sessionId}\0${requestId}`);
      };
      const placedSteers = new Set<string>();

      (async () => {
        try {
          await awaitCreate(sessionId);
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
          );
          const response = await fetch(url, {
            method: "POST",
            headers: buildHeaders(),
            body: JSON.stringify(body),
            signal: controller.signal,
          });
          if (!response.ok) throw new Error(await readErrorResponse(response));
          const reader = response.body?.getReader();
          if (!reader) throw new Error("No response body");

          const decoder = new TextDecoder();
          let buffer = "";
          let gotResult = false;
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const { events, remainder } = consumeSSEEvents(buffer);
            buffer = remainder;

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
              } else if (evt.event === "tool_end") {
                updateTurn((t) => ({ ...t, steps: endTool(t.steps, payload) }));
              } else if (evt.event === "ui") {
                updateTurn((t) => appendLiveBlock(t, payload));
              } else if (evt.event === "status") {
                setRun(sessionId, (run) => ({
                  ...run,
                  statusMessage: payload.message ?? null,
                }));
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
                finish(
                  resultToBlocks(result),
                  typeof entryId === "string" && entryId ? entryId : undefined,
                );
              } else if (evt.event === "error") {
                throw new Error(payload.detail);
              }
            }
          }
          if (!gotResult) {
            throw new Error("The connection closed before the answer was complete");
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
            }
            return;
          }
          const message = err instanceof Error ? err.message : "Request failed";
          if (continuing && turn.steps.length === 0 && shown.length === history.length) {
            // A refused continue changed nothing: show the chat as it was, and why.
            updateSessionMessages(sessionId, original);
            setNotices((prev) => ({ ...prev, [sessionId]: message }));
            return;
          }
          updateSessionMessages(sessionId, [
            ...shown,
            { role: "assistant", content: `Error: ${message}` },
          ]);
        } finally {
          controllers.current.delete(sessionId);
          turnAnchors.current.delete(sessionId);
          setRun(sessionId, null);
          // The stream ended without saying where these steers landed: a stop or a dropped
          // connection may have come just after the answer read one. Ask the runtime.
          updateSteers(sessionId, settleOpenSteers);
          afterStream.current(sessionId, controller);
        }
      })();
      return true;
    },
    [activeSessionId, awaitCreate, createNewSession, setRun, updateSessionMessages, updateSteers],
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
      if (!pending || pending.status !== "delivered" || pending.unplaced) return;
      const session = sessionsRef.current.find((s) => s.id === sessionId);
      const placed = session ? placeLateSteer(session.messages, pending) : null;
      if (!placed) {
        updateSteers(sessionId, (list) => patchSteer(list, requestId, { unplaced: true }));
        return;
      }
      if (placed !== session!.messages) updateSessionMessages(sessionId, placed);
      steerStreams.current.delete(requestId);
      updateSteers(sessionId, (list) => list.filter((s) => s.requestId !== requestId));
    },
    [findSteer, updateSessionMessages, updateSteers],
  );

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
    if (owner === null) forgetStoredSteers(previous);
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
      if (!trimmed || !controller) return false;
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
      void apiSteer(sessionId, requestId, trimmed, projectId).then((reply) => {
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
    controller.abort("stop");
    // Closing the stream keeps the partial answer here, but the runtime keeps
    // working on the turn until told otherwise.
    fetch(`${BASE_URL}/copilot/chat/stop`, {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify({ session_id: sessionId }),
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
          const reply = await apiBranchSession(sessionId, entryId, targetId);
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

  // Abort everything on unmount (e.g. logout).
  useEffect(() => {
    const active = controllers.current;
    return () => active.forEach((c) => c.abort());
  }, []);

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
