import { cleanup, render, screen } from "@testing-library/react";
import type { Layout } from "plotly.js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlotCard } from "@/components/charts/PlotCard";

const plotProps = vi.hoisted(() => [] as Array<{ layout: Partial<Layout> }>);

vi.mock("next/dynamic", () => ({
  default: () =>
    function PlotStub(props: { layout: Partial<Layout> }) {
      plotProps.push(props);
      return <div data-testid="plot" />;
    },
}));

const layout: Partial<Layout> = {
  title: { text: "T1 & T2 echo", font: { size: 24 } },
  showlegend: true,
  legend: { x: 1.02, xanchor: "left" },
  margin: { l: 64, r: 24, t: 72, b: 64 },
  xaxis: { title: { text: "Time (JST)" } },
  yaxis: { title: { text: "T1 [us]" } },
  yaxis2: { title: { text: "T2 echo [us]" }, overlaying: "y", side: "right" },
};

const plotData = [{ x: [1], y: [2], name: "T1 Q0" }];

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
}

function lastLayout() {
  return plotProps[plotProps.length - 1]?.layout;
}

describe("PlotCard", () => {
  const originalWidth = window.innerWidth;

  beforeEach(() => {
    plotProps.length = 0;
  });

  afterEach(() => {
    cleanup();
    setViewportWidth(originalWidth);
  });

  it("renders a single plot with the caller layout on wide viewports", () => {
    setViewportWidth(1280);
    render(<PlotCard title="Time Series Plot" plotData={plotData} layout={layout} />);

    expect(screen.getByRole("heading", { name: "Time Series Plot" })).toBeInTheDocument();
    expect(screen.getAllByTestId("plot")).toHaveLength(1);
    expect(lastLayout()).toBe(layout);
  });

  it("enables automargin for both y axes when the legend is hidden on narrow viewports", () => {
    setViewportWidth(375);
    render(<PlotCard title="Time Series Plot" plotData={plotData} layout={layout} />);

    expect(screen.getAllByTestId("plot")).toHaveLength(1);
    const mobile = lastLayout();
    expect(mobile?.showlegend).toBe(false);
    expect(mobile?.xaxis?.automargin).toBe(true);
    expect(mobile?.yaxis?.automargin).toBe(true);
    expect(mobile?.yaxis?.title).toEqual({ text: "T1 [us]" });
    expect(mobile?.yaxis2?.automargin).toBe(true);
    expect(mobile?.yaxis2?.title).toEqual({ text: "T2 echo [us]" });
    expect(mobile?.yaxis2?.side).toBe("right");
    expect(mobile?.title).toEqual({ text: "T1 & T2 echo", font: { size: 14 } });
  });

  it("does not add a secondary axis to single-axis layouts on narrow viewports", () => {
    setViewportWidth(375);
    const { yaxis2: _unused, ...singleAxis } = layout;
    render(<PlotCard title="Histogram" plotData={plotData} layout={singleAxis} />);

    expect(lastLayout()).not.toHaveProperty("yaxis2");
  });

  it("shows the empty state instead of a plot when there is no data", () => {
    setViewportWidth(1280);
    render(
      <PlotCard
        title="Time Series Plot"
        plotData={[]}
        layout={layout}
        hasData={false}
        emptyStateMessage="Select chip and parameters to visualize data"
      />,
    );

    expect(screen.getByText("Select chip and parameters to visualize data")).toBeInTheDocument();
    expect(screen.queryByTestId("plot")).not.toBeInTheDocument();
  });

  it("applies breakpoint heights to the single plot area", () => {
    setViewportWidth(1280);
    render(
      <PlotCard
        title="Time Series Plot"
        plotData={plotData}
        layout={layout}
        height="700px"
        mobileHeight="420px"
      />,
    );

    const area = screen.getByTestId("plot-card-area");
    expect(area.style.getPropertyValue("--plot-card-height")).toBe("700px");
    expect(area.style.getPropertyValue("--plot-card-mobile-height")).toBe("420px");
  });
});
