"use client";

import dynamic from "next/dynamic";
import React, { useMemo } from "react";

import { useGetChipMetrics } from "@/client/metrics/metrics";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";

const Plot = dynamic(() => import("@/components/charts/Plot"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[500px]">
      <div className="loading loading-spinner loading-lg"></div>
    </div>
  ),
});

type TimeRange = "current" | "24h" | "48h" | "72h";

interface MetricCardProps {
  chipId: string;
  topologyId: string;
  metricKey: string;
  title: string;
  unit: string;
  colorscale: string;
  timeRange: TimeRange;
  scale?: number;
  isCoupling?: boolean;
}

export function MetricCard({
  chipId,
  topologyId,
  metricKey,
  title,
  unit,
  colorscale,
  timeRange,
  scale = 1,
  isCoupling = false,
}: MetricCardProps) {
  // Get topology configuration
  const {
    muxSize = 2,
    hasMux = false,
    layoutType = "grid",
  } = useTopologyConfig(topologyId) ?? {};

  // Fetch metrics data
  const withinHours = timeRange === "current" ? undefined : parseInt(timeRange);
  const { data, isLoading, isError } = useGetChipMetrics(
    chipId,
    withinHours ? { within_hours: withinHours } : undefined,
    {
      query: {
        enabled: !!chipId,
        staleTime: 30000, // 30 seconds
      },
    },
  );

  // Extract metric data
  const metricData = useMemo(() => {
    if (!data?.data) return null;

    const metricsSource = isCoupling
      ? data.data.coupling_metrics
      : data.data.qubit_metrics;

    const rawData = metricsSource?.[metricKey as keyof typeof metricsSource];

    if (!rawData) return null;

    // Apply scale and convert to appropriate format
    // Use simple numeric format (e.g., "0", "1")
    const scaledData: { [key: string]: number | null } = {};
    Object.entries(rawData).forEach(([key, value]) => {
      const qid = key.startsWith("Q")
        ? String(parseInt(key.slice(1), 10))
        : String(parseInt(key, 10));
      scaledData[qid] =
        value !== null && value !== undefined && typeof value === "number"
          ? value * scale
          : null;
    });

    return scaledData;
  }, [data, metricKey, isCoupling, scale]);

  // Create heatmap data for qubit metrics
  const heatmapData = useMemo(() => {
    if (!metricData || isCoupling) return null;

    // Calculate grid size from the number of qubits
    const numQubits = Object.keys(metricData).length;
    const gridSize = Math.ceil(Math.sqrt(numQubits));

    // Layout params for grid position calculations
    const layoutParams: TopologyLayoutParams = {
      muxEnabled: hasMux,
      muxSize,
      gridSize,
      layoutType,
    };

    // Create a position-to-qubit map based on topology layout
    const positionMap: Map<string, string> = new Map();
    Object.keys(metricData).forEach((qid) => {
      const qidNum = parseInt(qid.replace(/\D/g, ""));
      const pos = getQubitGridPosition(qidNum, layoutParams);
      positionMap.set(`${pos.row}-${pos.col}`, qid);
    });

    const values: (number | null)[][] = [];
    const texts: string[][] = [];
    const hovertexts: string[][] = [];

    for (let row = 0; row < gridSize; row++) {
      const rowValues: (number | null)[] = [];
      const rowTexts: string[] = [];
      const rowHovertexts: string[] = [];

      for (let col = 0; col < gridSize; col++) {
        const qid = positionMap.get(`${row}-${col}`);
        const value = qid ? metricData[qid] : null;

        rowValues.push(value);
        rowTexts.push(
          value !== null && value !== undefined && qid
            ? `${qid}\n${value.toFixed(metricKey.includes("fidelity") ? 1 : 2)}\n${unit}`
            : "N/A",
        );
        rowHovertexts.push(
          value !== null && value !== undefined && qid
            ? `${qid}: ${value.toFixed(3)} ${unit}`
            : qid
              ? `${qid}: N/A`
              : "N/A",
        );
      }

      values.push(rowValues);
      texts.push(rowTexts);
      hovertexts.push(rowHovertexts);
    }

    return { values, texts, hovertexts };
  }, [metricData, isCoupling, unit, metricKey, hasMux, muxSize, layoutType]);

  if (isLoading) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h3 className="card-title">{title}</h3>
          <div className="flex items-center justify-center h-[500px]">
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        </div>
      </div>
    );
  }

  if (isError || !metricData) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h3 className="card-title">{title}</h3>
          <div className="alert alert-error">
            <span>Failed to load metric data</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body">
        <h3 className="card-title text-lg">{title}</h3>
        {isCoupling ? (
          <div className="text-sm text-base-content/60 py-4">
            Coupling graph visualization coming soon...
            <div className="stats shadow mt-4">
              <div className="stat">
                <div className="stat-title">Total Couplings</div>
                <div className="stat-value text-2xl">
                  {Object.keys(metricData).length}
                </div>
              </div>
            </div>
          </div>
        ) : heatmapData ? (
          <Plot
            data={[
              {
                type: "heatmap",
                z: heatmapData.values,
                text: heatmapData.texts as any,
                hovertext: heatmapData.hovertexts as any,
                hoverinfo: "text",
                colorscale: colorscale,
                showscale: true,
                texttemplate: "%{text}",
                textfont: {
                  family: "monospace",
                  size: 11,
                },
              },
            ]}
            layout={{
              margin: { t: 30, r: 60, b: 30, l: 30 },
              xaxis: {
                ticks: "",
                showgrid: false,
                zeroline: false,
                showticklabels: false,
              },
              yaxis: {
                ticks: "",
                autorange: "reversed",
                showgrid: false,
                zeroline: false,
                showticklabels: false,
              },
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: "rgba(0,0,0,0)",
            }}
            config={{
              displaylogo: false,
              responsive: true,
            }}
            style={{ width: "100%", height: "500px" }}
          />
        ) : (
          <div className="alert alert-info">
            <span>No data available</span>
          </div>
        )}
      </div>
    </div>
  );
}
