"use client";

import { type KeyboardEvent, useId, useMemo, useState } from "react";

import type { CollisionCellResponse, CollisionEvaluateResponse } from "@/schemas";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";

import { topologyGridDimensions } from "./useElementSize";

/** Fill of a qubit the response has no cell for; matches the API's "Not evaluated" colour. */
export const NOT_EVALUATED_COLOR = "#737373";

const CELL = 40;
const PAD = 8;
/** Gap between qubits: tight for qubit heatmaps, wide enough for arrows on pair maps. */
const QUBIT_GAP = 4;
const PAIR_GAP = 30;

type Direction = "both" | "forward" | "reverse";

const DIRECTIONS: ReadonlyArray<{ value: Direction; label: string; title: string }> = [
  { value: "both", label: "Both", title: "Show both directions of every pair" },
  {
    value: "forward",
    label: "Forward",
    title: "Show pairs whose control qubit has the lower ID",
  },
  {
    value: "reverse",
    label: "Reverse",
    title: "Show pairs whose control qubit has the higher ID",
  },
];

interface Point {
  x: number;
  y: number;
}

/** Legend entries with the number of cells drawn in each colour. */
function countCellsByLegend(
  response: Pick<CollisionEvaluateResponse, "legend" | "cells" | "target">,
  missingQubits = 0,
): Array<{ color: string; label: string; count: number }> {
  const counts = new Map<string, number>();
  for (const cell of response.cells) {
    const color = cell.color.toLowerCase();
    counts.set(color, (counts.get(color) ?? 0) + 1);
  }
  if (missingQubits > 0) {
    const key = NOT_EVALUATED_COLOR.toLowerCase();
    counts.set(key, (counts.get(key) ?? 0) + missingQubits);
  }
  return response.legend.map((entry) => ({
    ...entry,
    count: counts.get(entry.color.toLowerCase()) ?? 0,
  }));
}

/** Two significant decimals, or "N/A" when the check could not be evaluated. */
function formatCollisionValue(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "N/A";
}

function cellAriaLabel(cell: CollisionCellResponse): string {
  const name =
    cell.source && cell.target ? `Q${cell.source} to Q${cell.target}` : `Q${cell.qid ?? cell.key}`;
  return `${name}: ${cell.label}`;
}

function onActivate(handler: () => void) {
  return (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler();
    }
  };
}

function unit(dx: number, dy: number): Point {
  const length = Math.hypot(dx, dy) || 1;
  return { x: dx / length, y: dy / length };
}

/** Distance from a square cell's centre to its edge along direction `u`. */
function squareInset(u: Point): number {
  return CELL / 2 / Math.max(Math.abs(u.x), Math.abs(u.y), 0.0001) + 2;
}

/**
 * SVG path of a directed edge between two qubit centres. Each direction sits
 * on its own left-hand side, so the two edges of a pair never overlap. Edges
 * that skip over a qubit in the same row or column bow outwards to clear it.
 */
