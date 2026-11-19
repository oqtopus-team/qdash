import type { MetricCell, MetricCellStatus } from "@/schemas";

/** Trim a number for display without losing small magnitudes. */
export function formatNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 0.001 || abs >= 1e6)) return value.toExponential(3);
  return String(Number(value.toPrecision(6)));
}

/** Unit as shown next to a value; the SDK's `dimensionless` is shown as nothing. */
export function displayUnit(unit: string | null | undefined): string {
  if (!unit || unit === "dimensionless") return "";
  if (unit === "percent") return "%";
  return unit;
}

/** "Q5" for a qubit cell, "Q5 → Q6" for a directed pair. */
export function cellName(cell: Pick<MetricCell, "key" | "qid" | "source" | "target">): string {
  if (cell.source && cell.target) return `Q${cell.source} → Q${cell.target}`;
  return `Q${cell.qid ?? cell.key}`;
}

export const STATUS_LABELS: Record<MetricCellStatus, string> = {
  ok: "OK",
  missing: "Missing data",
  empty: "No result",
  error: "Error",
};

/** Short mark drawn in place of a value for cells without one. */
export const STATUS_GLYPHS: Record<MetricCellStatus, string> = {
  ok: "",
  missing: "–",
  empty: "∅",
  error: "!",
};

/** What a map tile or table shows for a cell's value: the number, else its status mark. */
export function cellValueText(cell: Pick<MetricCell, "status" | "value">): string {
  if (typeof cell.value === "number" && Number.isFinite(cell.value)) {
    return formatCompact(cell.value);
  }
  return cell.status === "ok" ? "–" : STATUS_GLYPHS[cell.status];
}

/** At most four significant digits, for tiles that have little room. */
export function formatCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 0.01 || abs >= 1e5)) return value.toExponential(1);
  if (abs >= 100) return value.toFixed(abs >= 1000 ? 0 : 1);
  return String(Number(value.toPrecision(3)));
}

/** Pluralized count: "1 cell", "3 cells". */
export function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
