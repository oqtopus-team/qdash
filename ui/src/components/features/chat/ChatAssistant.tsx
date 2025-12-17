"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChatPopup } from "./ChatPopup";
import {
  AssistantRuntimeProvider,
  registerTool,
  unregisterTool,
} from "./AssistantRuntimeProvider";
import { listChips } from "@/client/chip/chip";
import { getChipMetrics, getMetricsConfig } from "@/client/metrics/metrics";
import { useGetCopilotConfig } from "@/client/copilot/copilot";

export function ChatAssistant() {
  const router = useRouter();
  const pathname = usePathname();
  const [clearKey, setClearKey] = useState(0);

  // Fetch copilot config once here
  const { data: copilotConfigResponse } = useGetCopilotConfig();
  const copilotConfigData = copilotConfigResponse?.data as
    | {
        initial_message?: string;
        suggestions?: Array<{ label: string; prompt: string }>;
        system_prompt?: string;
        model?: {
          provider?: string;
          name?: string;
          temperature?: number;
          max_tokens?: number;
        };
      }
    | undefined;

  // Clear messages by remounting the runtime provider
  const handleClearMessages = useCallback(() => {
    setClearKey((prev) => prev + 1);
  }, []);

  // Register navigation tools
  useEffect(() => {
    registerTool("navigateTo", async (args) => {
      const path = args.path as string;
      const description = args.description as string | undefined;
      router.push(path);
      return `Navigated to ${description || path}`;
    });

    registerTool("navigateToChip", async (args) => {
      const chipId = args.chipId as string;
      router.push(`/chip?selected=${encodeURIComponent(chipId)}`);
      return `Navigated to chip ${chipId}`;
    });

    registerTool("navigateToQubit", async (args) => {
      const chipId = args.chipId as string;
      const qubitId = args.qubitId as string;
      router.push(
        `/chip/${encodeURIComponent(chipId)}/qubit/${encodeURIComponent(qubitId)}`,
      );
      return `Navigated to qubit ${qubitId} on chip ${chipId}`;
    });

    registerTool("navigateToWorkflow", async (args) => {
      const workflowName = args.workflowName as string;
      router.push(`/workflow/${encodeURIComponent(workflowName)}`);
      return `Navigated to workflow ${workflowName}`;
    });

    registerTool("navigateToExecution", async (args) => {
      const chipId = args.chipId as string;
      const executeId = args.executeId as string;
      router.push(
        `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executeId)}`,
      );
      return `Navigated to execution ${executeId}`;
    });

    // Data fetching tools
    registerTool("getChipList", async () => {
      try {
        const response = await listChips();
        const chips = response.data?.chips || [];
        if (chips.length === 0) {
          return "No chips found in the system.";
        }
        const chipList = chips.map((chip) => chip.chip_id).join(", ");
        return `Available chips: ${chipList}. Latest chip: ${chips[0].chip_id}`;
      } catch (error) {
        return `Error fetching chips: ${error instanceof Error ? error.message : "Unknown error"}`;
      }
    });

    registerTool("getChipMetricsData", async (args) => {
      try {
        const chipId = args.chipId as string | undefined;
        const withinHours = (args.withinHours as number) || 168; // Default 7 days

        // If no chipId, get the latest chip
        let targetChipId = chipId;
        if (!targetChipId) {
          const chipsResponse = await listChips();
          const chips = chipsResponse.data?.chips || [];
          if (chips.length === 0) {
            return "No chips found. Cannot fetch metrics.";
          }
          targetChipId = chips[0].chip_id;
        }

        // Fetch metrics config and data in parallel
        const [configResponse, metricsResponse] = await Promise.all([
          getMetricsConfig(),
          getChipMetrics(targetChipId, {
            within_hours: withinHours,
            selection_mode: "latest",
          }),
        ]);

        const config = configResponse.data;
        const metrics = metricsResponse.data;

        if (!metrics) {
          return `No metrics data found for chip ${targetChipId}`;
        }

        // Get metric configs
        type MetricConfig = {
          title: string;
          unit: string;
          scale: number;
        };
        const qubitMetricConfigs = (config?.qubit_metrics || {}) as Record<
          string,
          MetricConfig
        >;
        const couplingMetricConfigs = (config?.coupling_metrics ||
          {}) as Record<string, MetricConfig>;

        // Build summary using config
        const qubitMetricsData = metrics.qubit_metrics as Record<
          string,
          Record<string, { value: number | null }> | undefined
        >;
        const couplingMetricsData = metrics.coupling_metrics as Record<
          string,
          Record<string, { value: number | null }> | undefined
        >;

        const qubitCount = metrics.qubit_count;

        // Calculate statistics for a metric
        const calcStats = (
          data: Record<string, { value: number | null }> | undefined,
        ) => {
          if (!data) return null;
          const values = Object.values(data)
            .map((d) => d.value)
            .filter((v): v is number => v !== null);
          if (values.length === 0) return null;
          const sum = values.reduce((a, b) => a + b, 0);
          const avg = sum / values.length;
          const min = Math.min(...values);
          const max = Math.max(...values);
          return { count: values.length, avg, min, max };
        };

        // Format value with scale
        const formatValue = (value: number, scale: number, decimals = 2) => {
          return (value * scale).toFixed(decimals);
        };

        let summary = `Chip: ${targetChipId} (last ${withinHours / 24} days)\n`;
        summary += `Qubits: ${qubitCount}\n\n`;

        // Process qubit metrics dynamically
        summary += "**Qubit Metrics:**\n";
        for (const [key, cfg] of Object.entries(qubitMetricConfigs)) {
          const data = qubitMetricsData[key];
          const stats = calcStats(data);
          if (stats) {
            const scale = cfg.scale || 1;
            const decimals = cfg.unit === "%" ? 2 : 1;
            summary += `${cfg.title}: avg=${formatValue(stats.avg, scale, decimals)}${cfg.unit}, range=[${formatValue(stats.min, scale, decimals)}-${formatValue(stats.max, scale, decimals)}]${cfg.unit} (${stats.count} qubits)\n`;
          }
        }

        // Process coupling metrics dynamically
        const hasCouplingData = Object.values(couplingMetricsData).some(
          (d) => d && Object.keys(d).length > 0,
        );
        if (hasCouplingData) {
          summary += "\n**Coupling Metrics:**\n";
          for (const [key, cfg] of Object.entries(couplingMetricConfigs)) {
            const data = couplingMetricsData[key];
            const stats = calcStats(data);
            if (stats) {
              const scale = cfg.scale || 1;
              const decimals = cfg.unit === "%" ? 2 : 1;
              summary += `${cfg.title}: avg=${formatValue(stats.avg, scale, decimals)}${cfg.unit}, range=[${formatValue(stats.min, scale, decimals)}-${formatValue(stats.max, scale, decimals)}]${cfg.unit} (${stats.count} couplings)\n`;
            }
          }
        }

        return summary;
      } catch (error) {
        return `Error fetching metrics: ${error instanceof Error ? error.message : "Unknown error"}`;
      }
    });

    registerTool("getMetricsConfiguration", async () => {
      try {
        const response = await getMetricsConfig();
        const config = response.data;
        if (!config) {
          return "No metrics configuration found.";
        }

        const qubitMetrics = config.qubit_metrics || {};
        const couplingMetrics = config.coupling_metrics || {};

        const qubitMetricNames = Object.keys(qubitMetrics).join(", ");
        const couplingMetricNames = Object.keys(couplingMetrics).join(", ");

        return `Available qubit metrics: ${qubitMetricNames}\nAvailable coupling metrics: ${couplingMetricNames}`;
      } catch (error) {
        return `Error fetching metrics config: ${error instanceof Error ? error.message : "Unknown error"}`;
      }
    });

    return () => {
      unregisterTool("navigateTo");
      unregisterTool("navigateToChip");
      unregisterTool("navigateToQubit");
      unregisterTool("navigateToWorkflow");
      unregisterTool("navigateToExecution");
      unregisterTool("getChipList");
      unregisterTool("getChipMetricsData");
      unregisterTool("getMetricsConfiguration");
    };
  }, [router]);

  return (
    <AssistantRuntimeProvider
      key={clearKey}
      context={{ pathname }}
      copilotConfig={{
        system_prompt: copilotConfigData?.system_prompt,
        model: copilotConfigData?.model,
      }}
    >
      <ChatPopup
        onClear={handleClearMessages}
        initialMessage={copilotConfigData?.initial_message}
        suggestions={copilotConfigData?.suggestions}
      />
    </AssistantRuntimeProvider>
  );
}
