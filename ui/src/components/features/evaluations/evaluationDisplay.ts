import type {
  EvaluationCallModel,
  EvaluationItem,
  EvaluationOutputModel,
  EvaluationRunSummary,
} from "@/schemas";

/** The parsed JSON diagnosis of an evaluation, when the model answered with one. */
export type Diagnosis = Record<string, unknown>;

export function diagnosisOf(item: Pick<EvaluationItem, "output">): Diagnosis | null {
  const diagnosis = item.output?.diagnosis;
  if (typeof diagnosis !== "object" || diagnosis === null || Array.isArray(diagnosis)) return null;
  return diagnosis as Diagnosis;
}

/** A nested answer of one question, when the diagnosis stores it as an object. */
function section(diagnosis: Diagnosis | null, key: string): Record<string, unknown> | null {
  const value = diagnosis?.[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function word(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** The outcome the model classified (expected / suboptimal / anomalous / apparatus), or null. */
export function diagnosisOutcome(diagnosis: Diagnosis | null): string | null {
  const value = word(section(diagnosis, "experimental_conclusion")?.classification);
  return value ? value.toLowerCase() : null;
}

export function outcomeBadgeClass(outcome: string | null): string {
  if (outcome === "expected") return "badge-success";
  if (outcome === "suboptimal") return "badge-warning";
  if (outcome === "anomalous" || outcome === "apparatus") return "badge-error";
  return "badge-ghost";
}

/**
 * The fit assessment of Q4 (reliable / unreliable / no_fit), or null. A record
 * made before the per-question protocol carries `fit_quality` instead, which
 * is not an assessment.
 */
export function fitAssessment(diagnosis: Diagnosis | null): string | null {
  const value = word(section(diagnosis, "fit_reliability")?.assessment);
  return value ? value.toLowerCase().replace(/\s+/g, "_") : null;
}

export function fitBadgeClass(fit: string | null): string {
  if (fit === "reliable") return "badge-success";
  if (fit === "unreliable") return "badge-error";
  if (fit === "no_fit") return "badge-warning";
  return "badge-ghost";
}

/** The fit assessment as the badge reads it. */
export function fitLabel(fit: string): string {
  return fit === "no_fit" ? "no fit" : `fit ${fit}`;
}

/** The status code of Q6 (calibration_diagnosis.status), or null. */
export function diagnosisStatus(diagnosis: Diagnosis | null): string | null {
  return word(section(diagnosis, "calibration_diagnosis")?.status);
}

/** The diagnosis' success verdict; null when the model left it out. */
export function diagnosisSuccess(diagnosis: Diagnosis | null): boolean | null {
  const value = diagnosis?.success;
  return typeof value === "boolean" ? value : null;
}

/** What the status badge says: the status code, or the success verdict when none was asked. */
export function statusLabel(diagnosis: Diagnosis | null): string | null {
  const status = diagnosisStatus(diagnosis);
  if (status) return status;
  const success = diagnosisSuccess(diagnosis);
  return success === null ? null : success ? "success" : "not successful";
}

function jsonText(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

/** A Q1 description as lines: plot type, axes, features. */
function plotDescription(value: Record<string, unknown>): string {
  const axis = (key: string): string | null => {
    const a = value[key];
    if (typeof a !== "object" || a === null) return typeof a === "string" ? a : null;
    const { label, scale, range } = a as { label?: unknown; scale?: unknown; range?: unknown };
    const parts = [
      typeof label === "string" ? label : null,
      typeof scale === "string" ? `(${scale})` : null,
      Array.isArray(range) ? `[${range.join(", ")}]` : null,
    ].filter(Boolean);
    return parts.length > 0 ? parts.join(" ") : null;
  };
  const lines = [
    typeof value.plot_type === "string" ? `${value.plot_type} plot` : null,
    axis("x_axis") ? `x: ${axis("x_axis")}` : null,
    axis("y_axis") ? `y: ${axis("y_axis")}` : null,
    typeof value.main_features === "string" ? value.main_features : null,
  ].filter(Boolean);
  return lines.length > 0 ? lines.join("\n") : jsonText(value);
}

/**
 * One diagnosis section as text: the answer's prose (the reason of a
 * classification, the notes of a status), structures pretty-printed, strings
 * as they are. Null when the question was not answered.
 */
export function diagnosisText(diagnosis: Diagnosis | null, key: string): string | null {
  const value = diagnosis?.[key];
  if (value === undefined || value === null || value === "") return null;
  if (typeof value === "string") return value;
  if (typeof value !== "object" || Array.isArray(value)) return jsonText(value);
  const object = value as Record<string, unknown>;
  switch (key) {
    case "technical_description":
      return plotDescription(object);
    case "experimental_conclusion":
    case "fit_reliability":
      return word(object.reason) ?? jsonText(object);
    case "calibration_diagnosis": {
      const range = word(object.suggested_range);
      const notes = word(object.notes);
      const lines = [range ? `Suggested range: ${range}` : null, notes].filter(Boolean);
      return lines.length > 0 ? lines.join("\n") : jsonText(object);
    }
    default:
      return jsonText(object);
  }
}

/**
 * How a completed answer fell short of the diagnosis, for a badge: prose
 * instead of JSON, or JSON lacking some of the six keys (the model closing the
 * object after the first one). Null when the answer is the whole diagnosis.
 */
export function answerShortfall(
  output: Pick<EvaluationOutputModel, "parsed" | "complete" | "missing_keys"> | null | undefined,
): { label: string; title: string } | null {
  if (!output) return null;
  if (!output.parsed) return { label: "prose", title: "The answer was not the JSON diagnosis" };
  if (output.complete === false) {
    const missing = output.missing_keys ?? [];
    return {
      label: "incomplete",
      title:
        missing.length > 0 ? `Missing: ${missing.join(", ")}` : "The diagnosis lacks some keys",
    };
  }
  return null;
}

/** Diagnosis sections in the order the evaluation model is asked (QCalEval Q1–Q6). */
export const DIAGNOSIS_SECTIONS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "technical_description", label: "What the plot shows" },
  { key: "experimental_conclusion", label: "Outcome" },
  { key: "experimental_significance", label: "Significance" },
  { key: "fit_reliability", label: "Fit" },
  { key: "parameter_extraction", label: "Extracted parameters" },
  { key: "calibration_diagnosis", label: "Diagnosis" },
];

/** The question a section answers, for a heading next to the raw answer. */
export function questionLabel(key: string): string {
  return DIAGNOSIS_SECTIONS.find((section) => section.key === key)?.label ?? key;
}

/**
 * Who prepared the prompt: QDash, the same fixed prompt every time (`direct`),
 * or Copilot, the chat planner, summarising the result and calling the
 * evaluation itself (`planner`). Independent of whether labeled examples were
 * shown (see `examplesLabel`).
 */
export function modeLabel(mode: string): string {
  return mode === "planner" ? "Via Copilot" : "Fixed prompt";
}

/** Whether labeled examples were shown before the figure, in QCalEval's terms. */
export function examplesLabel(withExamples: boolean | undefined): string {
  return withExamples ? "In-context" : "Zero-shot";
}

export function triggerLabel(trigger: string): string {
  if (trigger === "single") return "Single result";
  if (trigger === "chat") return "Chat";
  return "Chip";
}

/** `name@version`, with the checkout commit when the code came from a mounted checkout. */
export function evaluatorLabel(
  evaluator: { name: string; version: string; commit?: string | null } | null | undefined,
): string | null {
  if (!evaluator) return null;
  const base = `${evaluator.name}@${evaluator.version}`;
  return evaluator.commit ? `${base} (${evaluator.commit})` : base;
}

/** Mean model time per completed evaluation of a run, or null before any completed. */
export function meanDurationMs(
  run: Pick<EvaluationRunSummary, "duration_ms_total" | "completed_count">,
): number | null {
  return run.completed_count > 0 ? run.duration_ms_total / run.completed_count : null;
}

/** A run's timing as text: how long it took end to end, and the mean per evaluation. */
export function runTimingLabel(
  run: Pick<EvaluationRunSummary, "elapsed_ms" | "duration_ms_total" | "completed_count">,
): string | null {
  const parts: string[] = [];
  const elapsed = formatDuration(run.elapsed_ms);
  const mean = formatDuration(meanDurationMs(run));
  if (elapsed) parts.push(`took ${elapsed}`);
  if (mean) parts.push(`${mean} per evaluation`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * One model call as text: the question it asked, its duration and how it
 * ended, e.g. "fit_reliability 3.3 min (length)".
 */
export function callLabel(call: EvaluationCallModel): string {
  const how =
    call.stop_reason === "stop" && call.missing_keys && call.missing_keys.length > 0
      ? "stop, incomplete"
      : call.stop_reason;
  const timing = `${formatDuration(call.duration_ms) ?? "?"} (${how})`;
  return call.question ? `${call.question} ${timing}` : timing;
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
