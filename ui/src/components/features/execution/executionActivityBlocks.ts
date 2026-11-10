import type { CSSProperties } from "react";

import type { ChartTheme } from "@/lib/chartTheme";
import type { ExecutionActivityDay } from "@/schemas";

/**
 * Block math and formatting shared by the execution activity charts on the Execution page and
 * Home, so both draw a bucket the same way and only differ in how tall a column may grow.
 */

export type ActivityStatusKey =
  | "completed"
  | "failed"
  | "running"
  | "scheduled"
  | "cancelled"
  | "other";

/** Stacking order, bottom to top. */
const ACTIVITY_SERIES: ReadonlyArray<{ key: ActivityStatusKey; label: string }> = [
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
  { key: "running", label: "Running" },
  { key: "scheduled", label: "Scheduled" },
  { key: "cancelled", label: "Cancelled" },
  { key: "other", label: "Other" },
];

/** One status's share of a block. */
interface ActivitySegment {
  status: ActivityStatusKey;
  /** Executions this segment stands for; its height is this divided by the scale. */
  executions: number;
  /** True when the segment fills less than a whole block. */
  partial: boolean;
}

/**
 * One block of a column: `scale` executions' worth of height. Statuses stack through the
 * column in order, so a block may hold several statuses, and only the top block may be
 * partly filled. A column's height is therefore exactly its total divided by the scale.
 */
interface ActivityBlock {
  segments: ActivitySegment[];
  /** Executions in the block, at most the scale. */
  executions: number;
}

export interface ActivityDayColumn {
  /** Calendar day the bucket starts on, YYYY-MM-DD. */
  date: string;
  /** The date as YYYYMMDD, the form the execution list filter uses. */
  compact: string;
  /** Bucket start and exclusive end, ISO 8601 in UTC. */
  start: string;
  end: string;
  /**
   * Local hours the bucket covers, such as "12:00–18:00", ending at 24:00 on the next midnight;
   * empty when no time zone was given, as daily charts never show hours.
   */
  hours: string;
  total: number;
  counts: ReadonlyArray<{ key: ActivityStatusKey; label: string; count: number }>;
  blocks: ActivityBlock[];
}

/** Local date and "HH:MM" of an instant in `timeZone`. */
const wallClockFormats = new Map<string, Intl.DateTimeFormat>();

function wallClock(iso: string, timeZone: string) {
  let format = wallClockFormats.get(timeZone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    wallClockFormats.set(timeZone, format);
  }
  const parts = Object.fromEntries(
    format.formatToParts(new Date(iso)).map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

function bucketHours(bucket: ExecutionActivityDay, timeZone: string): string {
  const end = wallClock(bucket.end, timeZone);
  return `${wallClock(bucket.start, timeZone).time}–${end.date === bucket.date ? end.time : "24:00"}`;
}

const activityCount = (bucket: ExecutionActivityDay, key: ActivityStatusKey) => bucket[key] ?? 0;

const bucketTotal = (bucket: ExecutionActivityDay) =>
  ACTIVITY_SERIES.reduce((acc, { key }) => acc + activityCount(bucket, key), 0);

/** Smallest 1-2-5 step that keeps every bucket within `maxBlocks` blocks. */
export function activityBlockScale(
  buckets: readonly ExecutionActivityDay[],
  maxBlocks: number,
): number {
  const busiest = buckets.reduce((acc, bucket) => Math.max(acc, bucketTotal(bucket)), 0);
  for (let magnitude = 1; ; magnitude *= 10) {
    for (const step of [1, 2, 5]) {
      const scale = step * magnitude;
      if (Math.ceil(busiest / scale) <= maxBlocks) return scale;
    }
  }
}

/**
 * Draws a bucket as blocks of `scale` executions. `timeZone`, the zone the buckets were counted
 * in, gives the bucket's local hours, the same ones the API used for its boundaries.
 */
export function toActivityColumn(
  bucket: ExecutionActivityDay,
  scale: number,
  timeZone?: string,
): ActivityDayColumn {
  const blocks: ActivityBlock[] = [];
  let open: ActivityBlock | null = null;
  for (const { key } of ACTIVITY_SERIES) {
    let left = activityCount(bucket, key);
    while (left > 0) {
      if (!open || open.executions === scale) {
        open = { segments: [], executions: 0 };
        blocks.push(open);
      }
      const take = Math.min(left, scale - open.executions);
      open.segments.push({ status: key, executions: take, partial: take < scale });
      open.executions += take;
      left -= take;
    }
  }
  const counts = activityCounts(bucket);
  return {
    date: bucket.date,
    compact: bucket.date.replace(/-/g, ""),
    start: bucket.start,
    end: bucket.end,
    hours: timeZone ? bucketHours(bucket, timeZone) : "",
    total: counts.reduce((acc, item) => acc + item.count, 0),
    counts,
    blocks,
  };
}

/** A bucket's executions per status, in stacking order. */
export const activityCounts = (bucket: ExecutionActivityDay) =>
  ACTIVITY_SERIES.map((series) => ({ ...series, count: activityCount(bucket, series.key) }));

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

/** Bucket length the activity endpoint was asked for. */
export type ActivityGranularity = "day" | "6h";

/** What a bucket's title and description need: its day, hours and counts. */
export type ActivityDaySummary = Pick<ActivityDayColumn, "date" | "hours" | "total" | "counts">;

/** Heading of a bucket: its day, plus its hours for a 6-hour bucket. */
export function activityBucketTitle(
  column: ActivityDaySummary,
  granularity: ActivityGranularity,
): string {
  const day = longActivityDate.format(parseActivityDay(column.date));
  return granularity === "6h" ? `${day}, ${column.hours}` : day;
}

/** One-line description of a bucket, for accessible names. */
export function describeActivityDay(
  column: ActivityDaySummary,
  granularity: ActivityGranularity = "day",
): string {
  const parts = column.counts
    .filter((item) => item.count > 0)
    .map((item) => `${item.count} ${item.label.toLowerCase()}`);
  const summary = pluralize(column.total, "execution");
  return `${activityBucketTitle(column, granularity)}: ${summary}${parts.length ? `, ${parts.join(", ")}` : ""}`;
}

/** Fill style of a status segment; "other" is outlined so it stays apart from cancelled. */
export function activityBlockStyler(palette: ChartTheme) {
  const colors: Record<ActivityStatusKey, string> = {
    completed: palette.pass,
    failed: palette.fail,
    running: palette.accent,
    scheduled: palette.warn,
    cancelled: palette.muted,
    other: palette.muted,
  };
  return (status: ActivityStatusKey): CSSProperties =>
    status === "other"
      ? { border: `1px solid ${colors.other}` }
      : { backgroundColor: colors[status] };
}

/** One-line legend of the block scale. */
export const activityScaleNote = (scale: number) =>
  scale === 1
    ? "1 block = 1 execution"
    : `1 block = ${scale} executions, a partly filled block holds fewer`;

/**
 * One-sentence summary of a window, such as "12 in the last 30 days, 2 failed, 1 in progress.";
 * failed and in-progress counts appear only when non-zero.
 */
export function activityWindowSummary(
  totals: ReadonlyArray<{ key: ActivityStatusKey; count: number }>,
  days: number,
): string {
  const count = (key: ActivityStatusKey) => totals.find((item) => item.key === key)?.count ?? 0;
  const total = totals.reduce((acc, item) => acc + item.count, 0);
  const failed = count("failed");
  const running = count("running");
  return (
    `${total} in the last ${days} days` +
    (failed > 0 ? `, ${failed} failed` : "") +
    (running > 0 ? `, ${running} in progress` : "") +
    "."
  );
}
