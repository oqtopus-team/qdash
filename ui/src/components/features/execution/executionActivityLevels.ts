import type { ExecutionActivityDay } from "@/schemas";

import {
  type ActivityDaySummary,
  activityCounts,
  parseActivityDay,
} from "./executionActivityBlocks";

/**
 * Calendar layout and intensity scale of the execution activity heatmap, shared by Home and the
 * Execution page so a day with the same count gets the same level and color everywhere.
 */

/** Intensity level of a day, 0 for no executions up to 4 for the busiest. */
export type ActivityLevel = 0 | 1 | 2 | 3 | 4;

/**
 * Fixed, roughly logarithmic levels. The bounds never depend on the window or the busiest day,
 * so one count always maps to one level whatever range or scope is shown.
 */
export const ACTIVITY_LEVELS: ReadonlyArray<{ level: ActivityLevel; min: number; label: string }> =
  [
    { level: 0, min: 0, label: "No executions" },
    { level: 1, min: 1, label: "1–4 executions" },
    { level: 2, min: 5, label: "5–19 executions" },
    { level: 3, min: 20, label: "20–99 executions" },
    { level: 4, min: 100, label: "100 or more executions" },
  ];

/** Fill of each level: a neutral cell for zero, then the primary color with rising opacity. */
export const ACTIVITY_LEVEL_CLASSES: Readonly<Record<ActivityLevel, string>> = {
  0: "bg-base-content/10",
  1: "bg-primary/25",
  2: "bg-primary/50",
  3: "bg-primary/75",
  4: "bg-primary",
};

export function activityLevel(count: number): ActivityLevel {
  let level: ActivityLevel = 0;
  for (const bound of ACTIVITY_LEVELS) {
    if (count >= bound.min) level = bound.level;
  }
  return level;
}

export interface HeatmapDay extends ActivityDaySummary {
  /** The date as YYYYMMDD, the form the execution list filter uses. */
  compact: string;
  /** Position in the window, oldest first; keyboard navigation moves by this index. */
  index: number;
  /** 0 for Sunday, the first row, through 6 for Saturday. */
  weekday: number;
  level: ActivityLevel;
}

export interface HeatmapLayout {
  days: HeatmapDay[];
  /** Week columns, oldest first; each holds seven rows, null outside the window. */
  weeks: Array<Array<HeatmapDay | null>>;
  /** Month names placed on the week column where the month starts. */
  monthLabels: Array<{ week: number; label: string }>;
}

const monthName = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });

/** Weeks a month label needs before the next one, so short labels do not overlap. */
const MIN_LABEL_WEEKS = 3;

/**
 * Lays daily buckets out as a calendar: one column per week starting on Sunday, one row per
 * weekday. Bucket dates are calendar days in the zone the API counted in, so they are read as
 * plain dates and never shifted into the browser's time zone.
 */
export function buildActivityHeatmap(buckets: readonly ExecutionActivityDay[]): HeatmapLayout {
  const days: HeatmapDay[] = buckets.map((bucket, index) => {
    const counts = activityCounts(bucket);
    const total = counts.reduce((acc, item) => acc + item.count, 0);
    return {
      date: bucket.date,
      compact: bucket.date.replace(/-/g, ""),
      hours: "",
      total,
      counts,
      index,
      weekday: parseActivityDay(bucket.date).getUTCDay(),
      level: activityLevel(total),
    };
  });

  const weeks: Array<Array<HeatmapDay | null>> = [];
  for (const day of days) {
    if (weeks.length === 0 || day.weekday === 0) weeks.push(Array(7).fill(null));
    weeks[weeks.length - 1][day.weekday] = day;
  }

  const monthLabels: Array<{ week: number; label: string }> = [];
  weeks.forEach((week, weekIndex) => {
    const starts = week.find((day) => day && day.date.endsWith("-01"));
    if (starts) {
      monthLabels.push({ week: weekIndex, label: monthName.format(parseActivityDay(starts.date)) });
    }
  });
  // The first, partial month is named only when there is room before the next label.
  const first = weeks[0]?.find((day) => day !== null);
  if (first && monthLabels[0]?.week !== 0) {
    const next = monthLabels[0]?.week ?? weeks.length;
    if (next >= MIN_LABEL_WEEKS) {
      monthLabels.unshift({ week: 0, label: monthName.format(parseActivityDay(first.date)) });
    }
  }

  return { days, weeks, monthLabels };
}

/** YYYYMMDD as a long date, such as "Mon, Nov 2, 2026", without a time zone shift. */
export function formatCompactActivityDate(compact: string, format: Intl.DateTimeFormat): string {
  return format.format(
    parseActivityDay(`${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}`),
  );
}
