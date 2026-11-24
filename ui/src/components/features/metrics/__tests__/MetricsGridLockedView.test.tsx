import type { ReactNode } from "react";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CouplingMetricsGrid } from "../CouplingMetricsGrid";
import { QubitMetricsGrid } from "../QubitMetricsGrid";

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

// Stands in for the pan/zoom canvas: the button reports a zoom-out to the grid.
vi.mock("react-zoom-pan-pinch", () => ({
  TransformWrapper: ({
    children,
    onTransform,
  }: {
    children: ReactNode;
    onTransform?: (ref: unknown, state: { scale: number }) => void;
  }) => (
    <div>
      <button type="button" onClick={() => onTransform?.(null, { scale: 0.5 })}>
        Report zoom-out
      </button>
      {children}
    </div>
  ),
  TransformComponent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  useControls: () => ({ zoomIn: vi.fn(), zoomOut: vi.fn(), resetTransform: vi.fn() }),
}));

vi.mock("../QubitMetricHistoryModal", () => ({
  QubitMetricHistoryModal: () => null,
}));

vi.mock("../CouplingMetricHistoryModal", () => ({
  CouplingMetricHistoryModal: () => null,
}));

const commonProps = {
  metricData: null,
  title: "Metric",
  metricKey: "t1",
  unit: "us",
  colorScale: { min: 0, max: 1, colors: ["#000000", "#ffffff"] },
  gridSize: 12,
  chipId: "chip",
  topologyId: "wide",
  selectedDate: "latest",
};

function expectLockedScroller(container: HTMLElement, contentClasses: string[]) {
  fireEvent.click(screen.getByRole("tab", { name: "Lock" }));

  const scroller = container.querySelector<HTMLElement>(".overflow-auto.justify-center-safe");
  expect(scroller).not.toBeNull();
  const outerContainer = scroller?.parentElement;
  expect(outerContainer).toHaveClass("overflow-hidden");
  const fullscreenButton = screen.getByRole("button", { name: "Fullscreen" });
  expect(outerContainer?.contains(fullscreenButton)).toBe(true);
  expect(scroller?.firstElementChild).toHaveClass(...contentClasses);
  expect(scroller?.contains(fullscreenButton)).toBe(false);
}

describe("metrics grids locked view", () => {
  afterEach(cleanup);

  it("wraps the locked qubit metrics grid in a scroller", () => {
    const { container } = render(<QubitMetricsGrid {...commonProps} />);
    expectLockedScroller(container, ["grid"]);
  });

  it("restores qubit labels, values and units when the zoomed-out grid is locked", () => {
    vi.useFakeTimers();
    try {
      render(<QubitMetricsGrid {...commonProps} />);
      expect(screen.getAllByText("N/A")).toHaveLength(24);

      fireEvent.click(screen.getByRole("button", { name: "Report zoom-out" }));
      act(() => {
        vi.runAllTimers();
      });
      expect(screen.queryByText("N/A")).toBeNull();
      expect(screen.queryByText("(us)")).toBeNull();

      fireEvent.click(screen.getByRole("tab", { name: "Lock" }));

      expect(screen.getAllByText("N/A")).toHaveLength(24);
      expect(screen.getAllByText("(us)")).toHaveLength(24);
      expect(screen.getByText("23")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("wraps the locked coupling metrics grid in a scroller", () => {
    const { container } = render(<CouplingMetricsGrid {...commonProps} />);
    expectLockedScroller(container, ["relative", "flex-shrink-0"]);
  });

  it("opens the qubit value tooltip on keyboard focus", () => {
    render(<QubitMetricsGrid {...commonProps} />);

    const cell = screen.getByText("23").closest("button");
    expect(cell).not.toBeNull();
    fireEvent.focus(cell!);

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toBe("23: No data");
    expect(cell?.getAttribute("aria-describedby")).toBe(tooltip.id);
  });

  it("names coupling cells and opens their tooltip on keyboard focus", () => {
    render(<CouplingMetricsGrid {...commonProps} />);

    const coupling = screen.getByRole("button", { name: "0\u21921: No data" });
    fireEvent.focus(coupling);

    expect(screen.getByRole("tooltip").textContent).toBe("0\u21921: No data");
  });
});
