import { useMemo } from "react";

import type {
  ParameterKey,
  TagKey,
  TimeSeriesDataPoint,
  TimeRangeState,
} from "../types";
import type { OutputParameterModel } from "@/schemas";

import { useFetchTimeseriesTaskResultByTagAndParameterAndQid } from "@/client/chip/chip";
import { useListAllTag } from "@/client/tag/tag";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";

interface UseQubitTimeseriesOptions {
  chipId: string;
  qubitId: string;
  parameter: ParameterKey;
  tag: TagKey;
  timeRange: TimeRangeState;
  enabled?: boolean;
}

/**
 * Custom hook for fetching and processing qubit time series data
 */
export function useQubitTimeseries(options: UseQubitTimeseriesOptions) {
  const {
    chipId,
    qubitId,
    parameter,
    tag,
    timeRange,
    enabled = true,
  } = options;

  // Fetch time series data
  const {
    data: timeseriesResponse,
    isLoading,
    error,
    refetch,
  } = useFetchTimeseriesTaskResultByTagAndParameterAndQid(
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
        enabled: Boolean(enabled && chipId && parameter && tag && qubitId),
        staleTime: 30000, // Keep data fresh for 30 seconds
      },
    },
  );

  // Process table data with performance optimization
  const tableData = useMemo((): TimeSeriesDataPoint[] => {
    if (!timeseriesResponse?.data?.data) return [];

    const qubitData = timeseriesResponse.data.data[qubitId];
    if (!Array.isArray(qubitData)) return [];

    return qubitData
      .map((point: OutputParameterModel) => ({
        time: point.calibrated_at || "",
        value: point.value || 0,
        error: point.error,
        unit: point.unit || "a.u.",
      }))
      .sort((a, b) => a.time.localeCompare(b.time)); // Use string comparison for ISO dates
  }, [timeseriesResponse?.data?.data, qubitId]);

  // Process plot data
  const plotData = useMemo(() => {
    if (!timeseriesResponse?.data?.data) return [];

    try {
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
    } catch (error) {
      console.error("Error processing plot data:", error);
      return [];
    }
  }, [timeseriesResponse?.data?.data, qubitId]);

  // Extract metadata for layout
  const metadata = useMemo(() => {
    const qubitData = timeseriesResponse?.data?.data?.[qubitId];
    if (!Array.isArray(qubitData) || qubitData.length === 0) {
      return { unit: "Value", description: "" };
    }

    const firstPoint = qubitData[0] as OutputParameterModel;
    return {
      unit: firstPoint.unit || "a.u.",
      description: firstPoint.description || "",
    };
  }, [timeseriesResponse?.data?.data, qubitId]);

  return {
    data: timeseriesResponse,
    tableData,
    plotData,
    metadata,
    isLoading,
    error,
    refetch,
  };
}

interface UseQubitParametersOptions {
  enabled?: boolean;
}

/**
 * Custom hook for fetching available parameters and tags
 * Uses useMetricsConfig for parameters (consistent with analysis views)
 */
export function useQubitParameters(options: UseQubitParametersOptions = {}) {
  const { enabled = true } = options;

  const {
    qubitMetrics,
    isLoading: isLoadingConfig,
    isError: isConfigError,
    error: configError,
  } = useMetricsConfig();

  const {
    data: tagsResponse,
    isLoading: isLoadingTags,
    error: tagsError,
  } = useListAllTag({
    query: { enabled },
  });

  // Extract parameter names from qubit metrics config
  const parameters = useMemo(() => {
    return qubitMetrics.map((m) => m.key);
  }, [qubitMetrics]);

  const tags = useMemo(() => {
    return tagsResponse?.data?.tags || [];
  }, [tagsResponse?.data?.tags]);

  return {
    parameters,
    tags,
    isLoading: isLoadingConfig || isLoadingTags,
    error: isConfigError ? configError : tagsError,
  };
}
