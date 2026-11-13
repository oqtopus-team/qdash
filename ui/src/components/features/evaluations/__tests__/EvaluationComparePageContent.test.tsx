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

vi.mock("@/components/ui/PierreDiffViewer", () => ({
  PierreDiffViewer: ({ oldContent, newContent }: { oldContent: string; newContent: string }) => (
    <div data-testid="prompt-diff-viewer">
      {oldContent} → {newContent}
    </div>
  ),
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

/** Builds a run summary for the compare page. */
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
    complete_count: 2,
    duration_ms_total: 60_000,
    success_count: 2,
    agree_count: 0,
    disagree_count: 0,
    model: "vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4",
    evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.2-beta.9", source: "package" },
    ...override,
  };
}

/** Builds an evaluation item of a run. */
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
    input: {
      context: "Task: CheckT1",
      prompt: `Reference for ${runId}\nTask: CheckT1 ${qid}`,
      system_prompt: "SYSTEM",
      knowledge_chars: runId === "evr_a" ? 1534 : 1600,
      knowledge_sha256: runId === "evr_a" ? "aaaa1111bbbb" : "cccc2222dddd",
      figures: [],
    },
    output: { model: "vllm/ising", fallback: false, diagnosis, parsed: true, duration_ms: 30_000 },
  };
}

/** Renders the compare page. */
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
        item("evr_a", "Q1", { fit_reliability: { assessment: "reliable" }, success: true }),
        item("evr_a", "Q2", { fit_reliability: { assessment: "reliable" }, success: true }),
      ],
    };
    runs.evr_b = {
      run: summary("evr_b", { with_examples: true, success_count: 1 }),
      evaluations: [
        item("evr_b", "Q1", { fit_reliability: { assessment: "reliable" }, success: true }),
        item("evr_b", "Q2", { fit_reliability: { assessment: "unreliable" }, success: false }),
      ],
    };
    renderPage();

    expect(screen.getByText("Compare runs · CheckT1 · 64Qv1")).toBeTruthy();
    const examples = screen.getByTestId("setting-examples");
    expect(within(examples).getByText("Zero-shot")).toBeTruthy();
    expect(within(examples).getByText("In-context requested · 0/2 used")).toBeTruthy();
    expect(examples.className).toContain("bg-warning");
    expect(screen.getByTestId("setting-chip").className).not.toContain("bg-warning");
    // The reference each run's records carry is a setting too; here it was edited in between.
    const reference = screen.getByTestId("setting-reference");
    expect(within(reference).getByText("1534 chars · aaaa1111")).toBeTruthy();
    expect(within(reference).getByText("1600 chars · cccc2222")).toBeTruthy();
    expect(reference.className).toContain("bg-warning");
    expect(screen.getByTestId("setting-system_prompt").className).not.toContain("bg-warning");

    const table = screen.getByTestId("compare-table");
    expect(within(table).getByText("same")).toBeTruthy();
    expect(within(table).getByText("decision differs")).toBeTruthy();
    expect(within(table).getAllByText("fit unreliable")).toHaveLength(1);

    // Only differences hides the row that agrees.
    fireEvent.click(screen.getByLabelText("Only differences"));
    expect(screen.queryByTestId("compare-row-Q1")).toBeNull();
    expect(screen.getByTestId("compare-row-Q2")).toBeTruthy();

    // Expanding a row shows both records with their diagnoses and the figure once.
    fireEvent.click(screen.getByTestId("compare-row-Q2"));
    expect(screen.getAllByTestId("evaluation-verdict")).toHaveLength(2);
    expect(screen.getAllByTestId("figure")).toHaveLength(1);

    // The two prompts open as a diff, A against B.
    const diff = screen.getByTestId("prompt-diff");
    expect(within(diff).getByText("differs")).toBeTruthy();
    expect(screen.queryByTestId("prompt-diff-viewer")).toBeNull();
    (diff as HTMLDetailsElement).open = true;
    fireEvent(diff, new Event("toggle"));
    expect(screen.getByTestId("prompt-diff-viewer").textContent).toContain(
      "Reference for evr_a\nTask: CheckT1 Q2 → Reference for evr_b\nTask: CheckT1 Q2",
    );
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
