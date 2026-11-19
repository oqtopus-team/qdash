"use client";

import { useId, useMemo } from "react";

import type { MetricCell, MetricScriptEvaluateResponse } from "@/schemas";

import { cellName, cellValueText, displayUnit, STATUS_LABELS } from "../format";
import { colorKey, countByStatus, createCellColoring } from "./legend";
import { MapLegend } from "./MapLegend";

const NO_PALETTE: readonly string[] = [];
import { CELL, MuxBoxes, onActivate, type Point, useTopologyLayout } from "./topologyLayout";

/** Gap between qubit tiles, wide enough for the arrows between them. */
const PAIR_GAP = 30;

export type PairDirection = "both" | "forward" | "reverse";

export const PAIR_DIRECTIONS: ReadonlyArray<{
  value: PairDirection;
  label: string;
  title: string;
}> = [
  { value: "both", label: "Both", title: "Show both directions of every pair" },
  { value: "forward", label: "Forward", title: "Show pairs whose source qubit has the lower ID" },
  { value: "reverse", label: "Reverse", title: "Show pairs whose source qubit has the higher ID" },
];

/** Whether a directed pair is shown under `direction`. */
export function matchesDirection(
  cell: Pick<MetricCell, "source" | "target">,
  direction: PairDirection,
): boolean {
  if (direction === "both") return true;
  const forward = Number(cell.source) < Number(cell.target);
  return (direction === "forward") === forward;
}

function unit(dx: number, dy: number): Point {
  const length = Math.hypot(dx, dy) || 1;
  return { x: dx / length, y: dy / length };
}

/** Distance from a square tile's centre to its edge along direction `u`. */
function squareInset(u: Point): number {
  return CELL / 2 / Math.max(Math.abs(u.x), Math.abs(u.y), 0.0001) + 2;
}

/**
 * SVG path of a directed edge between two qubit centres and a point on it. Each direction
 * sits on its own left-hand side, so the two edges of a pair never overlap. Edges that skip
 * over a qubit in the same row or column bow outwards to clear it.
 */
