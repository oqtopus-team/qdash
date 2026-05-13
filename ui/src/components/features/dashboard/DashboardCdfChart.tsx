"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

const Plot = dynamic(() => import("@/components/charts/Plot"), { ssr: false });

interface MetricDataItem {
  value: number | null;
}

interface DashboardCdfChartProps {
  metricData: { [key: string]: MetricDataItem } | null;
  title: string;
  unit: string;
  /** Plot height in px. Defaults to 280. */
  height?: number;
}

interface CdfPoint {
  x: number[];
  y: number[];
  median: number;
  n: number;
}

function calculateCdf(data: { [key: string]: MetricDataItem } | null): CdfPoint | null {
  if (!data) return null;
  const values = Object.values(data)
    .map((item) => item.value)
    .filter((v): v is number => v !== null && !isNaN(v))
    .sort((a, b) => a - b);
  if (values.length === 0) return null;

  const n = values.length;
  const min = values[0];
  const max = values[n - 1];
  const range = max - min;
  const ext = range * 0.05;

  const x: number[] = [min - ext];
  const y: number[] = [0];
  values.forEach((v, i) => {
    x.push(v);
    y.push(((i + 1) / n) * 100);
  });
  x.push(max + ext);
  y.push(100);

  return { x, y, median: values[Math.floor(n / 2)], n };
}

/**
 * Dashboard-specific CDF chart for one metric. Strips the daisyUI collapse and
 * max-width wrapper that ships with MetricsCdfChart so it fills the column it
 * sits in next to a heatmap.
 */
export function DashboardCdfChart({
  metricData,
  title,
  unit,
  height = 280,
}: DashboardCdfChartProps) {
  const cdf = useMemo(() => calculateCdf(metricData), [metricData]);

  if (!cdf) {
    return (
      <div
        className="flex items-center justify-center bg-base-200 rounded-lg border border-base-300"
        style={{ height }}
      >
        <span className="text-base-content/50 text-xs">No CDF data</span>
      </div>
    );
  }

  return (
    <div
      className="bg-base-100 rounded-lg shadow-sm border border-base-300 p-2 w-full"
      style={{ minHeight: height }}
    >
      <div className="px-1 pb-1 text-xs font-semibold text-base-content/80">
        CDF · {title} <span className="text-base-content/50 font-normal">(n={cdf.n})</span>
      </div>
      <Plot
        data={[
          {
            x: cdf.x,
            y: cdf.y,
            type: "scatter",
            mode: "lines",
            name: title,
            line: { color: "#3b82f6", width: 2, shape: "hv" },
            hovertemplate: `${title}: %{x:.3f} ${unit}<br>Percentile: %{y:.1f}%<extra></extra>`,
          },
          {
            x: [cdf.median, cdf.median],
            y: [0, 50],
            type: "scatter",
            mode: "lines",
            name: `Median: ${cdf.median.toFixed(2)}`,
            line: { color: "#3b82f6", width: 1, dash: "dot" },
            hoverinfo: "skip",
          },
        ]}
        layout={{
          autosize: true,
          height,
          margin: { l: 50, r: 16, t: 8, b: 40 },
          xaxis: {
            title: { text: `${title} (${unit})`, font: { size: 10 } },
            gridcolor: "rgba(128,128,128,0.2)",
            zeroline: false,
          },
          yaxis: {
            title: { text: "Cumulative %", font: { size: 10 } },
            range: [0, 100],
            gridcolor: "rgba(128,128,128,0.2)",
            zeroline: false,
          },
          showlegend: false,
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          hovermode: "x unified",
        }}
        config={{ displayModeBar: false, responsive: true }}
        useResizeHandler
        style={{ width: "100%", height: `${height}px` }}
      />
    </div>
  );
}
