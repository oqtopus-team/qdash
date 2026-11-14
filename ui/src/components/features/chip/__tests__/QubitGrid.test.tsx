import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QubitGrid } from "../QubitGrid";

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
    gridSize: 12,
  }),
}));

vi.mock("@/hooks/useQubitTaskResults", () => ({
  useQubitTaskResults: () => ({
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

vi.mock("@/components/features/chip/modals/TaskHistoryModal", () => ({
  TaskHistoryModal: () => null,
}));

describe("QubitGrid locked view", () => {
  it("lets a wide non-square grid scroll instead of clipping its cells", () => {
    const { container } = render(
      <QubitGrid
        chipId="chip"
        topologyId="wide"
        selectedTask="CheckT1"
        selectedDate="latest"
        gridSize={12}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Lock" }));

    const grid = container.querySelector<HTMLElement>(".grid.rounded-xl");
    expect(grid?.style.gridTemplateColumns).toContain("repeat(12,");
    expect(grid?.style.gridTemplateRows).toContain("repeat(2,");
    const scroller = grid?.parentElement;
    expect(scroller).toHaveClass("overflow-auto");
    expect(scroller).toHaveClass("justify-center-safe");
    const outerContainer = scroller?.parentElement;
    expect(outerContainer).toHaveClass("overflow-hidden");
    const fullscreenButton = screen.getByRole("button", { name: "Fullscreen" });
    expect(outerContainer?.contains(fullscreenButton)).toBe(true);
    expect(scroller?.contains(fullscreenButton)).toBe(false);
  });
});
