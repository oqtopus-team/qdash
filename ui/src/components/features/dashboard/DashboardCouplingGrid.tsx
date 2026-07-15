"use client";

import { useMemo, useState } from "react";

import { MessageSquare, StickyNote } from "lucide-react";

import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { forumMarkerClass } from "../forum/categories";
import { getQubitGridPosition } from "@/lib/utils/grid-position";

import type { NoteEntryWithMetric, TargetNoteEntry } from "./MetricNotePanel";
import { DashboardNoteTooltip, type ForumLinkEntry } from "./DashboardNoteTooltip";

interface MetricValue {
  value: number | null;
  stddev?: number | null;
}

interface DashboardCouplingGridProps {
  metricData: { [key: string]: MetricValue } | null;
  unit: string;
  topologyId: string;
  colors: string[];
  /** Maximum cell side length in px. Cells shrink to fit narrower containers. */
  maxCellSize?: number;
  /** Render the reverse direction of each topology coupling. */
  reverseDirection?: boolean;
  notedTargets?: Set<string>;
  targetNotedTargets?: Set<string>;
  /** Linked forum discussion label keyed by coupling ID. */
  forumLinkedTargets?: Record<string, string>;
  /** Linked forum discussion details keyed by coupling ID. */
  forumLinksByTarget?: Record<string, ForumLinkEntry[]>;
  crossMetricNotedTargets?: Set<string>;
  notesByTarget?: Record<string, NoteEntryWithMetric[]>;
  /** Target-level notes keyed by qubit/coupling ID. */
  targetNotesByTarget?: Record<string, TargetNoteEntry>;
  metricKey?: string;
  /** Presentation optimized for metric heatmaps or note summary topology. */
  presentation?: "metric" | "summary";
  onCouplingClick?: (couplingId: string) => void;
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
 * Read-only, compact coupling heatmap for the dashboard. Qubits are drawn as
 * faint background tiles in their topology positions; each coupling is rendered
 * as a colored chip overlaid between its two qubits with an arrow pointing in
 * the direction defined by the coupling ID. Mirrors the metrics
 * CouplingMetricsGrid layout but skips zoom/pan/region/modal so several
 * instances can be stacked on the dashboard.
 */
export function DashboardCouplingGrid({
  metricData,
  unit,
  topologyId,
  colors,
  maxCellSize = 60,
  reverseDirection = false,
  notedTargets,
  targetNotedTargets,
  forumLinkedTargets,
  forumLinksByTarget,
  crossMetricNotedTargets,
  notesByTarget,
  targetNotesByTarget,
  metricKey,
  presentation = "metric",
  onCouplingClick,
}: DashboardCouplingGridProps) {
  const [hover, setHover] = useState<{
    key: string;
    x: number;
    y: number;
  } | null>(null);
  const isSummaryPresentation = presentation === "summary";

  const {
    muxSize = 2,
    hasMux = false,
    layoutType = "grid",
    qubits: topologyQubits,
    couplings: topologyCouplings,
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

  const layoutParams = useMemo(
    () => ({
      muxEnabled: hasMux,
      muxSize,
      gridSize: Math.max(gridRows, gridCols),
      layoutType,
    }),
    [hasMux, muxSize, gridRows, gridCols, layoutType],
  );

  const getPos = (qid: number) => {
    if (topologyQubits && topologyQubits[qid]) return topologyQubits[qid];
    return getQubitGridPosition(qid, layoutParams);
  };

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

  const couplingList: [number, number][] = useMemo(() => {
    const base =
      topologyCouplings && topologyCouplings.length > 0
        ? topologyCouplings
        : metricData
          ? Object.keys(metricData).map((key) => {
              const [a, b] = key.split("-").map(Number);
              return [a, b] as [number, number];
            })
          : [];
    return reverseDirection ? base.map(([a, b]) => [b, a] as [number, number]) : base;
  }, [topologyCouplings, metricData, reverseDirection]);

  // Fixed cell size (capped). Using pixel sizing here is simpler than
  // responsive 1fr columns because couplings need absolute positioning between
  // qubit cells.
  const cellSize = maxCellSize;
  const gap = 2;
  const width = gridCols * cellSize + (gridCols - 1) * gap;
  const height = gridRows * cellSize + (gridRows - 1) * gap;

  return (
    <div className="w-full overflow-x-auto">
      <div className="relative mx-auto" style={{ width, height, maxWidth: "100%" }}>
        {/* Qubit cells (background) */}
        {Array.from({ length: gridRows * gridCols }).map((_, idx) => {
          const row = Math.floor(idx / gridCols);
          const col = idx % gridCols;
          const x = col * (cellSize + gap);
          const y = row * (cellSize + gap);
          // Find qubit at this position
          let qid: number | null = null;
          if (topologyQubits) {
            for (const [k, p] of Object.entries(topologyQubits)) {
              if (p.row === row && p.col === col) {
                qid = Number(k);
                break;
              }
            }
          }
          if (qid === null) {
            return (
              <div
                key={`bg-${row}-${col}`}
                className={`absolute rounded-md ${
                  isSummaryPresentation
                    ? "bg-base-200/25 border border-base-300/40"
                    : "bg-base-300/20"
                }`}
                style={{
                  top: y,
                  left: x,
                  width: cellSize,
                  height: cellSize,
                }}
              />
            );
          }
          return (
            <div
              key={`qubit-${qid}`}
              className={`absolute rounded-md flex items-start justify-start ${
                isSummaryPresentation
                  ? "bg-base-100/60 border border-base-300/60 text-base-content/35"
                  : "bg-base-300/40 text-base-content/40"
              }`}
              style={{
                top: y,
                left: x,
                width: cellSize,
                height: cellSize,
              }}
            >
              <span className="text-[10px] font-semibold px-1 leading-tight">{qid}</span>
            </div>
          );
        })}

        {/* Coupling cells (overlay) */}
        {couplingList.map(([qid1, qid2]) => {
          const pos1 = getPos(qid1);
          const pos2 = getPos(qid2);
          if (!pos1 || !pos2) return null;
          const couplingId = `${qid1}-${qid2}`;
          const metric = metricData?.[couplingId];
          const value = metric?.value ?? null;
          const bg = value !== null ? pickColor(value, autoMin, autoMax, colors) : null;
          const centerX = ((pos1.col + pos2.col) / 2) * (cellSize + gap) + cellSize / 2;
          const centerY = ((pos1.row + pos2.row) / 2) * (cellSize + gap) + cellSize / 2;
          const dx = pos2.col - pos1.col;
          const dy = pos2.row - pos1.row;
          const arrowAngle = (Math.atan2(dy, dx) * 180) / Math.PI;
          const hasNote = notedTargets?.has(couplingId) ?? false;
          const hasTargetNote = targetNotedTargets?.has(couplingId) ?? false;
          const forumLabel = forumLinkedTargets?.[couplingId];
          const hasForumDiscussion = !!forumLabel;
          const hasCrossMetricNote =
            !hasNote && !hasTargetNote && (crossMetricNotedTargets?.has(couplingId) ?? false);
          const Tag = onCouplingClick ? "button" : "div";
          const handleClick = () => onCouplingClick?.(couplingId);
          const summaryChipClass = hasTargetNote
            ? "bg-warning border-warning shadow-md opacity-95"
            : hasForumDiscussion
              ? "bg-info border-info shadow-md opacity-95"
              : "bg-base-content/25 border-base-content/20 opacity-70 hover:opacity-100";
          const titleText =
            (isSummaryPresentation
              ? `Q${qid1}→Q${qid2}: pinned summary target`
              : value !== null
                ? `Q${qid1}→Q${qid2}: ${value.toFixed(4)} ${unit}`
                : `Q${qid1}→Q${qid2}: No data`) +
            (hasNote
              ? " · has legacy metric note"
              : hasTargetNote
                ? " · has pinned summary"
                : hasCrossMetricNote
                  ? " · legacy note on another metric"
                  : "") +
            (hasForumDiscussion ? " · has linked forum discussion" : "") +
            (onCouplingClick ? " (click to edit pinned summary)" : "");
          return (
            <Tag
              key={couplingId}
              onClick={onCouplingClick ? handleClick : undefined}
              onMouseEnter={(e: React.MouseEvent<HTMLElement>) => {
                const rect = e.currentTarget.getBoundingClientRect();
                setHover({
                  key: couplingId,
                  x: rect.left + rect.width / 2,
                  y: rect.top,
                });
              }}
              onMouseLeave={() => setHover(null)}
              className={`absolute flex items-center justify-center transition-all ${
                isSummaryPresentation
                  ? "rounded-full"
                  : "rounded-md shadow-sm flex-col -translate-x-1/2 -translate-y-1/2"
              } ${onCouplingClick ? "cursor-pointer hover:ring-2 hover:ring-primary/60 hover:scale-105" : ""} ${
                isSummaryPresentation ? `border ${summaryChipClass}` : !bg ? "bg-base-300/60" : ""
              }`}
              style={{
                top: centerY,
                left: centerX,
                width: isSummaryPresentation ? cellSize * 0.74 : cellSize * 0.72,
                height: isSummaryPresentation ? Math.max(6, cellSize * 0.12) : cellSize * 0.5,
                backgroundColor: isSummaryPresentation ? undefined : (bg ?? undefined),
                transform: isSummaryPresentation
                  ? `translate(-50%, -50%) rotate(${arrowAngle}deg)`
                  : undefined,
              }}
              aria-label={titleText}
            >
              {isSummaryPresentation ? (
                <span className="sr-only">
                  Q{qid1}→Q{qid2}
                </span>
              ) : value !== null ? (
                <span className="text-[10px] font-bold text-white drop-shadow leading-none">
                  {value.toFixed(2)}
                </span>
              ) : (
                <span className="text-[9px] text-base-content/50 leading-none">—</span>
              )}
              {!isSummaryPresentation && (
                <svg
                  width="12"
                  height="5"
                  viewBox="0 0 18 7"
                  className="mt-px drop-shadow-[0_1px_2px_rgba(0,0,0,0.5)]"
                  style={{ transform: `rotate(${arrowAngle}deg)` }}
                >
                  <line
                    x1="1"
                    y1="3.5"
                    x2="14"
                    y2="3.5"
                    stroke={bg ? "white" : "currentColor"}
                    strokeWidth="1.5"
                  />
                  <polyline
                    points="11,0.5 16,3.5 11,6.5"
                    fill="none"
                    stroke={bg ? "white" : "currentColor"}
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
              {(hasNote || hasTargetNote) && (
                <span
                  className={`absolute rounded-full bg-warning text-warning-content p-0.5 shadow ${
                    isSummaryPresentation ? "-top-2 -right-2" : "-top-1 -right-1"
                  }`}
                  title={hasNote ? "Has legacy metric note" : "Has pinned summary"}
                >
                  <StickyNote className="h-2.5 w-2.5" />
                </span>
              )}
              {hasCrossMetricNote && (
                <span
                  className={`absolute rounded-full bg-base-100/90 text-base-content/60 p-0.5 shadow border border-base-300 ${
                    isSummaryPresentation ? "-top-2 -right-2" : "-top-1 -right-1"
                  }`}
                  title="Legacy note exists on another metric"
                >
                  <StickyNote className="h-2.5 w-2.5" />
                </span>
              )}
              {hasForumDiscussion && (
                <span
                  className={`absolute rounded-full p-0.5 shadow ${
                    isSummaryPresentation ? "-bottom-2 -right-2" : "-bottom-1 -right-1"
                  } ${forumMarkerClass(forumLabel)}`}
                  title="Linked forum discussion"
                >
                  <MessageSquare className="h-2.5 w-2.5" />
                </span>
              )}
            </Tag>
          );
        })}

        {hover &&
          (() => {
            const allNotes = notesByTarget?.[hover.key] ?? [];
            const targetNote = targetNotesByTarget?.[hover.key];
            const forumLinks = forumLinksByTarget?.[hover.key] ?? [];
            const current = allNotes.find((n) => n.metricKey === metricKey);
            const others = allNotes.filter((n) => n.metricKey !== metricKey);
            const v = metricData?.[hover.key]?.value ?? null;
            const [a, b] = hover.key.split("-");
            const header =
              v !== null ? `Q${a} → Q${b}: ${v.toFixed(4)} ${unit}` : `Q${a} → Q${b}: No data`;
            return (
              <DashboardNoteTooltip
                position={{ x: hover.x, y: hover.y }}
                header={header}
                targetNote={targetNote}
                current={current}
                others={others}
                forumLinks={forumLinks}
              />
            );
          })()}
      </div>
    </div>
  );
}
