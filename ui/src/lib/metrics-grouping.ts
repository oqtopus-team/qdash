import type { GroupBase } from "react-select";

import { getMetricCategory } from "./metrics-categories";

import type { MetricConfig } from "@/hooks/useMetricsConfig";

/**
 * Option shape used by the metrics dropdown menus.
 */
export interface MetricOption {
  value: string;
  label: string;
}

/** Group used for metrics without a configured category. Always rendered last. */
const FALLBACK_CATEGORY = "Other";

/**
 * Group metric options by their UI category for use in react-select.
 *
 * Categories are resolved from the UI-side {@link METRIC_CATEGORIES} map keyed
 * by metric key — the backend metrics config carries no category, so the
 * grouping is purely a presentation concern. Categories are emitted in the
 * order they first appear in the provided metrics list (which follows the
 * backend config order), so the logical ordering is preserved. Metrics without
 * a configured category fall back to an "Other" group that is always placed
 * last.
 *
 * @param metrics - Metric configurations to group.
 * @returns Grouped options suitable for the react-select `options` prop.
 */
export function groupMetricsByCategory(metrics: MetricConfig[]): GroupBase<MetricOption>[] {
  const groups = new Map<string, MetricOption[]>();

  for (const metric of metrics) {
    const category = getMetricCategory(metric.key)?.trim() || FALLBACK_CATEGORY;
    const option: MetricOption = { value: metric.key, label: metric.title };
    const existing = groups.get(category);
    if (existing) {
      existing.push(option);
    } else {
      groups.set(category, [option]);
    }
  }

  // `Array.prototype.sort` is stable, so only the fallback group is reordered;
  // all other categories keep their first-seen order.
  return Array.from(groups.entries())
    .sort(([a], [b]) => {
      if (a === b) return 0;
      if (a === FALLBACK_CATEGORY) return 1;
      if (b === FALLBACK_CATEGORY) return -1;
      return 0;
    })
    .map(([label, options]) => ({ label, options }));
}
