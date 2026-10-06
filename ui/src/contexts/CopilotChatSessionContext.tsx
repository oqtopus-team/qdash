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
import type { ModelOverride } from "@/lib/copilotModels";
import {
  appendDelta,
  endTool,
  startTool,
  streamedAnswer,
  toPersistedTrace,
} from "@/lib/copilotChatStream";
import { buildHeaders, consumeSSEEvents, readErrorResponse } from "@/lib/sse-utils";
import type {
  AnalysisContext,
  ChatMessage,
  CopilotBlocksResult,
  LiveTurn,
} from "@/types/copilotChat";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CopilotChatSession {
  id: string;
  title: string;
  /** Set when the chat is about one calibration result. */
  context: AnalysisContext | null;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
  /** True once the server-stored messages have been fetched for this session. */
  messagesLoaded: boolean;
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
  /** The user's decision on the write operation the last answer asked approval for. */
  approval?: { id: string; approve: boolean };
}

interface CopilotChatSessionContextValue {
  sessions: CopilotChatSession[];
  isLoadingSessions: boolean;
  activeSessionId: string | null;
  activeSession: CopilotChatSession | null;
  runs: Record<string, SessionRun>;

  switchSession: (sessionId: string | null) => void;
  createNewSession: (context?: AnalysisContext | null) => string;
  deleteSession: (sessionId: string) => void;
  findSessionByContext: (context: AnalysisContext) => CopilotChatSession | null;

  sendMessage: (text: string, options?: SendOptions) => void;
  stop: (sessionId: string) => void;
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

function sameContext(a: AnalysisContext | null, b: AnalysisContext): boolean {
  return a !== null && a.taskId === b.taskId && a.executionId === b.executionId && a.qid === b.qid;
}

function contextTitle(context: AnalysisContext): string {
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
  created_at?: string | null;
}

interface ServerSessionSummary {
  session_id: string;
  title: string;
  context?: AnalysisContext | null;
  message_count: number;
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
  };
}

function localMessageToServer(m: ChatMessage): ServerMessage {
  return {
    role: m.role,
    content: m.content,
    attached_image: m.attachedImage ? "1" : null,
  };
}

