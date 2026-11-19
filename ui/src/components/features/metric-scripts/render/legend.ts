import type { LegendItem, LegendStop, MetricCell, MetricCellStatus, MetricLegend } from "@/schemas";
import {
  type ColorRange,
  getValueExtent,
  interpolateColor,
  pickColor,
} from "@/lib/utils/color-scale";

/** Fill of a cell without a value or colour; matches the templates' "Not evaluated" grey. */
export const NOT_EVALUATED_COLOR = "#737373";

/** Palette used when the metrics configuration has none (viridis ends). */
export const FALLBACK_PALETTE = ["#440154", "#31688e", "#35b779", "#fde724"];

/** `#rrggbb` for a `#rgb` or `#rrggbb` colour, else null. */
function normalizeHex(color: string): string | null {
  const value = color.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(value)) return value;
  if (/^#[0-9a-f]{3}$/.test(value)) {
    return `#${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`;
  }
  return null;
}

/** Key for comparing colours written differently, such as `#FFF` and `#ffffff`. */
export function colorKey(color: string): string {
  return normalizeHex(color) ?? color.trim().toLowerCase();
}

/**
 * Colour of `value` on a continuous legend: linear between the surrounding stops, clamped to
 * the end stops. Stops that are not hex colours are used as they are, without blending.
 */
export function continuousColor(stops: readonly LegendStop[], value: number): string {
  const sorted = [...stops].sort((a, b) => a.value - b.value);
  if (sorted.length === 0) return NOT_EVALUATED_COLOR;
  if (value <= sorted[0].value) return sorted[0].color;
  const last = sorted[sorted.length - 1];
  if (value >= last.value) return last.color;
  for (let index = 1; index < sorted.length; index += 1) {
    const upper = sorted[index];
    if (value > upper.value) continue;
    const lower = sorted[index - 1];
    const span = upper.value - lower.value;
    const from = normalizeHex(lower.color);
    const to = normalizeHex(upper.color);
    if (span <= 0 || !from || !to) return lower.color;
    return interpolateColor(from, to, (value - lower.value) / span);
  }
  return last.color;
}

function finiteValue(cell: Pick<MetricCell, "value">): number | null {
  return typeof cell.value === "number" && Number.isFinite(cell.value) ? cell.value : null;
}

/** How the cells of one result get their colours. */
export interface CellColoring {
  /**
   * `continuous`: the metric's legend stops; `range`: the palette over the values' extent;
   * `categorical`: the metric's own colours with a categorical legend; `none`: no values.
   */
  mode: "categorical" | "continuous" | "range" | "none";
  /** The extent the palette spans in `range` mode. */
  range: ColorRange | null;
  colorOf: (cell: MetricCell) => string;
}

/**
 * Colour each cell: the colour the script returned, else the continuous legend at its value,
 * else the metrics colour scale over the range of all values. Cells without either are grey.
 */
export function createCellColoring(
  result: { legend?: MetricLegend | null; cells: readonly MetricCell[] },
  palette: readonly string[],
): CellColoring {
  const legend = result.legend ?? null;
  const stops = legend?.kind === "continuous" ? (legend.stops ?? []) : [];
  const range = getValueExtent(result.cells.map(finiteValue));
  const colors = palette.length > 0 ? [...palette] : FALLBACK_PALETTE;
  const valueColor = (value: number): string => {
    if (stops.length > 0) return continuousColor(stops, value);
    if (range) return pickColor(value, range.min, range.max, colors) ?? NOT_EVALUATED_COLOR;
    return NOT_EVALUATED_COLOR;
  };
  const mode: CellColoring["mode"] =
    legend?.kind === "categorical"
      ? "categorical"
      : stops.length > 0
        ? "continuous"
        : range
          ? "range"
          : "none";
  return {
    mode,
    range: mode === "range" ? range : null,
    colorOf: (cell) => {
      if (cell.color) return cell.color;
      const value = finiteValue(cell);
      return value === null ? NOT_EVALUATED_COLOR : valueColor(value);
    },
  };
}

export interface LegendCount extends LegendItem {
  count: number;
}

/**
 * Categorical legend entries with how many cells are drawn in each colour. `extra` adds
 * cells that are drawn without a result, such as qubits the response has no cell for.
 */
export function countByLegend(
  items: readonly LegendItem[],
  colors: readonly string[],
  extra: Readonly<Record<string, number>> = {},
): LegendCount[] {
  const counts = new Map<string, number>();
  for (const color of colors) {
    const key = colorKey(color);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  for (const [color, count] of Object.entries(extra)) {
    const key = colorKey(color);
    counts.set(key, (counts.get(key) ?? 0) + count);
  }
  return items.map((item) => ({ ...item, count: counts.get(colorKey(item.color)) ?? 0 }));
}

/** Cells per status, every status present. */
export function countByStatus(
  cells: readonly Pick<MetricCell, "status">[],
): Record<MetricCellStatus, number> {
  const counts: Record<MetricCellStatus, number> = { ok: 0, missing: 0, empty: 0, error: 0 };
  for (const cell of cells) counts[cell.status] += 1;
  return counts;
}

/** Black or white, whichever reads better on `background`. */
export function readableTextColor(background: string): string {
  const hex = normalizeHex(background);
  if (!hex) return "#ffffff";
  const channel = (offset: number) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
  return luminance > 0.4 ? "#111827" : "#ffffff";
}
