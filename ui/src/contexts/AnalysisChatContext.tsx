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
  title: string;
  context: AnalysisContext | null;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

interface AnalysisChatContextValue {
  // sidebar open/close
  isOpen: boolean;
  openAnalysisChat: (context: AnalysisContext) => void;
  openGeneralChat: () => void;
  closeAnalysisChat: () => void;
  toggleAnalysisChat: () => void;

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

function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as ChatSession[];

    // One-time migration from legacy keys
    const merged: ChatSession[] = [];

    const legacyAnalysis = localStorage.getItem(LEGACY_ANALYSIS_KEY);
    if (legacyAnalysis) {
      const old = JSON.parse(legacyAnalysis) as Omit<ChatSession, "title">[];
      for (const s of old) {
        merged.push({
          ...s,
          title: s.context
            ? `${s.context.taskName} / ${s.context.qid}`
            : "General Chat",
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
          createdAt: s.createdAt,
          updatedAt: s.updatedAt,
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

const GENERAL_CHAT_KEY = "__general__";

function contextKey(ctx: AnalysisContext | null): string {
  if (!ctx) return GENERAL_CHAT_KEY;
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
          title: `${ctx.taskName} / ${ctx.qid}`,
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

  const openGeneralChat = useCallback(() => {
    // Find existing general session (no context)
    const existing = sessions.find(
      (s) => contextKey(s.context) === GENERAL_CHAT_KEY,
    );
    if (existing) {
      setActiveSessionId(existing.id);
    } else {
      const id = generateId();
      const now = Date.now();
      const session: ChatSession = {
        id,
        title: "New Chat",
        context: null,
        messages: [],
        createdAt: now,
        updatedAt: now,
      };
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(id);
    }
    setIsOpen(true);
  }, [sessions]);

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

  const createNewSession = useCallback(
    (ctx: AnalysisContext | null): string => {
      const id = generateId();
      const now = Date.now();
      const session: ChatSession = {
        id,
        title: ctx ? `${ctx.taskName} / ${ctx.qid}` : "New Chat",
        context: ctx,
        messages: [],
        createdAt: now,
        updatedAt: now,
      };
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(id);
      return id;
    },
    [],
  );

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

  const updateSessionMessages = useCallback(
    (sessionId: string, messages: ChatMessage[]) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId ? { ...s, messages, updatedAt: Date.now() } : s,
        ),
      );
    },
    [],
  );

  const autoTitleSession = useCallback(
    (sessionId: string, firstMessage: string) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId && s.title === "New Chat"
            ? { ...s, title: firstMessage.slice(0, 50) }
            : s,
        ),
      );
    },
    [],
  );

  return (
    <AnalysisChatCtx.Provider
      value={{
        isOpen,
        openAnalysisChat,
        openGeneralChat,
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
    throw new Error(
      "useAnalysisChatContext must be used within AnalysisChatProvider",
    );
  }
  return ctx;
}
