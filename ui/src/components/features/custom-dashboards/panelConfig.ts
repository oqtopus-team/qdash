import { FileText, Grid3x3, Network, TriangleAlert, type LucideIcon } from "lucide-react";

import type {
  CollisionCheckInfo,
  DashboardPanelModel,
  DashboardPanelModelConfig,
  DashboardPanelModelType,
} from "@/schemas";

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

/** Config of a `collision_check` panel. */
export interface CollisionPanelConfig {
  check: string;
  params: Record<string, number>;
  hops: number[];
}

export const ALL_HOPS: readonly number[] = [1, 2];

export const PANEL_TYPES: ReadonlyArray<{
  value: DashboardPanelModelType;
  label: string;
  icon: LucideIcon;
}> = [
  { value: "qubit_metric", label: "Qubit metric", icon: Grid3x3 },
  { value: "coupling_metric", label: "Coupling metric", icon: Network },
  { value: "collision_check", label: "Frequency collision check", icon: TriangleAlert },
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

export function readMetricConfig(panel: DashboardPanelModel): MetricPanelConfig {
  const config = asRecord(panel.config);
  return {
    metric: typeof config.metric === "string" ? config.metric : "",
    selection_mode: isSelectionMode(config.selection_mode) ? config.selection_mode : "latest",
  };
}

export function readCollisionConfig(panel: DashboardPanelModel): CollisionPanelConfig {
  const config = asRecord(panel.config);
  const params: Record<string, number> = {};
  if (config.params && typeof config.params === "object") {
    for (const [name, value] of Object.entries(config.params as Record<string, unknown>)) {
      if (typeof value === "number" && Number.isFinite(value)) params[name] = value;
    }
  }
  const hops = Array.isArray(config.hops)
    ? ALL_HOPS.filter((hop) => (config.hops as unknown[]).includes(hop))
    : [...ALL_HOPS];
  return {
    check: typeof config.check === "string" ? config.check : "",
    params,
    hops: hops.length > 0 ? hops : [...ALL_HOPS],
  };
}

export function readMarkdownContent(panel: DashboardPanelModel): string {
  const config = asRecord(panel.config);
  return typeof config.content === "string" ? config.content : "";
}

function isSameNumber(a: number, b: number): boolean {
  return Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(b));
}

/**
 * Parameter overrides worth storing: values that parse to a finite number and
 * differ from the check's default. Unknown names and blank inputs are dropped.
 */
export function buildCollisionParams(
  check: CollisionCheckInfo | undefined,
  values: Record<string, string>,
): Record<string, number> {
  const params: Record<string, number> = {};
  if (!check) return params;
  for (const parameter of check.parameters) {
    const raw = values[parameter.name];
    if (raw === undefined || raw.trim() === "") continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || isSameNumber(value, parameter.default)) continue;
    params[parameter.name] = value;
  }
  return params;
}

/** Validation message for one parameter input, or null when it is acceptable. */
export function collisionParamError(
  parameter: CollisionCheckInfo["parameters"][number],
  raw: string | undefined,
): string | null {
  if (raw === undefined || raw.trim() === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return "Enter a number";
  if (parameter.min !== null && parameter.min !== undefined && value < parameter.min) {
    return `Must be at least ${parameter.min}`;
  }
  return null;
}

/** Trim a number for display without losing small magnitudes. */
export function formatNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 0.001 || abs >= 1e6)) return value.toExponential(3);
  return String(Number(value.toPrecision(6)));
}
