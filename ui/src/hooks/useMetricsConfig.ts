/**
 * Custom hook for loading metrics configuration from backend.
 *
 * This hook loads the metrics metadata (titles, units, scales) from the backend's
 * YAML configuration file. The configuration is cached indefinitely since it rarely changes.
 */

import { useMemo } from "react";
import { useMetricsGetMetricsConfig } from "@/client/metrics/metrics";

export interface MetricMetadata {
  title: string;
  unit: string;
  scale: number;
  display_order: number;
  description?: string;
}

export interface MetricsConfig {
  qubit_metrics: Record<string, MetricMetadata>;
  coupling_metrics: Record<string, MetricMetadata>;
  color_scale: {
    colors: string[];
  };
}

export interface MetricConfig {
  key: string;
  title: string;
  unit: string;
  scale: number;
  displayOrder: number;
  description?: string;
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

    // Transform qubit metrics to array and sort by display_order
    const qubitMetrics: MetricConfig[] = Object.entries(
      config.qubit_metrics || {},
    )
      .map(([key, metadata]) => ({
        key,
        title: metadata.title,
        unit: metadata.unit,
        scale: metadata.scale,
        displayOrder: metadata.display_order,
        description: metadata.description,
      }))
      .sort((a, b) => a.displayOrder - b.displayOrder);

    // Transform coupling metrics to array and sort by display_order
    const couplingMetrics: MetricConfig[] = Object.entries(
      config.coupling_metrics || {},
    )
      .map(([key, metadata]) => ({
        key,
        title: metadata.title,
        unit: metadata.unit,
        scale: metadata.scale,
        displayOrder: metadata.display_order,
        description: metadata.description,
      }))
      .sort((a, b) => a.displayOrder - b.displayOrder);

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

/**
 * Get a specific qubit metric configuration by key.
 */
export function useQubitMetricConfig(metricKey: string) {
  const { qubitMetrics, isLoading, isError } = useMetricsConfig();

  const metric = useMemo(
    () => qubitMetrics.find((m) => m.key === metricKey),
    [qubitMetrics, metricKey],
  );

  return {
    metric,
    isLoading,
    isError,
  };
}

/**
 * Get a specific coupling metric configuration by key.
 */
export function useCouplingMetricConfig(metricKey: string) {
  const { couplingMetrics, isLoading, isError } = useMetricsConfig();

  const metric = useMemo(
    () => couplingMetrics.find((m) => m.key === metricKey),
    [couplingMetrics, metricKey],
  );

  return {
    metric,
    isLoading,
    isError,
  };
}
