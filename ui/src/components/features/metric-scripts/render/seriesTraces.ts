import type { MetricCell, MetricSeriesPoint } from "@/schemas";
import { type ChartTheme, seriesColor } from "@/lib/chartTheme";

import { formatTarget } from "../targets";

/** A UTC instant as Plotly date text ("2026-11-12 06:00:00"); Plotly ignores offsets. */
export function utcPlotTime(iso: string): string {
  return new Date(iso).toISOString().slice(0, 19).replace("T", " ");
}

/** "2026-11-12 06:00" in UTC. */
function utcMinute(iso: string): string {
  return utcPlotTime(iso).slice(0, 16);
}

/**
 * What a point's observation count means. One observation is said as such: a median of one
 * value is that value, which a reader should know before trusting a trend.
 */
export function describeCount(count: number | null | undefined): string {
  if (count === null || count === undefined) return "observations not reported";
  if (count === 1) return "n = 1 (one observation)";
  return `n = ${count} observations`;
}

/** The time a point covers: its bin when the script reported one, else its timestamp. */
export function describeBin(point: MetricSeriesPoint): string {
  if (point.start && point.end) return `${utcMinute(point.start)} – ${utcMinute(point.end)} UTC`;
  return `${utcMinute(point.timestamp)} UTC`;
}

/** "Q0 → Q1 (%)": the target and the unit, as the legend shows it. */
function seriesName(cell: MetricCell, unit: string): string {
  return unit ? `${formatTarget(cell.key)} (${unit})` : formatTarget(cell.key);
}

export interface SeriesTrace {
  type: "scatter";
  mode: "lines+markers";
  name: string;
  x: string[];
  /** Null for a gap; with `connectgaps: false` the line breaks there instead of joining. */
  y: (number | null)[];
  connectgaps: false;
  line: { color: string; width: number };
  marker: { color: string; size: number };
  customdata: string[][];
  hovertemplate: string;
}

/** Cells that drew at least one point, in the order the server returned them. */
export function plottedCells(cells: readonly MetricCell[]): MetricCell[] {
  return cells.filter((cell) => (cell.series ?? []).some((point) => point.status === "ok"));
}

/**
 * One line per target with a categorical series color (the color names the target, not a
 * verdict), null at every gap so the line breaks, and a tooltip with the bin, value, unit and
 * observation count of each point.
 */
export function buildSeriesTraces(
  cells: readonly MetricCell[],
  unit: string,
  theme: ChartTheme,
): SeriesTrace[] {
  return plottedCells(cells).map((cell, index) => {
    const points = cell.series ?? [];
    const color = seriesColor(theme, index);
    const name = seriesName(cell, unit);
    return {
      type: "scatter",
      mode: "lines+markers",
      name,
      x: points.map((point) => utcPlotTime(point.timestamp)),
      y: points.map((point) =>
        point.status === "ok" && typeof point.value === "number" ? point.value : null,
      ),
      connectgaps: false,
      line: { color, width: 2 },
      marker: { color, size: 6 },
      customdata: points.map((point) => [
        describeBin(point),
        describeCount(point.count),
        escapeHover(point.reason ?? ""),
      ]),
      hovertemplate:
        `<b>${escapeHover(name)}</b><br>%{customdata[0]}<br>%{y:.4~g}${unit ? ` ${escapeHover(unit)}` : ""}` +
        "<br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>",
    };
  });
}

/** Plotly reads tags in hover text; script-chosen text must not become markup. */
function escapeHover(text: string): string {
  return text.replace(/[&<>"]/g, (char) => `&#${char.charCodeAt(0)};`);
}

/** Gaps by status for one target, such as "3 without data". Empty when there is none. */
export function describeGaps(points: readonly MetricSeriesPoint[]): string {
  const noData = points.filter((point) => point.status === "no_data").length;
  const insufficient = points.filter((point) => point.status === "insufficient").length;
  return [
    noData ? `${noData} without data` : "",
    insufficient ? `${insufficient} with too few observations` : "",
  ]
    .filter(Boolean)
    .join(", ");
}
