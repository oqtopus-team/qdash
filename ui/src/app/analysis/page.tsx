"use client";

import { useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { useListChips, useFetchChip } from "@/client/chip/chip";
import { TimeSeriesView } from "./components/TimeSeriesView";

interface ParameterValue {
  value: number;
  unit: string;
  description: string;
  updated: string;
}

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[500px]">
      <div className="loading loading-spinner loading-lg text-primary"></div>
    </div>
  ),
});

type AnalyzeView = "correlation" | "timeseries";

export default function AnalyzePage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [xAxis, setXAxis] = useState<string>("");
  const [yAxis, setYAxis] = useState<string>("");
  const [currentView, setCurrentView] = useState<AnalyzeView>("correlation");
  const { data: chipsResponse } = useListChips();
  const { data: chipResponse } = useFetchChip(selectedChip);

  const chips = useMemo(() => chipsResponse?.data ?? [], [chipsResponse]);
  const chipData = useMemo(() => chipResponse?.data, [chipResponse]);

  // Extract available parameters from qubit data
  const availableParameters = useMemo(() => {
    if (!chipData?.qubits) return [];
    const params = new Set<string>(["qid"]);

    Object.entries(chipData.qubits).forEach(([_, qubit]: [string, any]) => {
      if (qubit?.data) {
        Object.keys(qubit.data).forEach((param) => {
          if (param !== "qid") {
            params.add(param);
          }
        });
      }
    });

    return Array.from(params).sort();
  }, [chipData]);

  // Get parameter value for a qubit
  const getParameterValue = (qubit: any, param: string): ParameterValue => {
    if (param === "qid") {
      return {
        value: Number(qubit.qid),
        unit: "",
        description: "Qubit ID",
        updated: "",
      };
    }

    const paramData = qubit?.data?.[param];
    if (!paramData) {
      return {
        value: 0,
        unit: "",
        description: "",
        updated: "",
      };
    }
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
    if (!chipData?.qubits || !xAxis || !yAxis) return null;

    const data = Object.entries(chipData.qubits)
      .filter(([_, qubit]: [string, any]) => {
        if (xAxis === "qid" && yAxis === "qid") return true;
        if (xAxis === "qid") return qubit?.data && qubit.data[yAxis];
        if (yAxis === "qid") return qubit?.data && qubit.data[xAxis];
        return qubit?.data && qubit.data[xAxis] && qubit.data[yAxis];
      })
      .map(([qid, qubit]: [string, any]) => {
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
    <div
      className="w-full min-h-screen bg-base-100/50 px-6 py-8"
      style={{ width: "calc(100vw - 20rem)" }}
    >
      <div className="max-w-[1400px] mx-auto space-y-8">
        {/* Header Section */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">Chip Analysis</h1>
            <p className="text-base-content/70">
              Analyze and visualize chip parameters
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <label className="label font-medium">Selected Chip</label>
              <select
                className="select select-bordered w-64 rounded-lg"
                value={selectedChip}
                onChange={(e) => setSelectedChip(e.target.value)}
              >
                <option value="">Select a chip</option>
                {chips.map((chip) => (
                  <option key={chip.chip_id} value={chip.chip_id}>
                    {chip.chip_id}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* View Selection Tabs */}
        <div className="tabs tabs-boxed w-fit gap-2 p-2">
          <button
            className={`tab ${
              currentView === "correlation" ? "tab-active" : ""
            }`}
            onClick={() => setCurrentView("correlation")}
          >
            Correlation Plot
          </button>
          <button
            className={`tab ${
              currentView === "timeseries" ? "tab-active" : ""
            }`}
            onClick={() => setCurrentView("timeseries")}
          >
            Time Series
          </button>
        </div>

        {currentView === "correlation" && (
          <div className="grid grid-cols-3 gap-8">
            {/* Parameter Selection Card */}
            <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
              <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-5 h-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 3v18h18"></path>
                  <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
                </svg>
                Parameter Selection
              </h2>
              <div className="grid grid-cols-2 gap-12">
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

            {/* Plot Area */}
            <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
              <h2 className="text-2xl font-semibold mb-6 text-center flex items-center justify-center gap-2">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-6 h-6"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 3v18h18"></path>
                  <circle cx="15" cy="10" r="1"></circle>
                  <circle cx="12" cy="15" r="1"></circle>
                  <circle cx="8" cy="9" r="1"></circle>
                </svg>
                Parameter Correlation Plot
              </h2>
              <div
                className="w-full max-w-4xl mx-auto bg-base-200/50 rounded-xl p-4"
                style={{ height: "550px" }}
              >
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
                      marker:
                        plotData.length > 20
                          ? {
                              size: 10,
                              line: {
                                color: "white",
                                width: 1,
                              },
                              opacity: 0.8,
                            }
                          : {
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
                      autosize: true,
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
                      margin: { t: 10, r: 140, b: 40, l: 60 },
                      showlegend: true,
                      legend: {
                        orientation: "v",
                        yanchor: "top",
                        y: 1,
                        xanchor: "left",
                        x: 1.02,
                        bgcolor: "rgba(255,255,255,0.8)",
                        bordercolor: "rgba(0,0,0,0.1)",
                        borderwidth: 1,
                        itemsizing: "constant",
                        font: {
                          size: 10,
                        },
                      },
                    }}
                    config={{
                      displaylogo: false,
                      responsive: true,
                      toImageButtonOptions: {
                        format: "svg",
                        filename: "parameter_correlation",
                        height: 600,
                        width: 800,
                        scale: 2,
                      },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler={true}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-base-content/70">
                    <div className="text-center">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="w-12 h-12 mx-auto mb-4 opacity-50"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M3 3v18h18"></path>
                        <circle cx="15" cy="10" r="1"></circle>
                        <circle cx="12" cy="15" r="1"></circle>
                        <circle cx="8" cy="9" r="1"></circle>
                      </svg>
                      <p className="text-lg">
                        Select parameters to visualize data
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Statistics Summary */}
            {plotData && plotData.length > 0 && (
              <>
                <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
                  <h3 className="font-medium mb-4 flex items-center gap-2">
                    <span className="text-primary">X:</span> {xAxis} Statistics
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="stat bg-base-200 rounded-lg">
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
                    <div className="stat bg-base-200 rounded-lg">
                      <div className="stat-title">Min / Max</div>
                      <div className="stat-value text-lg flex items-center gap-2">
                        <span>
                          {Math.min(...plotData.map((d) => d.x)).toFixed(4)}
                        </span>
                        <span className="text-base-content/50">/</span>
                        <span>
                          {Math.max(...plotData.map((d) => d.x)).toFixed(4)}
                        </span>
                        {plotData[0].xUnit && (
                          <span className="text-sm ml-1">
                            {plotData[0].xUnit}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
                  <h3 className="font-medium mb-4 flex items-center gap-2">
                    <span className="text-secondary">Y:</span> {yAxis}{" "}
                    Statistics
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="stat bg-base-200 rounded-lg">
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
                    <div className="stat bg-base-200 rounded-lg">
                      <div className="stat-title">Min / Max</div>
                      <div className="stat-value text-lg flex items-center gap-2">
                        <span>
                          {Math.min(...plotData.map((d) => d.y)).toFixed(4)}
                        </span>
                        <span className="text-base-content/50">/</span>
                        <span>
                          {Math.max(...plotData.map((d) => d.y)).toFixed(4)}
                        </span>
                        {plotData[0].yUnit && (
                          <span className="text-sm ml-1">
                            {plotData[0].yUnit}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-base-300">
                  <h3 className="font-medium mb-4 flex items-center gap-2">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="w-4 h-4"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    Additional Information
                  </h3>
                  <div className="stats stats-vertical shadow w-full">
                    <div className="stat bg-base-200 rounded-lg">
                      <div className="stat-title">Total Points</div>
                      <div className="stat-value text-lg">
                        {plotData.length}
                      </div>
                      <div className="stat-desc mt-2">
                        <div className="badge badge-sm">
                          Data points plotted
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Data Table */}
            <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-semibold">Data Table</h2>
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
                        row.style.display = qid.includes(searchText)
                          ? ""
                          : "none";
                      }
                    });
                  }}
                />
              </div>
              {plotData && plotData.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="table table-compact table-zebra w-full border border-base-300 bg-base-100">
                    <thead>
                      <tr>
                        <th className="text-center bg-base-200">QID</th>
                        <th className="text-center bg-base-200">{xAxis}</th>
                        {xAxis !== "qid" && (
                          <th className="text-center bg-base-200">
                            Description (X)
                          </th>
                        )}
                        {xAxis !== "qid" && (
                          <th className="text-center bg-base-200">
                            Updated (X)
                          </th>
                        )}
                        <th className="text-center bg-base-200">{yAxis}</th>
                        {yAxis !== "qid" && (
                          <th className="text-center bg-base-200">
                            Description (Y)
                          </th>
                        )}
                        {yAxis !== "qid" && (
                          <th className="text-center bg-base-200">
                            Updated (Y)
                          </th>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {chipData?.qubits &&
                        Object.entries(chipData.qubits).map(([qid, _]) => {
                          const data = plotData.find((d) => d.qid === qid);
                          if (!data) return null;

                          return (
                            <tr key={data.qid}>
                              <td className="text-center font-medium">
                                {data.qid}
                              </td>
                              <td className="text-center">
                                {data.x.toFixed(4)} {data.xUnit}
                              </td>
                              {xAxis !== "qid" && (
                                <td className="text-center">
                                  {data.xDescription}
                                </td>
                              )}
                              {xAxis !== "qid" && (
                                <td className="text-center text-base-content/70">
                                  {data.xUpdated}
                                </td>
                              )}
                              <td className="text-center">
                                {data.y.toFixed(4)} {data.yUnit}
                              </td>
                              {yAxis !== "qid" && (
                                <td className="text-center">
                                  {data.yDescription}
                                </td>
                              )}
                              {yAxis !== "qid" && (
                                <td className="text-center text-base-content/70">
                                  {data.yUpdated}
                                </td>
                              )}
                            </tr>
                          );
                        })}
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
        )}

        {currentView === "timeseries" && <TimeSeriesView />}
      </div>
    </div>
  );
}
