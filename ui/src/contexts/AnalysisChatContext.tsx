"use client";

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import type { AnalysisContext, ChatMessage } from "@/hooks/useAnalysisChat";
import { buildHeaders } from "@/lib/sse-utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatSession {
  id: string;
  title: string;
  context: AnalysisContext | null;
  messages: ChatMessage[];
  messageCount: number;
  createdAt: number;
  updatedAt: number;
  messagesLoaded: boolean;
}

interface AnalysisChatContextValue {
  // sidebar open/close
  isOpen: boolean;
  openAnalysisChat: (context: AnalysisContext) => void;
  openGeneralChat: () => void;
  closeAnalysisChat: () => void;
  toggleAnalysisChat: () => void;

  // mini chat (floating window above modals)
  miniChat: { isOpen: boolean; context: AnalysisContext | null };
  openMiniChat: (context: AnalysisContext) => void;
  closeMiniChat: () => void;

  // session management
  sessions: ChatSession[];
  activeSessionId: string | null;
  activeSession: ChatSession | null;
  switchSession: (sessionId: string) => void;
  createNewSession: (context: AnalysisContext | null) => string;
  deleteSession: (sessionId: string) => void;
  clearActiveSession: () => void;

  // message sync (used by useAnalysisChat)
  getSessionMessages: (ctx: AnalysisContext) => ChatMessage[];
  setSessionMessages: (ctx: AnalysisContext, messages: ChatMessage[]) => void;

  // message sync by session ID (used by useCopilotChat)
  updateSessionMessages: (sessionId: string, messages: ChatMessage[]) => void;
  autoTitleSession: (sessionId: string, firstMessage: string) => void;
}

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = "qdash_chat_sessions";
const LEGACY_ANALYSIS_KEY = "qdash_analysis_sessions";
const LEGACY_COPILOT_KEY = "qdash_copilot_sessions";
const MAX_SESSIONS = 50;

interface LegacyCopilotSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

interface ServerMessage {
  role: string;
  content: string;
  attached_image?: string | null;
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

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const SESSIONS_PATH = "/copilot/chat/sessions";

function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return (JSON.parse(raw) as Array<Partial<ChatSession> & Pick<ChatSession, "id">>).map(
        (session) => ({
          id: session.id,
          title: session.title ?? "New Chat",
          context: session.context ?? null,
          messages: session.messages ?? [],
          messageCount: session.messageCount ?? session.messages?.length ?? 0,
          createdAt: session.createdAt ?? Date.now(),
          updatedAt: session.updatedAt ?? Date.now(),
          messagesLoaded: session.messagesLoaded ?? true,
        }),
      );
    }

    // One-time migration from legacy keys
    const merged: ChatSession[] = [];

    const legacyAnalysis = localStorage.getItem(LEGACY_ANALYSIS_KEY);
    if (legacyAnalysis) {
      const old = JSON.parse(legacyAnalysis) as Omit<ChatSession, "title">[];
      for (const s of old) {
        merged.push({
          ...s,
          title: s.context ? `${s.context.taskName} / ${s.context.qid}` : "General Chat",
          messageCount: s.messages.length,
          messagesLoaded: true,
        });
      }
    }

    const legacyCopilot = localStorage.getItem(LEGACY_COPILOT_KEY);
    if (legacyCopilot) {
      const old = JSON.parse(legacyCopilot) as LegacyCopilotSession[];
      for (const s of old) {
        // Skip duplicates by id
        if (merged.some((m) => m.id === s.id)) continue;
        merged.push({
          id: s.id,
          title: s.title || "New Chat",
          context: null,
          messages: s.messages,
          messageCount: s.messages.length,
          createdAt: s.createdAt,
          updatedAt: s.updatedAt,
          messagesLoaded: true,
        });
      }
    }

    if (merged.length > 0) {
      merged.sort((a, b) => b.updatedAt - a.updatedAt);
      saveSessions(merged);
      localStorage.removeItem(LEGACY_ANALYSIS_KEY);
      localStorage.removeItem(LEGACY_COPILOT_KEY);
      return merged;
    }

    return [];
  } catch {
    return [];
  }
}

