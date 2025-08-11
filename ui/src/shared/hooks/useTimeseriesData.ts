import { useMemo } from "react";
import {
  TimeSeriesDataPoint,
  TimeRangeState,
  ParameterKey,
  TagKey,
} from "../types/analysis";
import { OutputParameterModel } from "@/schemas";

interface UseTimeseriesDataOptions {
  chipId: string;
  parameter: ParameterKey;
  tag: TagKey;
  timeRange: TimeRangeState;
  qubitId?: string; // Optional for multi-qubit analysis
  refreshInterval?: number;
  enabled?: boolean;
}

type TimeseriesFetcher = (
  chipId: string,
  parameter: string,
  qubitId: string | undefined,
  params: any,
  options: any,
) => any;

/**
 * Generic hook for fetching and processing time series data
 * Works for both single qubit and multi-qubit analysis
 */
export function useTimeseriesData(
  options: UseTimeseriesDataOptions,
  fetcher: TimeseriesFetcher,
) {
  const {
    chipId,
    parameter,
    tag,
    timeRange,
    qubitId,
    refreshInterval = 30000,
    enabled = true,
  } = options;

  // Use the provided fetcher function
  const {
    data: timeseriesResponse,
    isLoading,
    error,
    refetch,
  } = fetcher(
    chipId,
    parameter,
    qubitId,
    {
      tag,
      start_at: timeRange.startAt,
      end_at: timeRange.endAt,
    },
    {
      query: {
        enabled: Boolean(enabled && chipId && parameter && tag),
        refetchInterval: refreshInterval,
        staleTime: refreshInterval * 0.8,
      },
    },
  );

  // Process table data for single qubit
  const qubitTableData = useMemo((): TimeSeriesDataPoint[] => {
    if (!timeseriesResponse?.data?.data || !qubitId) return [];

    const qubitData = timeseriesResponse.data.data[qubitId];
    if (!Array.isArray(qubitData)) return [];

    return qubitData
      .map((point: OutputParameterModel) => ({
        time: point.calibrated_at || "",
        value: point.value || 0,
        error: point.error,
        unit: point.unit || "a.u.",
        qid: qubitId,
      }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [timeseriesResponse?.data?.data, qubitId]);

  // Process table data for multi-qubit analysis
  const multiQubitTableData = useMemo((): TimeSeriesDataPoint[] => {
    if (!timeseriesResponse?.data?.data) return [];
    const rows: TimeSeriesDataPoint[] = [];

    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          dataPoints.forEach((point: OutputParameterModel) => {
            rows.push({
              qid,
              time: point.calibrated_at || "",
              value: point.value || 0,
              error: point.error,
              unit: point.unit || "a.u.",
            });
          });
        }
      },
    );

    // Sort by QID and time
    return rows.sort((a, b) => {
      const qidCompare = parseInt(a.qid!) - parseInt(b.qid!);
      if (qidCompare !== 0) return qidCompare;
      return a.time.localeCompare(b.time);
    });
  }, [timeseriesResponse?.data?.data]);

  // Generate plot data for Plotly
  const plotData = useMemo(() => {
    if (!timeseriesResponse?.data?.data) return [];

    try {
      if (qubitId) {
        // Single qubit plot
        const qubitData = timeseriesResponse.data.data[qubitId];
        if (!Array.isArray(qubitData)) return [];

        const x = qubitData.map(
          (point: OutputParameterModel) => point.calibrated_at || "",
        );
        const y = qubitData.map((point: OutputParameterModel) => {
          const value = point.value;
          if (typeof value === "number") return value;
          if (typeof value === "string") {
            const parsed = Number(value);
            return isNaN(parsed) ? 0 : parsed;
          }
          return 0;
        });
        const errorArray = qubitData.map(
          (point: OutputParameterModel) => point.error || 0,
        );

        return [
          {
            x,
            y,
            error_y: {
              type: "data" as const,
              array: errorArray as Plotly.Datum[],
              visible: errorArray.some((e) => e > 0),
            },
            type: "scatter" as const,
            mode: "lines+markers" as const,
            name: `Qubit ${qubitId}`,
            line: {
              shape: "linear" as const,
              width: 2,
              color: "#3b82f6",
            },
            marker: {
              size: 8,
              symbol: "circle",
              color: "#3b82f6",
            },
            hovertemplate:
              "Time: %{x}<br>" +
              "Value: %{y:.8f}" +
              (errorArray.some((e) => e > 0)
                ? "<br>Error: ±%{error_y.array:.8f}"
                : "") +
              "<br>Qubit: " +
              qubitId +
              "<extra></extra>",
          },
        ];
      } else {
        // Multi-qubit plot
        const qidData: {
          [key: string]: {
            x: string[];
            y: number[];
            error: number[];
          };
        } = {};

        // Organize data by QID
        Object.entries(timeseriesResponse.data.data).forEach(
          ([qid, dataPoints]) => {
            if (Array.isArray(dataPoints)) {
              qidData[qid] = {
                x: dataPoints.map(
                  (point: OutputParameterModel) => point.calibrated_at || "",
                ),
                y: dataPoints.map((point: OutputParameterModel) => {
                  const value = point.value;
                  if (typeof value === "number") return value;
                  if (typeof value === "string") return Number(value) || 0;
                  return 0;
                }),
                error: dataPoints.map(
                  (point: OutputParameterModel) => point.error || 0,
                ),
              };
            }
          },
        );

        // Sort QIDs numerically
        const sortedQids = Object.keys(qidData).sort(
          (a, b) => parseInt(a) - parseInt(b),
        );

        // Create traces for each QID
        return sortedQids.map((qid) => ({
          x: qidData[qid].x,
          y: qidData[qid].y,
          error_y: {
            type: "data" as const,
            array: qidData[qid].error as Plotly.Datum[],
            visible: true,
          },
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
            "Value: %{y:.8f}" +
            (qidData[qid].error[0] ? "<br>Error: ±%{error_y.array:.8f}" : "") +
            "<br>QID: " +
            qid +
            "<extra></extra>",
        }));
      }
    } catch (error) {
      console.error("Error processing plot data:", error);
      return [];
    }
  }, [timeseriesResponse?.data?.data, qubitId]);

  // Extract metadata for layout
  const metadata = useMemo(() => {
    const data = timeseriesResponse?.data?.data;
    if (!data) return { unit: "Value", description: "" };

    // Get first available data point for metadata
    const firstEntry = Object.entries(data)[0];
    if (!firstEntry) return { unit: "Value", description: "" };

    const [, dataPoints] = firstEntry;
    if (!Array.isArray(dataPoints) || dataPoints.length === 0) {
      return { unit: "Value", description: "" };
    }

    const firstPoint = dataPoints[0] as OutputParameterModel;
    return {
      unit: firstPoint.unit || "a.u.",
      description: firstPoint.description || "",
    };
  }, [timeseriesResponse?.data?.data]);

  return {
    data: timeseriesResponse,
    tableData: qubitId ? qubitTableData : multiQubitTableData,
    plotData,
    metadata,
    isLoading,
    error,
    refetch,
  };
}