function edgeGeometry(
  from: Point,
  to: Point,
  hops: number,
  pitch: number,
): { path: string; mid: Point } {
  const u = unit(to.x - from.x, to.y - from.y);
  const normal = { x: u.y, y: -u.x };
  const distance = Math.hypot(to.x - from.x, to.y - from.y);
  const aligned = Math.abs(u.x) < 0.01 || Math.abs(u.y) < 0.01;
  if (aligned && distance > pitch * 1.5) {
    const bow = CELL * 1.4;
    const control = {
      x: (from.x + to.x) / 2 + normal.x * bow,
      y: (from.y + to.y) / 2 + normal.y * bow,
    };
    const startDir = unit(control.x - from.x, control.y - from.y);
    const endDir = unit(control.x - to.x, control.y - to.y);
    const start = {
      x: from.x + startDir.x * squareInset(startDir),
      y: from.y + startDir.y * squareInset(startDir),
    };
    const end = {
      x: to.x + endDir.x * squareInset(endDir),
      y: to.y + endDir.y * squareInset(endDir),
    };
    // Midpoint of the quadratic curve at t = 0.5.
    const mid = {
      x: 0.25 * start.x + 0.5 * control.x + 0.25 * end.x,
      y: 0.25 * start.y + 0.5 * control.y + 0.25 * end.y,
    };
    return { path: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`, mid };
  }
  const offset = hops >= 2 ? 8 : 5;
  const inset = squareInset(u);
  const start = {
    x: from.x + u.x * inset + normal.x * offset,
    y: from.y + u.y * inset + normal.y * offset,
  };
  const end = {
    x: to.x - u.x * inset + normal.x * offset,
    y: to.y - u.y * inset + normal.y * offset,
  };
  return {
    path: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
    mid: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 },
  };
}

function edgeLabel(cell: MetricCell, unitText: string): string {
  const value =
    typeof cell.value === "number"
      ? `${cellValueText(cell)}${unitText ? ` ${unitText}` : ""}`
      : STATUS_LABELS[cell.status];
  return [cellName(cell), value, cell.label].filter(Boolean).join(": ");
}

interface PairMapProps {
  result: MetricScriptEvaluateResponse;
  topologyId: string;
  /** Metrics colour scale, used when the metric declares no legend. */
  palette?: readonly string[];
  direction: PairDirection;
  /** Shows the direction toggle when set. */
  onDirectionChange?: (direction: PairDirection) => void;
  /** Pair distances to draw; all when omitted. */
  hops?: readonly number[];
  onSelectCell: (cell: MetricCell) => void;
}

/**
 * Chip topology with one directed edge per evaluated pair: solid for coupled pairs, dashed
 * for pairs two couplings apart. Cells without a value are drawn faded with their status.
 */
export function PairMap({
  result,
  topologyId,
  palette = NO_PALETTE,
  direction,
  onDirectionChange,
  hops,
  onSelectCell,
}: PairMapProps) {
  const markerPrefix = `pair-arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const layout = useTopologyLayout(topologyId, PAIR_GAP);
  const coloring = useMemo(() => createCellColoring(result, palette), [palette, result]);
  const unitText = displayUnit(result.metric.unit);

  const edges = useMemo(
    () =>
      result.cells.filter((cell) => {
        if (!cell.source || !cell.target) return false;
        if (!layout.positions.has(cell.source) || !layout.positions.has(cell.target)) return false;
        if (hops && !hops.includes(cell.hops ?? 1)) return false;
        return matchesDirection(cell, direction);
      }),
    [direction, hops, layout.positions, result.cells],
  );
  const edgeColors = useMemo(() => edges.map((cell) => coloring.colorOf(cell)), [coloring, edges]);
  const markerColors = useMemo(() => Array.from(new Set(edgeColors.map(colorKey))), [edgeColors]);

  if (layout.isLoading) {
    return <div className="skeleton h-full min-h-24 w-full" aria-label="Loading topology" />;
  }
  if (layout.positions.size === 0) {
    return (
      <p className="py-6 text-center text-sm text-base-content/60">
        The chip topology has no qubit positions to draw
      </p>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {onDirectionChange && (
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-base-content/60" id={`${markerPrefix}-direction`}>
            Direction
          </span>
          <div className="join" role="group" aria-labelledby={`${markerPrefix}-direction`}>
            {PAIR_DIRECTIONS.map((entry) => (
              <button
                key={entry.value}
                type="button"
                title={entry.title}
                aria-pressed={direction === entry.value}
                className={`btn btn-xs join-item ${direction === entry.value ? "btn-active" : ""}`}
                onClick={() => onDirectionChange(entry.value)}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </div>
      )}
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="min-h-0 w-full flex-1"
        role="group"
        aria-label={`${result.metric.title} on ${result.chip_id}`}
        data-testid="pair-map"
      >
        <defs>
          {markerColors.map((color, index) => (
            <marker
              key={color}
              id={`${markerPrefix}-${index}`}
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="4"
              markerHeight="4"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
            </marker>
          ))}
        </defs>

        <MuxBoxes boxes={layout.muxBoxes} />

        {Array.from(layout.positions.entries()).map(([qid, pos]) => (
          <g key={qid} data-qid={qid}>
            <rect
              x={pos.x}
              y={pos.y}
              width={CELL}
              height={CELL}
              rx={6}
              strokeWidth={1}
              className="fill-base-200 stroke-base-300"
            />
            <text
              x={pos.x + CELL / 2}
              y={pos.y + CELL / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={12}
              className="fill-base-content font-mono"
            >
              {qid}
            </text>
          </g>
        ))}

        {edges.map((cell, index) => {
          const from = layout.positions.get(cell.source ?? "");
          const to = layout.positions.get(cell.target ?? "");
          if (!from || !to) return null;
          const hopCount = cell.hops ?? 1;
          const { path, mid } = edgeGeometry(
            { x: from.x + CELL / 2, y: from.y + CELL / 2 },
            { x: to.x + CELL / 2, y: to.y + CELL / 2 },
            hopCount,
            layout.pitch,
          );
          const color = edgeColors[index];
          const markerIndex = markerColors.indexOf(colorKey(color));
          const label = edgeLabel(cell, unitText);
          const faded = cell.status !== "ok" && typeof cell.value !== "number" && !cell.color;
          return (
            <g
              key={cell.key}
              data-edge-key={cell.key}
              role="button"
              tabIndex={0}
              aria-label={label}
              className="group cursor-pointer outline-none"
              onClick={() => onSelectCell(cell)}
              onKeyDown={onActivate(() => onSelectCell(cell))}
            >
              <title>{label}</title>
              <path d={path} fill="none" stroke="transparent" strokeWidth={10} />
              <path
                d={path}
                fill="none"
                stroke={color}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeOpacity={faded ? 0.55 : 1}
                strokeDasharray={hopCount >= 2 ? "5 4" : undefined}
                markerEnd={markerIndex >= 0 ? `url(#${markerPrefix}-${markerIndex})` : undefined}
                className="transition-opacity group-hover:opacity-70 group-focus-visible:opacity-70"
                data-testid={`metric-edge-${cell.key}`}
                data-hops={hopCount}
                data-status={cell.status}
              />
              {cell.status === "error" && (
                <g aria-hidden="true">
                  <circle cx={mid.x} cy={mid.y} r={6} className="fill-error" />
                  <text
                    x={mid.x}
                    y={mid.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={9}
                    fontWeight={700}
                    className="fill-error-content"
                  >
                    !
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
      <MapLegend
        legend={result.legend}
        coloring={coloring}
        drawnColors={edgeColors}
        palette={palette}
        unit={result.metric.unit}
        statusCounts={countByStatus(edges)}
        showHops
      />
    </div>
  );
}
