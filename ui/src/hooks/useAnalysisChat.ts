"use client";

import { useState, useCallback, useRef } from "react";
import { flushSync } from "react-dom";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AnalysisResult {
  summary: string;
  assessment: "good" | "warning" | "bad";
  explanation: string;
  potential_issues: string[];
  recommendations: string[];
}

export interface AnalysisContext {
  taskName: string;
  chipId: string;
  qid: string;
  executionId: string;
  taskId: string;
}

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Match custom-instance.ts interceptor: cookie "access_token"
  const accessToken = document.cookie
    .split("; ")
    .find((row) => row.startsWith("access_token="))
    ?.split("=")[1];
  if (accessToken) {
    headers["Authorization"] = `Bearer ${decodeURIComponent(accessToken)}`;
  }

  // Match AxiosProvider interceptor: cookie "token" (username)
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

  // Match AxiosProvider: localStorage project ID
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

function parseSSEEvents(text: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  const blocks = text.split("\n\n");
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) {
        event = line.slice(7);
      } else if (line.startsWith("data: ")) {
        data = line.slice(6);
      }
    }
    if (event && data) {
      events.push({ event, data });
    }
  }
  return events;
}

export function useAnalysisChat(context: AnalysisContext | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (userMessage: string, imageBase64?: string) => {
      if (!context) return;

      // Abort any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setError(null);
      setStatusMessage("分析を開始中...");
      const newUserMessage: ChatMessage = {
        role: "user",
        content: userMessage,
      };
      setMessages((prev) => [...prev, newUserMessage]);
      setIsLoading(true);

      try {
        const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";
        const response = await fetch(`${baseURL}/copilot/analyze/stream`, {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify({
            task_name: context.taskName,
            chip_id: context.chipId,
            qid: context.qid,
            execution_id: context.executionId,
            task_id: context.taskId,
            message: userMessage,
            image_base64: imageBase64 || null,
            conversation_history: messages.map((m) => ({
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

          // Process complete SSE events (delimited by \n\n)
          const events = parseSSEEvents(buffer);
          // Keep the last incomplete block in buffer
          const lastDoubleNewline = buffer.lastIndexOf("\n\n");
          if (lastDoubleNewline !== -1) {
            buffer = buffer.slice(lastDoubleNewline + 2);
          }

          for (const evt of events) {
            if (evt.event === "status") {
              const payload = JSON.parse(evt.data);
              flushSync(() => setStatusMessage(payload.message));
            } else if (evt.event === "result") {
              const result: AnalysisResult = JSON.parse(evt.data);
              const formattedResponse = formatAnalysisResponse(result);
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: formattedResponse },
              ]);
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
        const errorMsg =
          err instanceof Error ? err.message : "Analysis request failed";
        setError(errorMsg);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Analysis failed: ${errorMsg}`,
          },
        ]);
      } finally {
        setIsLoading(false);
        setStatusMessage(null);
        abortRef.current = null;
      }
    },
    [context, messages],
  );

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    setStatusMessage(null);
  }, []);

  return {
    messages,
    isLoading,
    statusMessage,
    error,
    sendMessage,
    clearMessages,
  };
}

function formatAnalysisResponse(result: AnalysisResult): string {
  const parts: string[] = [];

  // Assessment badge
  const badge =
    result.assessment === "good"
      ? "Good"
      : result.assessment === "warning"
        ? "Warning"
        : "Bad";
  parts.push(`**[${badge}]** ${result.summary}\n`);

  // Explanation
  parts.push(result.explanation);

  // Issues
  if (result.potential_issues.length > 0) {
    parts.push("\n**Potential Issues:**");
    result.potential_issues.forEach((issue) => {
      parts.push(`- ${issue}`);
    });
  }

  // Recommendations
  if (result.recommendations.length > 0) {
    parts.push("\n**Recommendations:**");
    result.recommendations.forEach((rec) => {
      parts.push(`- ${rec}`);
    });
  }

  return parts.join("\n");
}
