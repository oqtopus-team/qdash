"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChatPopup } from "./ChatPopup";
import {
  AssistantRuntimeProvider,
  registerTool,
  unregisterTool,
} from "./AssistantRuntimeProvider";
import { listChips } from "@/client/chip/chip";
import { getChipMetrics, getMetricsConfig } from "@/client/metrics/metrics";

export function ChatAssistant() {
  const router = useRouter();
  const pathname = usePathname();

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

        const response = await getChipMetrics(targetChipId, {
          within_hours: withinHours,
          selection_mode: "latest",
        });

        const metrics = response.data;
        if (!metrics) {
          return `No metrics data found for chip ${targetChipId}`;
        }

        // Build summary using typed schema
        const qubitMetrics = metrics.qubit_metrics;
        const couplingMetrics = metrics.coupling_metrics;

        const qubitCount = metrics.qubit_count;
        const couplingCount = Object.keys(
          couplingMetrics?.zx90_gate_fidelity || {},
        ).length;

        // Calculate statistics for key metrics
        type MetricData = Record<string, { value: number | null }>;
        const calcStats = (data: MetricData | undefined) => {
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

        const t1Stats = calcStats(qubitMetrics?.t1 as MetricData | undefined);
        const t2Stats = calcStats(
          qubitMetrics?.t2_echo as MetricData | undefined,
        );
        const x90FidelityStats = calcStats(
          qubitMetrics?.x90_gate_fidelity as MetricData | undefined,
        );
        const readoutFidelityStats = calcStats(
          qubitMetrics?.average_readout_fidelity as MetricData | undefined,
        );

        let summary = `Chip: ${targetChipId} (last ${withinHours / 24} days)\n`;
        summary += `Qubits: ${qubitCount}, Couplings: ${couplingCount}\n\n`;

        if (t1Stats) {
          summary += `T1: avg=${(t1Stats.avg * 1e6).toFixed(1)}µs, range=[${(t1Stats.min * 1e6).toFixed(1)}-${(t1Stats.max * 1e6).toFixed(1)}]µs (${t1Stats.count} qubits)\n`;
        }
        if (t2Stats) {
          summary += `T2 Echo: avg=${(t2Stats.avg * 1e6).toFixed(1)}µs, range=[${(t2Stats.min * 1e6).toFixed(1)}-${(t2Stats.max * 1e6).toFixed(1)}]µs (${t2Stats.count} qubits)\n`;
        }
        if (x90FidelityStats) {
          summary += `X90 Gate Fidelity: avg=${(x90FidelityStats.avg * 100).toFixed(2)}%, range=[${(x90FidelityStats.min * 100).toFixed(2)}-${(x90FidelityStats.max * 100).toFixed(2)}]% (${x90FidelityStats.count} qubits)\n`;
        }
        if (readoutFidelityStats) {
          summary += `Readout Fidelity: avg=${(readoutFidelityStats.avg * 100).toFixed(2)}%, range=[${(readoutFidelityStats.min * 100).toFixed(2)}-${(readoutFidelityStats.max * 100).toFixed(2)}]% (${readoutFidelityStats.count} qubits)\n`;
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
    <AssistantRuntimeProvider context={{ pathname }}>
      <ChatPopup />
    </AssistantRuntimeProvider>
  );
}
