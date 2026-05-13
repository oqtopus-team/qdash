"use client";

import { useMemo, useState } from "react";

import { StickyNote } from "lucide-react";

import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";

import type { NoteEntryWithMetric } from "./MetricNotePanel";
import { DashboardNoteTooltip } from "./DashboardNoteTooltip";

interface MetricValue {
  value: number | null;
  stddev?: number | null;
}

interface DashboardQubitGridProps {
  metricData: { [key: string]: MetricValue } | null;
  unit: string;
  topologyId: string;
  colors: string[];
  /** Maximum cell side length in px. Cells shrink to fit narrower containers. */
  maxCellSize?: number;
  /** Set of qubit IDs that have a note for the metric this grid represents. */
  notedQids?: Set<string>;
  /**
   * Set of qubit IDs that have notes on OTHER metrics (not this one). Used to
   * render a subtle indicator so users know to click to read the cross-metric
   * context.
   */
  crossMetricNotedQids?: Set<string>;
  /** All notes for each qubit (across metrics), keyed by qubit ID. */
  notesByTarget?: Record<string, NoteEntryWithMetric[]>;
  /** The metric_key this grid renders, used to split current vs. other notes. */
  metricKey?: string;
  /** Click handler when a qubit cell is clicked. */
  onQubitClick?: (qid: string) => void;
}

