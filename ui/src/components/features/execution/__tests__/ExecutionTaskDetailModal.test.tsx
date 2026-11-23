import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Task } from "@/schemas";

import { ExecutionTaskDetailModal } from "../ExecutionTaskDetailModal";

const investigate = vi.fn();

vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ openMiniChat: vi.fn() }),
  useOptionalChatDock: () => ({ investigate }),
}));
vi.mock("@/components/features/task-history/ExecutionHistoryModalContent", () => ({
  ExecutionHistoryModalContent: ({ details }: { details: ReactNode }) => <div>{details}</div>,
}));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));
vi.mock("@/components/features/evaluations/AskAiButton", () => ({ AskAiButton: () => null }));
vi.mock("@/components/features/evaluations/TaskResultEvaluations", () => ({
  TaskResultEvaluations: () => null,
}));
vi.mock("@/components/features/forum/TaskResultThreads", () => ({ TaskResultThreads: () => null }));
vi.mock("@/components/features/metrics/TaskResultMemo", () => ({ TaskResultMemo: () => null }));

afterEach(() => {
  cleanup();
  investigate.mockClear();
});

function renderModal(tasks: Task[]) {
  render(
    <ExecutionTaskDetailModal
      isOpen
      chipId="64Q"
      executionId="exec-1"
      qid="3"
      tasks={tasks}
      onClose={() => {}}
    />,
  );
}

describe("ExecutionTaskDetailModal investigation", () => {
  it("investigates a failed task that never produced a task result", () => {
    renderModal([{ name: "CheckRabi", status: "failed", message: "KeyError: 'qubit_frequency'" }]);

    expect(screen.getByText("KeyError: 'qubit_frequency'")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Investigate with AI" }));

    expect(investigate).toHaveBeenCalledWith(
      { executionId: "exec-1", taskId: null, taskName: "CheckRabi", qid: "3", chipId: "64Q" },
      "mini",
    );
  });

  it("offers nothing for a task that did not fail", () => {
    renderModal([{ name: "CheckRabi", status: "completed", task_id: "t1", message: "done" }]);

    expect(screen.queryByRole("button", { name: "Investigate with AI" })).toBeNull();
  });
});

describe("ExecutionTaskDetailModal task calls", () => {
  it("tells repeated calls of one task apart by their call id", () => {
    renderModal([
      {
        name: "CheckRamsey",
        status: "completed",
        task_id: "t1",
        invocation: { step_id: "ramsey", call_id: "ramsey_coarse" },
      },
      {
        name: "CheckRamsey",
        status: "failed",
        task_id: "t2",
        invocation: { step_id: "ramsey", call_id: "ramsey_fine" },
      },
    ]);

    // The selected run names its planned call as step.call.
    expect(screen.getByText("ramsey.ramsey_coarse")).not.toBeNull();
    expect(screen.queryByText("ramsey.ramsey_fine")).toBeNull();
  });
});
