"use client";

import { useState, useCallback, useRef } from "react";
import {
  useCopilotChatSessionContext,
  type CopilotChatSession,
} from "@/contexts/CopilotChatSessionContext";
import type { BlocksResult, ChatMessage } from "@/hooks/useAnalysisChat";
import type { ModelOverride } from "@/lib/copilotModels";
import { buildHeaders, consumeSSEEvents, readErrorResponse } from "@/lib/sse-utils";

// Re-export for backward compat
export type CopilotMessage = ChatMessage;
export type CopilotSession = CopilotChatSession;

// ---------------------------------------------------------------------------
// Live transcript of one turn
// ---------------------------------------------------------------------------

export type TraceStep =
  | { kind: "thinking"; text: string; startedAt: number; endedAt?: number }
  | {
      kind: "tool";
      id: string;
      tool: string;
      label: string;
      args?: unknown;
      status: "running" | "done" | "error";
      startedAt: number;
      endedAt?: number;
    }
  | { kind: "text"; text: string };

/** The work behind an answer, persisted with it so the steps survive a reload. */
export interface ChatTrace {
  steps: TraceStep[];
  durationMs: number;
}

/** Assistant payload stored in `ChatMessage.content` as JSON. */
export type CopilotBlocksResult = BlocksResult & {
  trace?: ChatTrace;
  /** The user stopped the turn; the blocks hold whatever had streamed. */
  stopped?: boolean;
};

export interface LiveTurn {
  steps: TraceStep[];
  startedAt: number;
}

// Bound what a single message adds to the stored session document.
const MAX_PERSISTED_THINKING = 20_000;
const MAX_PERSISTED_ARGS = 4_000;

function closeThinking(steps: TraceStep[], now: number): TraceStep[] {
  return steps.map((step) =>
    step.kind === "thinking" && step.endedAt === undefined ? { ...step, endedAt: now } : step,
  );
}

function closeOpenSteps(steps: TraceStep[], now: number): TraceStep[] {
  return steps.map((step) => {
    if (step.kind === "thinking" && step.endedAt === undefined) return { ...step, endedAt: now };
    if (step.kind === "tool" && step.status === "running") return { ...step, endedAt: now };
    return step;
  });
}

/** Append streamed text to the last step of the same kind, or open a new one. */
function appendDelta(steps: TraceStep[], kind: "text" | "thinking", text: string): TraceStep[] {
  const now = Date.now();
  const last = steps[steps.length - 1];
  if (last && last.kind === kind) {
    return [...steps.slice(0, -1), { ...last, text: last.text + text }];
  }
  // Moving from thinking to text (or vice versa) ends the previous thinking span.
  return [
    ...closeThinking(steps, now),
    kind === "text" ? { kind, text } : { kind, text, startedAt: now },
  ];
}

/** Index where the trailing answer text starts; everything before it is "work". */
export function answerStartIndex(steps: TraceStep[]): number {
  let i = steps.length;
  while (i > 0 && steps[i - 1].kind === "text") i--;
  return i;
}

function truncateArgs(args: unknown): unknown {
  if (args === undefined) return undefined;
  try {
    const json = JSON.stringify(args);
    return json.length > MAX_PERSISTED_ARGS ? `${json.slice(0, MAX_PERSISTED_ARGS)}…` : args;
  } catch {
    return undefined;
  }
}

/** Shrink the live steps into what is stored alongside the final answer. */
function toPersistedTrace(turn: LiveTurn, now: number): ChatTrace | undefined {
  const work = closeOpenSteps(turn.steps, now).slice(0, answerStartIndex(turn.steps));
  if (work.length === 0) return undefined;
  let thinkingBudget = MAX_PERSISTED_THINKING;
  const steps = work.map((step): TraceStep => {
    if (step.kind === "thinking") {
      const text = step.text.slice(0, Math.max(0, thinkingBudget));
      thinkingBudget -= text.length;
      return { ...step, text };
    }
    if (step.kind === "tool") return { ...step, args: truncateArgs(step.args) };
    return step;
  });
  return { steps, durationMs: now - turn.startedAt };
}

