/**
 * Per-chip color range overrides for metric heatmaps, shared by the Dashboard
 * and Metrics pages and remembered per browser. A metric without an override
 * falls back to the YAML default and then to the data extent.
 */

import {
  type ColorRange,
  getValueExtent,
  isValidColorRange,
  scaleColorRange,
  unionColorRanges,
} from "@/lib/utils/color-scale";

const STORAGE_KEY_PREFIX = "qdash_metric_color_ranges:";

export type StoredColorRanges = Record<string, ColorRange>;

function storageKey(chipId: string): string {
  return `${STORAGE_KEY_PREFIX}${chipId}`;
}

export function getStoredColorRanges(chipId: string): StoredColorRanges {
  if (typeof window === "undefined" || !chipId) return {};
  try {
    const raw = localStorage.getItem(storageKey(chipId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const result: StoredColorRanges = {};
    for (const [metricKey, range] of Object.entries(parsed as Record<string, unknown>)) {
      if (isValidColorRange(range)) result[metricKey] = { min: range.min, max: range.max };
    }
    return result;
  } catch {
    return {};
  }
}

export function setStoredColorRanges(chipId: string, ranges: StoredColorRanges): void {
  if (typeof window === "undefined" || !chipId) return;
  try {
    if (Object.keys(ranges).length === 0) {
      localStorage.removeItem(storageKey(chipId));
    } else {
      localStorage.setItem(storageKey(chipId), JSON.stringify(ranges));
    }
  } catch {
    // Remembering the range is a convenience; the heatmap still updates.
  }
}

export interface ResolvedColorRange {
  /** Interval the heatmap maps onto the palette. */
  effective: ColorRange;
  /** Interval the reset action restores: the YAML default, else the data extent. */
  defaultRange: ColorRange;
  /** Whole interval the slider can cover. */
  bounds: ColorRange;
  /** True when the user moved the range away from the default. */
  isOverridden: boolean;
}

/**
 * Decide which interval a metric heatmap should map onto the palette.
 *
 * Priority: the user's override, then the YAML default (`color_range`, scaled
 * to display units), then the extent of the data. Returns null when there is no
 * data, since a slider over nothing has no meaning.
 */
export function resolveMetricColorRange(
  values: Iterable<number | null | undefined>,
  yamlDefault: ColorRange | null | undefined,
  scale: number,
  override: ColorRange | null | undefined,
): ResolvedColorRange | null {
  const extent = getValueExtent(values);
  if (!extent) return null;
  const scaledDefault =
    yamlDefault && isValidColorRange(yamlDefault) ? scaleColorRange(yamlDefault, scale) : null;
  const defaultRange = scaledDefault ?? extent;
  const effective = override && isValidColorRange(override) ? override : defaultRange;
  const bounds = unionColorRanges(extent, scaledDefault, effective) ?? extent;
  const isOverridden = effective.min !== defaultRange.min || effective.max !== defaultRange.max;
  return { effective, defaultRange, bounds, isOverridden };
}
