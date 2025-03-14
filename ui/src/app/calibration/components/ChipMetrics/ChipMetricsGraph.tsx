"use client";

import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[600px]">
      <div className="loading loading-spinner loading-lg"></div>
    </div>
  ),
});

export default function ChipMetricsGraph() {
  return (
    <div className="w-full h-full">
      <Plot
        data={[]}
        layout={{
          title: {
            text: "Chip Metrics",
            font: {
              size: 24,
            },
          },
          plot_bgcolor: "rgba(0,0,0,0)",
          paper_bgcolor: "rgba(0,0,0,0)",
          margin: { t: 50, r: 50, b: 50, l: 50 },
        }}
        config={{
          displaylogo: false,
          responsive: true,
        }}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}
