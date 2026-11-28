import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CouplingMetricHistoryModal } from "@/components/features/metrics/CouplingMetricHistoryModal";
import { QubitMetricHistoryModal } from "@/components/features/metrics/QubitMetricHistoryModal";

const mocks = vi.hoisted(() => {
  const historyItem = (executionId: string, timestamp: string, value: number) => ({
    value,
    execution_id: executionId,
    task_id: `task-${executionId}`,
    timestamp,
    calibrated_at: null,
    name: "CheckRabi",
    input_parameters: null,
    output_parameters: null,
  });
  return {
    historyItem,
    couplingHistoryCalls: [] as string[],
    executionCalls: [] as string[],
    memo: vi.fn(),
  };
});

vi.mock("@/client/metrics/metrics", () => ({
  useGetQubitMetricHistory: () => ({
    data: {
      data: {
        history: [
          mocks.historyItem("exec-new", "2026-11-10T00:00:00Z", 1),
          mocks.historyItem("exec-old", "2026-11-01T00:00:00Z", 2),
        ],
      },
    },
    isLoading: false,
    isError: false,
  }),
  useGetCouplingMetricHistory: (_chipId: string, couplingId: string) => {
    mocks.couplingHistoryCalls.push(couplingId);
    // Only the forward direction has history, so reversing shows the empty state.
    return {
      data: {
        data: {
          history:
            couplingId === "0-1"
              ? [
                  mocks.historyItem("exec-new", "2026-11-10T00:00:00Z", 0.9),
                  mocks.historyItem("exec-old", "2026-11-01T00:00:00Z", 0.8),
                ]
              : [],
        },
      },
      isLoading: false,
      isError: false,
    };
  },
}));
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: (executionId: string) => {
    mocks.executionCalls.push(executionId);
    return {
      data: {
        data: {
          task: [
            {
              task_id: `task-${executionId}`,
              name: "CheckRabi",
              status: "completed",
              qid: "3",
            },
            {
              task_id: `task-${executionId}`,
              name: "CheckRabi",
              status: "completed",
              qid: "0-1",
            },
          ],
        },
      },
      isLoading: false,
      isError: false,
    };
  },
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ openMiniChat: vi.fn() }),
}));
vi.mock("@/hooks/useManualOverrides", () => ({ useManualOverrides: () => ({}) }));
// Render the history and details columns once instead of the mobile and desktop copies.
vi.mock("@/components/features/task-history/ExecutionHistoryModalContent", () => ({
  ExecutionHistoryModalContent: ({
    history,
    details,
    topContent,
  }: {
    history: ReactNode;
    details: ReactNode;
    topContent?: ReactNode;
  }) => (
    <div>
      {topContent}
      {history}
      {details}
    </div>
  ),
}));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));
vi.mock("@/components/features/metrics/ParametersTable", () => ({ ParametersTable: () => null }));
vi.mock("@/components/features/metrics/TaskResultMemo", () => ({
  TaskResultMemo: () => {
    mocks.memo();
    return null;
  },
}));
vi.mock("@/components/features/metrics/TaskResultExcludeButton", () => ({
  TaskResultExcludeButton: () => null,
}));
vi.mock("@/components/features/forum/TaskResultThreads", () => ({ TaskResultThreads: () => null }));
vi.mock("@/components/features/evaluations/TaskResultEvaluations", () => ({
  TaskResultEvaluations: () => null,
}));
vi.mock("@/components/features/provenance/ParameterLineageDialog", () => ({
  LineageButton: ({ children }: { children: ReactNode }) => (
    <button type="button">{children}</button>
  ),
}));

function last(values: string[]): string | undefined {
  return values[values.length - 1];
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.couplingHistoryCalls.length = 0;
  mocks.executionCalls.length = 0;
});

describe("QubitMetricHistoryModal", () => {
  it("selects the newest execution and shows result notes", () => {
    render(<QubitMetricHistoryModal chipId="64Q" qid="3" metricName="t1" metricUnit="us" />);

    expect(screen.getByText("2 executions with t1")).not.toBeNull();
    expect(last(mocks.executionCalls)).toBe("exec-new");
    expect(mocks.memo).toHaveBeenCalled();
    expect(screen.queryByTitle(/Switch to/)).toBeNull();
  });

  it("keeps the selected execution when the qubit ID changes", () => {
    const { rerender } = render(
      <QubitMetricHistoryModal chipId="64Q" qid="3" metricName="t1" metricUnit="us" />,
    );
    fireEvent.click(screen.getByText("#2").closest("button")!);
    expect(last(mocks.executionCalls)).toBe("exec-old");

    rerender(<QubitMetricHistoryModal chipId="64Q" qid="4" metricName="t1" metricUnit="us" />);

    expect(last(mocks.executionCalls)).toBe("exec-old");
  });
});

describe("CouplingMetricHistoryModal", () => {
  function renderCoupling() {
    render(
      <CouplingMetricHistoryModal
        chipId="64Q"
        couplingId="0-1"
        metricName="zx90_gate_fidelity"
        metricUnit="%"
      />,
    );
  }

  it("shows the direction toggle and no result notes", () => {
    renderCoupling();

    expect(screen.getByTitle("Switch to 1-0")).not.toBeNull();
    expect(screen.getByText("2 executions with zx90_gate_fidelity")).not.toBeNull();
    expect(mocks.memo).not.toHaveBeenCalled();
  });

  it("refetches the reversed direction and keeps the toggle in the empty state", () => {
    renderCoupling();
    fireEvent.click(screen.getByTitle("Switch to 1-0"));

    expect(last(mocks.couplingHistoryCalls)).toBe("1-0");
    expect(
      screen.getByText(/No zx90_gate_fidelity history available for 1-0 in the last 365 days/),
    ).not.toBeNull();
    expect(screen.getByTitle("Switch to 0-1")).not.toBeNull();
  });

  it("clears the selected execution when the direction changes and back", () => {
    renderCoupling();
    fireEvent.click(screen.getByText("#2").closest("button")!);
    expect(last(mocks.executionCalls)).toBe("exec-old");

    fireEvent.click(screen.getByTitle("Switch to 1-0"));
    fireEvent.click(screen.getByTitle("Switch to 0-1"));

    // The selection reset re-selects the newest execution of the restored direction.
    expect(last(mocks.executionCalls)).toBe("exec-new");
  });

  it("keeps the selected execution when the coupling ID changes", () => {
    const props = { chipId: "64Q", metricName: "zx90_gate_fidelity", metricUnit: "%" };
    const { rerender } = render(<CouplingMetricHistoryModal {...props} couplingId="0-1" />);
    fireEvent.click(screen.getByText("#2").closest("button")!);
    expect(last(mocks.executionCalls)).toBe("exec-old");

    rerender(<CouplingMetricHistoryModal {...props} couplingId="1-0" />);

    expect(last(mocks.couplingHistoryCalls)).toBe("1-0");
    expect(last(mocks.executionCalls)).toBe("exec-old");
  });
});
