"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChatPopup } from "./ChatPopup";
import {
  AssistantRuntimeProvider,
  registerTool,
  unregisterTool,
} from "./AssistantRuntimeProvider";
import { listChips, getChip } from "@/client/chip/chip";
import { getChipMetrics, getMetricsConfig } from "@/client/metrics/metrics";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import { getTopologyById } from "@/client/topology/topology";

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

    // Helper function to find the latest chip by installed_at
    const findLatestChip = (
      chips: Array<{ chip_id: string; installed_at?: string }>,
    ) => {
      if (chips.length === 0) return null;
      return chips.reduce((latest, chip) => {
        if (!latest.installed_at) return chip;
        if (!chip.installed_at) return latest;
        return new Date(chip.installed_at) > new Date(latest.installed_at)
          ? chip
          : latest;
      });
    };

    // Data fetching tools
    registerTool("getChipList", async () => {
      try {
        const response = await listChips();
        const chips = response.data?.chips || [];
        if (chips.length === 0) {
          return "No chips found in the system.";
        }
        const chipList = chips.map((chip) => chip.chip_id).join(", ");
        const latestChip = findLatestChip(chips);
        return `Available chips: ${chipList}. Latest chip: ${latestChip?.chip_id || chips[0].chip_id}`;
      } catch (error) {
        return `Error fetching chips: ${error instanceof Error ? error.message : "Unknown error"}`;
      }
    });

    registerTool("getChipMetricsData", async (args) => {
      try {
        const chipId = args.chipId as string | undefined;
        const withinHours = (args.withinHours as number) || 168; // Default 7 days

        // If no chipId or chipId is "latest", get the latest chip from the list
        let targetChipId = chipId;
        if (!targetChipId || targetChipId.toLowerCase() === "latest") {
          const chipsResponse = await listChips();
          const chips = chipsResponse.data?.chips || [];
          if (chips.length === 0) {
            return "No chips found. Cannot fetch metrics.";
          }
          const latestChip = findLatestChip(chips);
          targetChipId = latestChip?.chip_id || chips[0].chip_id;
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

    registerTool("getChipTopology", async (args) => {
      try {
        const chipId = args.chipId as string | undefined;

        // Get chip ID (use latest if not specified)
        let targetChipId = chipId;
        if (!targetChipId || targetChipId.toLowerCase() === "latest") {
          const chipsResponse = await listChips();
          const chips = chipsResponse.data?.chips || [];
          if (chips.length === 0) {
            return "No chips found. Cannot fetch topology.";
          }
          const latestChip = findLatestChip(chips);
          targetChipId = latestChip?.chip_id || chips[0].chip_id;
        }

        // Get chip info to find topology_id
        const chipResponse = await getChip(targetChipId);
        const chip = chipResponse.data;
        if (!chip) {
          return `Chip ${targetChipId} not found.`;
        }

        const topologyId = chip.topology_id;
        if (!topologyId) {
          return `Chip ${targetChipId} has no topology_id configured.`;
        }

        // Fetch topology definition
        const topologyResponse = await getTopologyById(topologyId);
        const topology = topologyResponse.data?.data as
          | {
              qubits?: Record<string, { row: number; col: number }>;
              couplings?: number[][];
            }
          | undefined;
        if (!topology) {
          return `Topology ${topologyId} not found.`;
        }

        // Format topology information
        // qubits: { "0": { row: 0, col: 0 }, "1": { row: 0, col: 1 }, ... }
        const qubits = topology.qubits || {};
        // couplings: [[0, 1], [1, 2], ...] - pairs of qubit IDs
        const couplings = topology.couplings || [];

        // Build qubit position map
        const qubitPositions: string[] = [];
        const neighborMap: Record<string, string[]> = {};

        for (const [qid, pos] of Object.entries(qubits)) {
          qubitPositions.push(`Q${qid}: (row=${pos.row}, col=${pos.col})`);
          neighborMap[qid] = [];
        }

        // Build coupling list and neighbor map
        const couplingList: string[] = [];
        for (let i = 0; i < couplings.length; i++) {
          const pair = couplings[i];
          if (pair && pair.length === 2) {
            const [q1, q2] = pair;
            couplingList.push(`C${i}: Q${q1} <-> Q${q2}`);
            const q1Str = String(q1);
            const q2Str = String(q2);
            if (neighborMap[q1Str]) neighborMap[q1Str].push(`Q${q2}`);
            if (neighborMap[q2Str]) neighborMap[q2Str].push(`Q${q1}`);
          }
        }

        // Format neighbor map
        const neighborSummary = Object.entries(neighborMap)
          .map(([qid, neighbors]) => `Q${qid}: [${neighbors.join(", ")}]`)
          .join("\n");

        return `Chip: ${targetChipId}\nTopology ID: ${topologyId}\nQubits: ${Object.keys(qubits).length}\nCouplings: ${couplings.length}\n\n**Qubit Positions:**\n${qubitPositions.join("\n")}\n\n**Couplings:**\n${couplingList.join("\n")}\n\n**Neighbor Map:**\n${neighborSummary}`;
      } catch (error) {
        return `Error fetching topology: ${error instanceof Error ? error.message : "Unknown error"}`;
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
      unregisterTool("getChipTopology");
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
