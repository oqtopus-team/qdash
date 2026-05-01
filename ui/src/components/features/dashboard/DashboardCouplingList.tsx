"use client";

import { useMemo, useState } from "react";

import { StickyNote } from "lucide-react";

import type { NoteEntryWithMetric } from "./ChipNoteEditor";
import { DashboardNoteTooltip } from "./DashboardNoteTooltip";

interface MetricValue {
  value: number | null;
}

interface DashboardCouplingListProps {
  metricData: { [key: string]: MetricValue } | null;
  unit: string;
  colors: string[];
  /** Set of coupling IDs (e.g. "0-1") that have a note for this metric. */
  notedTargets?: Set<string>;
  /**
   * Set of coupling IDs that have notes on OTHER metrics (not this one), so
   * users see there is cross-metric context to read.
   */
  crossMetricNotedTargets?: Set<string>;
  /** All notes for each coupling (across metrics), keyed by coupling ID. */
  notesByTarget?: Record<string, NoteEntryWithMetric[]>;
  /** The metric_key this list renders, used to split current vs. other notes. */
  metricKey?: string;
  /** Click handler when a coupling chip is clicked. Receives the coupling ID. */
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

function pickColor(
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

/**
 * Compact coupling display for the dashboard. Renders each coupling as a chip
 * with control/target qubits and the metric value, colored by value. Clicking
 * a chip opens the note editor for that (coupling, metric) pair.
 */
export function DashboardCouplingList({
  metricData,
  unit,
  colors,
  notedTargets,
  crossMetricNotedTargets,
  notesByTarget,
  metricKey,
  onCouplingClick,
}: DashboardCouplingListProps) {
  const [hover, setHover] = useState<{
    key: string;
    x: number;
    y: number;
  } | null>(null);
  const { autoMin, autoMax, entries } = useMemo(() => {
    if (!metricData) return { autoMin: 0, autoMax: 0, entries: [] };
    const allEntries = Object.entries(metricData)
      .filter(([, v]) => v?.value !== null && v?.value !== undefined)
      .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }));
    const vals = allEntries.map(([, v]) => v.value as number);
    return {
      autoMin: vals.length ? Math.min(...vals) : 0,
      autoMax: vals.length ? Math.max(...vals) : 0,
      entries: allEntries,
    };
  }, [metricData]);

  if (entries.length === 0) {
    return (
      <div className="text-sm text-base-content/60 italic">
        No coupling data.
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, metric]) => {
        const value = metric.value as number;
        const bg = pickColor(value, autoMin, autoMax, colors);
        const [a, b] = key.split("-");
        const hasNote = notedTargets?.has(key) ?? false;
        const hasCrossMetricNote =
          !hasNote && (crossMetricNotedTargets?.has(key) ?? false);
        const Tag = onCouplingClick ? "button" : "div";
        const handleClick = () => onCouplingClick?.(key);
        return (
          <Tag
            key={key}
            onClick={onCouplingClick ? handleClick : undefined}
            onMouseEnter={(e: React.MouseEvent<HTMLElement>) => {
              const rect = e.currentTarget.getBoundingClientRect();
              setHover({
                key,
                x: rect.left + rect.width / 2,
                y: rect.top,
              });
            }}
            onMouseLeave={() => setHover(null)}
            className={`rounded-md px-2 py-1 shadow-sm flex items-center gap-1.5 text-xs font-medium tabular-nums relative ${
              onCouplingClick
                ? "cursor-pointer hover:ring-2 hover:ring-primary/60"
                : ""
            }`}
            style={{ backgroundColor: bg ?? undefined, color: "#fff" }}
            aria-label={
              `Q${a} → Q${b}: ${value.toFixed(4)} ${unit}` +
              (hasNote
                ? " · has note"
                : hasCrossMetricNote
                  ? " · note on other metric"
                  : "") +
              (onCouplingClick ? " (click to edit note)" : "")
            }
          >
            <span className="opacity-90">
              Q{a}→Q{b}
            </span>
            <span className="font-bold">{value.toFixed(2)}</span>
            {hasNote && (
              <span
                className="absolute -top-1 -right-1 rounded-full bg-warning text-warning-content p-0.5 shadow"
                title="Has note"
              >
                <StickyNote className="h-2.5 w-2.5" />
              </span>
            )}
            {hasCrossMetricNote && (
              <span
                className="absolute -top-1 -right-1 rounded-full bg-base-100/90 text-base-content/60 p-0.5 shadow border border-base-300"
                title="Note exists on another metric"
              >
                <StickyNote className="h-2.5 w-2.5" />
              </span>
            )}
          </Tag>
        );
      })}
      {hover &&
        (() => {
          const allNotes = notesByTarget?.[hover.key] ?? [];
          const current = allNotes.find((n) => n.metricKey === metricKey);
          const others = allNotes.filter((n) => n.metricKey !== metricKey);
          const v = metricData?.[hover.key]?.value ?? null;
          const [a, b] = hover.key.split("-");
          const header =
            v !== null
              ? `Q${a} → Q${b}: ${v.toFixed(4)} ${unit}`
              : `Q${a} → Q${b}: No data`;
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
