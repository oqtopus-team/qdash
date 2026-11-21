"use client";

import { useMemo } from "react";

import { useGetChipMetrics } from "@/client/metrics/metrics";
import { CouplingMetricGrid } from "@/components/features/overview/CouplingMetricGrid";
import { QubitMetricGrid } from "@/components/features/overview/QubitMetricGrid";
import { type MetricConfig, useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { getStoredColorRanges, resolveMetricColorRange } from "@/lib/metricColorRanges";
import { getApiErrorMessage } from "@/lib/utils/apiError";

import { type MetricSelectionMode, SELECTION_MODES } from "../panelConfig";
import { PanelMessage, PanelSkeleton } from "./PanelStates";
import { fitCellSize, topologyGridDimensions, useElementSize } from "./useElementSize";

interface MetricValueLike {
  value: number | null;
  stddev?: number | null;
}

type MetricMap = Record<string, MetricValueLike>;

const FALLBACK_COLORS = ["#440154", "#31688e", "#35b779", "#fde724"];

/**
 * Scale raw metric values into display units. Qubit keys lose their `Q`
 * prefix so they match the topology IDs, as on the Dashboard page.
 */
function scaleMetricValues(
  raw: Record<string, MetricValueLike> | undefined,
  scale: number,
  metricType: "qubit" | "coupling",
): MetricMap | null {
  if (!raw) return null;
  const out: MetricMap = {};
  for (const [key, metric] of Object.entries(raw)) {
    const formattedKey =
      metricType === "qubit" ? String(parseInt(key.startsWith("Q") ? key.slice(1) : key, 10)) : key;
    const value = metric?.value;
    const stddev = metric?.stddev;
    out[formattedKey] = {
      value: typeof value === "number" ? value * scale : null,
      stddev: typeof stddev === "number" ? stddev * scale : null,
    };
  }
  return out;
}

interface MetricPanelProps {
  chipId: string;
  topologyId: string;
  metricKey: string;
  selectionMode: MetricSelectionMode;
}

function MetricPanel({
  chipId,
  topologyId,
  metricKey,
  selectionMode,
  metricType,
}: MetricPanelProps & { metricType: "qubit" | "coupling" }) {
  const {
    qubitMetrics,
    couplingMetrics,
    colorScale,
    isLoading: isConfigLoading,
  } = useMetricsConfig();
  const metric: MetricConfig | undefined = (
    metricType === "qubit" ? qubitMetrics : couplingMetrics
  ).find((entry) => entry.key === metricKey);

  const { data, isLoading, isError, error } = useGetChipMetrics(
    chipId,
    { selection_mode: selectionMode },
    { query: { enabled: !!chipId, staleTime: 30_000 } },
  );
  const { qubits, gridSize } = useTopologyConfig(topologyId);
  const { rows, cols } = topologyGridDimensions(qubits, gridSize);
  const { ref, width, height } = useElementSize<HTMLDivElement>();

  const metricData = useMemo(() => {
    if (!metric) return null;
    const source = (
      metricType === "qubit" ? data?.data?.qubit_metrics : data?.data?.coupling_metrics
    ) as Record<string, Record<string, MetricValueLike>> | undefined;
    // The backend reports the bare_frequency config key as qubit_frequency.
    const schemaKey = metric.key === "bare_frequency" ? "qubit_frequency" : metric.key;
    return scaleMetricValues(source?.[schemaKey], metric.scale, metricType);
  }, [data, metric, metricType]);

  const colorRange = useMemo(() => {
    if (!metric) return null;
    const override = getStoredColorRanges(chipId)[metric.key];
    return resolveMetricColorRange(
      Object.values(metricData ?? {}).map((entry) => entry.value),
      metric.colorRange,
      metric.scale,
      override,
    );
  }, [chipId, metric, metricData]);

  const colors = colorScale.colors?.length ? colorScale.colors : FALLBACK_COLORS;

  if (!chipId) return <PanelMessage>Select a chip to show this panel</PanelMessage>;
  if (isConfigLoading || isLoading) return <PanelSkeleton />;
  if (!metric)
    return <PanelMessage tone="warning">Unknown metric: {metricKey || "none"}</PanelMessage>;
  if (isError) {
    return (
      <PanelMessage tone="error">
        {getApiErrorMessage(error, "Failed to load metrics")}
      </PanelMessage>
    );
  }

  const cellSize = fitCellSize(width, height, rows, cols);
  const hasValues = Object.values(metricData ?? {}).some((entry) => entry.value !== null);

  return (
    <div className="flex h-full min-h-0 flex-col gap-1">
      <div className="flex items-center justify-between gap-2 text-xs text-base-content/60">
        <span className="truncate">{metric.title}</span>
        <span className="shrink-0">
          {metric.unit ? `${metric.unit} · ` : ""}
          {SELECTION_MODES.find((entry) => entry.value === selectionMode)?.label ?? selectionMode}
        </span>
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-hidden">
        {hasValues ? (
          metricType === "qubit" ? (
            <QubitMetricGrid
              metricData={metricData}
              unit={metric.unit}
              topologyId={topologyId}
              colors={colors}
              colorRange={colorRange?.effective}
              maxCellSize={cellSize}
            />
          ) : (
            <CouplingMetricGrid
              metricData={metricData}
              unit={metric.unit}
              topologyId={topologyId}
              colors={colors}
              colorRange={colorRange?.effective}
              maxCellSize={cellSize}
            />
          )
        ) : (
          <PanelMessage>No values for {metric.title} on this chip</PanelMessage>
        )}
      </div>
    </div>
  );
}

export function QubitMetricPanel(props: MetricPanelProps) {
  return <MetricPanel {...props} metricType="qubit" />;
}

export function CouplingMetricPanel(props: MetricPanelProps) {
  return <MetricPanel {...props} metricType="coupling" />;
}
