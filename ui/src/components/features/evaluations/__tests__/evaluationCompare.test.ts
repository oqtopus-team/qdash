import { describe, expect, it } from "vitest";

import type { EvaluationItem, EvaluationRunSummary } from "@/schemas";

import {
  compareHref,
  compareQids,
  joinEvaluations,
  rowOutcome,
  runSettings,
  summarizeRows,
} from "../evaluationCompare";

function item(
  qid: string,
  diagnosis: Record<string, unknown> | null,
  override: Partial<EvaluationItem> = {},
): EvaluationItem {
  return {
    evaluation_id: `ev_${qid}`,
    run_id: "evr_a",
    task_id: `task-${qid}`,
    task_name: "CheckT1",
    qid,
    execution_id: "exec-1",
    figure_path: [],
    json_figure_path: [],
    status: "completed",
    requested_at: "2026-10-11T07:00:00Z",
    output: diagnosis
      ? { model: "vllm/ising", fallback: false, diagnosis, parsed: true, duration_ms: 1000 }
      : { model: "vllm/ising", fallback: false, raw: "prose", parsed: false, duration_ms: 1000 },
    ...override,
  };
}

const run: EvaluationRunSummary = {
  run_id: "evr_a",
  chip_id: "64Qv1",
  task_name: "CheckT1",
  entity_type: "qubit",
  trigger: "bulk",
  mode: "direct",
  with_examples: false,
  requested_by: "alice",
  requested_at: "2026-10-11T07:00:00Z",
  status: "completed",
  total: 2,
  completed_count: 2,
  failed_count: 0,
  pending_count: 0,
  parsed_count: 2,
  success_count: 1,
  agree_count: 0,
  disagree_count: 0,
  model: "vllm/ising",
  evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.2-beta.9", source: "package" },
};

describe("evaluationCompare", () => {
  it("orders entities naturally", () => {
    expect(["Q10", "Q2", "Q1"].sort(compareQids)).toEqual(["Q1", "Q2", "Q10"]);
    expect(["0-10", "0-2"].sort(compareQids)).toEqual(["0-2", "0-10"]);
  });

  it("compares fit quality and success only when both sides answered in JSON", () => {
    const good = item("Q1", { fit_quality: "good", success: true });
    expect(rowOutcome(good, item("Q1", { fit_quality: "Good, clean decay", success: true }))).toBe(
      "same",
    );
    expect(rowOutcome(good, item("Q1", { fit_quality: "poor", success: true }))).toBe("differs");
    expect(rowOutcome(good, item("Q1", { fit_quality: "good", success: false }))).toBe("differs");
    expect(rowOutcome(good, item("Q1", null))).toBe("incomplete");
    expect(rowOutcome(good, item("Q1", { success: true }, { status: "failed" }))).toBe(
      "incomplete",
    );
    expect(rowOutcome(good, null)).toBe("incomplete");
  });

  it("joins the two runs by entity and keeps whether they judged the same result", () => {
    const rows = joinEvaluations(
      [item("Q2", { success: true }), item("Q1", { success: true })],
      [
        item("Q1", { success: true }, { run_id: "evr_b" }),
        item("Q2", { success: false }, { run_id: "evr_b", task_id: "task-Q2-newer" }),
        item("Q3", { success: true }, { run_id: "evr_b" }),
      ],
    );
    expect(rows.map((row) => row.qid)).toEqual(["Q1", "Q2", "Q3"]);
    expect(rows[0]).toMatchObject({ sameResult: true, outcome: "same" });
    expect(rows[1]).toMatchObject({ sameResult: false, outcome: "differs" });
    expect(rows[2]).toMatchObject({ a: null, sameResult: null, outcome: "incomplete" });

    expect(summarizeRows(rows)).toEqual({
      rows: 3,
      paired: 2,
      sameResult: 1,
      compared: 2,
      same: 1,
      differs: 1,
    });
  });

  it("flags the run settings that differ", () => {
    const settings = runSettings(run, {
      ...run,
      run_id: "evr_b",
      with_examples: true,
      mode: "planner",
      planner_model: "openai-compatible/qwen3.8-flash-next",
    });
    const byKey = Object.fromEntries(settings.map((setting) => [setting.key, setting]));
    expect(byKey.chip).toMatchObject({ a: "64Qv1", b: "64Qv1", differs: false });
    expect(byKey.examples).toMatchObject({ a: "off", b: "shown", differs: true });
    expect(byKey.mode).toMatchObject({ a: "Direct", b: "Planner", differs: true });
    expect(byKey.planner).toMatchObject({
      a: "-",
      b: "openai-compatible/qwen3.8-flash-next",
      differs: true,
    });
    expect(byKey.evaluator).toMatchObject({
      a: "@orangekame3/pi-qcaleval@0.0.2-beta.9",
      differs: false,
    });
    expect(byKey.date).toMatchObject({ a: "latest", b: "latest" });
  });

  it("builds the compare page link", () => {
    expect(compareHref("evr_a", "evr_b")).toBe("/evaluations/compare?a=evr_a&b=evr_b");
  });
});
