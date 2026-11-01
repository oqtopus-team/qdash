import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskResultEvaluations } from "../TaskResultEvaluations";

const evaluations = vi.hoisted(() => ({ items: [] as Array<Record<string, unknown>> }));

vi.mock("@/client/evaluation/evaluation", () => ({
  useListEvaluations: () => ({ data: { data: { evaluations: evaluations.items } } }),
  useSetEvaluationVerdict: () => ({ mutate: vi.fn(), isPending: false }),
  getGetEvaluationRunQueryKey: (runId: string) => ["/evaluations/runs", runId],
  getListEvaluationsQueryKey: (params: unknown) => ["/evaluations", params],
}));
vi.mock("@/client/task/task", () => ({ useGetTaskResult: () => ({ data: undefined }) }));
vi.mock("../AskAiButton", () => ({
  AskAiButton: ({ onRequested }: { onRequested?: () => void }) => (
    <button type="button" onClick={onRequested}>
      request
    </button>
  ),
}));

afterEach(() => {
  cleanup();
  evaluations.items = [];
});

function renderSection() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TaskResultEvaluations
        taskId="t1"
        chipId="64Qv3"
        taskName="CheckRabi"
        qid="Q05"
        executionId="e1"
      />
    </QueryClientProvider>,
  );
}

describe("TaskResultEvaluations after Ask AI", () => {
  it("says an evaluation is on its way until its record arrives", () => {
    const { rerender } = renderSection();
    expect(screen.queryByRole("status")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "request" }));
    expect(screen.getByRole("status")).toHaveTextContent("Evaluating");

    evaluations.items = [
      {
        evaluation_id: "ev1",
        run_id: "r1",
        task_id: "t1",
        status: "completed",
        output: { complete: true },
      },
    ];
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TaskResultEvaluations
          taskId="t1"
          chipId="64Qv3"
          taskName="CheckRabi"
          qid="Q05"
          executionId="e1"
        />
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});
