import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EvaluationItem } from "@/schemas";

import { EvaluationCard } from "../EvaluationCard";

const mutate = vi.fn();
vi.mock("@/client/evaluation/evaluation", () => ({
  useSetEvaluationVerdict: () => ({ mutate, isPending: false }),
  getGetEvaluationRunQueryKey: (runId: string) => ["/evaluations/runs", runId],
  getListEvaluationsQueryKey: (params: unknown) => ["/evaluations", params],
}));

const item: EvaluationItem = {
  evaluation_id: "ev_1",
  run_id: "evr_1",
  task_id: "task-1",
  task_name: "ZX90InterleavedRandomizedBenchmarking",
  qid: "4-6",
  execution_id: "exec-1",
  figure_path: [],
  json_figure_path: [],
  status: "completed",
  requested_at: "2026-10-11T07:00:00Z",
  completed_at: "2026-10-11T07:00:33Z",
  input: {
    context: "Task: ZX90",
    prompt: "Reference for this experiment ...\nExperiment context:\nTask: ZX90",
    knowledge_chars: 1534,
    figures: [],
  },
  output: {
    model: "vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4",
    fallback: false,
    diagnosis: {
      technical_description: "Two exponential decays.",
      experimental_conclusion: { classification: "expected", reason: "Both decays are clean." },
      fit_reliability: { assessment: "reliable", reason: "The fit follows the data." },
      parameter_extraction: { zx90_gate_fidelity: 0.9882 },
      calibration_diagnosis: { status: "SUCCESS", suggested_range: null, notes: "Nothing to do." },
      success: true,
    },
    answers: {
      experimental_conclusion: "Classification: Expected behavior\nReason: Both decays are clean.",
      fit_reliability: "Assessment: Reliable\nReason: The fit follows the data.",
    },
    parsed: true,
    complete: true,
    missing_keys: [],
    duration_ms: 32858,
  },
  evaluator: {
    name: "@orangekame3/pi-qcaleval",
    version: "0.0.1",
    source: "checkout",
    commit: "042e45",
  },
  planner: {
    model: "openai-compatible/qwen3.8-flash-next",
    answer: "I agree with the diagnosis.",
    tool_calls: ["qdash_build_qcal_evidence", "qcal_evaluate"],
    duration_ms: 44525,
  },
};

/** Renders a card for a completed evaluation with overrides. */
function renderCard(override: Partial<EvaluationItem> = {}) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <EvaluationCard item={{ ...item, ...override }} showFigure={false} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  mutate.mockClear();
});

