"use client";

import { useQuery } from "@tanstack/react-query";

import Plot from "@/components/charts/Plot";

export function PlotlyRenderer({
  fullPath,
  className = "",
}: {
  fullPath: string;
  className?: string;
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
        data={figure.data}
        layout={{
          ...figure.layout,
          autosize: false,
          // Preserve original width/height from the figure JSON
        }}
        config={{ displayModeBar: true, responsive: false }}
        useResizeHandler={false}
        style={{ width: "auto", height: "auto" }}
      />
    </div>
  );
}
