"use client";

import { useState, useCallback, useRef } from "react";
import {
  useAnalysisChatContext,
  type ChatSession,
} from "@/contexts/AnalysisChatContext";
import type { ChatMessage } from "@/hooks/useAnalysisChat";

// Re-export for backward compat
export type CopilotMessage = ChatMessage;
export type CopilotSession = ChatSession;

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

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
  const {
    sessions,
    activeSessionId,
    activeSession,
    switchSession,
    createNewSession,
    deleteSession,
    clearActiveSession: ctxClearActiveSession,
    updateSessionMessages,
    autoTitleSession,
  } = useAnalysisChatContext();

  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const createSession = useCallback((): string => {
    const id = createNewSession(null);
    setError(null);
    return id;
  }, [createNewSession]);

  const handleSwitchSession = useCallback(
    (id: string) => {
      switchSession(id);
      setError(null);
      setStatusMessage(null);
    },
    [switchSession],
  );

  const handleDeleteSession = useCallback(
    (id: string) => {
      deleteSession(id);
    },
    [deleteSession],
  );

  const sendMessage = useCallback(
    async (userMessage: string) => {
      let sessionId = activeSessionId;

      // Auto-create session if none active
      if (!sessionId) {
        sessionId = createNewSession(null);
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setError(null);
      setStatusMessage("応答を準備中...");
      setIsLoading(true);

      const userMsg: CopilotMessage = { role: "user", content: userMessage };

      // Get current messages before adding the user message
      const currentMessages = activeSession?.messages ?? [];

      // Add user message and auto-title
      updateSessionMessages(sessionId, [...currentMessages, userMsg]);
      autoTitleSession(sessionId, userMessage);

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
        // Track messages locally to avoid stale closure issues during streaming
        let messagesSnapshot = [...currentMessages, userMsg];

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
              messagesSnapshot = [...messagesSnapshot, assistantMsg];
              updateSessionMessages(sessionId!, messagesSnapshot);
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
        // Re-read messages from context to get latest state
        updateSessionMessages(sessionId!, [
          ...currentMessages,
          userMsg,
          errorAssistant,
        ]);
      } finally {
        setIsLoading(false);
        setStatusMessage(null);
        abortRef.current = null;
      }
    },
    [
      activeSessionId,
      activeSession,
      createNewSession,
      updateSessionMessages,
      autoTitleSession,
    ],
  );

  const clearActiveSession = useCallback(() => {
    abortRef.current?.abort();
    ctxClearActiveSession();
    setError(null);
    setStatusMessage(null);
  }, [ctxClearActiveSession]);

  return {
    sessions,
    activeSession,
    activeSessionId,
    isLoading,
    statusMessage,
    error,
    createSession,
    switchSession: handleSwitchSession,
    deleteSession: handleDeleteSession,
    sendMessage,
    clearActiveSession,
  };
}