describe("EvaluationCard", () => {
  it("shows the diagnosis, who judged, what the model saw and what the planner did", () => {
    renderCard();
    expect(screen.getByText("4-6")).toBeTruthy();
    expect(screen.getByText("expected")).toBeTruthy();
    expect(screen.getByText("fit reliable")).toBeTruthy();
    expect(screen.getByText("SUCCESS")).toBeTruthy();
    expect(screen.getByText("Two exponential decays.")).toBeTruthy();
    expect(screen.getByText("Both decays are clean.")).toBeTruthy();
    expect(screen.getByText("The fit follows the data.")).toBeTruthy();
    expect(screen.getByText("Nothing to do.")).toBeTruthy();
    // The raw answers sit behind a toggle, one per question.
    expect(screen.getByText("Answers as returned")).toBeTruthy();
    expect(screen.getByText(/Classification: Expected behavior/)).toBeTruthy();
    expect(screen.getByText(/"zx90_gate_fidelity": 0.9882/)).toBeTruthy();
    expect(screen.getByText("vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4")).toBeTruthy();
    expect(screen.getByText("32.9 s")).toBeTruthy();
    expect(screen.getByText("reference 1534 chars")).toBeTruthy();
    expect(screen.getByText("@orangekame3/pi-qcaleval@0.0.1 (042e45)")).toBeTruthy();
    expect(screen.getByText("Prompt sent to the model")).toBeTruthy();
    // The full input renders (and loads its figures) only once opened.
    expect(screen.queryByText(/Reference for this experiment/)).toBeNull();
    const details = screen
      .getByText("Prompt sent to the model")
      .closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(screen.getByText(/Reference for this experiment/)).toBeTruthy();
    expect(screen.getByText("System prompt")).toBeTruthy();
    expect(screen.getByText("What Copilot did")).toBeTruthy();
    expect(screen.getByText("qdash_build_qcal_evidence")).toBeTruthy();
    expect(screen.getByText("via Copilot")).toBeTruthy();
  });

  it("keeps a prose answer readable and marks it", () => {
    renderCard({
      output: {
        model: "vllm/x",
        fallback: true,
        diagnosis: null,
        raw: "The oscillation decays as expected.",
        parsed: false,
        duration_ms: 1000,
      },
      planner: undefined,
    });
    expect(screen.getByText("prose")).toBeTruthy();
    expect(screen.getByText("fallback model")).toBeTruthy();
    expect(screen.getByText("The oscillation decays as expected.")).toBeTruthy();
    expect(screen.queryByText("What Copilot did")).toBeNull();
  });

  it("marks a diagnosis that lacks keys and keeps the answer as returned", () => {
    renderCard({
      output: {
        model: "vllm/x",
        fallback: false,
        diagnosis: { technical_description: "Two exponential decays." },
        raw: '{"technical_description": "Two exponential decays."}',
        parsed: true,
        complete: false,
        missing_keys: ["experimental_conclusion", "fit_quality", "success"],
        attempts: 2,
        structured: false,
        calls: [
          {
            question: "experimental_significance",
            duration_ms: 195_000,
            stop_reason: "length",
            output_tokens: 2000,
          },
          {
            duration_ms: 30_000,
            stop_reason: "stop",
            structured: false,
            output_tokens: 300,
            missing_keys: ["experimental_conclusion", "fit_quality", "success"],
          },
        ],
        duration_ms: 225_000,
      },
      planner: undefined,
    });
    const badge = screen.getByText("incomplete");
    expect(badge.getAttribute("title")).toBe(
      "Missing: experimental_conclusion, fit_quality, success",
    );
    expect(screen.getByText("Answer as returned")).toBeTruthy();
    expect(
      screen.getByText(
        "2 calls: experimental_significance 3.3 min (length) + 30.0 s (stop, incomplete)",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("free-form decoding")).toBeNull();
    expect(screen.queryByText("prose")).toBeNull();
  });

  it("says how many times the model was asked when the calls were not recorded", () => {
    renderCard({
      output: {
        model: "vllm/x",
        fallback: false,
        diagnosis: { technical_description: "Two exponential decays." },
        parsed: true,
        complete: false,
        attempts: 2,
        duration_ms: 1000,
      },
      planner: undefined,
    });
    expect(screen.getByText("2 attempts")).toBeTruthy();
  });

  it("records a verdict and clears it when clicked again", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: /Disagree/ }));
    expect(mutate).toHaveBeenCalledWith(
      { evaluationId: "ev_1", data: { agree: false, note: null } },
      expect.anything(),
    );

    cleanup();
    renderCard({
      verdict: {
        agree: false,
        note: "Tail ignored",
        username: "alice",
        updated_at: "2026-10-11T08:00:00Z",
      },
    });
    expect(screen.getByText(/“Tail ignored”/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Disagree/ }));
    expect(mutate).toHaveBeenLastCalledWith(
      { evaluationId: "ev_1", data: { agree: null, note: null } },
      expect.anything(),
    );
  });

  it("shows the failure instead of a diagnosis", () => {
    renderCard({
      status: "failed",
      error: "evaluation: HTTP 400 Non-base64",
      output: undefined,
      planner: undefined,
    });
    expect(screen.getByText("evaluation: HTTP 400 Non-base64")).toBeTruthy();
    expect(screen.queryByText("Do you agree?")).toBeNull();
  });
});
