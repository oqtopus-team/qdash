import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";

const mocks = vi.hoisted(() => ({
  historyTask: {
    task_id: "task-1",
    name: "CheckRabi",
    status: "completed",
    execution_id: "exec-1",
    end_at: "2026-11-10T00:00:00Z",
  } as Record<string, unknown>,
  executionTasks: [] as Record<string, unknown>[],
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    className,
    children,
  }: {
    href: string;
    className?: string;
    children: ReactNode;
  }) => (
    <a href={href} className={className} data-next-link="true">
      {children}
    </a>
  ),
}));
vi.mock("@/client/task-result/task-result", () => {
  const history = () => ({
    data: { data: { data: { [String(mocks.historyTask.task_id)]: mocks.historyTask } } },
    isLoading: false,
    isError: false,
  });
  return { useGetQubitTaskHistory: history, useGetCouplingTaskHistory: history };
});
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: () => ({ data: { data: { task: mocks.executionTasks } }, isLoading: false }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ focusTaskChat: vi.fn(), openMiniChat: vi.fn() }),
}));
vi.mock("@/hooks/useManualOverrides", () => ({ useManualOverrides: () => ({}) }));
// Render each column once instead of the mobile and desktop copies.
vi.mock("@/components/features/task-history/ExecutionHistoryModalContent", () => ({
  ExecutionHistoryModalContent: ({ tasks, details }: { tasks: ReactNode; details: ReactNode }) => (
    <div>
      {tasks}
      {details}
    </div>
  ),
}));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));
vi.mock("@/components/features/chip/TaskArtifactDownloads", () => ({
  TaskArtifactDownloads: () => null,
}));
vi.mock("@/components/features/metrics/ParametersTable", () => ({ ParametersTable: () => null }));
vi.mock("@/components/features/provenance/ParameterLineageDialog", () => ({
  LineageButton: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/components/features/evaluations/TaskResultEvaluations", () => ({
  TaskResultEvaluations: () => null,
}));
vi.mock("@/components/features/forum/TaskResultThreads", () => ({ TaskResultThreads: () => null }));
vi.mock("@/components/features/metrics/TaskResultMemo", () => ({ TaskResultMemo: () => null }));
vi.mock("@/components/features/chat/DockedChatPanel", () => ({ DockedChatPanel: () => null }));

const TARGETS = [
  {
    kind: "qubit",
    targetId: "3",
    renderModal: () =>
      render(
        <TaskHistoryModal chipId="64Q" qid="3" taskName="CheckRabi" isOpen onClose={vi.fn()} />,
      ),
  },
  {
    kind: "coupling",
    targetId: "0-1",
    renderModal: () =>
      render(
        <CouplingTaskHistoryModal
          chipId="64Q"
          couplingId="0-1"
          taskName="CheckRabi"
          isOpen
          onClose={vi.fn()}
        />,
      ),
  },
] as const;

function isHighlighted(text: string): boolean {
  return screen.getByText(text).closest("button")!.className.includes("bg-secondary ");
}

afterEach(() => {
  cleanup();
  mocks.historyTask.task_id = "task-1";
});

describe("task history modals", () => {
  it("opens the qubit task result with client-side routing", () => {
    mocks.executionTasks = [{ ...mocks.historyTask, qid: "3" }];
    TARGETS[0].renderModal();

    expect(screen.getByRole("link", { name: "task-1" }).dataset.nextLink).toBe("true");
  });

  it("opens the coupling task result with a full page load", () => {
    mocks.executionTasks = [{ ...mocks.historyTask, qid: "0-1" }];
    TARGETS[1].renderModal();
    const link = screen.getByRole("link", { name: "task-1" });

    expect(link.getAttribute("href")).toBe("/task-results/task-1");
    expect(link.dataset.nextLink).toBeUndefined();
  });

  it.each(TARGETS)(
    "highlights every $kind task sharing the selected task ID",
    ({ targetId, renderModal }) => {
      mocks.executionTasks = [
        { task_id: "task-1", name: "CheckRabi", status: "completed", qid: targetId },
        { task_id: "task-1", name: "CheckT1", status: "completed", qid: targetId },
        { task_id: "task-2", name: "CheckT2", status: "completed", qid: targetId },
      ];
      renderModal();

      expect([isHighlighted("CheckT1"), isHighlighted("CheckT2")]).toEqual([true, false]);
    },
  );

  it.each(TARGETS)(
    "highlights every $kind task without an ID when the selection has none",
    ({ targetId, renderModal }) => {
      mocks.historyTask.task_id = undefined;
      mocks.executionTasks = [
        { name: "CheckRabi", status: "completed", qid: targetId },
        { name: "CheckT1", status: "completed", qid: targetId },
        { task_id: "task-2", name: "CheckT2", status: "completed", qid: targetId },
      ];
      renderModal();

      expect([isHighlighted("CheckT1"), isHighlighted("CheckT2")]).toEqual([true, false]);
    },
  );
});
