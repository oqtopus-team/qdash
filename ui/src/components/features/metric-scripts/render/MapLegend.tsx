"use client";

import type { MetricCellStatus, MetricLegend } from "@/schemas";

import { displayUnit, formatCompact, STATUS_GLYPHS, STATUS_LABELS } from "../format";
import { type CellColoring, countByLegend, FALLBACK_PALETTE } from "./legend";

const NON_OK: MetricCellStatus[] = ["missing", "empty", "error"];

function GradientBar({
  colors,
  min,
  max,
  unit,
}: {
  colors: readonly string[];
  min: number;
  max: number;
  unit: string;
}) {
  const gradient = `linear-gradient(to right, ${colors.join(", ")})`;
  return (
    <li className="flex items-center gap-1.5">
      <span className="font-mono tabular-nums">{formatCompact(min)}</span>
      <span
        className="inline-block h-2.5 w-24 rounded-sm"
        style={{ backgroundImage: gradient }}
        aria-hidden="true"
      />
      <span className="font-mono tabular-nums">{formatCompact(max)}</span>
      {unit && <span className="text-base-content/60">{unit}</span>}
    </li>
  );
}

interface MapLegendProps {
  legend: MetricLegend | null | undefined;
  coloring: CellColoring;
  /** Fill of every drawn cell, for counting categorical entries. */
  drawnColors: readonly string[];
  /** Cells drawn without a result, by colour (qubits the response has no cell for). */
  extra?: Readonly<Record<string, number>>;
  palette: readonly string[];
  unit: string;
  statusCounts: Record<MetricCellStatus, number>;
  /** Pair maps also explain the edge styles. */
  showHops?: boolean;
}

/** Colour key of a map: categorical entries with counts, or the value scale, and status marks. */
export function MapLegend({
  legend,
  coloring,
  drawnColors,
  extra,
  palette,
  unit,
  statusCounts,
  showHops = false,
}: MapLegendProps) {
  const shownUnit = displayUnit(unit);
  const stops =
    legend?.kind === "continuous"
      ? [...(legend.stops ?? [])].sort((a, b) => a.value - b.value)
      : [];
  return (
    <ul
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/70"
      aria-label="Legend"
    >
      {legend?.kind === "categorical" &&
        countByLegend(legend.items ?? [], drawnColors, extra).map((entry) => (
          <li key={`${entry.color}-${entry.label}`} className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ backgroundColor: entry.color }}
              aria-hidden="true"
            />
            <span>{entry.label}</span>
            <span className="font-mono tabular-nums text-base-content">{entry.count}</span>
          </li>
        ))}
      {stops.length > 0 && (
        <GradientBar
          colors={stops.map((stop) => stop.color)}
          min={stops[0].value}
          max={stops[stops.length - 1].value}
          unit={shownUnit}
        />
      )}
      {coloring.mode === "range" && coloring.range && (
        <GradientBar
          colors={palette.length > 0 ? palette : FALLBACK_PALETTE}
          min={coloring.range.min}
          max={coloring.range.max}
          unit={shownUnit}
        />
      )}
      {NON_OK.filter((status) => statusCounts[status] > 0).map((status) => (
        <li key={status} className="flex items-center gap-1" data-status={status}>
          <span
            className={`font-mono font-semibold ${status === "error" ? "text-error" : "text-base-content/60"}`}
            aria-hidden="true"
          >
            {STATUS_GLYPHS[status]}
          </span>
          <span>{STATUS_LABELS[status]}</span>
          <span className="font-mono tabular-nums text-base-content">{statusCounts[status]}</span>
        </li>
      ))}
      {showHops && (
        <li className="flex items-center gap-1.5 text-base-content/60">
          <svg width="22" height="6" aria-hidden="true">
            <line x1="0" y1="3" x2="22" y2="3" strokeWidth="2" className="stroke-base-content/60" />
          </svg>
          1 hop
          <svg width="22" height="6" aria-hidden="true">
            <line
              x1="0"
              y1="3"
              x2="22"
              y2="3"
              strokeWidth="2"
              strokeDasharray="5 4"
              className="stroke-base-content/60"
            />
          </svg>
          2 hops
        </li>
      )}
    </ul>
  );
}
