import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatLinkPreviewContext } from "../ChatPreviewLink";
import {
  ExecutionProgress,
  executionIdFromArgs,
  executionPagePath,
  finishedTasks,
} from "../ExecutionProgress";

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
    // The task running now is shown, but has no result to link to yet.
    expect(screen.getByText("CheckT1 · 0").closest("a")).toBeNull();
    expect(screen.getByRole("img", { name: "CheckRabi_0" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open execution" }).getAttribute("href")).toBe(
      "/execution/64Qv3/20261006-012",
    );
  });

  it("shows a loading line until the execution arrives", () => {
    useGetExecution.mockReturnValue({ data: undefined });
    wrap(<ExecutionProgress executionId="20261006-012" />);
    expect(screen.getByRole("status").textContent).toMatch(/Loading execution 20261006-012/);
  });

  it("says the execution could not be loaded instead of loading forever", () => {
    useGetExecution.mockReturnValue({ data: undefined, isError: true });
    wrap(<ExecutionProgress executionId="20261006-012" />);
    expect(screen.getByText("Could not load execution 20261006-012.")).toBeTruthy();
    expect(screen.queryByText(/Loading execution/)).toBeNull();
    // Without a chip, the link goes through the id-only route that redirects.
    expect(screen.getByRole("link", { name: "Open execution" }).getAttribute("href")).toBe(
      "/executions/20261006-012",
    );
  });

  it("links each finished task to its result and previews it over the chat", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: {
          name: "one-qubit",
          status: "completed",
          chip_id: "64Qv3",
          note: {},
          task: [
            { task_id: "t1", name: "CheckRabi", qid: "0", status: "completed" },
            { task_id: "t2", name: "CheckRabi", qid: "1", status: "failed" },
            { name: "CheckT1", qid: "0", status: "completed" },
          ],
        },
      },
    });
    const preview = vi.fn(() => true);
    wrap(
      <ChatLinkPreviewContext.Provider value={{ preview }}>
        <ExecutionProgress executionId="exec-1" />
      </ChatLinkPreviewContext.Provider>,
    );

    const ok = screen.getByRole("link", { name: "CheckRabi · 0" });
    expect(ok.getAttribute("href")).toBe("/task-results/t1");
    const failed = screen.getByRole("link", { name: "CheckRabi · 1" });
    expect(failed.getAttribute("href")).toBe("/task-results/t2");
    expect(within(failed.closest("li")!).getByText("failed")).toBeTruthy();
    // A task without an id has no result page to open.
    expect(screen.getByText("CheckT1 · 0").closest("a")).toBeNull();

    fireEvent.click(ok);
    expect(preview).toHaveBeenCalledWith("/task-results/t1");
  });

  it("folds older finished tasks behind a keyboard-reachable disclosure", () => {
    const task = Array.from({ length: 8 }, (_, i) => ({
      task_id: `t${i}`,
      name: "CheckRabi",
      qid: String(i),
      status: "completed",
    }));
    useGetExecution.mockReturnValue({
      data: { data: { name: "many", status: "completed", chip_id: "c", note: {}, task } },
    });
    wrap(<ExecutionProgress executionId="exec-1" />);
    const summary = screen.getByText("2 earlier finished");
    expect(summary.tagName).toBe("SUMMARY");
    // The folded tasks still link to their results.
    expect(screen.getByRole("link", { name: "CheckRabi · 0", hidden: true })).toBeTruthy();
    expect(screen.getByRole("link", { name: "CheckRabi · 7" })).toBeTruthy();
  });

  it("says when an execution is waiting for its first task or recorded none", () => {
    useGetExecution.mockReturnValue({
      data: { data: { name: "e", status: "scheduled", chip_id: "c", note: {}, task: [] } },
    });
    const { unmount } = wrap(<ExecutionProgress executionId="exec-1" />);
    expect(screen.getByText("Waiting for the first task…")).toBeTruthy();
    unmount();

    useGetExecution.mockReturnValue({
      data: { data: { name: "e", status: "failed", chip_id: "c", note: {}, task: [] } },
    });
    wrap(<ExecutionProgress executionId="exec-1" />);
    expect(screen.getByText("No tasks were recorded.")).toBeTruthy();
    expect(screen.getByText(/failed · 0\/0 tasks/)).toBeTruthy();
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
              // A run recorded before transform steps had executions.
              { index: 2, name: "filter_by_status", kind: "transform", status: "not_recorded" },
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
    expect(screen.getByText(/4\/4/).textContent).toBe("4/4 · 1 failed");
    expect(screen.getByText(/1\/2$/)).toBeTruthy();
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Open execution" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-1",
    );
    expect(screen.getByText(/· 1 failed tasks/)).toBeTruthy();
    // Each step that has started links to its own execution; a transform has none.
    expect(screen.getByRole("link", { name: "1. one_qubit_check" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-1",
    );
    expect(screen.getByRole("link", { name: "3. coherence" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-2",
    );
    expect(screen.getByText("2. filter_by_status").closest("a")).toBeNull();
    expect(screen.getByText("not recorded")).toBeTruthy();
  });

  it("shows each transform step's own execution and decision, not task counts", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: {
          name: "p",
          status: "completed",
          chip_id: "64Qv3",
          note: {},
          task: [],
          pipeline: {
            name: "filter-then-pairs",
            flow_run_id: "run-1",
            root_execution_id: "exec-1",
            status: "failed",
            steps: [
              {
                index: 1,
                name: "check",
                key: "check",
                kind: "calibration",
                execution_id: "exec-1",
                status: "completed",
                task_total: 2,
                task_finished: 2,
              },
              {
                index: 2,
                name: "filter_by_status",
                key: "filter_by_status",
                kind: "transform",
                execution_id: "exec-2",
                status: "completed",
                task_total: 0,
                transform: {
                  kind: "filter",
                  input_qids: ["0", "1", "2"],
                  output_qids: ["0"],
                  excluded: [
                    { target: "1", reason: "step check failed" },
                    { target: "2", reason: "no result from step check" },
                  ],
                  source_found: true,
                },
              },
              {
                index: 3,
                name: "generate_cr_schedule",
                key: "generate_cr_schedule",
                kind: "transform",
                execution_id: "exec-3",
                status: "failed",
              },
              {
                index: 4,
                name: "two_qubit",
                key: "two_qubit",
                kind: "calibration",
                status: "skipped",
              },
            ],
          },
        },
      },
    });
    wrap(<ExecutionProgress executionId="exec-1" />);

    expect(screen.getByText(/failed · 3\/4 steps/)).toBeTruthy();
    expect(screen.getByText("Kept 1 of 3 qubits")).toBeTruthy();
    expect(screen.getByRole("link", { name: "2. filter_by_status" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-2",
    );
    // A failed transform links to its execution and shows no 0/0 task count.
    expect(screen.getByRole("link", { name: "3. generate_cr_schedule" })).toBeTruthy();
    expect(screen.queryByText("0/0")).toBeNull();
    expect(screen.getByText("not reached")).toBeTruthy();
  });

  it("summarizes a transform step's execution instead of reporting missing tasks", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: {
          name: "nightly_generate_cr_schedule",
          status: "completed",
          chip_id: "c",
          note: {
            step_kind: "transform",
            transform_result: { kind: "cr_schedule", groups: [["0-1", "2-3"], ["4-5"]] },
          },
          task: [],
        },
      },
    });
    wrap(<ExecutionProgress executionId="exec-1" />);
    expect(screen.getByText(/completed · 3 pairs in 2 groups/)).toBeTruthy();
    expect(screen.queryByText("No tasks were recorded.")).toBeNull();
  });

  it("does not show a cancelled step as a failure", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: {
          name: "p",
          status: "cancelled",
          chip_id: "64Qv3",
          note: {},
          task: [],
          pipeline: {
            name: "pipe",
            flow_run_id: "run-1",
            root_execution_id: "exec-1",
            status: "cancelled",
            steps: [
              { index: 1, name: "a", kind: "calibration", status: "cancelled" },
              { index: 2, name: "b", kind: "calibration", status: "pending" },
            ],
          },
        },
      },
    });
    wrap(<ExecutionProgress executionId="exec-1" />);
    expect(screen.getByText(/cancelled · 0\/2 steps/)).toBeTruthy();
    expect(screen.queryByText(/failed/)).toBeNull();
    expect(screen.queryByText(/Waiting for the first results/)).toBeNull();
    // Steps without an execution yet have nothing to open.
    expect(screen.queryByRole("link", { name: /^1\. a/ })).toBeNull();
  });
});

describe("executionPagePath", () => {
  it("uses the chip route when the chip is known and the redirect route otherwise", () => {
    expect(executionPagePath("e 1", "64Qv3")).toBe("/execution/64Qv3/e%201");
    expect(executionPagePath("e 1")).toBe("/executions/e%201");
    expect(executionPagePath("e 1", "")).toBe("/executions/e%201");
  });
});
