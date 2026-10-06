/**
 * Pure helpers that fold Copilot SSE events into a live transcript.
 */

import type { ChatTrace, LiveTurn, TraceStep } from "@/types/copilotChat";

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
export function appendDelta(
  steps: TraceStep[],
  kind: "text" | "thinking",
  text: string,
): TraceStep[] {
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

export function startTool(
  steps: TraceStep[],
  payload: { id?: string | null; tool: string; label?: string; args?: unknown },
): TraceStep[] {
  const now = Date.now();
  return [
    ...closeThinking(steps, now),
    {
      kind: "tool",
      id: payload.id ?? `${payload.tool}-${now}`,
      tool: payload.tool,
      label: payload.label ?? payload.tool,
      args: payload.args ?? undefined,
      status: "running",
      startedAt: now,
    },
  ];
}

export function endTool(
  steps: TraceStep[],
  payload: { id?: string | null; tool: string; is_error?: boolean },
): TraceStep[] {
  // Match by call id; fall back to the oldest running call of that tool.
  const idx =
    payload.id != null
      ? steps.findIndex((s) => s.kind === "tool" && s.id === payload.id)
      : steps.findIndex(
          (s) => s.kind === "tool" && s.tool === payload.tool && s.status === "running",
        );
  const step = steps[idx];
  if (!step || step.kind !== "tool") return steps;
  const next = [...steps];
  next[idx] = { ...step, status: payload.is_error ? "error" : "done", endedAt: Date.now() };
  return next;
}

/** Index where the trailing answer text starts; everything before it is "work". */
export function answerStartIndex(steps: TraceStep[]): number {
  let i = steps.length;
  while (i > 0 && steps[i - 1].kind === "text") i--;
  return i;
}

export function streamedAnswer(turn: LiveTurn): string {
  return turn.steps
    .slice(answerStartIndex(turn.steps))
    .map((step) => (step.kind === "text" ? step.text : ""))
    .join("");
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
export function toPersistedTrace(turn: LiveTurn, now: number): ChatTrace | undefined {
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
