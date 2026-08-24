import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Task } from "@/schemas";

import { ExecutionTopologyView } from "@/components/features/execution/ExecutionTopologyView";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderTopologyView(props: React.ComponentProps<typeof ExecutionTopologyView>) {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ExecutionTopologyView {...props} />
    </QueryClientProvider>,
  );
}

vi.mock("@/client/chip/chip", () => ({
  useGetChip: () => ({
    data: { data: { size: 4, topology_id: "test-topology" } },
  }),
}));

vi.mock("@/hooks/useTopologyConfig", () => ({
  useTopologyConfig: () => ({
    muxSize: 2,
    hasMux: false,
    layoutType: "grid",
    showMuxBoundaries: false,
    qubits: {
      "0": { row: 0, col: 0 },
      "1": { row: 0, col: 1 },
    },
    gridSize: 2,
  }),
}));

afterEach(() => {
  cleanup();
});

describe("ExecutionTopologyView grid figures", () => {
  it("renders a one-qubit figure without an expand button", () => {
    const tasks: Task[] = [
      {
        task_id: "task-1",
        qid: "0",
        name: "CheckT1",
        status: "completed",
        figure_path: ["/path/to/qubit-figure.png"],
      },
    ];

    renderTopologyView({
      chipId: "chip-1",
      executionId: "exec-1",
      executionName: "Execution 1",
      tasks,
      topologyMode: "1q",
      filterTaskName: "CheckT1",
      onToggleFullscreen: vi.fn(),
    });

    expect(screen.getByAltText("Result for QID 0")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Expand figure" })).toBeNull();
  });

  it("renders a coupling figure without an expand button", () => {
    const tasks: Task[] = [
      {
        task_id: "task-2",
        qid: "0-1",
        name: "CheckCoupling",
        status: "completed",
        figure_path: ["/path/to/coupling-figure.png"],
      },
    ];

    renderTopologyView({
      chipId: "chip-1",
      executionId: "exec-1",
      executionName: "Execution 1",
      tasks,
      topologyMode: "2q",
      filterTaskName: "CheckCoupling",
      onToggleFullscreen: vi.fn(),
    });

    expect(screen.getByAltText("Result for QID 0-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Expand figure" })).toBeNull();
  });
});
