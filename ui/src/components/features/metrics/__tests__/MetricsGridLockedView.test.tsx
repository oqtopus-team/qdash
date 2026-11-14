import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  fireEvent.click(screen.getByRole("button", { name: "Lock" }));

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
    expectLockedScroller(container, ["grid", "rounded-xl"]);
  });

  it("wraps the locked coupling metrics grid in a scroller", () => {
    const { container } = render(<CouplingMetricsGrid {...commonProps} />);
    expectLockedScroller(container, ["relative", "flex-shrink-0"]);
  });
});
