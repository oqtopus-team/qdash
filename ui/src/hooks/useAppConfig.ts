/**
 * Unified application configuration hook.
 *
 * This hook loads all application configuration from the backend's /config/all endpoint
 * in a single request. The configuration is cached indefinitely since it rarely changes.
 *
 * Use this hook when you need access to:
 * - UI settings (task files editor settings)
 * - Metrics configuration (titles, units, thresholds)
 * - Copilot configuration
 */

import { useMemo } from "react";

import { useGetConfigAll } from "@/client/config/config";

interface ThresholdRange {
  min: number;
  max: number;
  step: number;
}

interface ThresholdConfig {
  value: number;
  range: ThresholdRange;
}

interface MetricMetadata {
  title: string;
  unit: string;
  scale: number;
  description?: string;
  evaluation: {
    mode: "maximize" | "minimize" | "none";
  };
  threshold?: ThresholdConfig;
  error_rate_range?: ThresholdRange;
}

interface MetricsConfig {
  qubit_metrics: Record<string, MetricMetadata>;
  coupling_metrics: Record<string, MetricMetadata>;
  color_scale?: {
    colors: string[];
  };
  cdf_groups?: {
    qubit: Array<{
      id: string;
      title: string;
      unit: string;
      metrics: string[];
    }>;
    coupling: Array<{
      id: string;
      title: string;
      unit: string;
      metrics: string[];
    }>;
  };
}

interface UISettings {
  task_files?: {
    default_backend?: string;
    default_view_mode?: string;
    sort_order?: string;
  };
}

interface CopilotConfig {
  enabled?: boolean;
  language?: string;
  model?: {
    provider: string;
    name: string;
    temperature: number;
    max_tokens: number;
  };
  evaluation_metrics?: {
    qubit: string[];
    coupling: string[];
  };
  scoring?: Record<
    string,
    {
      good: number;
      excellent: number;
      unit: string;
      higher_is_better: boolean;
    }
  >;
  system_prompt?: string;
  initial_message?: string;
  suggestions?: Array<{
    label: string;
    prompt: string;
  }>;
}

export interface MetricConfig {
  key: string;
  title: string;
  unit: string;
  scale: number;
  description?: string;
  evaluationMode: "maximize" | "minimize" | "none";
  threshold?: ThresholdConfig;
  errorRateRange?: ThresholdRange;
}

/**
 * Hook to load all application configuration.
 *
 * @returns Object containing:
 *   - ui: UI settings (task files, etc.)
 *   - metrics: Metrics configuration with parsed qubit/coupling metrics
 *   - copilot: Copilot configuration
 *   - isLoading: Loading state
 *   - isError: Error state
 *   - error: Error object if failed
 */
export function useAppConfig() {
  const { data, isLoading, isError, error } = useGetConfigAll({
    query: {
      staleTime: Infinity, // Config rarely changes, cache indefinitely
      gcTime: Infinity, // Keep in cache forever
    },
  });

  // Parse and transform config data
  const parsedConfig = useMemo(() => {
    if (!data) {
      return {
        ui: {} as UISettings,
        metrics: null,
        copilot: null,
        // Derived metrics helpers
        qubitMetrics: [] as MetricConfig[],
        couplingMetrics: [] as MetricConfig[],
        allMetrics: [] as MetricConfig[],
        colorScale: { colors: [] as string[] },
        getMetricThreshold: () => undefined as ThresholdConfig | undefined,
        getErrorRateRange: () => undefined as ThresholdRange | undefined,
      };
    }

    const uiSettings = data.ui as unknown as UISettings;
    const metricsConfig = data.metrics as unknown as MetricsConfig;
    const copilotConfig = data.copilot as unknown as CopilotConfig;

    // Transform qubit metrics to array
    const qubitMetrics: MetricConfig[] = Object.entries(
      metricsConfig?.qubit_metrics || {},
    ).map(([key, metadata]) => ({
      key,
      title: metadata.title,
      unit: metadata.unit,
      scale: metadata.scale,
      description: metadata.description,
      evaluationMode: metadata.evaluation?.mode || "none",
      threshold: metadata.threshold,
      errorRateRange: metadata.error_rate_range,
    }));

    // Transform coupling metrics to array
    const couplingMetrics: MetricConfig[] = Object.entries(
      metricsConfig?.coupling_metrics || {},
    ).map(([key, metadata]) => ({
      key,
      title: metadata.title,
      unit: metadata.unit,
      scale: metadata.scale,
      description: metadata.description,
      evaluationMode: metadata.evaluation?.mode || "none",
      threshold: metadata.threshold,
      errorRateRange: metadata.error_rate_range,
    }));

    // Combined metrics
    const allMetrics = [...qubitMetrics, ...couplingMetrics];

    // Helper to get metric threshold by key
    const getMetricThreshold = (
      metricKey: string,
    ): ThresholdConfig | undefined => {
      const metric =
        metricsConfig?.qubit_metrics?.[metricKey] ||
        metricsConfig?.coupling_metrics?.[metricKey];
      return metric?.threshold;
    };

    // Helper to get error rate range by key
    const getErrorRateRange = (
      metricKey: string,
    ): ThresholdRange | undefined => {
      const metric =
        metricsConfig?.qubit_metrics?.[metricKey] ||
        metricsConfig?.coupling_metrics?.[metricKey];
      return metric?.error_rate_range;
    };

    return {
      ui: uiSettings || {},
      metrics: metricsConfig,
      copilot: copilotConfig,
      // Derived metrics helpers
      qubitMetrics,
      couplingMetrics,
      allMetrics,
      colorScale: metricsConfig?.color_scale || { colors: [] },
      getMetricThreshold,
      getErrorRateRange,
    };
  }, [data]);

  return {
    ...parsedConfig,
    isLoading,
    isError,
    error,
  };
}
