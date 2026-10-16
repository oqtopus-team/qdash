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
      fit_quality: "good",
      parameter_extraction: { zx90_gate_fidelity: 0.9882 },
      success: true,
    },
    parsed: true,
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
    expect(screen.getByText("fit good")).toBeTruthy();
    expect(screen.getByText("success")).toBeTruthy();
    expect(screen.getByText("Two exponential decays.")).toBeTruthy();
    expect(screen.getByText(/"zx90_gate_fidelity": 0.9882/)).toBeTruthy();
    expect(screen.getByText("vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4")).toBeTruthy();
    expect(screen.getByText("32.9 s")).toBeTruthy();
    expect(screen.getByText("reference 1534 chars")).toBeTruthy();
    expect(screen.getByText("@orangekame3/pi-qcaleval@0.0.1 (042e45)")).toBeTruthy();
    expect(screen.getByText("What the model saw")).toBeTruthy();
    // The full input renders (and loads its figures) only once opened.
    expect(screen.queryByText(/Reference for this experiment/)).toBeNull();
    const details = screen.getByText("What the model saw").closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(screen.getByText(/Reference for this experiment/)).toBeTruthy();
    expect(screen.getByText("System prompt")).toBeTruthy();
    expect(screen.getByText("What the planner did")).toBeTruthy();
    expect(screen.getByText("qdash_build_qcal_evidence")).toBeTruthy();
    expect(screen.getByText("planner")).toBeTruthy();
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
    expect(screen.queryByText("What the planner did")).toBeNull();
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
