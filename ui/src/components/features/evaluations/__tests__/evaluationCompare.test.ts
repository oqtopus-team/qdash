import { describe, expect, it } from "vitest";

import type { EvaluationItem, EvaluationRunSummary } from "@/schemas";

import {
  compareHref,
  compareQids,
  diagnosisDifference,
  joinEvaluations,
  rowOutcome,
  runSettings,
  summarizeRows,
} from "../evaluationCompare";

/** Builds an evaluation item with an optional diagnosis. */
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
  complete_count: 2,
  elapsed_ms: 90_000,
  duration_ms_total: 60_000,
  success_count: 1,
  agree_count: 0,
  disagree_count: 0,
  evaluation_model: "openai-compatible-evaluation/ising-requested",
  model: "vllm/ising",
  evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.2-beta.9", source: "package" },
};

describe("evaluationCompare", () => {
  it("orders entities naturally", () => {
    expect(["Q10", "Q2", "Q1"].sort(compareQids)).toEqual(["Q1", "Q2", "Q10"]);
    expect(["0-10", "0-2"].sort(compareQids)).toEqual(["0-2", "0-10"]);
  });

  it("compares the full diagnosis and classifies decision and content changes", () => {
    const answered = (
      status: string,
      fit: string,
      outcome: string,
      success: boolean,
    ): Record<string, unknown> => ({
      experimental_conclusion: { classification: outcome, reason: "" },
      fit_reliability: { assessment: fit, reason: "" },
      calibration_diagnosis: { status, suggested_range: null, notes: "" },
      success,
    });
    const good = item("Q1", answered("SUCCESS", "reliable", "expected", true));
    expect(rowOutcome(good, item("Q1", answered("SUCCESS", "Reliable", "expected", true)))).toBe(
      "same",
    );
    expect(rowOutcome(good, item("Q1", answered("SUCCESS", "unreliable", "expected", true)))).toBe(
      "differs",
    );
    expect(
      rowOutcome(good, item("Q1", answered("LOW_CONTRAST", "reliable", "expected", false))),
    ).toBe("differs");
    expect(rowOutcome(good, item("Q1", answered("SUCCESS", "reliable", "suboptimal", true)))).toBe(
      "differs",
    );
    expect(rowOutcome(good, item("Q1", null))).toBe("incomplete");
    // A diagnosis without a verdict, or with a labelled answer on one side only, is not compared.
    expect(rowOutcome(good, item("Q1", { technical_description: "only" }))).toBe("incomplete");
    expect(rowOutcome(good, item("Q1", { success: true }))).toBe("incomplete");
    expect(
      rowOutcome(
        good,
        item("Q1", answered("SUCCESS", "reliable", "expected", true), { status: "failed" }),
      ),
    ).toBe("incomplete");
    expect(rowOutcome(good, null)).toBe("incomplete");
    // Older records with only a success verdict still compare on it.
    expect(rowOutcome(item("Q1", { success: true }), item("Q1", { success: false }))).toBe(
      "differs",
    );
    expect(rowOutcome(item("Q1", { success: true }), item("Q1", { success: true }))).toBe("same");
    expect(
      rowOutcome(
        item("Q1", {
          ...answered("SUCCESS", "reliable", "expected", true),
          parameter_extraction: { t1: 10 },
        }),
        item("Q1", {
          ...answered("SUCCESS", "reliable", "expected", true),
          parameter_extraction: { t1: 11 },
        }),
      ),
    ).toBe("differs");
    expect(
      diagnosisDifference(
        item("Q1", {
          ...answered("SUCCESS", "reliable", "expected", true),
          parameter_extraction: { t1: 10 },
        }),
        item("Q1", {
          ...answered("SUCCESS", "reliable", "expected", true),
          parameter_extraction: { t1: 11 },
        }),
      ),
    ).toBe("content");
    expect(
      diagnosisDifference(
        good,
        item("Q1", answered("LOW_CONTRAST", "reliable", "expected", false)),
      ),
    ).toBe("decision");
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
    const settings = runSettings(
      { run },
      {
        run: {
          ...run,
          run_id: "evr_b",
          with_examples: true,
          mode: "planner",
          planner_model: "openai-compatible/qwen3.8-flash-next",
          evaluation_model: "openai-compatible-chat/qwen3.8-flash-next",
        },
      },
    );
    const byKey = Object.fromEntries(settings.map((setting) => [setting.key, setting]));
    expect(byKey.chip).toMatchObject({ a: "64Qv1", b: "64Qv1", differs: false });
    expect(byKey.examples).toMatchObject({
      a: "Zero-shot",
      b: "In-context requested · 0/2 used",
      differs: true,
    });
    expect(byKey.mode).toMatchObject({ a: "Fixed prompt", b: "Via Copilot", differs: true });
    expect(byKey.planner).toMatchObject({
      a: "-",
      b: "openai-compatible/qwen3.8-flash-next",
      differs: true,
    });
    expect(byKey.model).toMatchObject({
      a: "openai-compatible-evaluation/ising-requested",
      b: "openai-compatible-chat/qwen3.8-flash-next",
      differs: true,
    });
    expect(byKey.evaluator).toMatchObject({
      a: "@orangekame3/pi-qcaleval@0.0.2-beta.9",
      differs: false,
    });
    expect(byKey.date).toMatchObject({ a: "latest", b: "latest" });
    // Timing rows: end to end, and the mean per completed evaluation.
    expect(byKey.elapsed).toMatchObject({ a: "1.5 min", b: "1.5 min", differs: false });
    expect(byKey.duration).toMatchObject({ a: "30.0 s", b: "30.0 s", differs: false });
    // Without evaluations the prompt rows have nothing to say.
    expect(byKey.reference).toMatchObject({ a: "-", b: "-", differs: false });
    expect(byKey.system_prompt).toMatchObject({ a: "-", b: "-", differs: false });
    expect(byKey.tokens).toMatchObject({ a: "-", b: "-", differs: false });
  });

  it("compares the largest prompt of two runs in tokens", () => {
    const withTokens = (input_tokens: number) => [
      item("Q1", null, {
        output: {
          parsed: true,
          context_window: 16384,
          calls: [{ duration_ms: 1, stop_reason: "stop", input_tokens, output_tokens: 100 }],
        },
      }),
    ];
    const settings = runSettings(
      { run, evaluations: withTokens(2000) },
      { run, evaluations: withTokens(9000) },
    );
    expect(settings.find((setting) => setting.key === "tokens")).toMatchObject({
      a: "largest prompt 2,000 tokens (2,100 of 16,384 with the answer)",
      b: "largest prompt 9,000 tokens (9,100 of 16,384 with the answer)",
      differs: true,
    });
  });

  it("flags a run against a knowledge draft, and two drafts that differ", () => {
    const draft = (id: string, name: string) => ({
      run: { ...run, knowledge_draft_id: id, knowledge_draft_name: name },
    });
    const shared = runSettings({ run }, draft("a".repeat(64), "rabi.zip"));
    const knowledge = shared.find((setting) => setting.key === "knowledge");
    expect(knowledge).toMatchObject({ a: "Shared", b: "Draft rabi.zip", differs: true });
    // Same file name, different contents: still a different draft.
    const renamed = runSettings(
      draft("a".repeat(64), "rabi.zip"),
      draft("b".repeat(64), "rabi.zip"),
    );
    expect(renamed.find((setting) => setting.key === "knowledge")?.differs).toBe(true);
  });

  it("flags different prompts and references even when their labels match", () => {
    const withInput = (system_prompt: string, knowledge_sha256: string) => [
      item("Q1", null, {
        input: {
          context: "c",
          figures: [],
          system_prompt,
          knowledge_chars: 10,
          knowledge_sha256,
        },
      }),
    ];
    const settings = runSettings(
      { run, evaluations: withInput("aa", "aaaaaaaa11") },
      { run, evaluations: withInput("bb", "bbbbbbbb22") },
    );
    const byKey = Object.fromEntries(settings.map((setting) => [setting.key, setting]));
    expect(byKey.system_prompt).toMatchObject({ a: "2 chars", b: "2 chars", differs: true });
    expect(byKey.reference.differs).toBe(true);
    const same = runSettings(
      { run, evaluations: withInput("aa", "aaaaaaaa11") },
      { run, evaluations: withInput("aa", "aaaaaaaa11") },
    );
    expect(same.find((setting) => setting.key === "system_prompt")?.differs).toBe(false);
    expect(same.find((setting) => setting.key === "reference")?.differs).toBe(false);
  });

  it("builds the compare page link", () => {
    expect(compareHref("evr_a", "evr_b")).toBe("/evaluations/compare?a=evr_a&b=evr_b");
  });
});
