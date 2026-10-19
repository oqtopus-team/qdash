import type { EvaluationItem, EvaluationRunSummary } from "@/schemas";

import {
  diagnosisOf,
  diagnosisSuccess,
  evaluatorLabel,
  fitQuality,
  modeLabel,
  triggerLabel,
} from "./evaluationDisplay";

/**
 * Two evaluation runs side by side, entity by entity.
 *
 * A run is the unit of comparison: the same selection evaluated again after a
 * change to the model, the extension, the task's reference, or with labeled
 * examples on, yields a second run with the same shape. Rows are joined by
 * entity (qid), since that is what a person compares; whether both sides
 * judged the very same task result is kept on the row.
 */

/** How the two judgements of one entity relate. */
export type RowOutcome = "same" | "differs" | "incomplete";

export interface CompareRow {
  qid: string;
  a: EvaluationItem | null;
  b: EvaluationItem | null;
  /** Both sides evaluated the same task result; null when a side is missing. */
  sameResult: boolean | null;
  outcome: RowOutcome;
}

export interface CompareSummary {
  rows: number;
  /** Rows present on both sides. */
  paired: number;
  /** Paired rows that judged the same task result. */
  sameResult: number;
  /** Rows whose outcome could be compared (both sides parsed as JSON). */
  compared: number;
  same: number;
  differs: number;
}

/** One run setting on both sides, flagged when it differs. */
export interface SettingDiff {
  key: string;
  label: string;
  a: string;
  b: string;
  differs: boolean;
}

/** Natural order of entity ids (Q2 before Q10, 0-1 before 0-10). */
export function compareQids(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true });
}

/**
 * The outcome of one row: fit quality and success compared when both sides
 * completed with a JSON diagnosis; incomplete otherwise (a side missing,
 * pending, failed, or answered in prose).
 */
export function rowOutcome(a: EvaluationItem | null, b: EvaluationItem | null): RowOutcome {
  if (!a || !b || a.status !== "completed" || b.status !== "completed") return "incomplete";
  const da = diagnosisOf(a);
  const db = diagnosisOf(b);
  if (!da || !db) return "incomplete";
  const sameSuccess = diagnosisSuccess(da) === diagnosisSuccess(db);
  const sameFit = fitQuality(da) === fitQuality(db);
  return sameSuccess && sameFit ? "same" : "differs";
}

/** Rows by entity, in natural order, from the evaluations of two runs. */
export function joinEvaluations(
  a: ReadonlyArray<EvaluationItem>,
  b: ReadonlyArray<EvaluationItem>,
): CompareRow[] {
  const byQid = new Map<string, { a: EvaluationItem | null; b: EvaluationItem | null }>();
  for (const item of a) byQid.set(item.qid, { a: item, b: null });
  for (const item of b) {
    const row = byQid.get(item.qid);
    if (row) row.b = item;
    else byQid.set(item.qid, { a: null, b: item });
  }
  return [...byQid.entries()]
    .sort(([left], [right]) => compareQids(left, right))
    .map(([qid, sides]) => ({
      qid,
      a: sides.a,
      b: sides.b,
      sameResult: sides.a && sides.b ? sides.a.task_id === sides.b.task_id : null,
      outcome: rowOutcome(sides.a, sides.b),
    }));
}

export function summarizeRows(rows: ReadonlyArray<CompareRow>): CompareSummary {
  const summary: CompareSummary = {
    rows: rows.length,
    paired: 0,
    sameResult: 0,
    compared: 0,
    same: 0,
    differs: 0,
  };
  for (const row of rows) {
    if (row.a && row.b) summary.paired += 1;
    if (row.sameResult) summary.sameResult += 1;
    if (row.outcome === "same") {
      summary.compared += 1;
      summary.same += 1;
    } else if (row.outcome === "differs") {
      summary.compared += 1;
      summary.differs += 1;
    }
  }
  return summary;
}

/** The settings of two runs side by side, each flagged when it differs. */
export function runSettings(a: EvaluationRunSummary, b: EvaluationRunSummary): SettingDiff[] {
  const settings: Array<[string, string, (run: EvaluationRunSummary) => string]> = [
    ["chip", "Chip", (run) => run.chip_id],
    ["task", "Task", (run) => run.task_name],
    ["entity", "Entities", (run) => run.entity_type],
    ["date", "Results", (run) => run.date || "latest"],
    ["trigger", "Trigger", (run) => triggerLabel(run.trigger)],
    ["mode", "Mode", (run) => modeLabel(run.mode)],
    ["planner", "Planner", (run) => (run.mode === "planner" ? run.planner_model || "-" : "-")],
    ["examples", "Labeled examples", (run) => (run.with_examples ? "shown" : "off")],
    ["question", "Question", (run) => run.question || "-"],
    ["model", "Evaluation model", (run) => run.model || "-"],
    ["evaluator", "Evaluator", (run) => evaluatorLabel(run.evaluator) || "-"],
  ];
  return settings.map(([key, label, read]) => {
    const left = read(a);
    const right = read(b);
    return { key, label, a: left, b: right, differs: left !== right };
  });
}

/** The compare page for two runs, A first. */
export function compareHref(runA: string, runB: string): string {
  return `/evaluations/compare?a=${encodeURIComponent(runA)}&b=${encodeURIComponent(runB)}`;
}