function saveSessions(sessions: ChatSession[]) {
  if (typeof window === "undefined") return;
  try {
    // Keep only the most recent sessions
    const trimmed = sessions.slice(0, MAX_SESSIONS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // localStorage full — silently ignore
  }
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toTimestamp(iso: string | undefined | null): number {
  if (!iso) return Date.now();
  const timestamp = new Date(iso).getTime();
  return Number.isNaN(timestamp) ? Date.now() : timestamp;
}

function serverMessageToLocal(message: ServerMessage): ChatMessage {
  return {
    role: message.role as ChatMessage["role"],
    content: message.content,
    attachedImage: Boolean(message.attached_image),
  };
}

function localMessageToServer(message: ChatMessage): ServerMessage {
  return {
    role: message.role,
    content: message.content,
    attached_image: message.attachedImage ? "1" : null,
  };
}

function summaryToSession(session: ServerSessionSummary): ChatSession {
  return {
    id: session.session_id,
    title: session.title,
    context: session.context ?? null,
    messages: [],
    messageCount: session.message_count,
    createdAt: toTimestamp(session.created_at),
    updatedAt: toTimestamp(session.updated_at),
    messagesLoaded: false,
  };
}

function detailToSession(session: ServerSessionDetail): ChatSession {
  return {
    id: session.session_id,
    title: session.title,
    context: session.context ?? null,
    messages: session.messages.map(serverMessageToLocal),
    messageCount: session.message_count,
    createdAt: toTimestamp(session.created_at),
    updatedAt: toTimestamp(session.updated_at),
    messagesLoaded: true,
  };
}

function deriveSessionTitle(currentTitle: string, messages: ChatMessage[]): string {
  if (currentTitle !== "New Chat") return currentTitle;
  const firstUserMessage = messages.find((message) => message.role === "user");
  return firstUserMessage?.content ? firstUserMessage.content.slice(0, 50) : currentTitle;
}

async function apiListSessions(): Promise<ServerSessionSummary[]> {
  const response = await fetch(`${BASE_URL}${SESSIONS_PATH}`, {
    headers: buildHeaders(),
  });
  if (!response.ok) throw new Error(`Failed to list sessions: ${response.status}`);
  const data = (await response.json()) as { sessions: ServerSessionSummary[] };
  return data.sessions;
}

async function apiGetSession(sessionId: string): Promise<ServerSessionDetail> {
  const response = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`, {
    headers: buildHeaders(),
  });
  if (!response.ok) throw new Error(`Failed to get session: ${response.status}`);
  return (await response.json()) as ServerSessionDetail;
}

async function apiCreateSession(session: ChatSession): Promise<ServerSessionDetail> {
  const response = await fetch(`${BASE_URL}${SESSIONS_PATH}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({
      session_id: session.id,
      title: session.title,
      context: session.context,
      messages: session.messages.map(localMessageToServer),
    }),
  });
  if (!response.ok) throw new Error(`Failed to create session: ${response.status}`);
  return (await response.json()) as ServerSessionDetail;
}

async function apiUpdateSession(
  sessionId: string,
  patch: {
    title?: string;
    context?: AnalysisContext | null;
    messages?: ServerMessage[];
  },
): Promise<ServerSessionDetail> {
  const response = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: buildHeaders(),
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(`Failed to update session: ${response.status}`);
  return (await response.json()) as ServerSessionDetail;
}

async function apiDeleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  if (!response.ok && response.status !== 404) {
    throw new Error(`Failed to delete session: ${response.status}`);
  }
}

const GENERAL_CHAT_KEY = "__general__";