function summaryToSession(s: ServerSessionSummary): CopilotChatSession {
  return {
    id: s.session_id,
    title: s.title,
    context: s.context ?? null,
    messages: [],
    createdAt: toTimestamp(s.created_at),
    updatedAt: toTimestamp(s.updated_at),
    messagesLoaded: false,
  };
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiListSessions(): Promise<ServerSessionSummary[]> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}`, { headers: buildHeaders() });
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
      context: session.context,
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

/** Request for one turn: analysis sessions go through the analyze endpoint. */
function buildTurnRequest(
  session: CopilotChatSession | undefined,
  sessionId: string,
  message: string,
  history: ChatMessage[],
  modelOverride: ModelOverride | null,
  approval: SendOptions["approval"],
): { url: string; body: Record<string, unknown> } {
  const common = {
    ...(approval ? { approval } : {}),
    message,
    // Required by the Pi backend, which restores conversation state from the
    // persisted session rather than from the request body.
    session_id: sessionId,
    request_id: crypto.randomUUID(),
    conversation_history: history.map((m) => ({ role: m.role, content: m.content })),
    model_override: modelOverride,
  };
  const context = session?.context;
  if (!context) {
    return { url: `${BASE_URL}/copilot/chat/stream`, body: common };
  }
  return {
    url: `${BASE_URL}/copilot/analyze/stream`,
    body: {
      ...common,
      task_name: context.taskName,
      chip_id: context.chipId,
      qid: context.qid,
      execution_id: context.executionId,
      task_id: context.taskId,
      image_base64: null,
    },
  };
}

function resultToBlocks(payload: Record<string, unknown>): CopilotBlocksResult {
  if (Array.isArray(payload.blocks)) return payload as unknown as CopilotBlocksResult;
  const text =
    typeof payload.explanation === "string" ? payload.explanation : JSON.stringify(payload);
  return { blocks: [{ type: "text", content: text, chart: null }], assessment: null };
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const CopilotChatSessionCtx = createContext<CopilotChatSessionContextValue | null>(null);

export function CopilotChatSessionProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<CopilotChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [runs, setRuns] = useState<Record<string, SessionRun>>({});

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
                  context: detail.context ?? s.context,
                  messages: detail.messages.map(serverMessageToLocal),
                  updatedAt: toTimestamp(detail.updated_at),
                  messagesLoaded: true,
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

  // ------- session CRUD -------

  const switchSession = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
  }, []);

  const createNewSession = useCallback((context: AnalysisContext | null = null): string => {
    const id = generateId();
    const ts = Date.now();
    const local: CopilotChatSession = {
      id,
      title: context ? contextTitle(context) : DEFAULT_TITLE,
      context,
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
  }, []);

  const findSessionByContext = useCallback(
    (context: AnalysisContext) => sessions.find((s) => sameContext(s.context, context)) ?? null,
    [sessions],
  );

  const deleteSession = useCallback(
    (sessionId: string) => {
      controllers.current.get(sessionId)?.abort();
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
      if (controllers.current.has(sessionId)) return;
      const session = sessionsRef.current.find((s) => s.id === sessionId);
      // A session restored from the list has no local history until its detail
      // request completes. Sending from that placeholder would replace the
      // persisted conversation with only the new turn.
      if (session && !session.messagesLoaded && !options?.history) return;
      const history = options?.history ?? session?.messages ?? [];

      const controller = new AbortController();
      controllers.current.set(sessionId, controller);
      // Only the first turn of an analysis carries the result figures.
      const userMsg: ChatMessage = {
        role: "user",
        content: text,
        attachedImage: Boolean(session?.context) && !history.some((m) => m.role === "user"),
      };
      updateSessionMessages(sessionId, [...history, userMsg]);

      // The live turn is folded locally and mirrored into state, so the final
      // message is built from what was streamed even if renders lag behind.
      let turn: LiveTurn = { steps: [], startedAt: Date.now() };
      setRuns((prev) => ({ ...prev, [sessionId]: { turn, statusMessage: null } }));
      const updateTurn = (fold: (t: LiveTurn) => LiveTurn) => {
        turn = fold(turn);
        const next = turn;
        setRun(sessionId, (run) => ({ ...run, turn: next }));
      };

      const finish = (result: CopilotBlocksResult) => {
        const trace = toPersistedTrace(turn, Date.now());
        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: JSON.stringify(trace ? { ...result, trace } : result),
        };
        updateSessionMessages(sessionId, [...history, userMsg, assistantMsg]);
      };

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
                updateTurn((t) => ({ ...t, steps: appendDelta(t.steps, "text", payload.text) }));
              } else if (evt.event === "thinking") {
                updateTurn((t) => ({
                  ...t,
                  steps: appendDelta(t.steps, "thinking", payload.text),
                }));
              } else if (evt.event === "tool_start") {
                updateTurn((t) => ({ ...t, steps: startTool(t.steps, payload) }));
              } else if (evt.event === "tool_end") {
                updateTurn((t) => ({ ...t, steps: endTool(t.steps, payload) }));
              } else if (evt.event === "status") {
                setRun(sessionId, (run) => ({ ...run, statusMessage: payload.message ?? null }));
              } else if (evt.event === "result") {
                gotResult = true;
                finish(resultToBlocks(payload));
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
              const partial = streamedAnswer(turn);
              finish({
                blocks: partial ? [{ type: "text", content: partial, chart: null }] : [],
                assessment: null,
                stopped: true,
              });
            }
            return;
          }
          const message = err instanceof Error ? err.message : "Request failed";
          updateSessionMessages(sessionId, [
            ...history,
            userMsg,
            { role: "assistant", content: `Error: ${message}` },
          ]);
        } finally {
          controllers.current.delete(sessionId);
          setRun(sessionId, null);
        }
      })();
    },
    [activeSessionId, awaitCreate, createNewSession, setRun, updateSessionMessages],
  );

  /** Stop streaming and keep the partial answer. */
  const stop = useCallback((sessionId: string) => {
    controllers.current.get(sessionId)?.abort("stop");
  }, []);

  // Abort everything on unmount (e.g. logout).
  useEffect(() => {
    const active = controllers.current;
    return () => active.forEach((c) => c.abort());
  }, []);

  const value = useMemo(
    () => ({
      sessions,
      isLoadingSessions,
      activeSessionId,
      activeSession,
      runs,
      switchSession,
      createNewSession,
      deleteSession,
      findSessionByContext,
      sendMessage,
      stop,
    }),
    [
      sessions,
      isLoadingSessions,
      activeSessionId,
      activeSession,
      runs,
      switchSession,
      createNewSession,
      deleteSession,
      findSessionByContext,
      sendMessage,
      stop,
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
