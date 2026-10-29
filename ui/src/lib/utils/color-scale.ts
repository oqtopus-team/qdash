/**
 * Shared value-to-color mapping for metric heatmaps.
 *
 * Every heatmap (dashboard and Metrics page) maps a numeric value onto the same
 * ordered palette. The palette itself comes from `config/domain/metrics.yaml`;
 * this module only decides where in the palette a value lands.
 */

/** Inclusive numeric interval that spans the whole palette. */
export interface ColorRange {
  min: number;
  max: number;
}

/** Linear blend between two `#rrggbb` colors. `factor` runs from 0 (c1) to 1 (c2). */
export function interpolateColor(c1: string, c2: string, factor: number): string {
  const a = parseInt(c1.slice(1), 16);
  const b = parseInt(c2.slice(1), 16);
  const ar = (a >> 16) & 0xff;
  const ag = (a >> 8) & 0xff;
  const ab = a & 0xff;
  const br = (b >> 16) & 0xff;
  const bg = (b >> 8) & 0xff;
  const bb = b & 0xff;
  const r = Math.round(ar + (br - ar) * factor);
  const g = Math.round(ag + (bg - ag) * factor);
  const bl = Math.round(ab + (bb - ab) * factor);
  return `#${((1 << 24) + (r << 16) + (g << 8) + bl).toString(16).slice(1)}`;
}

/**
 * Pick the palette color for `value` within `[min, max]`. Values outside the
 * range clamp to the palette ends. Returns null when the palette is empty.
 */
export function pickColor(
  value: number,
  min: number,
  max: number,
  colors: string[],
): string | null {
  if (colors.length === 0) return null;
  if (min === max) return colors[colors.length - 1];
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const pos = t * (colors.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, colors.length - 1);
  const f = pos - lo;
  if (f === 0 || lo === hi) return colors[lo];
  return interpolateColor(colors[lo], colors[hi], f);
}

/** Min and max of the finite numbers in `values`, or null when there are none. */
export function getValueExtent(values: Iterable<number | null | undefined>): ColorRange | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const v of values) {
    if (typeof v !== "number" || !Number.isFinite(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (min === Number.POSITIVE_INFINITY) return null;
  return { min, max };
}

/** True when `range` has finite bounds in increasing order. */
export function isValidColorRange(range: unknown): range is ColorRange {
  if (!range || typeof range !== "object") return false;
  const { min, max } = range as Partial<ColorRange>;
  return (
    typeof min === "number" &&
    typeof max === "number" &&
    Number.isFinite(min) &&
    Number.isFinite(max) &&
    min < max
  );
}

/** Multiply both bounds by `scale`, keeping min below max when `scale` is negative. */
export function scaleColorRange(range: ColorRange, scale: number): ColorRange {
  const a = range.min * scale;
  const b = range.max * scale;
  return a <= b ? { min: a, max: b } : { min: b, max: a };
}

/** Smallest interval that contains every given range. */
export function unionColorRanges(...ranges: (ColorRange | null | undefined)[]): ColorRange | null {
  let result: ColorRange | null = null;
  for (const r of ranges) {
    if (!r) continue;
    result = result
      ? { min: Math.min(result.min, r.min), max: Math.max(result.max, r.max) }
      : { ...r };
  }
  return result;
}

/**
 * Slider step for `range`: about 200 stops across the span, rounded down to a
 * power of ten so the displayed numbers stay short.
 */
export function colorRangeStep(range: ColorRange): number {
  const span = range.max - range.min;
  if (!(span > 0)) return 1;
  const raw = span / 200;
  return 10 ** Math.floor(Math.log10(raw));
}

/** Format a bound with just enough digits to distinguish it at `step` resolution. */
export function formatRangeValue(value: number, step: number): string {
  if (!Number.isFinite(value)) return "";
  const decimals = step >= 1 ? 0 : Math.min(6, Math.max(0, -Math.floor(Math.log10(step))));
  return value.toFixed(decimals);
}
