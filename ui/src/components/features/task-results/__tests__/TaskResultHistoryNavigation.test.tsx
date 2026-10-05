import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaskResultHistoryNavigation } from "@/components/features/task-results/TaskResultHistoryNavigation";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  qubitHistory: vi.fn(),
  couplingHistory: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/client/task-result/task-result", () => ({
  useGetQubitTaskHistory: mocks.qubitHistory,
  useGetCouplingTaskHistory: mocks.couplingHistory,
}));

const historyResponse = {
  data: {
    data: {
      data: {
        "task-current": { end_at: "2026-09-02T00:00:00Z" },
        "task-older": { end_at: "2026-09-01T00:00:00Z" },
        "task-newer": { end_at: "2026-09-03T00:00:00Z" },
      },
    },
  },
  isLoading: false,
};

describe("TaskResultHistoryNavigation", () => {
  afterEach(cleanup);

  beforeEach(() => {
    mocks.push.mockReset();
    mocks.qubitHistory.mockReset().mockReturnValue({ data: undefined, isLoading: false });
    mocks.couplingHistory.mockReset().mockReturnValue({ data: undefined, isLoading: false });
  });

  it("navigates to the adjacent results for the same qubit task", () => {
    mocks.qubitHistory.mockReturnValue(historyResponse);

    render(
      <TaskResultHistoryNavigation
        taskId="task-current"
        taskName="CheckRabi"
        chipId="chip-1"
        qid="32"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Previous result" }));
    expect(mocks.push).toHaveBeenLastCalledWith("/task-results/task-older");

    fireEvent.click(screen.getByRole("button", { name: "Next result" }));
    expect(mocks.push).toHaveBeenLastCalledWith("/task-results/task-newer");
    expect(mocks.qubitHistory.mock.calls[0]?.[2].query.enabled).toBe(true);
    expect(mocks.couplingHistory.mock.calls[0]?.[2].query.enabled).toBe(false);
  });

  it("uses coupling history for a coupling qid", () => {
    mocks.couplingHistory.mockReturnValue(historyResponse);

    render(
      <TaskResultHistoryNavigation
        taskId="task-current"
        taskName="CheckCrossResonance"
        chipId="chip-1"
        qid="32-33"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Previous result" }));
    expect(mocks.push).toHaveBeenCalledWith("/task-results/task-older");
    expect(mocks.qubitHistory.mock.calls[0]?.[2].query.enabled).toBe(false);
    expect(mocks.couplingHistory.mock.calls[0]?.[2].query.enabled).toBe(true);
  });

  it("disables navigation beyond the ends of the history", () => {
    mocks.qubitHistory.mockReturnValue({
      data: {
        data: {
          data: {
            "task-current": { end_at: "2026-09-03T00:00:00Z" },
            "task-older": { end_at: "2026-09-01T00:00:00Z" },
          },
        },
      },
      isLoading: false,
    });

    render(
      <TaskResultHistoryNavigation
        taskId="task-current"
        taskName="CheckRabi"
        chipId="chip-1"
        qid="32"
      />,
    );

    expect(screen.getByRole("button", { name: "Previous result" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Next result" })).toBeDisabled();
  });
});
