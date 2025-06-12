"use client";

import Plot from "react-plotly.js";
import { useEffect, useState } from "react";

export default function PlotlyRenderer({
  fullPath,
  className = "",
}: {
  fullPath: string;
  className?: string;
}) {
  const [figure, setFigure] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(fullPath)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((fig) => setFigure(fig))
      .catch((err) => {
        console.error("Failed to load Plotly figure:", err);
        setError("Failed to load plot");
      });
  }, [fullPath]);

  if (error) return <div className="text-red-500">{error}</div>;
  if (!figure) return <div>Loading...</div>;

  return (
    <Plot
      data={figure.data}
      layout={{ ...figure.layout, autosize: true }}
      config={{ displayModeBar: true, responsive: true }}
      useResizeHandler
      className={className}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
