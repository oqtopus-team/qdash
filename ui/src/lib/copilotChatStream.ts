/**
 * Pure helpers that fold Copilot SSE events into a live transcript.
 */

import type {
  ChatTrace,
  ContentBlock,
  LiveTurn,
  ToolClassification,
  ToolEvaluation,
  TraceStep,
} from "@/types/copilotChat";

// Bound what a single message adds to the stored session document.
const MAX_PERSISTED_THINKING = 20_000;
const MAX_PERSISTED_ARGS = 4_000;
const MAX_PERSISTED_PROMPT = 12_000;
const MAX_PERSISTED_OUTPUT = 2_000;

function closeThinking(steps: TraceStep[], now: number): TraceStep[] {
  return steps.map((step) =>
    step.kind === "thinking" && step.endedAt === undefined ? { ...step, endedAt: now } : step,
  );
}

function closeOpenSteps(steps: TraceStep[], now: number): TraceStep[] {
  return steps.map((step) => {
    if (step.kind === "thinking" && step.endedAt === undefined) return { ...step, endedAt: now };
    // A call still being written when the turn ended was never made: it is
    // kept as cancelled, with what was typed as its arguments, never as done.
    if (step.kind === "tool" && step.status === "drafting") {
      return { ...step, status: "cancelled", endedAt: now };
    }
    if (step.kind === "tool" && step.status === "running") {
      return { ...step, status: "done", endedAt: now };
    }
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

/** The model started writing a tool call: a drafting step that `appendArgsDelta` fills. */
export function startDraft(
  steps: TraceStep[],
  payload: { index: number; id?: string | null; tool: string; label?: string },
): TraceStep[] {
  const now = Date.now();
  return [
    ...closeThinking(steps, now),
    {
      kind: "tool",
      id: payload.id || `draft-${payload.tool}-${payload.index}-${now}`,
      tool: payload.tool,
      label: payload.label ?? payload.tool,
      status: "drafting",
      startedAt: now,
      draft: {},
      draftIndex: payload.index,
    },
  ];
}

/** Text the model appended to one argument of the call it is writing. */
export function appendArgsDelta(
  steps: TraceStep[],
  payload: { index: number; path?: unknown; delta?: unknown },
): TraceStep[] {
  if (typeof payload.delta !== "string" || !payload.delta || !Array.isArray(payload.path)) {
    return steps;
  }
  const key = payload.path.map(String).join(".");
  let idx = -1;
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    if (s.kind === "tool" && s.status === "drafting" && s.draftIndex === payload.index) {
      idx = i;
      break;
    }
  }
  const step = steps[idx];
  if (!step || step.kind !== "tool") return steps;
  const draft = { ...(step.draft ?? {}), [key]: (step.draft?.[key] ?? "") + payload.delta };
  const next = [...steps];
  next[idx] = { ...step, draft };
  return next;
}

/** The call starts running: the drafting step becomes it, or a new step opens. */
export function startTool(
  steps: TraceStep[],
  payload: { id?: string | null; tool: string; label?: string; args?: unknown },
): TraceStep[] {
  const now = Date.now();
  // The draft is the one with this call's id; a provider that streams the call
  // without an id (the draft then got a synthetic one) leaves the latest draft
  // of the same tool, which is the call being written.
  let idx = -1;
  let sameTool = -1;
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    if (s.kind !== "tool" || s.status !== "drafting") continue;
    if (payload.id != null && s.id === payload.id) {
      idx = i;
      break;
    }
    if (
      sameTool === -1 &&
      s.tool === payload.tool &&
      (payload.id == null || s.id.startsWith("draft-"))
    ) {
      sameTool = i;
    }
  }
  if (idx === -1) idx = sameTool;
  const running = {
    id: payload.id ?? `${payload.tool}-${now}`,
    tool: payload.tool,
    label: payload.label ?? payload.tool,
    args: payload.args ?? undefined,
    status: "running" as const,
  };
  if (idx !== -1) {
    const step = steps[idx] as Extract<TraceStep, { kind: "tool" }>;
    const next = [...steps];
    const { draft: _draft, draftIndex: _draftIndex, ...rest } = step;
    next[idx] = { ...rest, ...running };
    return next;
  }
  return [...closeThinking(steps, now), { kind: "tool", ...running, startedAt: now }];
}

/** The evaluation summary of a tool_end payload, when it is well-formed. */
function toolEvaluation(value: unknown): ToolEvaluation | undefined {
  if (!value || typeof value !== "object") return undefined;
  const { prompt, model, fallback, run_id, evaluation_id } = value as Record<string, unknown>;
  if (typeof prompt !== "string" || !prompt) return undefined;
  return {
    prompt,
    ...(typeof model === "string" && model ? { model } : {}),
    ...(fallback === true ? { fallback: true } : {}),
    ...(typeof run_id === "string" && run_id ? { runId: run_id } : {}),
    ...(typeof evaluation_id === "string" && evaluation_id ? { evaluationId: evaluation_id } : {}),
  };
}

const CLASSIFICATION_OUTCOMES = new Set<ToolClassification["outcome"]>([
  "classified",
  "ambiguous",
  "failed",
]);

const isProbability = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;

/** The classifier decision of a tool_end payload (classify), when it is well-formed. */
function toolClassification(value: unknown): ToolClassification | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const { classifier, outcome, category, probability, margin, probabilities, reason } =
    value as Record<string, unknown>;
  if (typeof classifier !== "string" || !classifier) return undefined;
  if (!CLASSIFICATION_OUTCOMES.has(outcome as ToolClassification["outcome"])) return undefined;
  const ranked = Array.isArray(probabilities)
    ? probabilities.flatMap((entry) => {
        if (!entry || typeof entry !== "object") return [];
        const { category: name, probability: p } = entry as Record<string, unknown>;
        return typeof name === "string" && name && isProbability(p)
          ? [{ category: name, probability: p }]
          : [];
      })
    : [];
  return {
    classifier,
    outcome: outcome as ToolClassification["outcome"],
    ...(typeof category === "string" && category ? { category } : {}),
    ...(isProbability(probability) ? { probability } : {}),
    ...(typeof margin === "number" && Number.isFinite(margin) ? { margin } : {}),
    ...(ranked.length ? { probabilities: ranked } : {}),
    ...(typeof reason === "string" && reason ? { reason } : {}),
  };
}

