"use client";

import { useMemo } from "react";
import { useCopilotReadable, useCopilotAction } from "@copilotkit/react-core";

import type { CopilotConfig } from "@/hooks/useCopilotConfig";

interface MetricValue {
  value: number | null;
  task_id?: string | null;
  execution_id?: string | null;
}

interface MetricConfig {
  key: string;
  title: string;
  unit: string;
  scale: number;
}

interface QubitPosition {
  row: number;
  col: number;
}

interface TopologyData {
  id: string;
  name: string;
  grid_size: number;
  num_qubits: number;
  qubits: Record<string, QubitPosition>;
  couplings: number[][];
}

interface UseMetricsCopilotProps {
  chipId: string;
  metricType: "qubit" | "coupling";
  selectedMetric: string;
  metricsConfig: MetricConfig[];
  metricData: Record<string, MetricValue> | null;
  allMetricsData: Record<
    string,
    Record<string, { value: number | null }>
  > | null;
  timeRange: string;
  selectionMode: string;
  aiConfig: CopilotConfig | null;
  topologyData: TopologyData | null;
  onMetricChange?: (metric: string) => void;
  onTimeRangeChange?: (range: string) => void;
}

/**
 * Hook to share metrics data with CopilotKit AI assistant
 */
export function useMetricsCopilot({
  chipId,
  metricType,
  selectedMetric,
  metricsConfig,
  metricData,
  allMetricsData,
  timeRange,
  selectionMode,
  aiConfig,
  topologyData,
  onMetricChange,
  onTimeRangeChange,
}: UseMetricsCopilotProps) {
  // Get scoring thresholds from config
  const scoringThresholds = useMemo(() => {
    return aiConfig?.scoring ?? {};
  }, [aiConfig]);

  // Get evaluation metrics from config
  const evaluationMetrics = useMemo(() => {
    if (!aiConfig?.evaluation_metrics) return new Set<string>();
    const metrics =
      metricType === "qubit"
        ? aiConfig.evaluation_metrics.qubit
        : aiConfig.evaluation_metrics.coupling;
    return new Set(metrics);
  }, [aiConfig, metricType]);
  // Calculate statistics from metric data
  const statistics = useMemo(() => {
    if (!metricData) return null;

    const values = Object.entries(metricData)
      .map(([key, data]) => ({ key, value: data.value }))
      .filter(
        (item): item is { key: string; value: number } => item.value !== null,
      );

    if (values.length === 0) return null;

    const sortedValues = [...values].sort((a, b) => a.value - b.value);
    const sum = values.reduce((acc, item) => acc + item.value, 0);
    const mean = sum / values.length;
    const variance =
      values.reduce((acc, item) => acc + Math.pow(item.value - mean, 2), 0) /
      values.length;
    const stdDev = Math.sqrt(variance);
    const median =
      sortedValues.length % 2 === 0
        ? (sortedValues[sortedValues.length / 2 - 1].value +
            sortedValues[sortedValues.length / 2].value) /
          2
        : sortedValues[Math.floor(sortedValues.length / 2)].value;

    // Find outliers (beyond 2 standard deviations)
    const lowOutliers = values.filter((item) => item.value < mean - 2 * stdDev);
    const highOutliers = values.filter(
      (item) => item.value > mean + 2 * stdDev,
    );

    return {
      count: values.length,
      mean: mean.toFixed(2),
      median: median.toFixed(2),
      min: {
        key: sortedValues[0].key,
        value: sortedValues[0].value.toFixed(2),
      },
      max: {
        key: sortedValues[sortedValues.length - 1].key,
        value: sortedValues[sortedValues.length - 1].value.toFixed(2),
      },
      stdDev: stdDev.toFixed(2),
      lowOutliers: lowOutliers.map((o) => ({
        key: o.key,
        value: o.value.toFixed(2),
      })),
      highOutliers: highOutliers.map((o) => ({
        key: o.key,
        value: o.value.toFixed(2),
      })),
    };
  }, [metricData]);

  // Create a summary of all metrics for cross-metric analysis
  const allMetricsSummary = useMemo(() => {
    if (!allMetricsData) return null;

    const summary: Record<
      string,
      {
        title: string;
        unit: string;
        mean: string;
        median: string;
        count: number;
      }
    > = {};

    for (const config of metricsConfig) {
      const data = allMetricsData[config.key];
      if (!data) continue;

      const values = Object.values(data)
        .map((d) => d.value)
        .filter((v): v is number => v !== null);

      if (values.length === 0) continue;

      const sortedValues = [...values].sort((a, b) => a - b);
      const sum = values.reduce((acc, v) => acc + v, 0);
      const mean = sum / values.length;
      const median =
        sortedValues.length % 2 === 0
          ? (sortedValues[sortedValues.length / 2 - 1] +
              sortedValues[sortedValues.length / 2]) /
            2
          : sortedValues[Math.floor(sortedValues.length / 2)];

      summary[config.key] = {
        title: config.title,
        unit: config.unit,
        mean: mean.toFixed(2),
        median: median.toFixed(2),
        count: values.length,
      };
    }

    return summary;
  }, [allMetricsData, metricsConfig]);

  // Create per-qubit multi-metric view for comprehensive evaluation
  const perQubitEvaluation = useMemo(() => {
    if (!allMetricsData || metricType !== "qubit") return null;

    // Collect all qubit IDs
    const qubitIds = new Set<string>();
    Object.values(allMetricsData).forEach((metricValues) => {
      Object.keys(metricValues).forEach((id) => qubitIds.add(id));
    });

    // Build per-qubit data with all metrics
    const evaluation: Record<
      string,
      {
        metrics: Record<string, { value: number | null; rating: string }>;
        overallScore: number;
        issues: string[];
      }
    > = {};

    for (const qubitId of qubitIds) {
      const metrics: Record<string, { value: number | null; rating: string }> =
        {};
      const issues: string[] = [];
      let scoreSum = 0;
      let scoreCount = 0;

      for (const config of metricsConfig) {
        // Only include metrics that are in the evaluation list
        if (!evaluationMetrics.has(config.key)) continue;

        const data = allMetricsData[config.key];
        const value = data?.[qubitId]?.value ?? null;

        let rating = "unknown";
        if (value !== null) {
          const threshold = scoringThresholds[config.key];
          if (threshold) {
            if (threshold.higher_is_better) {
              if (value >= threshold.excellent) {
                rating = "excellent";
                scoreSum += 3;
              } else if (value >= threshold.good) {
                rating = "good";
                scoreSum += 2;
              } else {
                rating = "poor";
                scoreSum += 1;
                issues.push(
                  `${config.title}: ${value.toFixed(2)}${config.unit} (below good threshold)`,
                );
              }
            } else {
              // For metrics where lower is better (if any)
              if (value <= threshold.excellent) {
                rating = "excellent";
                scoreSum += 3;
              } else if (value <= threshold.good) {
                rating = "good";
                scoreSum += 2;
              } else {
                rating = "poor";
                scoreSum += 1;
                issues.push(
                  `${config.title}: ${value.toFixed(2)}${config.unit} (above good threshold)`,
                );
              }
            }
            scoreCount++;
          }
        }

        metrics[config.key] = { value, rating };
      }

      evaluation[qubitId] = {
        metrics,
        overallScore: scoreCount > 0 ? scoreSum / scoreCount : 0,
        issues,
      };
    }

    return evaluation;
  }, [
    allMetricsData,
    metricsConfig,
    metricType,
    scoringThresholds,
    evaluationMetrics,
  ]);

  // Identify problematic qubits based on multi-metric analysis
  const problematicQubits = useMemo(() => {
    if (!perQubitEvaluation) return null;

    return Object.entries(perQubitEvaluation)
      .filter(([, data]) => data.issues.length > 0 || data.overallScore < 2)
      .sort((a, b) => a[1].overallScore - b[1].overallScore)
      .slice(0, 10) // Top 10 worst
      .map(([qubitId, data]) => ({
        qubitId,
        overallScore: data.overallScore.toFixed(2),
        issues: data.issues,
        metrics: Object.fromEntries(
          Object.entries(data.metrics)
            .filter(([, m]) => m.value !== null)
            .map(([key, m]) => [
              key,
              { value: m.value?.toFixed(2), rating: m.rating },
            ]),
        ),
      }));
  }, [perQubitEvaluation]);

  // Summary of chip health
  const chipHealthSummary = useMemo(() => {
    if (!perQubitEvaluation) return null;

    const scores = Object.values(perQubitEvaluation).map((q) => q.overallScore);
    const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
    const excellentCount = scores.filter((s) => s >= 2.5).length;
    const goodCount = scores.filter((s) => s >= 2 && s < 2.5).length;
    const poorCount = scores.filter((s) => s < 2).length;

    return {
      totalQubits: scores.length,
      averageScore: avgScore.toFixed(2),
      distribution: {
        excellent: excellentCount,
        good: goodCount,
        poor: poorCount,
      },
      healthRating:
        avgScore >= 2.5
          ? "Excellent"
          : avgScore >= 2
            ? "Good"
            : avgScore >= 1.5
              ? "Fair"
              : "Poor",
    };
  }, [perQubitEvaluation]);

  // Get current metric config
  const currentMetricConfig = useMemo(
    () => metricsConfig.find((m) => m.key === selectedMetric),
    [metricsConfig, selectedMetric],
  );

  // Share chip and context info
  useCopilotReadable({
    description: "Currently selected chip and analysis context",
    value: {
      chipId,
      metricType,
      timeRange:
        timeRange === "1d"
          ? "Last 24 hours"
          : timeRange === "7d"
            ? "Last 7 days"
            : "Last 30 days",
      selectionMode:
        selectionMode === "latest" ? "Latest values" : "Best values",
    },
    available: chipId ? "enabled" : "disabled",
  });

  // Share current metric details
  useCopilotReadable({
    description: "Currently selected metric and its statistics",
    value: {
      metric: currentMetricConfig
        ? {
            key: currentMetricConfig.key,
            name: currentMetricConfig.title,
            unit: currentMetricConfig.unit,
          }
        : null,
      statistics,
    },
    available: currentMetricConfig && statistics ? "enabled" : "disabled",
  });

  // Share individual qubit/coupling values
  useCopilotReadable({
    description: `Individual ${metricType} values for the selected metric`,
    value: metricData
      ? Object.entries(metricData)
          .filter(([, data]) => data.value !== null)
          .map(([key, data]) => ({
            id: key,
            value: data.value?.toFixed(3),
          }))
      : null,
    available: metricData ? "enabled" : "disabled",
  });

  // Share summary of all metrics for cross-metric analysis
  useCopilotReadable({
    description:
      "Summary statistics for all available metrics (for comparison)",
    value: allMetricsSummary,
    available: allMetricsSummary ? "enabled" : "disabled",
  });

  // Share chip health summary for multi-metric evaluation
  useCopilotReadable({
    description:
      "Overall chip health summary based on multi-metric evaluation (T1, T2, fidelity, etc.)",
    value: chipHealthSummary,
    available: chipHealthSummary ? "enabled" : "disabled",
  });

  // Share problematic qubits identified through multi-metric analysis
  useCopilotReadable({
    description:
      "Qubits with issues identified through multi-metric analysis (worst performers)",
    value: problematicQubits,
    available:
      problematicQubits && problematicQubits.length > 0
        ? "enabled"
        : "disabled",
  });

  // Share evaluation thresholds for reference
  useCopilotReadable({
    description:
      "Reference thresholds used for metric evaluation (good/excellent levels)",
    value: scoringThresholds,
    available:
      Object.keys(scoringThresholds).length > 0 ? "enabled" : "disabled",
  });

  // Compute neighbor map from topology for crosstalk analysis
  const neighborMap = useMemo(() => {
    if (!topologyData?.couplings) return null;

    const neighbors: Record<string, string[]> = {};
    for (const [q1, q2] of topologyData.couplings) {
      const id1 = `Q${String(q1).padStart(2, "0")}`;
      const id2 = `Q${String(q2).padStart(2, "0")}`;
      if (!neighbors[id1]) neighbors[id1] = [];
      if (!neighbors[id2]) neighbors[id2] = [];
      neighbors[id1].push(id2);
      neighbors[id2].push(id1);
    }
    return neighbors;
  }, [topologyData]);

  // Share topology information for spatial/crosstalk analysis
  useCopilotReadable({
    description:
      "Chip topology: qubit positions (row, col) and coupling connections for spatial and crosstalk analysis",
    value: topologyData
      ? {
          topology_id: topologyData.id,
          name: topologyData.name,
          grid_size: topologyData.grid_size,
          num_qubits: topologyData.num_qubits,
          qubit_positions: Object.fromEntries(
            Object.entries(topologyData.qubits).map(([id, pos]) => [
              `Q${String(id).padStart(2, "0")}`,
              { row: pos.row, col: pos.col },
            ])
          ),
          couplings: topologyData.couplings.map(([q1, q2]) => [
            `Q${String(q1).padStart(2, "0")}`,
            `Q${String(q2).padStart(2, "0")}`,
          ]),
          neighbor_map: neighborMap,
        }
      : null,
    available: topologyData ? "enabled" : "disabled",
  });

  // Action to change metric
  useCopilotAction({
    name: "changeMetric",
    description: "Change the currently displayed metric",
    parameters: [
      {
        name: "metricKey",
        type: "string",
        description: `The metric key to switch to. Available: ${metricsConfig.map((m) => m.key).join(", ")}`,
        required: true,
      },
    ],
    available: onMetricChange ? "enabled" : "disabled",
    handler: async ({ metricKey }) => {
      const config = metricsConfig.find((m) => m.key === metricKey);
      if (config && onMetricChange) {
        onMetricChange(metricKey);
        return `Switched to ${config.title}`;
      }
      return `Metric ${metricKey} not found`;
    },
  });

  // Action to change time range
  useCopilotAction({
    name: "changeTimeRange",
    description: "Change the time range for metrics data",
    parameters: [
      {
        name: "range",
        type: "string",
        description:
          "Time range: '1d' for last day, '7d' for last week, '30d' for last month",
        required: true,
      },
    ],
    available: onTimeRangeChange ? "enabled" : "disabled",
    handler: async ({ range }) => {
      if (["1d", "7d", "30d"].includes(range) && onTimeRangeChange) {
        onTimeRangeChange(range);
        const labels: Record<string, string> = {
          "1d": "last 24 hours",
          "7d": "last 7 days",
          "30d": "last 30 days",
        };
        return `Changed time range to ${labels[range]}`;
      }
      return "Invalid time range. Use '1d', '7d', or '30d'";
    },
  });

  return { statistics, allMetricsSummary };
}
