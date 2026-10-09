import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionProgress, executionIdFromArgs, finishedTasks } from "../ExecutionProgress";

const useGetExecution = vi.fn();
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: (...args: unknown[]) => useGetExecution(...args),
}));

afterEach(() => {
  cleanup();
  useGetExecution.mockReset();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("executionIdFromArgs", () => {
  it("reads the wait tool's executionId in either spelling", () => {
    expect(executionIdFromArgs({ executionId: "20261006-012" })).toBe("20261006-012");
    expect(executionIdFromArgs({ execution_id: "20261006-012" })).toBe("20261006-012");
    expect(executionIdFromArgs({ executionId: " " })).toBeNull();
    expect(executionIdFromArgs(null)).toBeNull();
  });
});

describe("finishedTasks", () => {
  it("keeps only completed and failed tasks", () => {
    expect(
      finishedTasks([{ status: "running" }, { status: "completed" }, { status: "failed" }, {}]),
    ).toEqual([{ status: "completed" }, { status: "failed" }]);
  });
});

describe("ExecutionProgress", () => {
  it("shows progress, the latest finished tasks, and their figures", async () => {
    useGetExecution.mockReturnValue({
      data: {
        data: {
          name: "coarse-then-coherence",
          status: "running",
          chip_id: "64Qv3",
          note: {},
          task: [
            {
              task_id: "t1",
              name: "CheckRabi",
              qid: "0",
              status: "completed",
              figure_path: ["exec/1/CheckRabi_0.png"],
            },
            { task_id: "t2", name: "CheckRabi", qid: "1", status: "failed", figure_path: null },
            { task_id: "t3", name: "CheckT1", qid: "0", status: "running" },
          ],
        },
      },
    });
    wrap(<ExecutionProgress executionId="20261006-012" />);

    expect(screen.getByTestId("execution-progress")).toBeTruthy();
    expect(useGetExecution).toHaveBeenCalledWith(
      "20261006-012",
      expect.objectContaining({ query: expect.objectContaining({ staleTime: 0 }) }),
    );
    expect(screen.getByText("coarse-then-coherence")).toBeTruthy();
    expect(screen.getByText(/running · 2\/3 tasks · 1 failed/)).toBeTruthy();
    expect(screen.getByText("CheckRabi · 0")).toBeTruthy();
    expect(screen.getByText("CheckRabi · 1")).toBeTruthy();
    expect(screen.queryByText("CheckT1 · 0")).toBeNull();
    expect(screen.getByRole("img", { name: "CheckRabi_0" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open execution" }).getAttribute("href")).toBe(
      "/execution/64Qv3/20261006-012",
    );
  });

  it("shows a loading line until the execution arrives", () => {
    useGetExecution.mockReturnValue({ data: undefined });
    wrap(<ExecutionProgress executionId="20261006-012" />);
    expect(screen.getByText(/Loading execution 20261006-012/)).toBeTruthy();
  });
});

describe("ExecutionProgress for a pipeline run", () => {
  it("lists every planned step with its progress and pools the figures", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: {
          name: "pipeline-exec-1",
          status: "completed",
          chip_id: "64Qv3",
          note: {},
          task: [],
          pipeline: {
            name: "coarse-then-coherence",
            flow_run_id: "run-1",
            root_execution_id: "exec-1",
            status: "running",
            steps: [
              {
                index: 1,
                name: "one_qubit_check",
                kind: "calibration",
                execution_id: "exec-1",
                status: "completed",
                task_total: 4,
                task_finished: 4,
                task_failed: 1,
                figure_paths: ["exec-1/CheckRabi_0.png"],
              },
              { index: 2, name: "filter_by_status", kind: "transform", status: "skipped" },
              {
                index: 3,
                name: "coherence",
                kind: "calibration",
                execution_id: "exec-2",
                status: "running",
                task_total: 2,
                task_finished: 1,
                task_failed: 0,
                figure_paths: ["exec-2/CheckT1_0.png"],
              },
            ],
          },
        },
      },
    });
    wrap(<ExecutionProgress executionId="exec-1" />);

    expect(screen.getByText("coarse-then-coherence")).toBeTruthy();
    expect(screen.getByText(/running · 1\/2 steps/)).toBeTruthy();
    expect(screen.getByText("1. one_qubit_check")).toBeTruthy();
    expect(screen.getByText("2. filter_by_status")).toBeTruthy();
    expect(screen.getByText("3. coherence")).toBeTruthy();
    expect(screen.getByText(/4\/4 · 1 failed/)).toBeTruthy();
    expect(screen.getByText(/1\/2$/)).toBeTruthy();
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Open execution" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-1",
    );
  });
});
