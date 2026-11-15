import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";
import { ExecutionTaskDetailModal } from "@/components/features/execution/ExecutionTaskDetailModal";
import { CouplingMetricHistoryModal } from "@/components/features/metrics/CouplingMetricHistoryModal";
import { QubitMetricHistoryModal } from "@/components/features/metrics/QubitMetricHistoryModal";
import type { Task } from "@/schemas";

const mocks = vi.hoisted(() => {
  const task = (qid: string) => ({
    task_id: `task-${qid}`,
    name: "CheckRabi",
    status: "completed",
    execution_id: "exec-1",
    qid,
    end_at: "2026-11-10T00:00:00Z",
  });
  const historyItem = (qid: string) => ({
    value: 1,
    execution_id: "exec-1",
    task_id: `task-${qid}`,
    timestamp: "2026-11-10T00:00:00Z",
    calibrated_at: null,
    name: "CheckRabi",
    input_parameters: null,
    output_parameters: null,
  });
  return {
    task,
    historyItem,
    openMiniChat: vi.fn(),
    focusTaskChat: vi.fn(),
    askAiButton: vi.fn(),
  };
});

vi.mock("@/client/task-result/task-result", () => ({
  useGetQubitTaskHistory: () => ({
    data: { data: { data: { a: mocks.task("3") } } },
    isLoading: false,
    isError: false,
  }),
  useGetCouplingTaskHistory: () => ({
    data: { data: { data: { a: mocks.task("0-1") } } },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: () => ({
    data: { data: { task: [mocks.task("3"), mocks.task("0-1")] } },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock("@/client/metrics/metrics", () => ({
  useGetQubitMetricHistory: () => ({
    data: { data: { history: [mocks.historyItem("3")] } },
    isLoading: false,
    isError: false,
  }),
  useGetCouplingMetricHistory: () => ({
    data: { data: { history: [mocks.historyItem("0-1")] } },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({
    openMiniChat: mocks.openMiniChat,
    focusTaskChat: mocks.focusTaskChat,
  }),
  useOptionalChatDock: () => null,
}));
vi.mock("@/hooks/useManualOverrides", () => ({ useManualOverrides: () => ({}) }));
// Render the details column once instead of the mobile and desktop copies.
vi.mock("@/components/features/task-history/ExecutionHistoryModalContent", () => ({
  ExecutionHistoryModalContent: ({ details }: { details: ReactNode }) => <div>{details}</div>,
}));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));
vi.mock("@/components/features/chip/TaskArtifactDownloads", () => ({
  TaskArtifactDownloads: () => null,
}));
vi.mock("@/components/features/metrics/ParametersTable", () => ({ ParametersTable: () => null }));
vi.mock("@/components/features/metrics/TaskResultMemo", () => ({ TaskResultMemo: () => null }));
vi.mock("@/components/features/metrics/TaskResultExcludeButton", () => ({
  TaskResultExcludeButton: () => null,
}));
vi.mock("@/components/features/forum/TaskResultThreads", () => ({ TaskResultThreads: () => null }));
vi.mock("@/components/features/chat/DockedChatPanel", () => ({ DockedChatPanel: () => null }));
vi.mock("@/components/features/provenance/ParameterLineageDialog", () => ({
  LineageButton: ({ children }: { children: ReactNode }) => (
    <button type="button">{children}</button>
  ),
}));
// A direct Ask AI entry in a modal would render this probe.
vi.mock("@/components/features/evaluations/AskAiButton", () => ({
  AskAiButton: () => {
    mocks.askAiButton();
    return <button type="button">Ask AI</button>;
  },
}));
// The canonical entry: the evaluation section's own Ask AI.
vi.mock("@/components/features/evaluations/TaskResultEvaluations", () => ({
  TaskResultEvaluations: (props: {
    taskId: string;
    qid?: string;
    executionId?: string;
    onChat?: () => void;
  }) => (
    <button
      type="button"
      data-task-id={props.taskId}
      data-qid={props.qid ?? ""}
      data-execution-id={props.executionId ?? ""}
      onClick={props.onChat}
    >
      Ask AI
    </button>
  ),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const executionTasks: Task[] = [
  { name: "CheckRabi", status: "completed", task_id: "task-3", qid: "3" } as Task,
];

const cases: {
  name: string;
  qid: string;
  render: () => void;
  chat: () => ReturnType<typeof vi.fn>;
}[] = [
  {
    name: "TaskHistoryModal",
    qid: "3",
    render: () =>
      render(
        <TaskHistoryModal chipId="64Q" qid="3" taskName="CheckRabi" isOpen onClose={vi.fn()} />,
      ),
    chat: () => mocks.focusTaskChat,
  },
  {
    name: "CouplingTaskHistoryModal",
    qid: "0-1",
    render: () =>
      render(
        <CouplingTaskHistoryModal
          chipId="64Q"
          couplingId="0-1"
          taskName="CheckRabi"
          isOpen
          onClose={vi.fn()}
        />,
      ),
    chat: () => mocks.openMiniChat,
  },
  {
    name: "QubitMetricHistoryModal",
    qid: "3",
    render: () =>
      render(<QubitMetricHistoryModal chipId="64Q" qid="3" metricName="t1" metricUnit="us" />),
    chat: () => mocks.openMiniChat,
  },
  {
    name: "CouplingMetricHistoryModal",
    qid: "0-1",
    render: () =>
      render(
        <CouplingMetricHistoryModal
          chipId="64Q"
          couplingId="0-1"
          metricName="zx90_gate_fidelity"
          metricUnit="%"
        />,
      ),
    chat: () => mocks.openMiniChat,
  },
  {
    name: "ExecutionTaskDetailModal",
    qid: "3",
    render: () =>
      render(
        <ExecutionTaskDetailModal
          isOpen
          chipId="64Q"
          executionId="exec-1"
          qid="3"
          tasks={executionTasks}
          onClose={vi.fn()}
        />,
      ),
    chat: () => mocks.openMiniChat,
  },
];

describe.each(cases)("$name Ask AI", ({ qid, render: renderModal, chat }) => {
  it("offers one Ask AI entry, the evaluation section's, beside Lineage", () => {
    renderModal();

    expect(screen.getByRole("button", { name: "Lineage" })).not.toBeNull();
    expect(screen.getAllByRole("button", { name: "Ask AI" })).toHaveLength(1);
    expect(mocks.askAiButton).not.toHaveBeenCalled();
  });

  it("keeps the selected result as the evaluation and chat context", () => {
    renderModal();
    const askAi = screen.getByRole("button", { name: "Ask AI" });

    expect(askAi.dataset.taskId).toBe(`task-${qid}`);
    expect(askAi.dataset.qid).toBe(qid);
    expect(askAi.dataset.executionId).toBe("exec-1");

    fireEvent.click(askAi);
    expect(chat()).toHaveBeenCalledWith({
      taskName: "CheckRabi",
      chipId: "64Q",
      qid,
      executionId: "exec-1",
      taskId: `task-${qid}`,
    });
  });
});
