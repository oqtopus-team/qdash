"use client";

import { useEffect, useMemo } from "react";
import {
  registerTool,
  unregisterTool,
} from "@/components/features/chat/AssistantRuntimeProvider";

interface MetricConfig {
  key: string;
  title: string;
  unit: string;
}

interface UseChatMetricsProps {
  chipId?: string;
  metricType?: "qubit" | "coupling";
  selectedMetric?: string;
  metricsConfig?: MetricConfig[];
  metricData?: Record<string, { value: number | null }> | null;
  timeRange?: string;
  onMetricChange?: (metric: string) => void;
  onTimeRangeChange?: (range: string) => void;
}

/**
 * Hook to register metrics-related chat tools and provide context
 */
export function useChatMetrics({
  // These are available for future context use
  chipId: _chipId,
  metricType: _metricType,
  selectedMetric: _selectedMetric,
  timeRange: _timeRange,
  metricsConfig,
  metricData,
  onMetricChange,
  onTimeRangeChange,
}: UseChatMetricsProps) {
  // Suppress unused variable warnings for context props
  void _chipId;
  void _metricType;
  void _selectedMetric;
  void _timeRange;
  // Calculate statistics
  const statistics = useMemo(() => {
    if (!metricData) return null;

    const values = Object.entries(metricData)
      .map(([key, data]) => ({ key, value: data.value }))
      .filter(
        (item): item is { key: string; value: number } => item.value !== null
      );

    if (values.length === 0) return null;

    const sortedValues = [...values].sort((a, b) => a.value - b.value);
    const sum = values.reduce((acc, item) => acc + item.value, 0);
    const mean = sum / values.length;

    return {
      count: values.length,
      mean: mean.toFixed(2),
      min: sortedValues[0].value.toFixed(2),
      max: sortedValues[sortedValues.length - 1].value.toFixed(2),
    };
  }, [metricData]);

  // Register metrics tools
  useEffect(() => {
    if (onMetricChange && metricsConfig) {
      registerTool("changeMetric", async (args) => {
        const metricKey = args.metricKey as string;
        const config = metricsConfig.find((m) => m.key === metricKey);
        if (config) {
          onMetricChange(metricKey);
          return `Switched to ${config.title}`;
        }
        return `Metric ${metricKey} not found. Available: ${metricsConfig.map((m) => m.key).join(", ")}`;
      });
    }

    if (onTimeRangeChange) {
      registerTool("changeTimeRange", async (args) => {
        const range = args.range as string;
        if (["1d", "7d", "30d"].includes(range)) {
          onTimeRangeChange(range);
          const labels: Record<string, string> = {
            "1d": "last 24 hours",
            "7d": "last 7 days",
            "30d": "last 30 days",
          };
          return `Changed time range to ${labels[range]}`;
        }
        return "Invalid time range. Use '1d', '7d', or '30d'";
      });
    }

    return () => {
      unregisterTool("changeMetric");
      unregisterTool("changeTimeRange");
    };
  }, [onMetricChange, onTimeRangeChange, metricsConfig]);

  return { statistics };
}
