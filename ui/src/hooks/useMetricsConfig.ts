/**
 * Custom hook for loading metrics configuration from backend.
 *
 * This hook loads the metrics metadata (titles, units, scales) from the backend's
 * YAML configuration file. The configuration is cached indefinitely since it rarely changes.
 */

import { useMemo } from "react";
import { useMetricsGetMetricsConfig } from "@/client/metrics/metrics";

interface EvaluationConfig {
  mode: "maximize" | "minimize" | "none";
}

interface MetricMetadata {
  title: string;
  unit: string;
  scale: number;
  description?: string;
  evaluation: EvaluationConfig;
}

interface MetricsConfig {
  qubit_metrics: Record<string, MetricMetadata>;
  coupling_metrics: Record<string, MetricMetadata>;
  color_scale: {
    colors: string[];
  };
}

interface MetricConfig {
  key: string;
  title: string;
  unit: string;
  scale: number;
  description?: string;
  evaluationMode: "maximize" | "minimize" | "none";
}

/**
 * Hook to load and parse metrics configuration.
 *
 * @returns Object containing:
 *   - qubitMetrics: Array of qubit metric configurations
 *   - couplingMetrics: Array of coupling metric configurations
 *   - colorScale: Color scale configuration
 *   - isLoading: Loading state
 *   - isError: Error state
 *   - error: Error object if failed
 */
export function useMetricsConfig() {
  const { data, isLoading, isError, error } = useMetricsGetMetricsConfig({
    query: {
      staleTime: Infinity, // Config rarely changes, cache indefinitely
      gcTime: Infinity, // Keep in cache forever
    },
  });

  // Parse and transform config data
  const parsedConfig = useMemo(() => {
    if (!data?.data) {
      return {
        qubitMetrics: [],
        couplingMetrics: [],
        colorScale: { colors: [] },
      };
    }

    const config = data.data as unknown as MetricsConfig;

    // Transform qubit metrics to array
    // Note: Object.entries() preserves insertion order in modern JS (ES2015+)
    const qubitMetrics: MetricConfig[] = Object.entries(
      config.qubit_metrics || {},
    ).map(([key, metadata]) => ({
      key,
      title: metadata.title,
      unit: metadata.unit,
      scale: metadata.scale,
      description: metadata.description,
      evaluationMode: metadata.evaluation?.mode || "none",
    }));

    // Transform coupling metrics to array
    const couplingMetrics: MetricConfig[] = Object.entries(
      config.coupling_metrics || {},
    ).map(([key, metadata]) => ({
      key,
      title: metadata.title,
      unit: metadata.unit,
      scale: metadata.scale,
      description: metadata.description,
      evaluationMode: metadata.evaluation?.mode || "none",
    }));

    return {
      qubitMetrics,
      couplingMetrics,
      colorScale: config.color_scale || { colors: [] },
    };
  }, [data]);

  return {
    ...parsedConfig,
    isLoading,
    isError,
    error,
  };
}
