"use client";

import { useMemo } from "react";

import { formatDate, formatDateTime } from "@/lib/utils/datetime";

interface TimelineCooldown {
  cooldown_id: string;
  started_at: string;
  ended_at?: string | null;
  chip_ids: string[];
}

interface CooldownTimelineProps {
  cooldowns: TimelineCooldown[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const ROW_HEIGHT = 30;
const BAR_HEIGHT = 22;
const TOP_PADDING = 10;
const ROW_PIXEL_GAP = 8;

const CHIP_STYLES = [
  {
    bar: "bg-sky-600/85 hover:bg-sky-600",
    dot: "bg-sky-600",
    badge: "border-sky-200 bg-sky-50 text-sky-800",
  },
  {
    bar: "bg-emerald-600/85 hover:bg-emerald-600",
    dot: "bg-emerald-600",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-800",
  },
  {
    bar: "bg-amber-600/85 hover:bg-amber-600",
    dot: "bg-amber-600",
    badge: "border-amber-200 bg-amber-50 text-amber-900",
  },
  {
    bar: "bg-violet-600/85 hover:bg-violet-600",
    dot: "bg-violet-600",
    badge: "border-violet-200 bg-violet-50 text-violet-800",
  },
  {
    bar: "bg-rose-600/85 hover:bg-rose-600",
    dot: "bg-rose-600",
    badge: "border-rose-200 bg-rose-50 text-rose-800",
  },
  {
    bar: "bg-cyan-700/85 hover:bg-cyan-700",
    dot: "bg-cyan-700",
    badge: "border-cyan-200 bg-cyan-50 text-cyan-800",
  },
] as const;

interface LaidOutBar {
  cooldown: TimelineCooldown;
  left: number;
  width: number;
  row: number;
  start: number;
  end: number;
}

function chipStyle(chipId: string | undefined) {
  if (!chipId) {
    return {
      bar: "bg-base-content/35 hover:bg-base-content/45",
      dot: "bg-base-content/40",
      badge: "border-base-300 bg-base-200/50 text-base-content/70",
    };
  }

  let hash = 0;
  for (let i = 0; i < chipId.length; i += 1) {
    hash = (hash * 31 + chipId.charCodeAt(i)) % CHIP_STYLES.length;
  }
  return CHIP_STYLES[hash];
}

function formatChipSummary(chipIds: string[]): string {
  if (chipIds.length === 0) return "No chips";
  if (chipIds.length <= 2) return chipIds.join(", ");
  return `${chipIds.slice(0, 2).join(", ")} +${chipIds.length - 2}`;
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
    const widthPct = Math.max(0.6, ((end - start) / span) * 100);
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
  const { bars, rowCount, ticks, chipLegend } = useMemo(() => {
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

    const ticks = [0, 0.2, 0.4, 0.6, 0.8, 1].map((f) => {
      const t = lo + span * f;
      const date = new Date(t);
      return {
        pct: f * 100,
        label: formatDateTime(date.toISOString(), "yyyy MMM"),
      };
    });

    const chipLegend = Array.from(new Set(cooldowns.flatMap((c) => c.chip_ids))).sort();

    return { bars, rowCount, ticks, chipLegend };
  }, [cooldowns]);

  const trackHeight = TOP_PADDING * 2 + rowCount * ROW_HEIGHT;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-base-content/60">
        <span>Timeline</span>
        <span className="text-[10px] text-base-content/40">
          {cooldowns.length} cool-down{cooldowns.length !== 1 ? "s" : ""} / {chipLegend.length} chip
          {chipLegend.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div
        className="relative rounded-lg border border-base-300 bg-base-200/40 shadow-inner"
        style={{ height: `${trackHeight}px` }}
      >
        {ticks.map((tick) => (
          <span
            key={tick.pct}
            className="pointer-events-none absolute bottom-0 top-0 border-l border-base-content/10"
            style={{ left: `${tick.pct}%` }}
          />
        ))}
        {bars.map((bar) => {
          const cd = bar.cooldown;
          const isActive = !cd.ended_at;
          const isSelected = cd.cooldown_id === selectedId;
          const top = TOP_PADDING + bar.row * ROW_HEIGHT;
          const chipSummary = formatChipSummary(cd.chip_ids);
          const primaryChipStyle = chipStyle(cd.chip_ids[0]);
          return (
            <button
              key={cd.cooldown_id}
              onClick={() => onSelect(cd.cooldown_id)}
              className={`absolute overflow-hidden rounded-md border border-white/20 text-left shadow-sm transition-all hover:brightness-110 ${primaryChipStyle.bar} ${
                isSelected ? "ring-2 ring-primary ring-offset-1 ring-offset-base-100 z-10" : ""
              }`}
              style={{
                left: `${bar.left}%`,
                width: `${bar.width}%`,
                top: `${top}px`,
                height: `${BAR_HEIGHT}px`,
              }}
              title={`${cd.cooldown_id} (${formatDate(cd.started_at)} → ${
                cd.ended_at ? formatDate(cd.ended_at) : "now"
              }) · ${chipSummary}`}
            >
              <span className="flex h-full min-w-0 items-center gap-1.5 px-2 text-[10px] font-semibold leading-none text-white">
                <span className="truncate font-mono">{cd.cooldown_id}</span>
                {cd.chip_ids.length > 0 && (
                  <span className="hidden min-w-0 flex-1 truncate font-mono opacity-90 sm:inline">
                    {chipSummary}
                  </span>
                )}
                {isActive && (
                  <span className="ml-auto h-2 w-2 flex-shrink-0 rounded-full bg-white/85" />
                )}
              </span>
            </button>
          );
        })}
      </div>
      <div className="relative mt-1 h-4">
        {ticks.map((t) => (
          <span
            key={t.pct}
            className="absolute -translate-x-1/2 text-[10px] text-base-content/50"
            style={{ left: `${t.pct}%` }}
          >
            {t.label}
          </span>
        ))}
      </div>
      {chipLegend.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
          {chipLegend.map((chipId) => {
            const style = chipStyle(chipId);
            return (
              <span
                key={chipId}
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono ${style.badge}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                {chipId}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
