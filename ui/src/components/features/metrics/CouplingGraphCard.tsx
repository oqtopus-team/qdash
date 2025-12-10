"use client";

import dynamic from "next/dynamic";
import React, { useMemo } from "react";

import { useGetChipMetrics } from "@/client/metrics/metrics";

const Plot = dynamic(() => import("@/components/charts/Plot"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[600px]">
      <div className="loading loading-spinner loading-lg"></div>
    </div>
  ),
});

type TimeRange = "current" | "24h" | "48h" | "72h";

interface CouplingGraphCardProps {
  chipId: string;
  metricKey: string;
  title: string;
  unit: string;
  colorscale: string;
  timeRange: TimeRange;
  scale?: number;
}

// 64-qubit chip layout: 8x8 grid
const GRID_SIZE = 8;
const NODE_SIZE = 24;

// Calculate node positions in an 8x8 grid
function getNodePosition(qid: number): { x: number; y: number } {
  const row = Math.floor(qid / GRID_SIZE);
  const col = qid % GRID_SIZE;
  return {
    x: col * NODE_SIZE * 3,
    y: row * NODE_SIZE * 3,
  };
}

export function CouplingGraphCard({
  chipId,
  metricKey,
  title,
  unit,
  colorscale,
  timeRange,
  scale = 1,
}: CouplingGraphCardProps) {
  // Fetch metrics data
  const withinHours = timeRange === "current" ? undefined : parseInt(timeRange);
  const { data, isLoading, isError } = useGetChipMetrics(
    chipId,
    withinHours ? { within_hours: withinHours } : undefined,
    {
      query: {
        enabled: !!chipId,
        staleTime: 30000,
      },
    },
  );

  // Extract coupling data
  const couplingData = useMemo(() => {
    if (!data?.data?.coupling_metrics) return null;

    const rawData =
      data.data.coupling_metrics[
        metricKey as keyof typeof data.data.coupling_metrics
      ];

    if (!rawData) return null;

    // Apply scale
    const scaledData: { [key: string]: number | null } = {};
    Object.entries(rawData).forEach(([key, value]) => {
      scaledData[key] =
        value !== null && value !== undefined && typeof value === "number"
          ? value * scale
          : null;
    });

    return scaledData;
  }, [data, metricKey, scale]);

  // Create graph traces
  const plotData = useMemo(() => {
    if (!couplingData) return null;

    // Node positions
    const nodeX: number[] = [];
    const nodeY: number[] = [];
    const nodeText: string[] = [];
    const nodeHovertext: string[] = [];

    for (let i = 0; i < 64; i++) {
      const pos = getNodePosition(i);
      nodeX.push(pos.x);
      nodeY.push(pos.y);
      nodeText.push(String(i));
      nodeHovertext.push(`Q${String(i).padStart(2, "0")}`);
    }

    // Edge traces - one for each edge with color based on value
    const edgeTraces: any[] = [];
    const edgeValues: number[] = [];
    const edgeTexts: string[] = [];
    const edgeHoverTexts: string[] = [];

    Object.entries(couplingData).forEach(([couplingId, value]) => {
      const [q1Str, q2Str] = couplingId.split("-");
      const q1 = parseInt(q1Str);
      const q2 = parseInt(q2Str);

      if (value === null || value === undefined || isNaN(q1) || isNaN(q2))
        return;

      const pos1 = getNodePosition(q1);
      const pos2 = getNodePosition(q2);

      edgeValues.push(value);
      edgeTexts.push(value.toFixed(1));
      edgeHoverTexts.push(`${couplingId}: ${value.toFixed(2)} ${unit}`);

      edgeTraces.push({
        type: "scatter",
        mode: "lines+text",
        x: [pos1.x, pos2.x, null],
        y: [pos1.y, pos2.y, null],
        line: {
          color: value,
          width: 3,
          colorscale: colorscale,
          cmin: Math.min(...edgeValues),
          cmax: Math.max(...edgeValues),
        },
        hoverinfo: "text",
        hovertext: edgeHoverTexts[edgeHoverTexts.length - 1],
        showlegend: false,
        text: ["", edgeTexts[edgeTexts.length - 1], ""],
        textposition: "middle center",
        textfont: {
          size: 10,
          color: "white",
        },
      });
    });

    // Node trace (circles representing qubits)
    const nodeTrace = {
      type: "scatter",
      mode: "markers+text",
      x: nodeX,
      y: nodeY,
      text: nodeText,
      hovertext: nodeHovertext,
      hoverinfo: "text",
      marker: {
        size: 20,
        color: "lightgray",
        line: {
          color: "black",
          width: 2,
        },
      },
      textfont: {
        size: 10,
        weight: "bold",
      },
      showlegend: false,
    };

    return [...edgeTraces, nodeTrace];
  }, [couplingData, colorscale, unit]);

  if (isLoading) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h3 className="card-title">{title}</h3>
          <div className="flex items-center justify-center h-[600px]">
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        </div>
      </div>
    );
  }

  if (isError || !couplingData || !plotData) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h3 className="card-title">{title}</h3>
          <div className="alert alert-error">
            <span>Failed to load coupling data</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body">
        <h3 className="card-title text-lg">{title}</h3>
        <Plot
          data={plotData}
          layout={{
            width: GRID_SIZE * NODE_SIZE * 3,
            height: GRID_SIZE * NODE_SIZE * 3,
            margin: { t: 30, r: 30, b: 30, l: 30 },
            xaxis: {
              ticks: "",
              showgrid: false,
              zeroline: false,
              showticklabels: false,
              constrain: "domain",
            },
            yaxis: {
              ticks: "",
              autorange: "reversed",
              showgrid: false,
              zeroline: false,
              showticklabels: false,
              scaleanchor: "x",
            },
            plot_bgcolor: "white",
            paper_bgcolor: "rgba(0,0,0,0)",
            showlegend: false,
            hovermode: "closest",
          }}
          config={{
            displaylogo: false,
            responsive: true,
          }}
          style={{ width: "100%", height: "600px" }}
        />
        <div className="stats shadow mt-2">
          <div className="stat">
            <div className="stat-title">Total Couplings</div>
            <div className="stat-value text-2xl">
              {Object.keys(couplingData).length}
            </div>
          </div>
          <div className="stat">
            <div className="stat-title">Avg {title}</div>
            <div className="stat-value text-2xl">
              {(
                Object.values(couplingData).reduce(
                  (sum: number, val) => sum + (val || 0),
                  0,
                ) / Object.keys(couplingData).length
              ).toFixed(1)}
              {unit}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
