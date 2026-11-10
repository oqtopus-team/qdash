"use client";

import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";

import { type KeyboardEvent, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import type { ExecutionActivityDay } from "@/schemas";

import {
  activityBlockStyler,
  describeActivityDay,
  longActivityDate,
  parseActivityDay,
  pluralize,
} from "./executionActivityBlocks";
import {
  ACTIVITY_LEVEL_CLASSES,
  ACTIVITY_LEVELS,
  type HeatmapDay,
  buildActivityHeatmap,
} from "./executionActivityLevels";

type ActivityHeatmapDensity = "compact" | "full";

/** Cell, column and gap sizes per density; label rows reuse them to stay aligned. */
const SIZES: Record<
  ActivityHeatmapDensity,
  { cell: string; width: string; height: string; gap: string }
> = {
  compact: { cell: "size-3", width: "w-3", height: "h-3", gap: "gap-0.5" },
  full: {
    cell: "size-3 sm:size-4",
    width: "w-3 sm:w-4",
    height: "h-3 sm:h-4",
    gap: "gap-0.5 sm:gap-1",
  },
};

/** Weekday rows that carry a label, Sunday first; the others stay blank like most calendars. */
const WEEKDAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];

/** Day keyboard moves: rows are weekdays, so up and down step a day and left and right a week. */
const KEY_STEPS: Record<string, number> = {
  ArrowUp: -1,
  ArrowDown: 1,
  ArrowLeft: -7,
  ArrowRight: 7,
};

interface ExecutionActivityHeatmapProps {
  /** Daily buckets of the activity endpoint, oldest first, empty days included. */
  buckets: readonly ExecutionActivityDay[];
  density: ActivityHeatmapDensity;
  /** Accessible name of the day grid, including what selecting a day does. */
  label: string;
  /** Selected day as YYYYMMDD, or `latest` for none. */
  selectedDate?: string;
  /** Called with a day's YYYYMMDD when it is activated; days render as buttons. */
  onDaySelect?: (date: string) => void;
  /** Link target of a day; days render as links instead of buttons. */
  dayHref?: (date: string) => string;
  /** Last line of a day's tooltip, saying what selecting it does. */
  dayHint?: (day: HeatmapDay, selected: boolean) => string;
}

/**
 * Executions per calendar day as a heatmap: one column per week, one row per weekday, with month
 * and weekday labels and a Less/More legend. Color shows how many executions ran, on the fixed
 * scale of `ACTIVITY_LEVELS`; exact counts per status are in each day's tooltip and accessible
 * name. The grid is one tab stop: arrow keys move by day and week, Home and End jump to the
 * first and last day. Wide windows scroll horizontally instead of shrinking the cells.
 */
