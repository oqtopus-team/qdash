import type { TraceStep, TurnActivitySnapshot } from "@/types/copilotChat";

const MAX_LABEL = 120;

/**
 * What a streaming turn is doing now, reduced to what may be stored with its pointer: the
 * last tool being written or run (its name and label), a thought, the answer being written,
 * or the server's status line. Null when the turn has said nothing yet.
 */
export function activitySnapshot(
  steps: TraceStep[],
  statusMessage: string | null,
): TurnActivitySnapshot | null {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.kind === "tool" && (step.status === "running" || step.status === "drafting")) {
      return { tool: step.tool, label: step.label.slice(0, MAX_LABEL) };
    }
  }
  if (steps.some((s) => s.kind === "thinking" && s.endedAt === undefined)) {
    return { tool: null, label: "Thinking" };
  }
  const last = steps[steps.length - 1];
  if (last?.kind === "text" && last.text) return { tool: null, label: "Writing the answer" };
  return statusMessage ? { tool: null, label: statusMessage.slice(0, MAX_LABEL) } : null;
}

export function sameActivity(
  a: TurnActivitySnapshot | null | undefined,
  b: TurnActivitySnapshot | null | undefined,
): boolean {
  return (a?.tool ?? null) === (b?.tool ?? null) && (a?.label ?? null) === (b?.label ?? null);
}