function interpolateColor(c1: string, c2: string, factor: number): string {
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

function pickColor(value: number, min: number, max: number, colors: string[]): string | null {
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

/**
 * Read-only, fixed-size qubit heatmap for the dashboard. Skips zoom/pan/region
 * controls so multiple instances can be stacked on a single page. Cells are
 * clickable and show a note indicator when a note exists.
 */
export function DashboardQubitGrid({
  metricData,
  unit,
  topologyId,
  colors,
  maxCellSize = 60,
  notedQids,
  crossMetricNotedQids,
  notesByTarget,
  metricKey,
  onQubitClick,
}: DashboardQubitGridProps) {
  const [hover, setHover] = useState<{
    qid: string;
    x: number;
    y: number;
  } | null>(null);
  const {
    muxSize = 2,
    hasMux = false,
    layoutType = "grid",
    qubits: topologyQubits,
    gridSize: topologyGridSize,
  } = useTopologyConfig(topologyId) ?? {};

  const { gridRows, gridCols } = useMemo(() => {
    if (topologyQubits) {
      let maxRow = 0;
      let maxCol = 0;
      Object.values(topologyQubits).forEach((pos) => {
        if (pos.row > maxRow) maxRow = pos.row;
        if (pos.col > maxCol) maxCol = pos.col;
      });
      return { gridRows: maxRow + 1, gridCols: maxCol + 1 };
    }
    const size = topologyGridSize ?? 8;
    return { gridRows: size, gridCols: size };
  }, [topologyQubits, topologyGridSize]);

  const layoutParams: TopologyLayoutParams = useMemo(
    () => ({
      muxEnabled: hasMux,
      muxSize,
      gridSize: Math.max(gridRows, gridCols),
      layoutType,
    }),
    [hasMux, muxSize, gridRows, gridCols, layoutType],
  );

  const { autoMin, autoMax } = useMemo(() => {
    if (!metricData) return { autoMin: 0, autoMax: 0 };
    const vals = Object.values(metricData)
      .map((m) => m.value)
      .filter((v): v is number => v !== null && v !== undefined);
    if (vals.length === 0) return { autoMin: 0, autoMax: 0 };
    return {
      autoMin: Math.min(...vals),
      autoMax: Math.max(...vals),
    };
  }, [metricData]);

  // Map (row,col) -> qid using topology when available, else getQubitGridPosition
  const cellMap = useMemo(() => {
    const map = new Map<string, string>();
    if (topologyQubits) {
      Object.entries(topologyQubits).forEach(([qid, pos]) => {
        map.set(`${pos.row}-${pos.col}`, qid);
      });
      return map;
    }
    for (let i = 0; i < gridRows * gridCols; i++) {
      const { row, col } = getQubitGridPosition(i, layoutParams);
      map.set(`${row}-${col}`, String(i));
    }
    return map;
  }, [topologyQubits, gridRows, gridCols, layoutParams]);

  const cells: Array<{ row: number; col: number; qid?: string }> = [];
  for (let r = 0; r < gridRows; r++) {
    for (let c = 0; c < gridCols; c++) {
      cells.push({ row: r, col: c, qid: cellMap.get(`${r}-${c}`) });
    }
  }

  return (
    <div
      className="grid gap-0.5 mx-auto w-full"
      style={{
        gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`,
        maxWidth: `${gridCols * maxCellSize + (gridCols - 1) * 2}px`,
      }}
    >
      {cells.map(({ row, col, qid }) => {
        if (qid === undefined) {
          return <div key={`${row}-${col}`} className="rounded-md bg-base-300/30 aspect-square" />;
        }
        const metric = metricData?.[qid];
        const value = metric?.value ?? null;
        const bg = value !== null ? pickColor(value, autoMin, autoMax, colors) : null;
        const hasNote = notedQids?.has(qid) ?? false;
        const hasCrossMetricNote = !hasNote && (crossMetricNotedQids?.has(qid) ?? false);
        const handleClick = () => onQubitClick?.(qid);
        const titleText =
          (value !== null ? `${qid}: ${value.toFixed(4)} ${unit}` : `${qid}: No data`) +
          (hasNote ? " · has note" : hasCrossMetricNote ? " · note on other metric" : "") +
          (onQubitClick ? " (click to edit note)" : "");
        const Tag = onQubitClick ? "button" : "div";
        return (
          <Tag
            key={`${row}-${col}`}
            onClick={onQubitClick ? handleClick : undefined}
            onMouseEnter={(e: React.MouseEvent<HTMLElement>) => {
              const rect = e.currentTarget.getBoundingClientRect();
              setHover({
                qid,
                x: rect.left + rect.width / 2,
                y: rect.top,
              });
            }}
            onMouseLeave={() => setHover(null)}
            className={`aspect-square rounded-md flex flex-col items-center justify-center relative shadow-sm text-left ${
              onQubitClick ? "cursor-pointer hover:ring-2 hover:ring-primary/60" : ""
            }`}
            style={{ backgroundColor: bg ?? undefined }}
            aria-label={titleText}
          >
            <span
              className={`absolute top-0.5 left-0.5 text-[10px] font-semibold px-1 rounded leading-tight ${
                bg ? "bg-black/30 text-white" : "bg-base-200 text-base-content"
              }`}
            >
              {qid}
            </span>
            {hasNote && (
              <span
                className="absolute top-1 right-1 rounded-full bg-warning/90 text-warning-content p-0.5 shadow"
                title="Has note"
              >
                <StickyNote className="h-3 w-3" />
              </span>
            )}
            {hasCrossMetricNote && (
              <span
                className="absolute top-1 right-1 rounded-full bg-base-100/80 text-base-content/60 p-0.5 shadow border border-base-300"
                title="Note exists on another metric"
              >
                <StickyNote className="h-3 w-3" />
              </span>
            )}
            {value !== null ? (
              <span className="text-[11px] font-bold text-white drop-shadow leading-tight mt-1.5">
                {value.toFixed(2)}
              </span>
            ) : (
              <span className="text-[10px] text-base-content/40 mt-1.5">N/A</span>
            )}
          </Tag>
        );
      })}
      {hover &&
        (() => {
          const allNotes = notesByTarget?.[hover.qid] ?? [];
          const current = allNotes.find((n) => n.metricKey === metricKey);
          const others = allNotes.filter((n) => n.metricKey !== metricKey);
          const v = metricData?.[hover.qid]?.value ?? null;
          const header =
            v !== null ? `Q${hover.qid}: ${v.toFixed(4)} ${unit}` : `Q${hover.qid}: No data`;
          return (
            <DashboardNoteTooltip
              position={{ x: hover.x, y: hover.y }}
              header={header}
              current={current}
              others={others}
            />
          );
        })()}
    </div>
  );
}
