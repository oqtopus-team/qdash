"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface MetricDataItem {
  value: number | null;
}

// Single metric CDF props
interface SingleMetricCdfProps {
  metricData: { [key: string]: MetricDataItem } | null;
  title: string;
  unit: string;
}

// Grouped metrics CDF props
interface GroupedMetricsCdfProps {
  metricsData: {
    key: string;
    title: string;
    data: { [key: string]: MetricDataItem } | null;
  }[];
  groupTitle: string;
  unit: string;
}

type MetricsCdfChartProps = SingleMetricCdfProps | GroupedMetricsCdfProps;

// Type guard to check if props are for grouped metrics
function isGroupedProps(
  props: MetricsCdfChartProps,
): props is GroupedMetricsCdfProps {
  return "metricsData" in props;
}

// Color palette for multiple metrics
const COLORS = [
  "#3b82f6", // blue
  "#10b981", // green
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // purple
  "#06b6d4", // cyan
];

interface CdfDataPoint {
  cdfX: number[];
  cdfY: number[];
  median: number;
}

function calculateCdf(
  data: { [key: string]: MetricDataItem } | null,
): CdfDataPoint | null {
  if (!data) return null;

  const values = Object.values(data)
    .map((item) => item.value)
    .filter((v): v is number => v !== null && !isNaN(v))
    .sort((a, b) => a - b);

  if (values.length === 0) return null;

  const n = values.length;
  const cdfX: number[] = [];
  const cdfY: number[] = [];

  const minValue = values[0];
  const maxValue = values[n - 1];
  const range = maxValue - minValue;
  const extension = range * 0.05; // Extend by 5% of range

  // Add starting point at 0% (extend slightly before min value)
  cdfX.push(minValue - extension);
  cdfY.push(0);

  values.forEach((value, index) => {
    cdfX.push(value);
    cdfY.push(((index + 1) / n) * 100);
  });

  // Add flat tail at 100% (extend slightly beyond max value)
  cdfX.push(maxValue + extension);
  cdfY.push(100);

  const median = values[Math.floor(n / 2)];

  return { cdfX, cdfY, median };
}

export function MetricsCdfChart(props: MetricsCdfChartProps) {
  const isGrouped = isGroupedProps(props);

  const plotData = useMemo(() => {
    const traces: any[] = [];

    if (isGrouped) {
      // Grouped metrics mode
      props.metricsData.forEach((metric, index) => {
        const cdf = calculateCdf(metric.data);
        if (!cdf) return;

        const color = COLORS[index % COLORS.length];
        const n = cdf.cdfX.length - 2; // Subtract the extension points

        // CDF line
        traces.push({
          x: cdf.cdfX,
          y: cdf.cdfY,
          type: "scatter",
          mode: "lines",
          name: `${metric.title} (n=${n})`,
          line: { color, width: 2, shape: "hv" },
          hovertemplate: `${metric.title}: %{x:.3f}<br>Percentile: %{y:.1f}%<extra></extra>`,
        });

        // Median reference line (vertical) - shown in legend
        traces.push({
          x: [cdf.median, cdf.median],
          y: [0, 50],
          type: "scatter",
          mode: "lines",
          name: `${metric.title} Median: ${cdf.median.toFixed(2)}`,
          line: { color, width: 1, dash: "dot" },
          hoverinfo: "skip",
        });
      });

      return traces.length > 0 ? traces : null;
    } else {
      // Single metric mode
      const cdf = calculateCdf(props.metricData);
      if (!cdf) return null;

      const n = cdf.cdfX.length - 2;

      traces.push(
        {
          x: cdf.cdfX,
          y: cdf.cdfY,
          type: "scatter",
          mode: "lines",
          name: `${props.title} (n=${n})`,
          line: { color: "#3b82f6", width: 2, shape: "hv" },
          hovertemplate: `${props.title}: %{x:.3f} ${props.unit}<br>Percentile: %{y:.1f}%<extra></extra>`,
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
      );

      return traces;
    }
  }, [isGrouped, props]);

  const title = isGrouped ? props.groupTitle : props.title;
  const unit = props.unit;

  if (!plotData) {
    return (
      <div className="flex items-center justify-center h-48 bg-base-200 rounded-lg">
        <span className="text-base-content/50">No data available</span>
      </div>
    );
  }

  return (
    <div className="collapse collapse-arrow bg-base-100 rounded-lg shadow-sm border border-base-300">
      <input type="checkbox" defaultChecked />
      <div className="collapse-title px-4 py-2 min-h-0 font-semibold text-sm">
        CDF - {title}
      </div>
      <div className="collapse-content p-0">
        <div
          className="p-2 w-full border-t border-base-300"
          style={{ minHeight: 250 }}
        >
          <Plot
            data={plotData}
            layout={{
              autosize: true,
              height: 250,
              margin: { l: 50, r: 20, t: 10, b: 50 },
              xaxis: {
                title: { text: `${title} (${unit})`, font: { size: 11 } },
                gridcolor: "rgba(128,128,128,0.2)",
                zeroline: false,
              },
              yaxis: {
                title: { text: "Cumulative %", font: { size: 11 } },
                range: [0, 100],
                gridcolor: "rgba(128,128,128,0.2)",
                zeroline: false,
              },
              showlegend: true,
              legend: {
                orientation: "h",
                y: -0.25,
                x: 0.5,
                xanchor: "center",
                font: { size: 10 },
              },
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: "rgba(0,0,0,0)",
              hovermode: "x unified",
            }}
            config={{
              displayModeBar: false,
              responsive: true,
            }}
            useResizeHandler={true}
            style={{ width: "100%", height: "100%" }}
          />
        </div>
      </div>
    </div>
  );
}
