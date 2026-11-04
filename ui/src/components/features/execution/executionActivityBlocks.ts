import type { CSSProperties } from "react";

import type { ChartTheme } from "@/lib/chartTheme";
import type { ExecutionActivityDay } from "@/schemas";

/**
 * Block math and formatting shared by the execution activity charts on the Execution page and
 * Home, so both draw a day the same way and only differ in how tall a column may grow.
 */

export type ActivityStatusKey = Exclude<keyof ExecutionActivityDay, "date" | "total">;

/** Stacking order, bottom to top. */
const ACTIVITY_SERIES: ReadonlyArray<{ key: ActivityStatusKey; label: string }> = [
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
  { key: "running", label: "Running" },
  { key: "scheduled", label: "Scheduled" },
  { key: "cancelled", label: "Cancelled" },
  { key: "other", label: "Other" },
];

/** Opacity of a block that stands for fewer executions than the scale. */
const PARTIAL_OPACITY = 0.45;

interface ActivityBlock {
  status: ActivityStatusKey;
  /** Executions this block stands for: the scale, or the remainder for a partial block. */
  executions: number;
  partial: boolean;
}

export interface ActivityDayColumn {
  date: string;
  /** The date as YYYYMMDD, the form the execution list filter uses. */
  compact: string;
  total: number;
  counts: ReadonlyArray<{ key: ActivityStatusKey; label: string; count: number }>;
  blocks: ActivityBlock[];
}

const activityCount = (bucket: ExecutionActivityDay, key: ActivityStatusKey) => bucket[key] ?? 0;

/** Blocks a day needs when one block stands for `scale` executions; each status rounds up. */
const blocksNeeded = (bucket: ExecutionActivityDay, scale: number) =>
  ACTIVITY_SERIES.reduce((acc, { key }) => acc + Math.ceil(activityCount(bucket, key) / scale), 0);

/**
 * Smallest 1-2-5 step that keeps every day within `maxBlocks`. A step always exists as long as
 * `maxBlocks` covers one block per status, because a day needs at most that many once the step
 * exceeds its largest count.
 */
export function activityBlockScale(
  buckets: readonly ExecutionActivityDay[],
  maxBlocks: number,
): number {
  for (let magnitude = 1; ; magnitude *= 10) {
    for (const step of [1, 2, 5]) {
      const scale = step * magnitude;
      if (buckets.every((bucket) => blocksNeeded(bucket, scale) <= maxBlocks)) return scale;
    }
  }
}

export function toActivityColumn(bucket: ExecutionActivityDay, scale: number): ActivityDayColumn {
  const blocks: ActivityBlock[] = [];
  for (const { key } of ACTIVITY_SERIES) {
    const value = activityCount(bucket, key);
    for (let i = 0; i < Math.floor(value / scale); i += 1) {
      blocks.push({ status: key, executions: scale, partial: false });
    }
    const remainder = value % scale;
    if (remainder > 0) blocks.push({ status: key, executions: remainder, partial: true });
  }
  const counts = ACTIVITY_SERIES.map((series) => ({
    ...series,
    count: activityCount(bucket, series.key),
  }));
  return {
    date: bucket.date,
    compact: bucket.date.replace(/-/g, ""),
    total: counts.reduce((acc, item) => acc + item.count, 0),
    counts,
    blocks,
  };
}

/** Executions per status across the whole window, in stacking order. */
export const activityStatusTotals = (buckets: readonly ExecutionActivityDay[]) =>
  ACTIVITY_SERIES.map((series) => ({
    ...series,
    count: buckets.reduce((acc, bucket) => acc + activityCount(bucket, series.key), 0),
  }));

export function parseActivityDay(date: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

// Bucket dates are calendar days in the requested zone, so they are formatted as UTC midnight.
export const shortActivityDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
export const longActivityDate = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

export const pluralize = (value: number, noun: string) =>
  `${value} ${noun}${value === 1 ? "" : "s"}`;

/** One-line description of a day, for accessible names. */
export function describeActivityDay(column: ActivityDayColumn): string {
  const parts = column.counts
    .filter((item) => item.count > 0)
    .map((item) => `${item.count} ${item.label.toLowerCase()}`);
  const summary = pluralize(column.total, "execution");
  return `${longActivityDate.format(parseActivityDay(column.date))}: ${summary}${parts.length ? `, ${parts.join(", ")}` : ""}`;
}

/** Fill style of a status block; "other" is outlined so it stays apart from cancelled. */
export function activityBlockStyler(palette: ChartTheme) {
  const colors: Record<ActivityStatusKey, string> = {
    completed: palette.pass,
    failed: palette.fail,
    running: palette.accent,
    scheduled: palette.warn,
    cancelled: palette.muted,
    other: palette.muted,
  };
  return (status: ActivityStatusKey, partial: boolean): CSSProperties => ({
    ...(status === "other"
      ? { border: `1px solid ${colors.other}` }
      : { backgroundColor: colors[status] }),
    opacity: partial ? PARTIAL_OPACITY : 1,
  });
}
