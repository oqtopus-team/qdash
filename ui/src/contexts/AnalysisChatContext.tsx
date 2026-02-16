"use client";

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import type { AnalysisContext, ChatMessage } from "@/hooks/useAnalysisChat";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatSession {
  id: string;
  context: AnalysisContext;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

interface AnalysisChatContextValue {
  // sidebar open/close
  isOpen: boolean;
  openAnalysisChat: (context: AnalysisContext) => void;
  closeAnalysisChat: () => void;
  toggleAnalysisChat: () => void;

  // session management
  sessions: ChatSession[];
  activeSessionId: string | null;
  activeSession: ChatSession | null;
  switchSession: (sessionId: string) => void;
  createNewSession: (context: AnalysisContext) => string;
  deleteSession: (sessionId: string) => void;
  clearActiveSession: () => void;

  // message sync (used by useAnalysisChat)
  getSessionMessages: (ctx: AnalysisContext) => ChatMessage[];
  setSessionMessages: (ctx: AnalysisContext, messages: ChatMessage[]) => void;
}

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = "qdash_analysis_sessions";
const MAX_SESSIONS = 50;

function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as ChatSession[];
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

function contextKey(ctx: AnalysisContext): string {
  return `${ctx.taskId}:${ctx.executionId}:${ctx.qid}`;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AnalysisChatCtx = createContext<AnalysisChatContextValue | null>(null);

export function AnalysisChatProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const initialized = useRef(false);

  // Load from localStorage on mount
  useEffect(() => {
    const loaded = loadSessions();
    setSessions(loaded);
    initialized.current = true;
  }, []);

  // Persist to localStorage when sessions change
  useEffect(() => {
    if (initialized.current) {
      saveSessions(sessions);
    }
  }, [sessions]);

  // Derived: active session
  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  // ------- sidebar -------

  const openAnalysisChat = useCallback(
    (ctx: AnalysisContext) => {
      const key = contextKey(ctx);
      // Find existing session for this context
      const existing = sessions.find((s) => contextKey(s.context) === key);
      if (existing) {
        setActiveSessionId(existing.id);
      } else {
        // Create new session
        const id = generateId();
        const now = Date.now();
        const session: ChatSession = {
          id,
          context: ctx,
          messages: [],
          createdAt: now,
          updatedAt: now,
        };
        setSessions((prev) => [session, ...prev]);
        setActiveSessionId(id);
      }
      setIsOpen(true);
    },
    [sessions],
  );

  const closeAnalysisChat = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggleAnalysisChat = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  // ------- session CRUD -------

  const switchSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  const createNewSession = useCallback((ctx: AnalysisContext): string => {
    const id = generateId();
    const now = Date.now();
    const session: ChatSession = {
      id,
      context: ctx,
      messages: [],
      createdAt: now,
      updatedAt: now,
    };
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(id);
    return id;
  }, []);

  const deleteSession = useCallback(
    (sessionId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
    },
    [activeSessionId],
  );

  const clearActiveSession = useCallback(() => {
    if (!activeSessionId) return;
    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSessionId
          ? { ...s, messages: [], updatedAt: Date.now() }
          : s,
      ),
    );
  }, [activeSessionId]);

  // ------- message sync (for useAnalysisChat hook) -------

  const getSessionMessages = useCallback(
    (_ctx: AnalysisContext) => {
      return activeSession?.messages ?? [];
    },
    [activeSession],
  );

  const setSessionMessages = useCallback(
    (_ctx: AnalysisContext, messages: ChatMessage[]) => {
      if (!activeSessionId) return;
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId
            ? { ...s, messages, updatedAt: Date.now() }
            : s,
        ),
      );
    },
    [activeSessionId],
  );

  return (
    <AnalysisChatCtx.Provider
      value={{
        isOpen,
        openAnalysisChat,
        closeAnalysisChat,
        toggleAnalysisChat,
        sessions,
        activeSessionId,
        activeSession,
        switchSession,
        createNewSession,
        deleteSession,
        clearActiveSession,
        getSessionMessages,
        setSessionMessages,
      }}
    >
      {children}
    </AnalysisChatCtx.Provider>
  );
}

export function useAnalysisChatContext() {
  const ctx = useContext(AnalysisChatCtx);
  if (!ctx) {
    throw new Error(
      "useAnalysisChatContext must be used within AnalysisChatProvider",
    );
  }
  return ctx;
}