export function ExecutionActivityHeatmap({
  buckets,
  density,
  label,
  selectedDate = "latest",
  onDaySelect,
  dayHref,
  dayHint,
}: ExecutionActivityHeatmapProps) {
  const blockStyle = activityBlockStyler(chartTheme(useIsDarkTheme()));
  const sizes = SIZES[density];
  const { days, weeks, monthLabels } = useMemo(() => buildActivityHeatmap(buckets), [buckets]);

  const selectedIndex = days.findIndex((day) => day.compact === selectedDate);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const activeIndex =
    focusIndex !== null && focusIndex < days.length
      ? focusIndex
      : selectedIndex >= 0
        ? selectedIndex
        : days.length - 1;
  const dayRefs = useRef<Array<HTMLElement | null>>([]);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>, index: number) => {
    let next: number;
    if (event.key in KEY_STEPS) next = index + KEY_STEPS[event.key];
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = days.length - 1;
    else return;
    event.preventDefault();
    next = Math.min(Math.max(next, 0), days.length - 1);
    setFocusIndex(next);
    dayRefs.current[next]?.focus();
  };

  const labelAt = new Map(monthLabels.map((item) => [item.week, item.label]));

  const renderDay = (day: HeatmapDay) => {
    const selected = day.compact === selectedDate;
    const common = {
      ref: (node: HTMLElement | null) => {
        dayRefs.current[day.index] = node;
      },
      tabIndex: day.index === activeIndex ? 0 : -1,
      "aria-label": describeActivityDay(day),
      "data-date": day.date,
      "data-level": day.level,
      onFocus: () => setFocusIndex(day.index),
      onKeyDown: (event: KeyboardEvent<HTMLElement>) => handleKeyDown(event, day.index),
      className: `block rounded-xs ${sizes.cell} ${ACTIVITY_LEVEL_CLASSES[day.level]} ${
        selected ? "ring-2 ring-base-content ring-offset-1 ring-offset-base-100" : ""
      } cursor-pointer transition-shadow focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary`,
    };
    const trigger = dayHref ? (
      <Link {...common} href={dayHref(day.compact)} />
    ) : (
      <button
        {...common}
        type="button"
        aria-pressed={selected}
        onClick={() => onDaySelect?.(day.compact)}
      />
    );
    const statuses = day.counts.filter((item) => item.count > 0);
    return (
      <Tooltip key={day.date}>
        <TooltipTrigger asChild>{trigger}</TooltipTrigger>
        <TooltipContent side="top">
          <p className="font-medium">{longActivityDate.format(parseActivityDay(day.date))}</p>
          <p className="text-base-content/60">{pluralize(day.total, "execution")}</p>
          {statuses.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {statuses.map((item) => (
                <li key={item.key} className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-xs"
                    style={blockStyle(item.key)}
                  />
                  <span>{item.label}</span>
                  <span className="ml-auto font-mono">{item.count}</span>
                </li>
              ))}
            </ul>
          )}
          {dayHint && <p className="mt-1 text-base-content/60">{dayHint(day, selected)}</p>}
        </TooltipContent>
      </Tooltip>
    );
  };

  return (
    <div className="min-w-0">
      <div className="overflow-x-auto pb-1" data-testid="activity-heatmap-scroll">
        <div className="flex w-max gap-1.5 text-xs text-base-content/60">
          <div aria-hidden="true" className={`flex flex-col ${sizes.gap} pt-5`}>
            {WEEKDAY_LABELS.map((weekday, row) => (
              <span key={row} className={`${sizes.height} flex items-center leading-none`}>
                {weekday}
              </span>
            ))}
          </div>
          <div>
            <div aria-hidden="true" className={`flex h-4 ${sizes.gap} mb-1`}>
              {weeks.map((_, weekIndex) => (
                <span key={weekIndex} className={`relative ${sizes.width}`}>
                  {labelAt.has(weekIndex) && (
                    <span className="absolute top-0 left-0 whitespace-nowrap leading-none">
                      {labelAt.get(weekIndex)}
                    </span>
                  )}
                </span>
              ))}
            </div>
            <div role="group" aria-label={label} className={`flex ${sizes.gap}`}>
              {weeks.map((week, weekIndex) => (
                <div key={weekIndex} className={`flex flex-col ${sizes.gap}`}>
                  {week.map((day, row) =>
                    day ? (
                      renderDay(day)
                    ) : (
                      <span
                        key={`pad-${row}`}
                        aria-hidden="true"
                        className={`block ${sizes.cell}`}
                      />
                    ),
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div
        className="mt-2 flex items-center justify-end gap-1 text-xs text-base-content/60"
        data-testid="activity-heatmap-legend"
      >
        <span aria-hidden="true">Less</span>
        <ul className="flex gap-0.5" aria-label="Executions per day, by color">
          {ACTIVITY_LEVELS.map((item) => (
            <li key={item.level} data-level={item.level}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    className={`block rounded-xs ${sizes.cell} ${ACTIVITY_LEVEL_CLASSES[item.level]}`}
                  >
                    <span className="sr-only">{item.label}</span>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{item.label}</TooltipContent>
              </Tooltip>
            </li>
          ))}
        </ul>
        <span aria-hidden="true">More</span>
      </div>
    </div>
  );
}