function streamedAnswer(turn: LiveTurn): string {
  return turn.steps
    .slice(answerStartIndex(turn.steps))
    .map((step) => (step.kind === "text" ? step.text : ""))
    .join("");
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

interface UseCopilotChatOptions {
  modelOverride?: ModelOverride | null;
}

export function useCopilotChat(options?: UseCopilotChatOptions) {
  const modelOverride = options?.modelOverride ?? null;
  const {
    sessions,
    activeSessionId,
    activeSession,
    isLoadingSessions,
    switchSession,
    createNewSession,
    deleteSession,
    clearActiveSession: ctxClearActiveSession,
    updateSessionMessages,
    autoTitleSession,
  } = useCopilotChatSessionContext();

  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [liveTurn, setLiveTurn] = useState<LiveTurn | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Mirror of liveTurn readable from async code without stale closures.
  const liveTurnRef = useRef<LiveTurn | null>(null);

  const updateLiveTurn = useCallback((update: (turn: LiveTurn) => LiveTurn) => {
    const current = liveTurnRef.current;
    if (!current) return;
    const next = update(current);
    liveTurnRef.current = next;
    setLiveTurn(next);
  }, []);

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
    async (userMessage: string, opts?: { history?: ChatMessage[] }) => {
      const requestId = crypto.randomUUID();
      let sessionId = activeSessionId;

      // Auto-create session if none active
      if (!sessionId) {
        sessionId = createNewSession(null);
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const turn: LiveTurn = { steps: [], startedAt: Date.now() };
      liveTurnRef.current = turn;
      setLiveTurn(turn);
      setError(null);
      setStatusMessage(null);
      setIsLoading(true);

      const userMsg: CopilotMessage = { role: "user", content: userMessage };

      // Messages before this turn. A retry passes the history without the
      // failed exchange so it is replaced rather than duplicated.
      const currentMessages = opts?.history ?? activeSession?.messages ?? [];

      updateSessionMessages(sessionId, [...currentMessages, userMsg]);
      autoTitleSession(sessionId, userMessage);

      const finish = (result: CopilotBlocksResult) => {
        const now = Date.now();
        const trace = liveTurnRef.current ? toPersistedTrace(liveTurnRef.current, now) : undefined;
        const assistantMsg: CopilotMessage = {
          role: "assistant",
          content: JSON.stringify(trace ? { ...result, trace } : result),
        };
        updateSessionMessages(sessionId!, [...currentMessages, userMsg, assistantMsg]);
      };

      try {
        const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";
        const response = await fetch(`${baseURL}/copilot/chat/stream`, {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify({
            message: userMessage,
            // Required by the Pi backend, which restores conversation state
            // from the persisted session rather than from the request body.
            session_id: sessionId,
            request_id: requestId,
            conversation_history: currentMessages.map((m) => ({
              role: m.role,
              content: m.content,
            })),
            model_override: modelOverride,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(await readErrorResponse(response));
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("No response body");
        }

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
              updateLiveTurn((t) => ({ ...t, steps: appendDelta(t.steps, "text", payload.text) }));
            } else if (evt.event === "thinking") {
              updateLiveTurn((t) => ({
                ...t,
                steps: appendDelta(t.steps, "thinking", payload.text),
              }));
            } else if (evt.event === "tool_start") {
              const now = Date.now();
              updateLiveTurn((t) => ({
                ...t,
                steps: [
                  ...closeThinking(t.steps, now),
                  {
                    kind: "tool",
                    id: payload.id ?? `${payload.tool}-${now}`,
                    tool: payload.tool,
                    label: payload.label ?? payload.tool,
                    args: payload.args ?? undefined,
                    status: "running",
                    startedAt: now,
                  },
                ],
              }));
            } else if (evt.event === "tool_end") {
              const now = Date.now();
              updateLiveTurn((t) => {
                // Match by call id; fall back to the oldest running call of that tool.
                const idx =
                  payload.id != null
                    ? t.steps.findIndex((s) => s.kind === "tool" && s.id === payload.id)
                    : t.steps.findIndex(
                        (s) =>
                          s.kind === "tool" && s.tool === payload.tool && s.status === "running",
                      );
                if (idx < 0) return t;
                const steps = [...t.steps];
                const step = steps[idx];
                if (step.kind === "tool") {
                  steps[idx] = {
                    ...step,
                    status: payload.is_error ? "error" : "done",
                    endedAt: now,
                  };
                }
                return { ...t, steps };
              });
            } else if (evt.event === "status") {
              setStatusMessage(payload.message);
            } else if (evt.event === "result") {
              gotResult = true;
              const result: CopilotBlocksResult =
                payload.blocks && Array.isArray(payload.blocks)
                  ? payload
                  : {
                      blocks: [
                        {
                          type: "text",
                          content: payload.explanation || JSON.stringify(payload),
                          chart: null,
                        },
                      ],
                      assessment: null,
                    };
              finish(result);
            } else if (evt.event === "error") {
              throw new Error(payload.detail);
            }
          }
        }

        if (!gotResult) {
          throw new Error("The connection closed before the answer was complete");
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // Keep whatever had streamed, like ChatGPT/Claude do on Stop.
          const turnSoFar = liveTurnRef.current;
          if (turnSoFar && controller.signal.reason === "stop") {
            const partial = streamedAnswer(turnSoFar);
            finish({
              blocks: partial ? [{ type: "text", content: partial, chart: null }] : [],
              assessment: null,
              stopped: true,
            });
          }
          return;
        }
        const errorMsg = err instanceof Error ? err.message : "Request failed";
        setError(errorMsg);
        const errorAssistant: CopilotMessage = {
          role: "assistant",
          content: `Error: ${errorMsg}`,
        };
        updateSessionMessages(sessionId!, [...currentMessages, userMsg, errorAssistant]);
      } finally {
        if (abortRef.current === controller) {
          setIsLoading(false);
          setStatusMessage(null);
          liveTurnRef.current = null;
          setLiveTurn(null);
          abortRef.current = null;
        }
      }
    },
    [
      activeSessionId,
      activeSession,
      createNewSession,
      updateSessionMessages,
      autoTitleSession,
      modelOverride,
      updateLiveTurn,
    ],
  );

  /** Stop streaming and keep the partial answer. */
  const stop = useCallback(() => {
    abortRef.current?.abort("stop");
  }, []);

  /** Re-send the last user message, replacing the failed or stopped answer. */
  const retryLast = useCallback(() => {
    const messages = activeSession?.messages ?? [];
    let lastUser = messages.length - 1;
    while (lastUser >= 0 && messages[lastUser].role !== "user") lastUser--;
    if (lastUser < 0 || isLoading) return;
    sendMessage(messages[lastUser].content, { history: messages.slice(0, lastUser) });
  }, [activeSession?.messages, isLoading, sendMessage]);

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
    isLoadingSessions,
    isLoading,
    statusMessage,
    liveTurn,
    error,
    createSession,
    switchSession: handleSwitchSession,
    deleteSession: handleDeleteSession,
    sendMessage,
    stop,
    retryLast,
    clearActiveSession,
  };
}
