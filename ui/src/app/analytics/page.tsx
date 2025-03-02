"use client";

import { useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface QubitParameter {
  value: number;
  unit: string;
  description: string;
  calibrated_at: string;
  execution_id: string;
}

interface QubitData {
  qid: string;
  status: string;
  data: {
    [key: string]: QubitParameter;
  };
  node_info: {
    position: {
      x: number;
      y: number;
    };
  };
}

interface ChipQubit {
  [qid: string]: QubitData;
}

interface ChipData {
  data: {
    qubits: ChipQubit;
  };
}

interface Chip {
  chip_id: string;
}

interface ChipsResponse {
  data: Chip[];
}

interface ParameterValue {
  value: number;
  unit: string;
  description: string;
  updated: string;
}

const useListChips = () => {
  return useQuery<ChipsResponse>({
    queryKey: ["chips"],
    queryFn: async () => {
      const { data } = await axios.get("/api/chips");
      return data;
    },
  });
};

const useFetchChip = (chipId: string) => {
  return useQuery<ChipData>({
    queryKey: ["chip", chipId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/chips/${chipId}`);
      return data;
    },
    enabled: !!chipId,
  });
};

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[600px]">
      <div className="loading loading-spinner loading-lg"></div>
    </div>
  ),
});

export default function AnalyticsPage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [xAxis, setXAxis] = useState<string>("");
  const [yAxis, setYAxis] = useState<string>("");
  const { data: chips } = useListChips();
  const { data: chipData } = useFetchChip(selectedChip);

  // Extract available parameters from qubit data
  const availableParameters = useMemo(() => {
    if (!chipData?.data?.qubits) return [];
    const params = new Set<string>(["qid"]);

    Object.values(chipData.data.qubits as ChipQubit).forEach((qubit) => {
      if (qubit.data) {
        Object.keys(qubit.data).forEach((param) => {
          params.add(param);
        });
      }
    });

    return Array.from(params).sort();
  }, [chipData]);

  // Get parameter value for a qubit
  const getParameterValue = (
    qubit: QubitData,
    param: string
  ): ParameterValue => {
    if (param === "qid") {
      return {
        value: Number(qubit.qid),
        unit: "",
        description: "Qubit ID",
        updated: "",
      };
    }

    const paramData = qubit.data[param];
    const value = paramData.value;
    const unit = paramData.unit === "ns" ? "μs" : paramData.unit;

    return {
      value: paramData.unit === "ns" ? value / 1000 : value,
      unit,
      description: paramData.description,
      updated: new Date(paramData.calibrated_at).toLocaleString(),
    };
  };

  // Prepare plot data
  const plotData = useMemo(() => {
    if (!chipData?.data?.qubits || !xAxis || !yAxis) return null;

    const data = Object.entries(chipData.data.qubits as ChipQubit)
      .filter(([_, qubit]) => {
        if (xAxis === "qid" && yAxis === "qid") return true;
        if (xAxis === "qid") return qubit.data && qubit.data[yAxis];
        if (yAxis === "qid") return qubit.data && qubit.data[xAxis];
        return qubit.data && qubit.data[xAxis] && qubit.data[yAxis];
      })
      .map(([qid, qubit]) => {
        const xData = getParameterValue(qubit, xAxis);
        const yData = getParameterValue(qubit, yAxis);

        return {
          qid,
          x: xData.value,
          xUnit: xData.unit,
          xDescription: xData.description,
          xUpdated: xData.updated,
          y: yData.value,
          yUnit: yData.unit,
          yDescription: yData.description,
          yUpdated: yData.updated,
        };
      });

    return data;
  }, [chipData, xAxis, yAxis]);

  return (
    <div className="w-full px-6 py-8" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-8">
        {/* Header Section */}
        <div className="flex justify-between items-center">
          <h1 className="text-3xl font-bold">Chip Analytics</h1>
          <select
            className="select select-bordered w-64 rounded-lg"
            value={selectedChip}
            onChange={(e) => setSelectedChip(e.target.value)}
          >
            <option value="">Select a chip</option>
            {chips?.data.map((chip) => (
              <option key={chip.chip_id} value={chip.chip_id}>
                {chip.chip_id}
              </option>
            ))}
          </select>
        </div>

        {/* Parameter Selection Card */}
        <div className="card bg-base-100 shadow-lg rounded-xl p-6">
          <h2 className="text-xl font-semibold mb-4">Parameter Selection</h2>
          <div className="grid grid-cols-2 gap-8">
            <div className="form-control">
              <label className="label font-medium">X-Axis Parameter</label>
              <select
                className="select select-bordered w-full"
                value={xAxis}
                onChange={(e) => setXAxis(e.target.value)}
              >
                <option value="">Select parameter</option>
                {availableParameters.map((param) => (
                  <option key={param} value={param}>
                    {param}
                  </option>
                ))}
              </select>
              {xAxis && plotData && plotData[0]?.xDescription && (
                <label className="label">
                  <span className="label-text-alt text-base-content/70">
                    {plotData[0].xDescription}
                  </span>
                </label>
              )}
            </div>
            <div className="form-control">
              <label className="label font-medium">Y-Axis Parameter</label>
              <select
                className="select select-bordered w-full"
                value={yAxis}
                onChange={(e) => setYAxis(e.target.value)}
              >
                <option value="">Select parameter</option>
                {availableParameters.map((param) => (
                  <option key={param} value={param}>
                    {param}
                  </option>
                ))}
              </select>
              {yAxis && plotData && plotData[0]?.yDescription && (
                <label className="label">
                  <span className="label-text-alt text-base-content/70">
                    {plotData[0].yDescription}
                  </span>
                </label>
              )}
            </div>
          </div>
        </div>

        {/* Statistics Summary */}
        {plotData && plotData.length > 0 && (
          <div className="card bg-base-100 shadow-lg rounded-xl p-6">
            <h2 className="text-xl font-semibold mb-4">Statistics Summary</h2>
            <div className="grid grid-cols-2 gap-8">
              <div>
                <h3 className="font-medium mb-2">{xAxis} Statistics</h3>
                <div className="stats stats-vertical shadow">
                  <div className="stat">
                    <div className="stat-title">Mean</div>
                    <div className="stat-value text-lg">
                      {(
                        plotData.reduce((acc, d) => acc + d.x, 0) /
                        plotData.length
                      ).toFixed(4)}
                      {plotData[0].xUnit && (
                        <span className="text-sm ml-1">
                          {plotData[0].xUnit}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="stat">
                    <div className="stat-title">Range</div>
                    <div className="stat-value text-lg">
                      {(
                        Math.max(...plotData.map((d) => d.x)) -
                        Math.min(...plotData.map((d) => d.x))
                      ).toFixed(4)}
                      {plotData[0].xUnit && (
                        <span className="text-sm ml-1">
                          {plotData[0].xUnit}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              <div>
                <h3 className="font-medium mb-2">{yAxis} Statistics</h3>
                <div className="stats stats-vertical shadow">
                  <div className="stat">
                    <div className="stat-title">Mean</div>
                    <div className="stat-value text-lg">
                      {(
                        plotData.reduce((acc, d) => acc + d.y, 0) /
                        plotData.length
                      ).toFixed(4)}
                      {plotData[0].yUnit && (
                        <span className="text-sm ml-1">
                          {plotData[0].yUnit}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="stat">
                    <div className="stat-title">Range</div>
                    <div className="stat-value text-lg">
                      {(
                        Math.max(...plotData.map((d) => d.y)) -
                        Math.min(...plotData.map((d) => d.y))
                      ).toFixed(4)}
                      {plotData[0].yUnit && (
                        <span className="text-sm ml-1">
                          {plotData[0].yUnit}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Plot Area */}
        <div className="card bg-base-100 shadow-lg rounded-xl p-6">
          <h2 className="text-xl font-semibold mb-4">
            Parameter Correlation Plot
          </h2>
          <div className="w-full" style={{ height: "600px" }}>
            {plotData && plotData.length > 0 ? (
              <Plot
                data={plotData.map((d) => ({
                  x: [d.x],
                  y: [d.y],
                  text: [d.qid],
                  textposition: "top center",
                  textfont: { size: 10 },
                  mode: "text+markers",
                  type: "scatter",
                  name: `QID: ${d.qid}`,
                  marker: {
                    size: 12,
                    line: {
                      color: "white",
                      width: 1,
                    },
                  },
                  hoverinfo: "text",
                  hovertext: [
                    `QID: ${d.qid}<br>` +
                      `${xAxis}: ${d.x.toFixed(4)} ${d.xUnit}<br>` +
                      `${yAxis}: ${d.y.toFixed(4)} ${d.yUnit}<br>` +
                      (d.xDescription
                        ? `Description (X): ${d.xDescription}<br>`
                        : "") +
                      (d.yDescription
                        ? `Description (Y): ${d.yDescription}<br>`
                        : "") +
                      (d.xUpdated ? `Updated (X): ${d.xUpdated}<br>` : "") +
                      (d.yUpdated ? `Updated (Y): ${d.yUpdated}` : ""),
                  ],
                }))}
                layout={{
                  title: "",
                  xaxis: {
                    title: {
                      text: `${xAxis} ${
                        plotData[0]?.xUnit ? `(${plotData[0].xUnit})` : ""
                      }`,
                      font: {
                        size: 14,
                      },
                    },
                    autorange: true,
                    rangemode: "normal",
                    type: "linear",
                    gridcolor: "rgba(128, 128, 128, 0.2)",
                    zerolinecolor: "rgba(128, 128, 128, 0.2)",
                    showgrid: true,
                    zeroline: true,
                    showline: true,
                    exponentformat: "e",
                  },
                  yaxis: {
                    title: {
                      text: `${yAxis} ${
                        plotData[0]?.yUnit ? `(${plotData[0].yUnit})` : ""
                      }`,
                      font: {
                        size: 14,
                      },
                    },
                    autorange: true,
                    rangemode: "normal",
                    type: "linear",
                    gridcolor: "rgba(128, 128, 128, 0.2)",
                    zerolinecolor: "rgba(128, 128, 128, 0.2)",
                    showgrid: true,
                    zeroline: true,
                    showline: true,
                    exponentformat: "e",
                  },
                  plot_bgcolor: "rgba(0,0,0,0)",
                  paper_bgcolor: "rgba(0,0,0,0)",
                  hovermode: "closest",
                  margin: { t: 20, r: 50, b: 150, l: 50 },
                  showlegend: true,
                  legend: {
                    orientation: "h",
                    yanchor: "bottom",
                    y: -0.6,
                    xanchor: "center",
                    x: 0.5,
                  },
                }}
                config={{
                  displaylogo: false,
                  toImageButtonOptions: {
                    format: "svg",
                    filename: "parameter_correlation",
                    height: 600,
                    width: 800,
                    scale: 2,
                  },
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-base-content/50">
                Select parameters to visualize data
              </div>
            )}
          </div>
        </div>

        {/* Data Table */}
        <div className="card bg-base-100 shadow-lg rounded-xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">Data Table</h2>
            <input
              type="text"
              placeholder="Filter by QID..."
              className="input input-bordered w-64"
              onChange={(e) => {
                const table = document.querySelector("table");
                const searchText = e.target.value.toLowerCase();

                table?.querySelectorAll("tbody tr").forEach((row) => {
                  const qid = row
                    .querySelector("td")
                    ?.textContent?.toLowerCase();
                  if (qid && row instanceof HTMLElement) {
                    row.style.display = qid.includes(searchText) ? "" : "none";
                  }
                });
              }}
            />
          </div>
          {plotData && plotData.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="table table-compact table-zebra w-full">
                <thead>
                  <tr>
                    <th>QID</th>
                    <th>{xAxis}</th>
                    {xAxis !== "qid" && <th>Description (X)</th>}
                    {xAxis !== "qid" && <th>Updated (X)</th>}
                    <th>{yAxis}</th>
                    {yAxis !== "qid" && <th>Description (Y)</th>}
                    {yAxis !== "qid" && <th>Updated (Y)</th>}
                  </tr>
                </thead>
                <tbody>
                  {chipData?.data?.qubits &&
                    Object.entries(chipData.data.qubits as ChipQubit).map(
                      ([qid, _]) => {
                        const data = plotData.find((d) => d.qid === qid);
                        if (!data) return null;

                        return (
                          <tr key={data.qid}>
                            <td>{data.qid}</td>
                            <td>
                              {data.x.toFixed(4)} {data.xUnit}
                            </td>
                            {xAxis !== "qid" && <td>{data.xDescription}</td>}
                            {xAxis !== "qid" && <td>{data.xUpdated}</td>}
                            <td>
                              {data.y.toFixed(4)} {data.yUnit}
                            </td>
                            {yAxis !== "qid" && <td>{data.yDescription}</td>}
                            {yAxis !== "qid" && <td>{data.yUpdated}</td>}
                          </tr>
                        );
                      }
                    )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-base-content/50">
              Select parameters to view data table
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
