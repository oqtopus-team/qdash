"use client";

import { useState, useCallback, useRef, useEffect } from "react";

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CopilotSession {
  id: string;
  title: string;
  messages: CopilotMessage[];
  createdAt: number;
  updatedAt: number;
}

const STORAGE_KEY = "qdash_copilot_sessions";
const PROJECT_STORAGE_KEY = "qdash_current_project_id";

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function loadSessions(): CopilotSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSessions(sessions: CopilotSession[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const accessToken = document.cookie
    .split("; ")
    .find((row) => row.startsWith("access_token="))
    ?.split("=")[1];
  if (accessToken) {
    headers["Authorization"] = `Bearer ${decodeURIComponent(accessToken)}`;
  }

  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("token="))
    ?.split("=")[1];
  if (token) {
    const decoded = decodeURIComponent(token);
    if (!headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${decoded}`;
    }
    headers["X-Username"] = decoded;
  }

  const projectId = localStorage.getItem(PROJECT_STORAGE_KEY);
  if (projectId) {
    headers["X-Project-Id"] = projectId;
  }

  return headers;
}

interface SSEEvent {
  event: string;
  data: string;
}

function consumeSSEEvents(text: string): {
  events: SSEEvent[];
  remainder: string;
} {
  const events: SSEEvent[] = [];
  const lastDoubleNewline = text.lastIndexOf("\n\n");
  if (lastDoubleNewline === -1) {
    return { events, remainder: text };
  }

  const completePart = text.slice(0, lastDoubleNewline);
  const remainder = text.slice(lastDoubleNewline + 2);

  const blocks = completePart.split("\n\n");
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) {
        event = line.slice(7);
      } else if (line.startsWith("data: ")) {
        dataLines.push(line.slice(6));
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5));
      }
    }
    const data = dataLines.join("\n");
    if (event && data) {
      events.push({ event, data });
    }
  }
  return { events, remainder };
}

export function useCopilotChat() {
  const [sessions, setSessionsRaw] = useState<CopilotSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load sessions from localStorage on mount
  useEffect(() => {
    const loaded = loadSessions();
    setSessionsRaw(loaded);
    if (loaded.length > 0) {
      setActiveSessionId(loaded[0].id);
    }
  }, []);

  const setSessions = useCallback(
    (
      updater:
        | CopilotSession[]
        | ((prev: CopilotSession[]) => CopilotSession[]),
    ) => {
      setSessionsRaw((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        saveSessions(next);
        return next;
      });
    },
    [],
  );

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  const createSession = useCallback((): string => {
    const id = generateId();
    const session: CopilotSession = {
      id,
      title: "New Chat",
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(id);
    setError(null);
    return id;
  }, [setSessions]);

  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id);
    setError(null);
    setStatusMessage(null);
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const next = prev.filter((s) => s.id !== id);
        if (activeSessionId === id) {
          setActiveSessionId(next.length > 0 ? next[0].id : null);
        }
        return next;
      });
    },
    [activeSessionId, setSessions],
  );

  const sendMessage = useCallback(
    async (userMessage: string) => {
      let sessionId = activeSessionId;

      // Auto-create session if none active
      if (!sessionId) {
        const id = generateId();
        const session: CopilotSession = {
          id,
          title: userMessage.slice(0, 50),
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        setSessions((prev) => [session, ...prev]);
        setActiveSessionId(id);
        sessionId = id;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setError(null);
      setStatusMessage("応答を準備中...");
      setIsLoading(true);

      const userMsg: CopilotMessage = { role: "user", content: userMessage };

      // Get current messages for conversation history
      let currentMessages: CopilotMessage[] = [];
      setSessions((prev) => {
        const updated = prev.map((s) => {
          if (s.id === sessionId) {
            const newMessages = [...s.messages, userMsg];
            currentMessages = s.messages; // messages before this one
            return {
              ...s,
              messages: newMessages,
              title:
                s.messages.length === 0 ? userMessage.slice(0, 50) : s.title,
              updatedAt: Date.now(),
            };
          }
          return s;
        });
        return updated;
      });

      try {
        const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";
        const response = await fetch(`${baseURL}/copilot/chat/stream`, {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify({
            message: userMessage,
            conversation_history: currentMessages.map((m) => ({
              role: m.role,
              content: m.content,
            })),
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("No response body");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const { events, remainder } = consumeSSEEvents(buffer);
          buffer = remainder;

          for (const evt of events) {
            if (evt.event === "status") {
              const payload = JSON.parse(evt.data);
              setStatusMessage(payload.message);
            } else if (evt.event === "result") {
              const result = JSON.parse(evt.data);
              const assistantContent =
                result.blocks && Array.isArray(result.blocks)
                  ? JSON.stringify(result)
                  : result.explanation || JSON.stringify(result);

              const assistantMsg: CopilotMessage = {
                role: "assistant",
                content: assistantContent,
              };
              setSessions((prev) =>
                prev.map((s) =>
                  s.id === sessionId
                    ? {
                        ...s,
                        messages: [...s.messages, assistantMsg],
                        updatedAt: Date.now(),
                      }
                    : s,
                ),
              );
            } else if (evt.event === "error") {
              const payload = JSON.parse(evt.data);
              throw new Error(payload.detail);
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        const errorMsg = err instanceof Error ? err.message : "Request failed";
        setError(errorMsg);
        const errorAssistant: CopilotMessage = {
          role: "assistant",
          content: `Error: ${errorMsg}`,
        };
        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  messages: [...s.messages, errorAssistant],
                  updatedAt: Date.now(),
                }
              : s,
          ),
        );
      } finally {
        setIsLoading(false);
        setStatusMessage(null);
        abortRef.current = null;
      }
    },
    [activeSessionId, setSessions],
  );

  const clearActiveSession = useCallback(() => {
    if (!activeSessionId) return;
    abortRef.current?.abort();
    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSessionId
          ? { ...s, messages: [], updatedAt: Date.now() }
          : s,
      ),
    );
    setError(null);
    setStatusMessage(null);
  }, [activeSessionId, setSessions]);

  return {
    sessions,
    activeSession,
    activeSessionId,
    isLoading,
    statusMessage,
    error,
    createSession,
    switchSession,
    deleteSession,
    sendMessage,
    clearActiveSession,
  };
}
