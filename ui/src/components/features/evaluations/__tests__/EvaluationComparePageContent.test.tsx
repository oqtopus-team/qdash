import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EvaluationItem, EvaluationRunDetailResponse, EvaluationRunSummary } from "@/schemas";

import { EvaluationComparePageContent } from "../EvaluationComparePageContent";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const query = { a: "evr_a" as string | null, b: "evr_b" as string | null };
const setQuery = vi.fn();
vi.mock("nuqs", () => ({
  parseAsString: {},
  useQueryState: (key: "a" | "b") => [query[key], setQuery],
}));

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: ({ path }: { path: string }) => <div data-testid="figure">{path}</div>,
}));

const runs: Record<string, EvaluationRunDetailResponse> = {};
vi.mock("@/client/evaluation/evaluation", () => ({
  useGetEvaluationRun: (runId: string, options: { query: { enabled: boolean } }) => ({
    data: options.query.enabled && runs[runId] ? { data: runs[runId] } : undefined,
    isLoading: false,
    isError: options.query.enabled && !runs[runId],
  }),
  useListEvaluationRuns: () => ({ data: { data: { runs: [] } }, isLoading: false }),
  useSetEvaluationVerdict: () => ({ mutate: vi.fn(), isPending: false }),
  getGetEvaluationRunQueryKey: (runId: string) => ["/evaluations/runs", runId],
  getListEvaluationsQueryKey: (params: unknown) => ["/evaluations", params],
}));

function summary(
  runId: string,
  override: Partial<EvaluationRunSummary> = {},
): EvaluationRunSummary {
  return {
    run_id: runId,
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
    success_count: 2,
    agree_count: 0,
    disagree_count: 0,
    model: "vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4",
    evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.2-beta.9", source: "package" },
    ...override,
  };
}

function item(runId: string, qid: string, diagnosis: Record<string, unknown>): EvaluationItem {
  return {
    evaluation_id: `ev_${runId}_${qid}`,
    run_id: runId,
    task_id: `task-${qid}`,
    task_name: "CheckT1",
    qid,
    execution_id: "exec-1",
    figure_path: [`/figures/${qid}.png`],
    json_figure_path: [],
    status: "completed",
    requested_at: "2026-10-11T07:00:00Z",
    completed_at: "2026-10-11T07:00:30Z",
    input: { context: "Task: CheckT1", prompt: "Reference ...", figures: [] },
    output: { model: "vllm/ising", fallback: false, diagnosis, parsed: true, duration_ms: 30_000 },
  };
}

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <EvaluationComparePageContent />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  push.mockClear();
  setQuery.mockClear();
  query.a = "evr_a";
  query.b = "evr_b";
  for (const key of Object.keys(runs)) delete runs[key];
});

describe("EvaluationComparePageContent", () => {
  it("lines up the two runs by entity and flags differing settings and outcomes", () => {
    runs.evr_a = {
      run: summary("evr_a"),
      evaluations: [
        item("evr_a", "Q1", { fit_quality: "good", success: true }),
        item("evr_a", "Q2", { fit_quality: "good", success: true }),
      ],
    };
    runs.evr_b = {
      run: summary("evr_b", { with_examples: true, success_count: 1 }),
      evaluations: [
        item("evr_b", "Q1", { fit_quality: "good", success: true }),
        item("evr_b", "Q2", { fit_quality: "poor", success: false }),
      ],
    };
    renderPage();

    expect(screen.getByText("Compare runs · CheckT1 · 64Qv1")).toBeTruthy();
    const examples = screen.getByTestId("setting-examples");
    expect(within(examples).getByText("off")).toBeTruthy();
    expect(within(examples).getByText("shown")).toBeTruthy();
    expect(examples.className).toContain("bg-warning");
    expect(screen.getByTestId("setting-chip").className).not.toContain("bg-warning");

    const table = screen.getByTestId("compare-table");
    expect(within(table).getByText("same")).toBeTruthy();
    expect(within(table).getByText("differs")).toBeTruthy();
    expect(within(table).getAllByText("poor")).toHaveLength(1);

    // Only differences hides the row that agrees.
    fireEvent.click(screen.getByLabelText("Only differences"));
    expect(screen.queryByTestId("compare-row-Q1")).toBeNull();
    expect(screen.getByTestId("compare-row-Q2")).toBeTruthy();

    // Expanding a row shows both records with their diagnoses and the figure once.
    fireEvent.click(screen.getByTestId("compare-row-Q2"));
    expect(screen.getAllByTestId("evaluation-verdict")).toHaveLength(2);
    expect(screen.getAllByTestId("figure")).toHaveLength(1);
  });

  it("asks for the other run when only one is in the URL", () => {
    query.b = null;
    runs.evr_a = { run: summary("evr_a"), evaluations: [] };
    renderPage();
    expect(screen.getByText("Choose run B")).toBeTruthy();
    expect(screen.getByTestId("run-picker")).toBeTruthy();
    expect(screen.queryByTestId("compare-table")).toBeNull();
  });

  it("points to the runs list when no run is chosen", () => {
    query.a = null;
    query.b = null;
    renderPage();
    expect(screen.getByText("Choose two runs")).toBeTruthy();
  });
});
