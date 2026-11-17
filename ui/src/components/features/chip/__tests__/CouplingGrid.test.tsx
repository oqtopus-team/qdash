import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CouplingGrid } from "../CouplingGrid";

const wideQubits = Object.fromEntries(
  Array.from({ length: 24 }, (_, index) => [
    index,
    { row: Math.floor(index / 12), col: index % 12 },
  ]),
);

vi.mock("@/hooks/useTopologyConfig", () => ({
  useTopologyConfig: () => ({
    muxSize: 2,
    regionSize: 4,
    hasMux: false,
    layoutType: "grid",
    showMuxBoundaries: false,
    qubits: wideQubits,
    couplings: [[0, 1]],
    gridSize: 12,
  }),
}));

vi.mock("@/hooks/useCouplingTaskResults", () => ({
  useCouplingTaskResults: () => ({
    data: { data: { result: {} } },
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/hooks/useGridLayout", () => ({
  useGridLayout: () => ({
    containerRef: { current: null },
    cellSize: 40,
    isMobile: false,
    viewportHeight: 900,
    gap: 8,
    padding: 32,
  }),
}));

vi.mock("@/client/task-result/task-result", () => ({
  downloadFiguresAsZip: vi.fn(),
}));

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: () => null,
}));

vi.mock("@/components/features/chip/modals/CouplingTaskHistoryModal", () => ({
  CouplingTaskHistoryModal: () => null,
}));

describe("CouplingGrid locked view", () => {
  it("wraps the locked grid in a scroller so overflowing cells stay reachable", () => {
    const { container } = render(
      <CouplingGrid
        chipId="chip"
        topologyId="wide"
        selectedTask="CheckZX90"
        selectedDate="latest"
        gridSize={12}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Lock" }));

    const scroller = container.querySelector<HTMLElement>(".overflow-auto.justify-center-safe");
    expect(scroller).not.toBeNull();
    const outerContainer = scroller?.parentElement;
    expect(outerContainer).toHaveClass("overflow-hidden");
    const fullscreenButton = screen.getByRole("button", { name: "Fullscreen" });
    expect(outerContainer?.contains(fullscreenButton)).toBe(true);
    expect(scroller?.firstElementChild).toHaveClass("relative", "flex-shrink-0");
    expect(scroller?.contains(fullscreenButton)).toBe(false);
  });
});