function contextKey(ctx: AnalysisContext | null): string {
  if (!ctx) return GENERAL_CHAT_KEY;
  return `${ctx.taskId}:${ctx.executionId}:${ctx.qid}`;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AnalysisChatCtx = createContext<AnalysisChatContextValue | null>(null);

export function AnalysisChatProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [miniChat, setMiniChat] = useState<{
    isOpen: boolean;
    context: AnalysisContext | null;
  }>({ isOpen: false, context: null });
  const initialized = useRef(false);
  const messagesFetched = useRef<Set<string>>(new Set());
  const pendingCreates = useRef<Map<string, Promise<void>>>(new Map());

  const awaitCreate = useCallback(async (sessionId: string) => {
    const pending = pendingCreates.current.get(sessionId);
    if (!pending) return;
    try {
      await pending;
    } catch {
      // The create path handles rollback.
    }
  }, []);

  // Load cached sessions immediately, then replace with server-backed sessions.
  useEffect(() => {
    const loaded = loadSessions();
    setSessions(loaded);
    initialized.current = true;

    let cancelled = false;
    apiListSessions()
      .then((serverSessions) => {
        if (cancelled) return;
        messagesFetched.current.clear();
        setSessions(serverSessions.map(summaryToSession));
      })
      .catch(() => {
        // Fall back to localStorage if the API is unavailable.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Persist to localStorage when sessions change
  useEffect(() => {
    if (initialized.current) {
      saveSessions(sessions);
    }
  }, [sessions]);

  // Derived: active session
  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  useEffect(() => {
    if (!activeSessionId) return;
    if (messagesFetched.current.has(activeSessionId)) return;
    messagesFetched.current.add(activeSessionId);

    let cancelled = false;
    apiGetSession(activeSessionId)
      .then((detail) => {
        if (cancelled) return;
        const session = detailToSession(detail);
        setSessions((prev) => prev.map((item) => (item.id === session.id ? session : item)));
      })
      .catch(() => {
        messagesFetched.current.delete(activeSessionId);
      });

    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  const createSession = useCallback((ctx: AnalysisContext | null): string => {
    const id = generateId();
    const now = Date.now();
    const session: ChatSession = {
      id,
      title: ctx ? `${ctx.taskName} / ${ctx.qid}` : "New Chat",
      context: ctx,
      messages: [],
      messageCount: 0,
      createdAt: now,
      updatedAt: now,
      messagesLoaded: true,
    };
    messagesFetched.current.add(id);
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(id);

    const createPromise = apiCreateSession(session)
      .then(() => {
        pendingCreates.current.delete(id);
      })
      .catch((error) => {
        pendingCreates.current.delete(id);
        messagesFetched.current.delete(id);
        setSessions((prev) => prev.filter((item) => item.id !== id));
        setActiveSessionId((current) => (current === id ? null : current));
        throw error;
      });
    pendingCreates.current.set(id, createPromise);
    return id;
  }, []);

  // ------- sidebar -------

  const openAnalysisChat = useCallback(
    (ctx: AnalysisContext) => {
      const key = contextKey(ctx);
      // Find existing session for this context
      const existing = sessions.find((s) => contextKey(s.context) === key);
      if (existing) {
        setActiveSessionId(existing.id);
      } else {
        createSession(ctx);
      }
      setIsOpen(true);
    },
    [createSession, sessions],
  );

  const openGeneralChat = useCallback(() => {
    // Find existing general session (no context)
    const existing = sessions.find((s) => contextKey(s.context) === GENERAL_CHAT_KEY);
    if (existing) {
      setActiveSessionId(existing.id);
    } else {
      createSession(null);
    }
    setIsOpen(true);
  }, [createSession, sessions]);

  const closeAnalysisChat = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggleAnalysisChat = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  // ------- mini chat -------

  const openMiniChat = useCallback(
    (ctx: AnalysisContext) => {
      // Create or find session for this context
      const key = contextKey(ctx);
      const existing = sessions.find((s) => contextKey(s.context) === key);
      if (existing) {
        setActiveSessionId(existing.id);
      } else {
        createSession(ctx);
      }
      setMiniChat({ isOpen: true, context: ctx });
    },
    [createSession, sessions],
  );

  const closeMiniChat = useCallback(() => {
    setMiniChat({ isOpen: false, context: null });
  }, []);

  // ------- session CRUD -------

  const switchSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  const createNewSession = useCallback(
    (ctx: AnalysisContext | null): string => {
      return createSession(ctx);
    },
    [createSession],
  );

  const deleteSession = useCallback(
    (sessionId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      messagesFetched.current.delete(sessionId);
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
      (async () => {
        try {
          await awaitCreate(sessionId);
          await apiDeleteSession(sessionId);
        } catch {
          apiListSessions().then((serverSessions) => {
            setSessions(serverSessions.map(summaryToSession));
          });
        }
      })();
    },
    [activeSessionId, awaitCreate],
  );

  const clearActiveSession = useCallback(() => {
    if (!activeSessionId) return;
    const sessionId = activeSessionId;
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId
          ? { ...s, messages: [], messageCount: 0, updatedAt: Date.now(), messagesLoaded: true }
          : s,
      ),
    );
    (async () => {
      await awaitCreate(sessionId);
      apiUpdateSession(sessionId, { messages: [] }).catch(() => {
        // Keep local state and retry on the next update.
      });
    })();
  }, [activeSessionId, awaitCreate]);

  // ------- message sync (for useAnalysisChat hook) -------

  const getSessionMessages = useCallback(
    (_ctx: AnalysisContext) => {
      return activeSession?.messages ?? [];
    },
    [activeSession],
  );

  const updateSessionMessages = useCallback(
    (sessionId: string, messages: ChatMessage[]) => {
      let patchTitle: string | undefined;
      let patchContext: AnalysisContext | null | undefined;

      setSessions((prev) =>
        prev.map((session) => {
          if (session.id !== sessionId) return session;
          const nextTitle = deriveSessionTitle(session.title, messages);
          if (nextTitle !== session.title) {
            patchTitle = nextTitle;
          }
          patchContext = session.context;
          return {
            ...session,
            title: nextTitle,
            messages,
            messageCount: messages.length,
            updatedAt: Date.now(),
            messagesLoaded: true,
          };
        }),
      );

      const patch: {
        title?: string;
        context?: AnalysisContext | null;
        messages: ServerMessage[];
      } = {
        messages: messages.map(localMessageToServer),
      };
      if (patchTitle !== undefined) {
        patch.title = patchTitle;
      }
      if (patchContext !== undefined) {
        patch.context = patchContext;
      }

      (async () => {
        await awaitCreate(sessionId);
        apiUpdateSession(sessionId, patch).catch(() => {
          // Keep local state and retry on the next update.
        });
      })();
    },
    [awaitCreate],
  );

  const setSessionMessages = useCallback(
    (_ctx: AnalysisContext, messages: ChatMessage[]) => {
      if (!activeSessionId) return;
      updateSessionMessages(activeSessionId, messages);
    },
    [activeSessionId, updateSessionMessages],
  );

  const autoTitleSession = useCallback(
    (sessionId: string, firstMessage: string) => {
      const newTitle = firstMessage.slice(0, 50);
      let shouldPersist = false;
      let patchContext: AnalysisContext | null | undefined;

      setSessions((prev) =>
        prev.map((session) => {
          if (session.id !== sessionId || session.title !== "New Chat") {
            return session;
          }
          shouldPersist = true;
          patchContext = session.context;
          return {
            ...session,
            title: newTitle,
          };
        }),
      );

      if (!shouldPersist) {
        return;
      }

      (async () => {
        await awaitCreate(sessionId);
        apiUpdateSession(sessionId, {
          title: newTitle,
          context: patchContext,
        }).catch(() => {
          // Keep local state and retry on the next message update.
        });
      })();
    },
    [awaitCreate],
  );

  return (
    <AnalysisChatCtx.Provider
      value={{
        isOpen,
        openAnalysisChat,
        openGeneralChat,
        closeAnalysisChat,
        toggleAnalysisChat,
        miniChat,
        openMiniChat,
        closeMiniChat,
        sessions,
        activeSessionId,
        activeSession,
        switchSession,
        createNewSession,
        deleteSession,
        clearActiveSession,
        getSessionMessages,
        setSessionMessages,
        updateSessionMessages,
        autoTitleSession,
      }}
    >
      {children}
    </AnalysisChatCtx.Provider>
  );
}

export function useAnalysisChatContext() {
  const ctx = useContext(AnalysisChatCtx);
  if (!ctx) {
    throw new Error("useAnalysisChatContext must be used within AnalysisChatProvider");
  }
  return ctx;
}
