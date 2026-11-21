import type { MetricInfo, MetricScriptSummary } from "@/schemas";
import { displayUnit } from "@/components/features/metric-scripts/format";

/**
 * One thing a metric panel can show, independent of where it comes from: a configured qubit
 * or coupling metric, or a metric of a saved script. The panel type follows from the choice.
 */
export type MetricChoice =
  | { kind: "qubit_metric"; metric: string }
  | { kind: "coupling_metric"; metric: string }
  | { kind: "metric_script"; script_id: string; metric_id: string };

export interface MetricChoiceOption {
  value: string;
  label: string;
  choice: MetricChoice;
}

/** Options grouped by source, in the order a `<select>` lists them. */
export interface MetricChoiceGroup {
  key: string;
  label: string;
  options: MetricChoiceOption[];
}

/** A configured chip metric, as `useMetricsConfig` lists them. */
interface ConfiguredMetric {
  key: string;
  title: string;
  unit?: string | null;
}

/** Not used by chip metric keys, script IDs or Python metric identifiers. */
const SEPARATOR = "|";

/** Stable `<option>` value of a choice; `parseChoiceValue` reads it back. */
export function choiceValue(choice: MetricChoice): string {
  if (choice.kind === "metric_script") {
    return [choice.kind, choice.script_id, choice.metric_id].join(SEPARATOR);
  }
  return [choice.kind, choice.metric].join(SEPARATOR);
}

export function parseChoiceValue(value: string): MetricChoice | null {
  const [kind, ...rest] = value.split(SEPARATOR);
  if (kind === "qubit_metric" || kind === "coupling_metric") {
    return rest.length === 1 && rest[0] ? { kind, metric: rest[0] } : null;
  }
  if (kind === "metric_script" && rest.length === 2 && rest[0] && rest[1]) {
    return { kind, script_id: rest[0], metric_id: rest[1] };
  }
  return null;
}

function configuredLabel(metric: ConfiguredMetric): string {
  return metric.unit ? `${metric.title} (${metric.unit})` : metric.title;
}

/** "Median ZX90 gate fidelity (%) · per pair": the title, unit and target of a script metric. */
export function scriptMetricLabel(metric: MetricInfo): string {
  const unit = displayUnit(metric.unit);
  const target = metric.target === "pair" ? "per pair" : "per qubit";
  return `${metric.title}${unit ? ` (${unit})` : ""} · ${target}`;
}

export interface MetricChoiceSources {
  qubitMetrics: ConfiguredMetric[];
  couplingMetrics: ConfiguredMetric[];
  /** Scripts the caller can see; only those with a valid active revision are offered. */
  scripts: MetricScriptSummary[];
  /**
   * The catalog to list for one script instead of its active one, e.g. the pinned revision of
   * the panel being edited, so a metric that a later revision dropped stays selectable.
   */
  pinnedCatalog?: { script_id: string; metrics: MetricInfo[]; label?: string } | null;
}

/**
 * Every metric a panel can show, grouped by source: the configured qubit and coupling
 * metrics first, then one group per script. Scripts without a valid revision are left out,
 * except the one whose pinned catalog is supplied.
 */
export function metricChoiceGroups(sources: MetricChoiceSources): MetricChoiceGroup[] {
  const groups: MetricChoiceGroup[] = [];
  const configured = (
    kind: "qubit_metric" | "coupling_metric",
    label: string,
    metrics: ConfiguredMetric[],
  ) => {
    if (metrics.length === 0) return;
    groups.push({
      key: kind,
      label,
      options: metrics.map((metric) => {
        const choice: MetricChoice = { kind, metric: metric.key };
        return { value: choiceValue(choice), label: configuredLabel(metric), choice };
      }),
    });
  };
  configured("qubit_metric", "Qubit metrics", sources.qubitMetrics);
  configured("coupling_metric", "Coupling metrics", sources.couplingMetrics);

  const pinned = sources.pinnedCatalog ?? null;
  const seen = new Set<string>();
  const scriptGroup = (script_id: string, label: string, metrics: MetricInfo[]) => {
    if (seen.has(script_id) || metrics.length === 0) return;
    seen.add(script_id);
    groups.push({
      key: `script:${script_id}`,
      label,
      options: metrics.map((metric) => {
        const choice: MetricChoice = { kind: "metric_script", script_id, metric_id: metric.id };
        return { value: choiceValue(choice), label: scriptMetricLabel(metric), choice };
      }),
    });
  };
  for (const script of sources.scripts) {
    const name = script.visibility === "private" ? `${script.name} (private)` : script.name;
    if (pinned && pinned.script_id === script.script_id) {
      scriptGroup(script.script_id, pinned.label ?? name, pinned.metrics);
      continue;
    }
    if (script.active_revision === null) continue;
    scriptGroup(script.script_id, name, script.metrics);
  }
  if (pinned && !seen.has(pinned.script_id)) {
    scriptGroup(pinned.script_id, pinned.label ?? pinned.script_id, pinned.metrics);
  }
  return groups;
}

export function findChoiceOption(
  groups: MetricChoiceGroup[],
  choice: MetricChoice | null,
): MetricChoiceOption | undefined {
  if (!choice) return undefined;
  const value = choiceValue(choice);
  for (const group of groups) {
    const option = group.options.find((entry) => entry.value === value);
    if (option) return option;
  }
  return undefined;
}
