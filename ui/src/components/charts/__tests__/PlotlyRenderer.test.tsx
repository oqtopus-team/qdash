import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlotlyRenderer, plotlySizingProps } from "@/components/charts/PlotlyRenderer";

const plotProps = vi.hoisted(() => ({
  calls: [] as Record<string, unknown>[],
}));

vi.mock("@/components/charts/Plot", () => ({
  default: (props: Record<string, unknown>) => {
    plotProps.calls.push(props);
    return <div data-testid="plot" />;
  },
}));

const figure = {
  data: [{ x: [1, 2], y: [3, 4], type: "scatter" }],
  layout: { width: 1200, height: 900, title: { text: "CR" } },
};

function renderWithQuery(node: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("plotlySizingProps", () => {
  it("keeps the stored figure size by default", () => {
    const sized = plotlySizingProps({ width: 1200, height: 900 }, "figure");

    expect(sized.layout).toMatchObject({
      width: 1200,
      height: 900,
      autosize: false,
    });
    expect(sized.config).toEqual({ displayModeBar: true, responsive: false });
    expect(sized.useResizeHandler).toBe(false);
    expect(sized.style).toEqual({ width: "auto", height: "auto" });
  });

  it("drops the stored size and follows the container when fitted", () => {
    const layout = { width: 1200, height: 900, title: { text: "CR" } };
    const sized = plotlySizingProps(layout, "container");

    expect(sized.layout).not.toHaveProperty("width");
    expect(sized.layout).not.toHaveProperty("height");
    expect(sized.layout).toMatchObject({
      autosize: true,
      title: { text: "CR" },
    });
    expect(sized.config).toEqual({ displayModeBar: true, responsive: true });
    expect(sized.useResizeHandler).toBe(true);
    expect(sized.style).toEqual({ width: "100%", height: "100%" });
    // The source figure layout is not mutated.
    expect(layout).toMatchObject({ width: 1200, height: 900 });
  });
});

describe("PlotlyRenderer", () => {
  beforeEach(() => {
    plotProps.calls.length = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(figure), { status: 200 })),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the figure at its stored size unless sizing is requested", async () => {
    renderWithQuery(<PlotlyRenderer fullPath="/figure-a.json" />);

    await waitFor(() => expect(plotProps.calls.length).toBeGreaterThan(0));
    const props = plotProps.calls[plotProps.calls.length - 1];
    expect(props.layout).toMatchObject({
      width: 1200,
      height: 900,
      autosize: false,
    });
    expect(props.useResizeHandler).toBe(false);
  });

  it("fills its container when sizing is container", async () => {
    renderWithQuery(<PlotlyRenderer fullPath="/figure-b.json" sizing="container" />);

    await waitFor(() => expect(plotProps.calls.length).toBeGreaterThan(0));
    const props = plotProps.calls[plotProps.calls.length - 1];
    expect(props.layout).not.toHaveProperty("width");
    expect(props.layout).toMatchObject({ autosize: true });
    expect(props.config).toEqual({ displayModeBar: true, responsive: true });
    expect(props.useResizeHandler).toBe(true);
  });

  it("keeps click handling and the highlight trace for manual correction", async () => {
    const onClick = vi.fn();
    renderWithQuery(
      <PlotlyRenderer
        fullPath="/figure-c.json"
        onClick={onClick}
        highlightPoint={{ x: 5, y: 6, label: "Manual correction" }}
      />,
    );

    await waitFor(() => expect(plotProps.calls.length).toBeGreaterThan(0));
    const props = plotProps.calls[plotProps.calls.length - 1];
    expect(props.onClick).toBe(onClick);
    expect(props.data).toHaveLength(2);
    expect((props.data as { x: number[] }[])[1].x).toEqual([5]);
  });
});
