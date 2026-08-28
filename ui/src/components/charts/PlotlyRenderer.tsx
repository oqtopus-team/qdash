"use client";

import { useQuery } from "@tanstack/react-query";
import type { PlotMouseEvent } from "plotly.js";

import Plot from "@/components/charts/Plot";

export function PlotlyRenderer({
  fullPath,
  className = "",
  onClick,
  highlightPoint,
}: {
  fullPath: string;
  className?: string;
  onClick?: (event: PlotMouseEvent) => void;
  highlightPoint?: { x: number; y: number; label?: string } | null;
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
        layout={{
          ...figure.layout,
          autosize: false,
          // Preserve original width/height from the figure JSON
        }}
        config={{ displayModeBar: true, responsive: false }}
        useResizeHandler={false}
        onClick={onClick}
        style={{ width: "auto", height: "auto" }}
      />
    </div>
  );
}
