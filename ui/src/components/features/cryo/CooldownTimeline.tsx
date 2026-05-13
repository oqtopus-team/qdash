"use client";

import { useMemo } from "react";

import { formatDate, formatDateTime } from "@/lib/utils/datetime";

interface TimelineCooldown {
  cooldown_id: string;
  started_at: string;
  ended_at?: string | null;
}

interface CooldownTimelineProps {
  cooldowns: TimelineCooldown[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const ROW_HEIGHT = 18;
const BAR_HEIGHT = 14;
const TOP_PADDING = 4;
const ROW_PIXEL_GAP = 4;

interface LaidOutBar {
  cooldown: TimelineCooldown;
  left: number;
  width: number;
  row: number;
  start: number;
  end: number;
}

/**
 * Greedy row assignment: sort bars by start time, then for each bar pick the
 * lowest row whose last bar ended before this one starts (with a small pixel
 * gap so adjacent bars don't kiss). This gives a compact, non-overlapping
 * stack instead of cycling through fixed rows.
 */
function layoutBars(
  cooldowns: TimelineCooldown[],
  lo: number,
  span: number,
  containerWidthPx: number,
  now: number,
): { bars: LaidOutBar[]; rowCount: number } {
  const sorted = [...cooldowns].sort(
    (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime(),
  );

  const rowEndsPx: number[] = [];
  const bars: LaidOutBar[] = [];

  // Convert pixel gap to a fraction of span. Conservative if width unknown.
  const gapPx = ROW_PIXEL_GAP;
  const containerW = Math.max(1, containerWidthPx);

  for (const cd of sorted) {
    const start = new Date(cd.started_at).getTime();
    const end = cd.ended_at ? new Date(cd.ended_at).getTime() : now;
    const leftPct = ((start - lo) / span) * 100;
    const widthPct = Math.max(0.5, ((end - start) / span) * 100);
    const leftPx = (leftPct / 100) * containerW;
    const rightPx = leftPx + (widthPct / 100) * containerW;

    let row = 0;
    while (row < rowEndsPx.length && rowEndsPx[row] + gapPx > leftPx) {
      row += 1;
    }
    rowEndsPx[row] = rightPx;

    bars.push({
      cooldown: cd,
      left: leftPct,
      width: widthPct,
      row,
      start,
      end,
    });
  }

  return { bars, rowCount: Math.max(1, rowEndsPx.length) };
}

export function CooldownTimeline({ cooldowns, selectedId, onSelect }: CooldownTimelineProps) {
  const { bars, rowCount, ticks } = useMemo(() => {
    const now = Date.now();
    const tMin = Math.min(...cooldowns.map((c) => new Date(c.started_at).getTime()));
    const tMax = Math.max(
      ...cooldowns.map((c) => (c.ended_at ? new Date(c.ended_at).getTime() : now)),
    );
    const range = Math.max(1, tMax - tMin);
    const padding = range * 0.05;
    const lo = tMin - padding;
    const hi = tMax + padding;
    const span = hi - lo;

    // Container width is unknown until layout; use a typical width as a
    // proxy. The greedy algorithm tolerates over- or under-estimation: rows
    // may be packed slightly tighter or looser than ideal but never overlap.
    const { bars, rowCount } = layoutBars(cooldowns, lo, span, 720, now);

    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const t = lo + span * f;
      const date = new Date(t);
      return {
        pct: f * 100,
        label: formatDateTime(date.toISOString(), "yyyy MMM"),
      };
    });

    return { bars, rowCount, ticks };
  }, [cooldowns]);

  const trackHeight = TOP_PADDING * 2 + rowCount * ROW_HEIGHT;

  return (
    <div>
      <div className="text-xs text-base-content/60 mb-1 flex items-center justify-between">
        <span>Timeline</span>
        <span className="text-[10px] text-base-content/40">
          {cooldowns.length} cool-down{cooldowns.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div
        className="relative bg-base-200/50 rounded-md border border-base-300"
        style={{ height: `${trackHeight}px` }}
      >
        {bars.map((bar) => {
          const cd = bar.cooldown;
          const isActive = !cd.ended_at;
          const isSelected = cd.cooldown_id === selectedId;
          const top = TOP_PADDING + bar.row * ROW_HEIGHT;
          return (
            <button
              key={cd.cooldown_id}
              onClick={() => onSelect(cd.cooldown_id)}
              className={`absolute rounded transition-all hover:brightness-110 ${
                isActive ? "bg-success/85 hover:bg-success" : "bg-info/60 hover:bg-info/80"
              } ${isSelected ? "ring-2 ring-primary ring-offset-1 ring-offset-base-100 z-10" : ""}`}
              style={{
                left: `${bar.left}%`,
                width: `${bar.width}%`,
                top: `${top}px`,
                height: `${BAR_HEIGHT}px`,
              }}
              title={`${cd.cooldown_id} (${formatDate(cd.started_at)} → ${
                cd.ended_at ? formatDate(cd.ended_at) : "now"
              })`}
            >
              <span className="text-[9px] font-bold text-white px-1 truncate block leading-[14px]">
                {cd.cooldown_id}
              </span>
            </button>
          );
        })}
      </div>
      <div className="relative h-4 mt-1">
        {ticks.map((t, i) => (
          <span
            key={i}
            className="absolute text-[10px] text-base-content/50 -translate-x-1/2"
            style={{ left: `${t.pct}%` }}
          >
            {t.label}
          </span>
        ))}
      </div>
    </div>
  );
}