export function endTool(
  steps: TraceStep[],
  payload: {
    id?: string | null;
    tool: string;
    is_error?: boolean;
    figures?: unknown;
    evaluation?: unknown;
    classification?: unknown;
    output?: unknown;
    exit_code?: unknown;
  },
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
  const figures = Array.isArray(payload.figures)
    ? payload.figures.filter((p): p is string => typeof p === "string" && p.length > 0)
    : [];
  const evaluation = toolEvaluation(payload.evaluation);
  const classification = toolClassification(payload.classification);
  const next = [...steps];
  next[idx] = {
    ...step,
    status: payload.is_error ? "error" : "done",
    endedAt: Date.now(),
    ...(figures.length ? { figures } : {}),
    ...(evaluation ? { evaluation } : {}),
    ...(classification ? { classification } : {}),
    ...(typeof payload.output === "string" && payload.output ? { output: payload.output } : {}),
    ...(typeof payload.exit_code === "number" ? { exitCode: payload.exit_code } : {}),
  };
  return next;
}

/** Index where the trailing answer text starts; everything before it is "work". */
export function answerStartIndex(steps: TraceStep[]): number {
  let i = steps.length;
  while (i > 0 && steps[i - 1].kind === "text") i--;
  return i;
}

/**
 * A `ui` SSE event: the block a `render_ui` call produced, added to the turn
 * as soon as its tool finished. The API sends a text block instead when the
 * runtime's payload was malformed but had a fallback.
 */
export function appendLiveBlock(turn: LiveTurn, payload: unknown): LiveTurn {
  if (!payload || typeof payload !== "object") return turn;
  const block = payload as Partial<ContentBlock>;
  if (block.type === "ui" && block.ui && typeof block.ui === "object") {
    return { ...turn, blocks: [...(turn.blocks ?? []), block as ContentBlock] };
  }
  if (block.type === "text" && typeof block.content === "string" && block.content) {
    return {
      ...turn,
      blocks: [...(turn.blocks ?? []), { type: "text", content: block.content, chart: null }],
    };
  }
  return turn;
}

/** The blocks kept when the user stops a turn: finished UI blocks, then the text so far. */
export function stoppedBlocks(turn: LiveTurn): ContentBlock[] {
  const partial = streamedAnswer(turn);
  return [
    ...(turn.blocks ?? []),
    ...(partial ? [{ type: "text" as const, content: partial, chart: null }] : []),
  ];
}

function streamedAnswer(turn: LiveTurn): string {
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
    if (step.kind === "tool") {
      const evaluation = step.evaluation && {
        ...step.evaluation,
        prompt: step.evaluation.prompt.slice(0, MAX_PERSISTED_PROMPT),
      };
      // A call the model never finished keeps what it wrote as its arguments.
      const { draft, draftIndex: _draftIndex, output, ...rest } = step;
      return {
        ...rest,
        args: truncateArgs(step.args ?? draft),
        ...(output
          ? {
              output:
                output.length > MAX_PERSISTED_OUTPUT
                  ? `…${output.slice(-MAX_PERSISTED_OUTPUT)}`
                  : output,
            }
          : {}),
        ...(evaluation ? { evaluation } : {}),
      };
    }
    return step;
  });
  return { steps, durationMs: now - turn.startedAt };
}
