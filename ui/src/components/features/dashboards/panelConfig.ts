import { FileCode, FileText, Grid3x3, Network, type LucideIcon } from "lucide-react";

import type {
  DashboardPanelModel,
  DashboardPanelModelConfig,
  DashboardPanelModelType,
} from "@/schemas";
import type { ParamValue } from "@/components/features/metric-scripts/parameters";
import {
  type MetricPeriod,
  periodError,
  readPeriod,
} from "@/components/features/metric-scripts/periods";
import type { ResultViewMode } from "@/components/features/metric-scripts/render/MetricResultView";
import type { PairDirection } from "@/components/features/metric-scripts/render/PairMap";

export type MetricSelectionMode = "latest" | "best" | "average";

export const SELECTION_MODES: ReadonlyArray<{ value: MetricSelectionMode; label: string }> = [
  { value: "latest", label: "Latest" },
  { value: "best", label: "Best" },
  { value: "average", label: "Average" },
];

/** Config of a `qubit_metric` or `coupling_metric` panel. `selection_mode` is UI-only. */
export interface MetricPanelConfig {
  metric: string;
  selection_mode: MetricSelectionMode;
}

/**
 * Config of a `metric_script` panel, as the API's `MetricScriptPanelConfig` defines it.
 * `script_revision` is null only while a stored config lacks it; such a panel cannot be saved.
 */
export interface MetricScriptPanelConfig {
  script_id: string;
  metric_id: string;
  script_revision: number | null;
  period: MetricPeriod;
  params: Record<string, ParamValue>;
  view: ResultViewMode;
  direction: PairDirection;
  hops: number[];
}

const KNOWN_HOPS = [1, 2];

const PANEL_TYPES: ReadonlyArray<{
  value: DashboardPanelModelType;
  label: string;
  icon: LucideIcon;
}> = [
  { value: "qubit_metric", label: "Qubit metric", icon: Grid3x3 },
  { value: "coupling_metric", label: "Coupling metric", icon: Network },
  { value: "metric_script", label: "Metric script", icon: FileCode },
  { value: "markdown", label: "Markdown note", icon: FileText },
];

export function panelTypeMeta(type: DashboardPanelModelType) {
  return PANEL_TYPES.find((entry) => entry.value === type) ?? PANEL_TYPES[0];
}

function asRecord(config: DashboardPanelModelConfig | undefined): Record<string, unknown> {
  return config && typeof config === "object" ? config : {};
}

function isSelectionMode(value: unknown): value is MetricSelectionMode {
  return value === "latest" || value === "best" || value === "average";
}

export function readMetricConfig(panel: Pick<DashboardPanelModel, "config">): MetricPanelConfig {
  const config = asRecord(panel.config);
  return {
    metric: typeof config.metric === "string" ? config.metric : "",
    selection_mode: isSelectionMode(config.selection_mode) ? config.selection_mode : "latest",
  };
}

function isParamValue(value: unknown): value is ParamValue {
  return (
    typeof value === "boolean" ||
    typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}

/** A `metric_script` panel's config, with defaults for anything missing or malformed. */
export function readMetricScriptConfig(
  panel: Pick<DashboardPanelModel, "config">,
): MetricScriptPanelConfig {
  const config = asRecord(panel.config);
  const params: Record<string, ParamValue> = {};
  if (config.params && typeof config.params === "object") {
    for (const [name, value] of Object.entries(config.params as Record<string, unknown>)) {
      if (isParamValue(value)) params[name] = value;
    }
  }
  const hops = Array.isArray(config.hops)
    ? KNOWN_HOPS.filter((hop) => (config.hops as unknown[]).includes(hop))
    : [...KNOWN_HOPS];
  const revision = config.script_revision;
  return {
    script_id: typeof config.script_id === "string" ? config.script_id : "",
    metric_id: typeof config.metric_id === "string" ? config.metric_id : "",
    script_revision:
      typeof revision === "number" && Number.isInteger(revision) && revision >= 1 ? revision : null,
    period: readPeriod(config.period),
    params,
    view: config.view === "table" ? "table" : "map",
    direction:
      config.direction === "forward" || config.direction === "reverse" ? config.direction : "both",
    hops: hops.length > 0 ? hops : [...KNOWN_HOPS],
  };
}

/** Why a `metric_script` config cannot be saved, or null when it can. */
export function metricScriptConfigError(config: MetricScriptPanelConfig): string | null {
  if (!config.script_id) return "Choose a script";
  if (config.script_revision === null) return "The script has no valid revision to pin";
  if (!config.metric_id) return "Choose a metric";
  if (config.hops.length === 0) return "Choose at least one pair distance";
  return periodError(config.period);
}

/**
 * The stored form of a `metric_script` config. The API rejects unknown keys for this panel
 * type, so only the fields of `MetricScriptPanelConfig` are written.
 */
export function writeMetricScriptConfig(
  config: MetricScriptPanelConfig,
): DashboardPanelModelConfig {
  return {
    script_id: config.script_id,
    metric_id: config.metric_id,
    script_revision: config.script_revision,
    period: config.period,
    params: config.params,
    view: config.view,
    direction: config.direction,
    hops: config.hops,
  };
}

export function readMarkdownContent(panel: Pick<DashboardPanelModel, "config">): string {
  const config = asRecord(panel.config);
  return typeof config.content === "string" ? config.content : "";
}