function edgePath(from: Point, to: Point, hops: number, pitch: number): string {
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
    return `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`;
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
  return `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
}

interface CollisionMapProps {
  response: CollisionEvaluateResponse;
  topologyId: string;
  onSelectCell: (cell: CollisionCellResponse) => void;
}

/**
 * Chip topology coloured by one collision check. Qubit checks colour each
 * qubit; pair checks draw one directed edge per evaluated pair, solid for
 * nearest neighbours and dashed for pairs two couplings apart.
 */
export function CollisionMap({ response, topologyId, onSelectCell }: CollisionMapProps) {
  const markerPrefix = `collision-arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const [direction, setDirection] = useState<Direction>("both");
  const {
    qubits,
    gridSize,
    muxGroups = [],
    hasMux = false,
    showMuxBoundaries = false,
    isLoading,
  } = useTopologyConfig(topologyId);

  const isPair = response.target === "pair";
  const gap = isPair ? PAIR_GAP : QUBIT_GAP;
  const pitch = CELL + gap;
  const { rows, cols } = topologyGridDimensions(qubits, gridSize);
  const width = cols * CELL + (cols - 1) * gap + PAD * 2;
  const height = rows * CELL + (rows - 1) * gap + PAD * 2;

  const positions = useMemo(() => {
    const map = new Map<string, Point & { row: number; col: number }>();
    for (const [qid, pos] of Object.entries(qubits ?? {})) {
      map.set(String(Number(qid)), {
        row: pos.row,
        col: pos.col,
        x: PAD + pos.col * pitch,
        y: PAD + pos.row * pitch,
      });
    }
    return map;
  }, [qubits, pitch]);

  const qubitCells = useMemo(() => {
    const map = new Map<string, CollisionCellResponse>();
    if (isPair) return map;
    for (const cell of response.cells) {
      const qid = cell.qid ?? cell.key.replace(/^Q/, "");
      map.set(String(Number(qid)), cell);
    }
    return map;
  }, [isPair, response.cells]);

  const edgeCells = useMemo(() => {
    if (!isPair) return [];
    return response.cells.filter((cell) => {
      if (!cell.source || !cell.target) return false;
      if (!positions.has(cell.source) || !positions.has(cell.target)) return false;
      const forward = Number(cell.source) < Number(cell.target);
      return direction === "both" || (direction === "forward") === forward;
    });
  }, [direction, isPair, positions, response.cells]);

  const markerColors = useMemo(
    () => Array.from(new Set(response.cells.map((cell) => cell.color.toLowerCase()))),
    [response.cells],
  );

  const missingQubits = isPair
    ? 0
    : Array.from(positions.keys()).filter((qid) => !qubitCells.has(qid)).length;
  const legend = countCellsByLegend(response, missingQubits);

  if (isLoading) {
    return <div className="skeleton h-full min-h-24 w-full" aria-label="Loading topology" />;
  }
  if (positions.size === 0) {
    return (
      <p className="py-6 text-center text-sm text-base-content/60">
        The chip topology has no qubit positions to draw
      </p>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {isPair && (
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-base-content/60" id={`${markerPrefix}-direction`}>
            Direction
          </span>
          <div className="join" role="group" aria-labelledby={`${markerPrefix}-direction`}>
            {DIRECTIONS.map((entry) => (
              <button
                key={entry.value}
                type="button"
                title={entry.title}
                aria-pressed={direction === entry.value}
                className={`btn btn-xs join-item ${direction === entry.value ? "btn-active" : ""}`}
                onClick={() => setDirection(entry.value)}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="min-h-0 w-full flex-1"
        role="group"
        aria-label={`${response.title} on ${response.chip_id}`}
        data-testid="collision-map"
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

        {hasMux &&
          showMuxBoundaries &&
          muxGroups.map((box) => (
            <rect
              key={box.muxId}
              x={PAD + box.minCol * pitch - gap / 2 + 1}
              y={PAD + box.minRow * pitch - gap / 2 + 1}
              width={(box.maxCol - box.minCol + 1) * pitch - 2}
              height={(box.maxRow - box.minRow + 1) * pitch - 2}
              rx={6}
              fill="none"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              className={box.isEven ? "stroke-primary/30" : "stroke-secondary/30"}
            >
              <title>{`MUX${box.muxId}`}</title>
            </rect>
          ))}

        {Array.from(positions.entries()).map(([qid, pos]) => {
          if (isPair) {
            return (
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
            );
          }
          const cell = qubitCells.get(qid);
          const fill = cell?.color ?? NOT_EVALUATED_COLOR;
          const content = (
            <>
              <rect
                x={pos.x}
                y={pos.y}
                width={CELL}
                height={CELL}
                rx={6}
                fill={fill}
                strokeWidth={2}
                className={
                  cell
                    ? "stroke-transparent group-hover:stroke-base-content group-focus-visible:stroke-base-content"
                    : "stroke-transparent"
                }
                data-testid={`collision-qubit-${qid}`}
              />
              <text
                x={pos.x + 3}
                y={pos.y + 3}
                dominantBaseline="hanging"
                fontSize={9}
                fill="#ffffff"
                className="font-mono"
              >
                {qid}
              </text>
              <text
                x={pos.x + CELL / 2}
                y={pos.y + CELL / 2 + 5}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={11}
                fill="#ffffff"
                stroke="rgba(0,0,0,0.35)"
                strokeWidth={2}
                paintOrder="stroke"
                className="font-mono"
              >
                {formatCollisionValue(cell?.value)}
              </text>
            </>
          );
          if (!cell) {
            return (
              <g key={qid} data-qid={qid}>
                <title>{`Q${qid}: Not evaluated`}</title>
                {content}
              </g>
            );
          }
          return (
            <g
              key={qid}
              data-qid={qid}
              role="button"
              tabIndex={0}
              aria-label={cellAriaLabel(cell)}
              className="group cursor-pointer outline-none"
              onClick={() => onSelectCell(cell)}
              onKeyDown={onActivate(() => onSelectCell(cell))}
            >
              <title>{cellAriaLabel(cell)}</title>
              {content}
            </g>
          );
        })}

        {edgeCells.map((cell) => {
          const from = positions.get(cell.source ?? "");
          const to = positions.get(cell.target ?? "");
          if (!from || !to) return null;
          const path = edgePath(
            { x: from.x + CELL / 2, y: from.y + CELL / 2 },
            { x: to.x + CELL / 2, y: to.y + CELL / 2 },
            cell.hops ?? 1,
            pitch,
          );
          const markerIndex = markerColors.indexOf(cell.color.toLowerCase());
          return (
            <g
              key={cell.key}
              data-edge-key={cell.key}
              role="button"
              tabIndex={0}
              aria-label={cellAriaLabel(cell)}
              className="group cursor-pointer outline-none"
              onClick={() => onSelectCell(cell)}
              onKeyDown={onActivate(() => onSelectCell(cell))}
            >
              <title>{cellAriaLabel(cell)}</title>
              <path d={path} fill="none" stroke="transparent" strokeWidth={10} />
              <path
                d={path}
                fill="none"
                stroke={cell.color}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeDasharray={(cell.hops ?? 1) >= 2 ? "5 4" : undefined}
                markerEnd={markerIndex >= 0 ? `url(#${markerPrefix}-${markerIndex})` : undefined}
                className="transition-opacity group-hover:opacity-70 group-focus-visible:opacity-70"
                data-testid={`collision-edge-${cell.key}`}
              />
            </g>
          );
        })}
      </svg>

      <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/70">
        {legend.map((entry) => (
          <li key={entry.color} className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ backgroundColor: entry.color }}
              aria-hidden="true"
            />
            <span>{entry.label}</span>
            <span className="font-mono tabular-nums text-base-content">{entry.count}</span>
          </li>
        ))}
        {isPair && (
          <li className="flex items-center gap-1.5 text-base-content/60">
            <svg width="22" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="22"
                y2="3"
                strokeWidth="2"
                className="stroke-base-content/60"
              />
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
    </div>
  );
}
