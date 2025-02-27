"use client";

import { useEffect, useState } from "react";
import {
  mapOneQubitCalibResponseToOneQubitCalibration,
  mapTwoQubitCalibResponseToTwoQubitCalibration,
} from "../../model";
import { Legend } from "./Legend";
import type { OneQubitCalib, TwoQubitCalib } from "../../model";
import {
  useFetchAllLatestOneQubitCalib,
  useFetchAllLatestTwoQubitCalib,
} from "@/client/calibration/calibration";
import { LoadingSpinner } from "@/app/components/LoadingSpinner";
import { ChipMetricsGraph } from "./ChipMetricsGraph";
import "color-legend-element";

const getNodeColor = (metricValue: number | string, selectedMetric: string) => {
  const colorPalettes = {
    status: {
      success: { color: "green" },
      running: { color: "blue" },
      failed: { color: "red" },
      scheduled: { color: "orange" },
    },
    qubit_freq_cw: [
      { threshold: 7750, color: "#2a4858" },
      { threshold: 8020, color: "#106e7c" },
      { threshold: 8290, color: "#00968e" },
      { threshold: 8560, color: "#4abd8c" },
      { threshold: 8830, color: "#9cdf7c" },
      { threshold: 9100, color: "#fafa6e" },
    ],
  };
  const colorPalette =
    colorPalettes[selectedMetric as keyof typeof colorPalettes];
  if (selectedMetric === "status" && typeof metricValue === "string") {
    return (
      (colorPalette as { [key: string]: { color: string } })[metricValue]
        ?.color || ""
    );
  } else if (
    selectedMetric === "qubit_freq_cw" &&
    typeof metricValue === "number"
  ) {
    const sortedPalette = (
      colorPalette as { threshold: number; color: string }[]
    ).sort((a, b) => b.threshold - a.threshold);
    for (const palette of sortedPalette) {
      if (metricValue >= palette.threshold) {
        return palette.color;
      }
    }
  }
  return "";
};

const updateNodesWithMetricColor = (
  nodes: OneQubitCalib[],
  selectedMetric: string,
) => {
  return nodes.map((node) => {
    let metricValue;
    switch (selectedMetric) {
      case "status":
        metricValue = node.data.status;
        break;
      case "qubit_freq_cw":
        metricValue =
          node.data.one_qubit_calib_data?.qubit_frequency?.value ?? null;
        break;
      default:
        metricValue = null;
    }
    node.fill = getNodeColor(metricValue?.toString() || "", selectedMetric);
    return node;
  });
};

const updateEdgesWithMetricColor = (
  edges: TwoQubitCalib[],
  selectedMetric: string,
) => {
  return edges.map((edge) => {
    let metricValue;
    switch (selectedMetric) {
      case "status":
        metricValue = edge.data.status;
        break;
      default:
        metricValue = null;
    }
    edge.fill = getNodeColor(metricValue?.toString() || "", selectedMetric);
    return edge;
  });
};

