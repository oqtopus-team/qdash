"use client";

import { useState, useCallback, useRef, useEffect } from "react";
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

export interface ContentBlock {
  type: "text" | "chart";
  content: string | null;
  chart: {
    data: Record<string, unknown>[];
    layout: Record<string, unknown>;
  } | null;
}

export interface BlocksResult {
  blocks: ContentBlock[];
  assessment: "good" | "warning" | "bad" | null;
  images_sent?: {
    experiment_figure: boolean;
    experiment_figure_paths: string[];
    expected_images: { alt_text: string; index: number }[];
    task_name: string;
  };
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

/**
 * Parse complete SSE events from the buffer.
 * Returns { events, remainder } where remainder is the unparsed trailing text.
 */
function consumeSSEEvents(text: string): {
  events: SSEEvent[];
  remainder: string;
} {
  const events: SSEEvent[] = [];

  // Only process up to the last complete block (terminated by \n\n)
  const lastDoubleNewline = text.lastIndexOf("\n\n");
  if (lastDoubleNewline === -1) {
    // No complete event yet — keep everything in buffer
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
        // "data:" with no space (empty or continuation)
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

export function useAnalysisChat(
  context: AnalysisContext | null,
  options?: {
    initialMessages?: ChatMessage[];
    onMessagesChange?: (messages: ChatMessage[]) => void;
  },
) {
  const [messages, setMessagesRaw] = useState<ChatMessage[]>(
    options?.initialMessages ?? [],
  );
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const onMessagesChangeRef = useRef(options?.onMessagesChange);
  onMessagesChangeRef.current = options?.onMessagesChange;

  // Wrapper that also syncs to external store
  const setMessages: typeof setMessagesRaw = useCallback((updater) => {
    setMessagesRaw((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      onMessagesChangeRef.current?.(next);
      return next;
    });
  }, []);

  // Sync from external initial messages when they change (context switch)
  const initialRef = useRef(options?.initialMessages);
  useEffect(() => {
    if (options?.initialMessages !== initialRef.current) {
      initialRef.current = options?.initialMessages;
      setMessagesRaw(options?.initialMessages ?? []);
    }
  }, [options?.initialMessages]);

  const sendMessage = useCallback(
    async (userMessage: string, imageBase64?: string) => {
      // Abort any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setError(null);
      setStatusMessage(context ? "分析を開始中..." : "チャットを開始中...");
      const newUserMessage: ChatMessage = {
        role: "user",
        content: userMessage,
      };
      setMessages((prev) => [...prev, newUserMessage]);
      setIsLoading(true);

      try {
        const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";

        // Use analyze endpoint when context is available, chat endpoint otherwise
        const endpoint = context
          ? `${baseURL}/copilot/analyze/stream`
          : `${baseURL}/copilot/chat/stream`;

        const body = context
          ? {
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
            }
          : {
              message: userMessage,
              conversation_history: messages.map((m) => ({
                role: m.role,
                content: m.content,
              })),
            };

        const response = await fetch(endpoint, {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify(body),
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

          // Process only complete SSE events (delimited by \n\n)
          const { events, remainder } = consumeSSEEvents(buffer);
          buffer = remainder;

          for (const evt of events) {
            if (evt.event === "status") {
              const payload = JSON.parse(evt.data);
              flushSync(() => setStatusMessage(payload.message));
            } else if (evt.event === "result") {
              const result = JSON.parse(evt.data);
              // Blocks format: store as JSON string for rich rendering
              if (result.blocks && Array.isArray(result.blocks)) {
                setMessages((prev) => [
                  ...prev,
                  {
                    role: "assistant",
                    content: JSON.stringify(result),
                  },
                ]);
              } else {
                // Legacy format fallback
                const formattedResponse = formatAnalysisResponse(
                  result as AnalysisResult,
                );
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: formattedResponse },
                ]);
              }
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
    [context, messages, setMessages],
  );

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    setStatusMessage(null);
  }, [setMessages]);

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
