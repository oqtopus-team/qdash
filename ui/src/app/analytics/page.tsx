"use client";

import { useListChips, useFetchChip } from "@/client/chip/chip";
import { useState, useMemo, Suspense } from "react";
import dynamic from "next/dynamic";
import { ChipResponse } from "@/schemas";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[600px]">
      <div className="loading loading-spinner loading-lg"></div>
    </div>
  ),
});

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

export default function AnalyticsPage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [xAxis, setXAxis] = useState<string>("");
  const [yAxis, setYAxis] = useState<string>("");
  const { data: chips } = useListChips();
  const { data: chipData } = useFetchChip(selectedChip);

  // Extract available parameters from qubit data
  const availableParameters = useMemo(() => {
    if (!chipData?.data?.qubits) return [];
    const params = new Set<string>();

    Object.values(chipData.data.qubits as ChipQubit).forEach((qubit) => {
      if (qubit.data) {
        Object.keys(qubit.data).forEach((param) => {
          params.add(param);
        });
      }
    });

    return Array.from(params).sort();
  }, [chipData]);

  // Prepare plot data
  const plotData = useMemo(() => {
    if (!chipData?.data?.qubits || !xAxis || !yAxis) return null;

    const data = Object.entries(chipData.data.qubits as ChipQubit)
      .filter(
        ([_, qubit]) => qubit.data && qubit.data[xAxis] && qubit.data[yAxis]
      )
      .map(([qid, qubit]) => {
        // Convert ns to μs for time parameters
        const xValue = qubit.data[xAxis].value;
        const yValue = qubit.data[yAxis].value;
        const xUnit = qubit.data[xAxis].unit;
        const yUnit = qubit.data[yAxis].unit;

        return {
          qid,
          x: xUnit === "ns" ? xValue / 1000 : xValue,
          xUnit: xUnit === "ns" ? "μs" : xUnit,
          xDescription: qubit.data[xAxis].description,
          xUpdated: new Date(qubit.data[xAxis].calibrated_at).toLocaleString(),
          y: yUnit === "ns" ? yValue / 1000 : yValue,
          yUnit: yUnit === "ns" ? "μs" : yUnit,
          yDescription: qubit.data[yAxis].description,
          yUpdated: new Date(qubit.data[yAxis].calibrated_at).toLocaleString(),
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
                      `Description (X): ${d.xDescription}<br>` +
                      `Description (Y): ${d.yDescription}<br>` +
                      `Updated: ${d.xUpdated}`,
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
                  margin: { t: 50, r: 50, b: 100, l: 50 },
                  showlegend: true,
                  legend: {
                    orientation: "h",
                    yanchor: "bottom",
                    y: -0.4,
                    xanchor: "center",
                    x: 0.5,
                  },
                }}
                config={{
                  responsive: true,
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
                      <th>Description (X)</th>
                      <th>Updated (X)</th>
                      <th>{yAxis}</th>
                      <th>Description (Y)</th>
                      <th>Updated (Y)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plotData.map((data) => (
                      <tr key={data.qid}>
                        <td>{data.qid}</td>
                        <td>
                          {data.x.toFixed(4)} {data.xUnit}
                        </td>
                        <td>{data.xDescription}</td>
                        <td>{data.xUpdated}</td>
                        <td>
                          {data.y.toFixed(4)} {data.yUnit}
                        </td>
                        <td>{data.yDescription}</td>
                        <td>{data.yUpdated}</td>
                      </tr>
                    ))}
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
