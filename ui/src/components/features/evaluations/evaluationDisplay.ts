import type { EvaluationItem, EvaluationRunSummary } from "@/schemas";

/** The parsed JSON diagnosis of an evaluation, when the model answered with one. */
export type Diagnosis = Record<string, unknown>;

export function diagnosisOf(item: Pick<EvaluationItem, "output">): Diagnosis | null {
  const diagnosis = item.output?.diagnosis;
  if (typeof diagnosis !== "object" || diagnosis === null || Array.isArray(diagnosis)) return null;
  return diagnosis as Diagnosis;
}

/** The diagnosis' fit quality as one word (good / marginal / poor), or null. */
export function fitQuality(diagnosis: Diagnosis | null): string | null {
  const value = diagnosis?.fit_quality;
  if (typeof value !== "string") return null;
  const word = value
    .trim()
    .split(/[\s,.:;(]/)[0]
    ?.toLowerCase();
  return word || null;
}

export function fitQualityBadgeClass(fit: string | null): string {
  if (fit === "good") return "badge-success";
  if (fit === "marginal") return "badge-warning";
  if (fit === "poor") return "badge-error";
  return "badge-ghost";
}

/** The diagnosis' success verdict; null when the model left it out. */
export function diagnosisSuccess(diagnosis: Diagnosis | null): boolean | null {
  const value = diagnosis?.success;
  return typeof value === "boolean" ? value : null;
}

/** One diagnosis field as text: strings as they are, structures pretty-printed. */
export function diagnosisText(diagnosis: Diagnosis | null, key: string): string | null {
  const value = diagnosis?.[key];
  if (value === undefined || value === null || value === "") return null;
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

/** Diagnosis sections in the order the evaluation model is asked for them. */
export const DIAGNOSIS_SECTIONS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "technical_description", label: "What the plot shows" },
  { key: "experimental_conclusion", label: "Conclusion" },
  { key: "experimental_significance", label: "Significance" },
  { key: "parameter_extraction", label: "Extracted parameters" },
];

export function modeLabel(mode: string): string {
  return mode === "planner" ? "Planner" : "Direct";
}

export function triggerLabel(trigger: string): string {
  return trigger === "single" ? "Single result" : "Chip";
}

export function statusBadgeClass(status: string): string {
  if (status === "completed") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "running") return "badge-info";
  return "badge-ghost";
}

/** `name@version`, with the checkout commit when the code came from a mounted checkout. */
export function evaluatorLabel(
  evaluator: { name: string; version: string; commit?: string | null } | null | undefined,
): string | null {
  if (!evaluator) return null;
  const base = `${evaluator.name}@${evaluator.version}`;
  return evaluator.commit ? `${base} (${evaluator.commit})` : base;
}

export function formatDuration(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 90_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

/** Finished evaluations of a run, done or failed. */
export function runDone(
  run: Pick<EvaluationRunSummary, "completed_count" | "failed_count">,
): number {
  return run.completed_count + run.failed_count;
}

/** Whether a run still has work in flight, so the page keeps polling. */
export function runIsActive(run: Pick<EvaluationRunSummary, "status" | "pending_count">): boolean {
  return run.status === "running" || run.pending_count > 0;
}

/** Agreement rate over the evaluations people have judged, or null before any verdict. */
export function agreementRate(
  run: Pick<EvaluationRunSummary, "agree_count" | "disagree_count">,
): number | null {
  const judged = run.agree_count + run.disagree_count;
  return judged === 0 ? null : run.agree_count / judged;
}
