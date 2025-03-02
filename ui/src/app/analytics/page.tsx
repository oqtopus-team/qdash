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
    <div className="w-full px-4 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-4">Chip Analytics</h1>

          {/* Chip Selection */}
          <select
            className="select select-bordered w-full max-w-xs rounded-lg mb-4"
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

          {/* Parameter Selection */}
          <div className="flex gap-4 mb-4">
            <div className="form-control">
              <label className="label">X軸パラメータ</label>
              <select
                className="select select-bordered"
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
            </div>
            <div className="form-control">
              <label className="label">Y軸パラメータ</label>
              <select
                className="select select-bordered"
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
            </div>
          </div>

          {/* Plot Area */}
          {plotData && plotData.length > 0 && (
            <div
              className="card bg-base-100 shadow-lg rounded-xl p-4"
              style={{
                minHeight: "650px",
                width: "100%",
                height: "100%",
              }}
            >
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
                  title: {
                    text: "Parameter Correlation Plot",
                    font: {
                      size: 24,
                    },
                  },
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
                  margin: { t: 50, r: 50, b: 150, l: 50 },
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
            </div>
          )}

          {/* Data Table */}
          {plotData && plotData.length > 0 && (
            <div className="card bg-base-100 shadow-lg rounded-xl p-4 mt-4">
              <h2 className="text-xl font-bold mb-4">Data Table</h2>
              <div className="overflow-x-auto">
                <table className="table table-zebra w-full">
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
