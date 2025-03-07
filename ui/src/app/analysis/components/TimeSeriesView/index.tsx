"use client";

import { useFetchAllParameters } from "@/client/parameter/parameter";
import { useListAllTag } from "@/client/tag/tag";
import { useFetchTimeseriesTaskResultByTagAndParameter } from "@/client/chip/chip";
import { useMemo, useState, useEffect } from "react";
import { DataModel } from "@/schemas/dataModel";
import { TimeSeriesData } from "@/schemas/timeSeriesData";
import { TimeSeriesDataData } from "@/schemas/timeSeriesDataData";
import { ParameterModel } from "@/schemas/parameterModel";
import { Tag } from "@/schemas/tag";
import dynamic from "next/dynamic";
import { Layout } from "plotly.js";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <div>Loading Plot...</div>,
});

interface ExtendedDataModel extends DataModel {
  output_parameters?: { [key: string]: any };
}

export function TimeSeriesView() {
  const [selectedParameter, setSelectedParameter] = useState<string>("");
  const [selectedTag, setSelectedTag] = useState<string>("");
  const [selectedQid, setSelectedQid] = useState<string>("");

  // パラメータとタグの取得
  const { data: parametersResponse, isLoading: isLoadingParameters } =
    useFetchAllParameters();
  const { data: tagsResponse, isLoading: isLoadingTags } = useListAllTag();

  // 時系列データの取得
  const { data: timeseriesResponse, isLoading: isLoadingTimeseries } =
    useFetchTimeseriesTaskResultByTagAndParameter(
      "SAMPLE", // chipId
      selectedParameter,
      { tag: selectedTag },
      {
        query: {
          enabled: Boolean(selectedParameter && selectedTag),
        },
      }
    );

  // プロットデータの準備
  const plotData = useMemo(() => {
    if (!timeseriesResponse?.data?.data) return [];

    try {
      // QID毎のデータを整理
      const qidData: { [key: string]: { x: string[]; y: number[] } } = {};
      const data = timeseriesResponse.data.data;

      // データ構造の検証
      if (typeof data === "object" && data !== null) {
        Object.entries(data).forEach(([qid, dataPoints]) => {
          if (Array.isArray(dataPoints)) {
            qidData[qid] = {
              x: dataPoints.map(
                (point: ExtendedDataModel) => point.calibrated_at || ""
              ),
              y: dataPoints.map((point: ExtendedDataModel) => {
                if (point.output_parameters && selectedParameter) {
                  const value = point.output_parameters[selectedParameter];
                  if (typeof value === "number") {
                    return value;
                  }
                  if (typeof value === "string") {
                    return Number(value) || 0;
                  }
                }
                return 0;
              }),
            };
          }
        });
      }

      // QIDを数値順にソート
      const sortedQids = Object.keys(qidData).sort((a, b) => {
        const numA = parseInt(a);
        const numB = parseInt(b);
        return numA - numB;
      });

      // Plotly用のトレースデータを作成
      return sortedQids.map((qid) => ({
        x: qidData[qid].x,
        y: qidData[qid].y,
        type: "scatter" as const,
        mode: "lines+markers" as const,
        name: `QID: ${qid}`,
        line: {
          shape: "linear" as const,
          width: 2,
        },
        marker: {
          size: 8,
          symbol: "circle",
        },
        hovertemplate:
          "Time: %{x}<br>" +
          "Value: %{y:.8f}<br>" +
          "QID: " +
          qid +
          "<extra></extra>",
      }));
    } catch (error) {
      console.error("Error processing plot data:", error);
      return [];
    }
  }, [timeseriesResponse, selectedParameter]);

  const layout = useMemo<Partial<Layout>>(() => {
    const data = timeseriesResponse?.data?.data;
    let unit = "Value";
    let description = "";

    if (typeof data === "object" && data !== null) {
      const entries = Object.entries(data);
      if (entries.length > 0) {
        const [, firstDataPoints] = entries[0];
        if (Array.isArray(firstDataPoints) && firstDataPoints.length > 0) {
          const firstPoint = firstDataPoints[0] as ExtendedDataModel;
          if (firstPoint.unit) {
            unit = firstPoint.unit || "a.u.";
          }
          if (firstPoint.description) {
            description = firstPoint.description;
          }
        }
      }
    }

    return {
      title: {
        text: `${selectedParameter} Time Series by QID`,
        font: {
          size: 24,
        },
      },
      xaxis: {
        title: "Time",
        type: "date",
        tickformat: "%Y-%m-%d %H:%M",
        gridcolor: "#eee",
        zeroline: false,
      },
      yaxis: {
        title: `${description} [${unit}]`,
        type: "linear",
        gridcolor: "#eee",
        zeroline: false,
        exponentformat: "e" as const,
      },
      showlegend: true,
      legend: {
        x: 1.05,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(255, 255, 255, 0.8)",
      },
      autosize: true,
      margin: {
        l: 80,
        r: 150,
        t: 100,
        b: 80,
      },
      plot_bgcolor: "white",
      paper_bgcolor: "white",
      hovermode: "closest",
    };
  }, [selectedParameter, timeseriesResponse]);

  const parameters = parametersResponse?.data?.parameters || [];
  const tags = tagsResponse?.data?.tags || [];
  const qids = useMemo(() => {
    if (!timeseriesResponse?.data?.data) return [];
    return Object.keys(timeseriesResponse.data.data).sort((a, b) => {
      const numA = parseInt(a);
      const numB = parseInt(b);
      return numA - numB;
    });
  }, [timeseriesResponse]);

  // 選択されたQIDのデータ
  const selectedQidData = useMemo(() => {
    if (!selectedQid || !timeseriesResponse?.data?.data) return [];
    const data = timeseriesResponse.data.data[selectedQid];
    if (!Array.isArray(data)) return [];
    return data.map((point: ExtendedDataModel) => ({
      time: point.calibrated_at || "",
      value:
        point.output_parameters && selectedParameter
          ? point.output_parameters[selectedParameter]
          : 0,
    }));
  }, [timeseriesResponse, selectedQid, selectedParameter]);

  return (
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
            <label className="label font-medium">Parameter</label>
            <select
              className="select select-bordered w-full"
              value={selectedParameter}
              onChange={(e) => setSelectedParameter(e.target.value)}
              disabled={isLoadingParameters}
            >
              <option value="">Select Parameter</option>
              {parameters.map((param: ParameterModel) => (
                <option key={param.name} value={param.name}>
                  {param.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-control">
            <label className="label font-medium">Tag</label>
            <select
              className="select select-bordered w-full"
              value={selectedTag}
              onChange={(e) => setSelectedTag(e.target.value)}
              disabled={isLoadingTags}
            >
              <option value="">Select Tag</option>
              {tags.map((tag: Tag) => (
                <option key={tag.name} value={tag.name}>
                  {tag.name}
                </option>
              ))}
            </select>
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
            <path d="M3 12h18"></path>
            <path d="M12 3v18"></path>
          </svg>
          Time Series Plot
        </h2>
        <div
          className="w-full bg-base-200/50 rounded-xl p-4"
          style={{ height: "550px" }}
        >
          {/* ローディング状態の表示 */}
          {isLoadingTimeseries && (
            <div className="flex items-center justify-center h-full">
              <div className="loading loading-spinner loading-lg text-primary"></div>
            </div>
          )}

          {/* エラー状態の表示 */}
          {!isLoadingTimeseries &&
            selectedParameter &&
            selectedTag &&
            !timeseriesResponse?.data?.data && (
              <div className="flex items-center justify-center h-full text-error">
                <span>No data available for the selected parameters</span>
              </div>
            )}

          {/* プロット表示エリア */}
          {plotData.length > 0 && (
            <Plot
              data={plotData}
              layout={layout}
              config={{
                displaylogo: false,
                responsive: true,
                toImageButtonOptions: {
                  format: "svg",
                  filename: "time_series",
                  height: 600,
                  width: 800,
                  scale: 2,
                },
              }}
              style={{ width: "100%", height: "100%" }}
              useResizeHandler={true}
            />
          )}

          {/* 未選択時の表示 */}
          {!selectedParameter || !selectedTag ? (
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
                  <path d="M3 12h18"></path>
                  <path d="M12 3v18"></path>
                </svg>
                <p className="text-lg">Select parameters to visualize data</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Data Table */}
      <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-semibold">Data Table</h2>
          <div className="form-control w-64">
            <select
              className="select select-bordered w-full"
              value={selectedQid}
              onChange={(e) => setSelectedQid(e.target.value)}
              disabled={!plotData.length}
            >
              <option value="">Select QID</option>
              {qids.map((qid) => (
                <option key={qid} value={qid}>
                  {qid}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="overflow-x-auto" style={{ minHeight: "300px" }}>
          {selectedQid ? (
            <table className="table table-compact table-zebra w-full border border-base-300 bg-base-100">
              <thead>
                <tr>
                  <th className="text-center bg-base-200">Time</th>
                  <th className="text-center bg-base-200">Value</th>
                </tr>
              </thead>
              <tbody>
                {selectedQidData.map((point, index) => (
                  <tr key={index}>
                    <td className="text-center">{point.time}</td>
                    <td className="text-center">
                      {typeof point.value === "number"
                        ? point.value.toFixed(4)
                        : point.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="flex items-center justify-center h-full text-base-content/70">
              <div className="text-center">
                <p className="text-lg">Select a QID to view data</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
