"use client";

import { useFetchAllParameters } from "@/client/parameter/parameter";
import { useListAllTag } from "@/client/tag/tag";
import { useFetchTimeseriesTaskResultByTagAndParameter } from "@/client/chip/chip";
import { useMemo, useState, useEffect } from "react";
import { DataModel } from "@/schemas/dataModel";
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

  // データ構造の確認
  useEffect(() => {
    if (timeseriesResponse?.data) {
      console.log("Time series response:", timeseriesResponse.data);
      console.log("Time series data:", timeseriesResponse.data.data);
      if (timeseriesResponse.data.data) {
        Object.entries(timeseriesResponse.data.data).forEach(
          ([qid, dataPoints]) => {
            if (Array.isArray(dataPoints)) {
              console.log(`QID ${qid} first point:`, dataPoints[0]);
              if (dataPoints[0]) {
                console.log(
                  "First point output_parameters:",
                  (dataPoints[0] as ExtendedDataModel).output_parameters
                );
              }
            }
          }
        );
      }
    }
  }, [timeseriesResponse]);

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
          } else {
            console.error("dataPoints is not an array:", dataPoints);
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
      width: 900,
      height: 600,
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

  return (
    <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-2xl font-semibold">Time Series Analysis</h2>
      </div>

      {/* パラメータとタグの選択 */}
      <div className="flex gap-4 mb-6">
        <select
          className="select select-bordered w-full max-w-xs"
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

        <select
          className="select select-bordered w-full max-w-xs"
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

      {/* ローディング状態の表示 */}
      {isLoadingTimeseries && (
        <div className="alert alert-info">
          <span className="loading loading-spinner"></span>
          <span>Loading time series data...</span>
        </div>
      )}

      {/* エラー状態の表示 */}
      {!isLoadingTimeseries &&
        selectedParameter &&
        selectedTag &&
        !timeseriesResponse?.data?.data && (
          <div className="alert alert-error">
            <span>No data available for the selected parameters</span>
          </div>
        )}

      {/* プロット表示エリア */}
      <div className="w-full">
        {plotData.length > 0 && (
          <Plot data={plotData} layout={layout} config={{ responsive: true }} />
        )}
      </div>
    </div>
  );
}
