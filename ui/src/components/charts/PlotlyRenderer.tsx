"use client";

import { useQuery } from "@tanstack/react-query";
import type { Layout, PlotMouseEvent } from "plotly.js";

import Plot from "@/components/charts/Plot";

/**
 * How a figure is sized.
 * - `figure`: keep the width and height stored in the figure JSON (default).
 * - `container`: ignore the stored size and fill the parent element, resizing with it.
 *   The parent must have a definite width and height.
 */
export type PlotlySizing = "figure" | "container";

/** Builds the Plotly layout and config for a sizing mode. */
export function plotlySizingProps(
  layout: Partial<Layout> | undefined,
  sizing: PlotlySizing,
): {
  layout: Partial<Layout>;
  config: { displayModeBar: true; responsive: boolean };
  useResizeHandler: boolean;
  style: { width: string; height: string };
} {
  if (sizing === "container") {
    // Drop the stored pixel size so Plotly measures the container instead.
    const fitted: Partial<Layout> = { ...layout, autosize: true };
    delete fitted.width;
    delete fitted.height;
    return {
      layout: fitted,
      config: { displayModeBar: true, responsive: true },
      useResizeHandler: true,
      style: { width: "100%", height: "100%" },
    };
  }
  return {
    // Preserve original width/height from the figure JSON
    layout: { ...layout, autosize: false },
    config: { displayModeBar: true, responsive: false },
    useResizeHandler: false,
    style: { width: "auto", height: "auto" },
  };
}

export function PlotlyRenderer({
  fullPath,
  className = "",
  onClick,
  highlightPoint,
  sizing = "figure",
}: {
  fullPath: string;
  className?: string;
  onClick?: (event: PlotMouseEvent) => void;
  highlightPoint?: { x: number; y: number; label?: string } | null;
  sizing?: PlotlySizing;
}) {
  const { data: figure, error } = useQuery({
    queryKey: ["plotly-figure", fullPath],
    queryFn: async () => {
      const res = await fetch(fullPath);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
  });

  if (error) return <div className="text-error">Failed to load plot</div>;
  if (!figure) return <div>Loading...</div>;

  const sized = plotlySizingProps(figure.layout, sizing);

  return (
    <div className={className}>
      <Plot
        data={[
          ...figure.data,
          ...(highlightPoint
            ? [
                {
                  x: [highlightPoint.x],
                  y: [highlightPoint.y],
                  type: "scatter" as const,
                  mode: "markers+text" as const,
                  name: highlightPoint.label ?? "Manual correction",
                  text: [highlightPoint.label ?? "Selected"],
                  textposition: "top center" as const,
                  marker: {
                    color: "var(--color-error)",
                    size: 12,
                    symbol: "x",
                    line: { width: 2 },
                  },
                  hovertemplate: "x=%{x}<br>y=%{y}<extra>Manual correction</extra>",
                },
              ]
            : []),
        ]}
        layout={sized.layout}
        config={sized.config}
        useResizeHandler={sized.useResizeHandler}
        onClick={onClick}
        style={sized.style}
      />
    </div>
  );
}
