"use client";

import { useState, useCallback, useRef } from "react";
import { buildHeaders, consumeSSEEvents } from "@/lib/sse-utils";

export function useIssueAiReply() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const triggerAiReply = useCallback(
    async (issueId: string, userMessage: string, onComplete: () => void) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsGenerating(true);
      setStatusMessage("AIが応答を準備中...");
      setError(null);

      try {
        const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";
        const response = await fetch(
          `${baseURL}/issues/${issueId}/ai-reply/stream`,
          {
            method: "POST",
            headers: buildHeaders(),
            body: JSON.stringify({ user_message: userMessage }),
            signal: controller.signal,
          },
        );

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
              // AI reply saved on server — trigger refresh
              onComplete();
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
        const errorMsg = err instanceof Error ? err.message : "AI reply failed";
        setError(errorMsg);
      } finally {
        setIsGenerating(false);
        setStatusMessage(null);
        abortRef.current = null;
      }
    },
    [],
  );

  return {
    isGenerating,
    statusMessage,
    error,
    triggerAiReply,
  };
}