export function ChipMetricsClient() {
  const [selectedMetric, setSelectedMetric] = useState<string>("status");
  const [oneQubitCalibInfo, setOneQubitCalibInfo] = useState<OneQubitCalib[]>(
    [],
  );
  const [twoQubitCalibInfo, setTwoQubitCalibInfo] = useState<TwoQubitCalib[]>(
    [],
  );
  const [hoveredNode, setHoveredNode] = useState<any>(null);
  const [hoveredEdge, setHoveredEdge] = useState<any>(null);

  const {
    data: oneQubitCalib,
    isError: isOneQubitCalibError,
    isLoading: isOneQubitCalibLoading,
    refetch: refetchOneQubitCalib,
  } = useFetchAllLatestOneQubitCalib();
  const {
    data: twoQubitCalib,
    isError: isTwoQubitCalibError,
    isLoading: isTwoQubitCalibLoading,
    refetch: refetchTwoQubitCalib,
  } = useFetchAllLatestTwoQubitCalib();

  useEffect(() => {
    if (oneQubitCalib) {
      const updatedNodes = updateNodesWithMetricColor(
        mapOneQubitCalibResponseToOneQubitCalibration(oneQubitCalib.data),
        selectedMetric,
      );
      setOneQubitCalibInfo(updatedNodes);
    }

    if (twoQubitCalib) {
      const updatedEdges = updateEdgesWithMetricColor(
        mapTwoQubitCalibResponseToTwoQubitCalibration(twoQubitCalib.data),
        selectedMetric,
      );
      setTwoQubitCalibInfo(updatedEdges);
    }
  }, [oneQubitCalib, twoQubitCalib, selectedMetric]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      refetchOneQubitCalib();
      refetchTwoQubitCalib();
    }, 5000);

    return () => clearInterval(intervalId);
  }, [refetchOneQubitCalib, refetchTwoQubitCalib]);

  const handleNodePointerOver = (node: any) => {
    setHoveredNode(node);
    setHoveredEdge(null);
  };

  const handleEdgePointerOver = (edge: any) => {
    setHoveredEdge(edge);
    setHoveredNode(null);
  };

  if (isOneQubitCalibLoading || isTwoQubitCalibLoading) {
    return <LoadingSpinner />;
  }

  if (isOneQubitCalibError || isTwoQubitCalibError) {
    return <div>Error loading calibration data</div>;
  }

  return (
    <div className="h-full relative">
      <div className="flex justify-between">
        <h2 className="text-left text-3xl font-bold my-4">Chip Metrics</h2>
      </div>
      <div className="flex justify-between items-center my-4">
        <Legend selectedMetric={selectedMetric} />
        <select
          className="select select-bordered w-full max-w-xs"
          value={selectedMetric}
          onChange={(e) => setSelectedMetric(e.target.value)}
        >
          <option value="status">Status</option>
          <option value="qubit_freq_cw">Qubit Frequency</option>
        </select>
      </div>
      <div className="h-5/6 relative flex">
        <div className="w-1/2 h-full">
          <div className="card bg-base-200 w-full h-full">
            <div className="card-body h-full w-full overflow-y-auto text-left">
              <h3 className="font-bold text-xl mb-4">Qubit Property</h3>
              {hoveredNode ? (
                <div className="mb-4 p-4 bg-base-100 rounded-lg shadow-md h-80">
                  <h4 className="font-bold text-lg text-primary">
                    {hoveredNode.label}
                  </h4>
                  <p className="py-2 text-base-content/70">
                    Status: {hoveredNode.status}
                  </p>
                  <p className="py-2 text-base-content/70">
                    Qubit Frequency:{" "}
                    {hoveredNode.one_qubit_calib_data?.qubit_frequency?.value ??
                      null}
                  </p>
                  <p className="py-2 text-base-content/70">
                    T1: {hoveredNode.one_qubit_calib_data?.t1?.value ?? null}
                  </p>
                  <p className="py-2 text-base-content/70">
                    Average Gate Fidelity:{" "}
                    {hoveredNode.one_qubit_calib_data?.average_gate_fidelity
                      ?.value ?? null}
                  </p>
                </div>
              ) : hoveredEdge ? (
                <div className="mb-4 p-4 bg-base-100 rounded-lg shadow-md h-80">
                  <h4 className="font-bold text-lg text-primary">
                    {hoveredEdge.label}
                  </h4>
                  <p className="py-2 text-base-content/70">
                    Status: {hoveredEdge.status}
                  </p>
                  <p className="py-2 text-base-content/70">
                    Average Gate Fidelity:{" "}
                    {hoveredEdge.two_qubit_calib_data?.average_gate_fidelity
                      ?.value ?? null}
                  </p>
                </div>
              ) : (
                <div className="mb-4 p-4 bg-base-100 rounded-lg shadow-md h-80">
                  <h4 className="font-bold text-lg text-primary">Qubit N/A</h4>
                  <p className="py-2 text-base-content/70">Status: N/A</p>
                  <p className="py-2 text-base-content/70">
                    Qubit Frequency: N/A
                  </p>
                  <p className="py-2 text-base-content/70">T1: N/A</p>
                  <p className="py-2 text-base-content/70">
                    Readout Accuracy: N/A
                  </p>
                  <p className="py-2 text-base-content/70">
                    Average Gate Fidelity: N/A
                  </p>
                  <p className="py-2 text-base-content/70">
                    Average Gate Fidelity DRAG: N/A
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="w-1/2 h-full">
          <div className="card bg-base-200 w-full h-full">
            <ChipMetricsGraph
              oneQubitCalibInfo={oneQubitCalibInfo}
              twoQubitCalibInfo={twoQubitCalibInfo}
              onNodePointerOver={handleNodePointerOver}
              onEdgePointerOver={handleEdgePointerOver}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
