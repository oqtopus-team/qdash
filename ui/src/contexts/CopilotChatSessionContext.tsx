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
import type { ChatMessage } from "@/hooks/useAnalysisChat";
import { buildHeaders } from "@/lib/sse-utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CopilotChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
  /** True until the server-stored messages have been fetched for this session. */
  messagesLoaded: boolean;
}

interface CopilotChatSessionContextValue {
  sessions: CopilotChatSession[];
  activeSessionId: string | null;
  activeSession: CopilotChatSession | null;
  isLoadingSessions: boolean;

  switchSession: (sessionId: string) => void;
  createNewSession: (context?: unknown) => string;
  deleteSession: (sessionId: string) => void;
  clearActiveSession: () => void;
  updateSessionMessages: (sessionId: string, messages: ChatMessage[]) => void;
  autoTitleSession: (sessionId: string, firstMessage: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const SESSIONS_PATH = "/copilot/chat/sessions";

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toTimestamp(iso: string | undefined | null): number {
  if (!iso) return Date.now();
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? Date.now() : t;
}

interface ServerMessage {
  role: string;
  content: string;
  /**
   * Server-side this is base64 image data, but qdash's frontend ChatMessage
   * only carries a boolean indicator (the image bytes are not retained client
   * side after send). We round-trip presence-only via the truthy-string trick.
   */
  attached_image?: string | null;
  created_at?: string | null;
}

interface ServerSessionSummary {
  session_id: string;
  title: string;
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
    // ChatMessage only records "was an image attached", not the bytes.
    attached_image: m.attachedImage ? "1" : null,
  };
}

function summaryToSession(s: ServerSessionSummary): CopilotChatSession {
  return {
    id: s.session_id,
    title: s.title,
    messages: [],
    createdAt: toTimestamp(s.created_at),
    updatedAt: toTimestamp(s.updated_at),
    messagesLoaded: false,
  };
}

// ---------------------------------------------------------------------------
// API helpers (plain fetch — matches useCopilotChat pattern)
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
  const res = await fetch(
    `${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`,
    { headers: buildHeaders() },
  );
  if (!res.ok) throw new Error(`Failed to get session: ${res.status}`);
  return (await res.json()) as ServerSessionDetail;
}

async function apiCreateSession(
  sessionId: string,
  title: string,
): Promise<ServerSessionDetail> {
  const res = await fetch(`${BASE_URL}${SESSIONS_PATH}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({ session_id: sessionId, title, messages: [] }),
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return (await res.json()) as ServerSessionDetail;
}

async function apiUpdateSession(
  sessionId: string,
  patch: { title?: string; messages?: ServerMessage[] },
): Promise<ServerSessionDetail> {
  const res = await fetch(
    `${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: buildHeaders(),
      body: JSON.stringify(patch),
    },
  );
  if (!res.ok) throw new Error(`Failed to update session: ${res.status}`);
  return (await res.json()) as ServerSessionDetail;
}

async function apiDeleteSession(sessionId: string): Promise<void> {
  const res = await fetch(
    `${BASE_URL}${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`,
    { method: "DELETE", headers: buildHeaders() },
  );
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete session: ${res.status}`);
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const CopilotChatSessionCtx =
  createContext<CopilotChatSessionContextValue | null>(null);

export function CopilotChatSessionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [sessions, setSessions] = useState<CopilotChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);

  // Sessions whose messages have already been fetched (or are in flight).
  const messagesFetched = useRef<Set<string>>(new Set());

  // ------- initial load -------

  useEffect(() => {
    let cancelled = false;
    setIsLoadingSessions(true);
    apiListSessions()
      .then((list) => {
        if (cancelled) return;
        setSessions(list.map(summaryToSession));
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

  // ------- derived -------

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );

  // ------- session CRUD -------

  const switchSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  const createNewSession = useCallback((): string => {
    const id = generateId();
    const ts = Date.now();
    const local: CopilotChatSession = {
      id,
      title: "New Chat",
      messages: [],
      createdAt: ts,
      updatedAt: ts,
      messagesLoaded: true,
    };
    messagesFetched.current.add(id);
    setSessions((prev) => [local, ...prev]);
    setActiveSessionId(id);
    apiCreateSession(id, "New Chat").catch(() => {
      // Roll back if the server refused (e.g. duplicate id).
      setSessions((prev) => prev.filter((s) => s.id !== id));
      messagesFetched.current.delete(id);
      if (activeSessionId === id) setActiveSessionId(null);
    });
    return id;
  }, [activeSessionId]);

  const deleteSession = useCallback(
    (sessionId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
      messagesFetched.current.delete(sessionId);
      apiDeleteSession(sessionId).catch(() => {
        // If delete failed, the session may still exist server-side. Reload.
        apiListSessions().then((list) => {
          setSessions(list.map(summaryToSession));
        });
      });
    },
    [activeSessionId],
  );

  const clearActiveSession = useCallback(() => {
    if (!activeSessionId) return;
    const id = activeSessionId;
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, messages: [], updatedAt: Date.now() } : s,
      ),
    );
    apiUpdateSession(id, { messages: [] }).catch(() => {
      /* swallow — next update will re-sync */
    });
  }, [activeSessionId]);

  const updateSessionMessages = useCallback(
    (sessionId: string, messages: ChatMessage[]) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                messages,
                updatedAt: Date.now(),
                messagesLoaded: true,
              }
            : s,
        ),
      );
      apiUpdateSession(sessionId, {
        messages: messages.map(localMessageToServer),
      }).catch(() => {
        /* swallow — local state is the source of truth until reload */
      });
    },
    [],
  );

  const autoTitleSession = useCallback(
    (sessionId: string, firstMessage: string) => {
      const newTitle = firstMessage.slice(0, 50);
      let didChange = false;
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id === sessionId && s.title === "New Chat") {
            didChange = true;
            return { ...s, title: newTitle };
          }
          return s;
        }),
      );
      if (didChange) {
        apiUpdateSession(sessionId, { title: newTitle }).catch(() => {
          /* swallow */
        });
      }
    },
    [],
  );

  return (
    <CopilotChatSessionCtx.Provider
      value={{
        sessions,
        activeSessionId,
        activeSession,
        isLoadingSessions,
        switchSession,
        createNewSession,
        deleteSession,
        clearActiveSession,
        updateSessionMessages,
        autoTitleSession,
      }}
    >
      {children}
    </CopilotChatSessionCtx.Provider>
  );
}

export function useCopilotChatSessionContext() {
  const ctx = useContext(CopilotChatSessionCtx);
  if (!ctx) {
    throw new Error(
      "useCopilotChatSessionContext must be used within CopilotChatSessionProvider",
    );
  }
  return ctx;
}
