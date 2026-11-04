"use client";

import { type KeyboardEvent, useCallback, useMemo, useRef, useState } from "react";

import { useGetExecutionActivity } from "@/client/execution/execution";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";
import { DEFAULT_TIMEZONE } from "@/lib/utils/datetime";

import { ActivityBlockStack } from "./ActivityBlockStack";
import {
  type ActivityDayColumn,
  type ActivityGranularity,
  activityBlockScale,
  activityBlockStyler,
  activityBucketTitle,
  activityScaleNote,
  activityStatusTotals,
  describeActivityDay,
  longActivityDate,
  parseActivityDay,
  pluralize,
  shortActivityDate,
  toActivityColumn,
} from "./executionActivityBlocks";

const ACTIVITY_WINDOWS = [7, 30, 90] as const;
export type ActivityWindow = (typeof ACTIVITY_WINDOWS)[number];
export const DEFAULT_ACTIVITY_WINDOW: ActivityWindow = 30;

/**
 * Seven daily columns are too sparse to read, so the 7-day window asks for 6-hour buckets:
 * 28 columns, about as dense as the 30-day window.
 */
const activityGranularity = (days: ActivityWindow): ActivityGranularity =>
  days === 7 ? "6h" : "day";

/** Tallest column in blocks; denser buckets are drawn with one block per several executions. */
const MAX_BLOCKS = 20;
/** Shortest grid, so a quiet window still reads as a grid of small blocks. */
const MIN_ROWS = 10;
/** Blocks between count guides on the y axis; the grid height is a multiple of it. */
const GUIDE_STEP = 5;

/** Every `step`-th daily column from the latest backwards carries a date under it. */
const labelStep = (columns: number) => (columns <= 7 ? 1 : columns <= 31 ? 5 : 15);

/**
 * Offset of the boundary below block `k` in a stack of `rows` blocks with 1px gaps, so a guide
 * sits on the gap between two blocks rather than drifting by up to half a pixel.
 */
const guideOffset = (k: number, rows: number) =>
  k === 0
    ? "0px"
    : k === rows
      ? "100%"
      : `calc((100% - ${rows - 1}px) * ${k / rows} + ${k - 0.5}px)`;

/** Count guides along the left of the grid; labels are execution counts, so integers. */
function ActivityYAxis({ rows, scale }: { rows: number; scale: number }) {
  const guides = Array.from({ length: rows / GUIDE_STEP + 1 }, (_, index) => index * GUIDE_STEP);
  return (
    <div
      aria-hidden="true"
      data-testid="activity-y-axis"
      className="h-40 w-8 shrink-0 py-1 text-right text-xs leading-none text-base-content/60"
    >
      <div className="relative h-full border-r border-base-300">
        {guides.map((k) => (
          <span
            key={k}
            data-guide={k * scale}
            className="absolute right-0 flex translate-y-1/2 items-center gap-1 tabular-nums"
            style={{ bottom: guideOffset(k, rows) }}
          >
            {k * scale}
            <span className="h-px w-1 bg-base-300" />
          </span>
        ))}
      </div>
    </div>
  );
}

interface ExecutionActivityChartProps {
  chipId: string;
  days: ActivityWindow;
  onDaysChange: (days: ActivityWindow) => void;
  /** Date filter of the list below, `latest` or YYYYMMDD; the matching day is highlighted. */
  selectedDate: string;
  /** Called with YYYYMMDD when a day is selected, or `latest` when the selection is cleared. */
  onDateSelect: (date: string) => void;
}

/**
 * Executions for the selected chip over the last 7, 30 or 90 days, drawn as a column of small
 * blocks per bucket stacked by status: 6-hour buckets for 7 days, daily buckets otherwise. One
 * block is one execution until the busiest bucket no longer fits, after which each block stands
 * for a labeled number of executions and the top block of a column may be partly filled.
 * Selecting a bucket filters the execution list to the day it starts on, since the list filters
 * by day; selecting that day again clears the filter.
 */
export function ExecutionActivityChart({
  chipId,
  days,
  onDaysChange,
  selectedDate,
  onDateSelect,
}: ExecutionActivityChartProps) {
  const palette = chartTheme(useIsDarkTheme());
  const { data, isLoading, isError } = useGetExecutionActivity(
    { chip_id: chipId, days, timezone: DEFAULT_TIMEZONE, granularity: activityGranularity(days) },
    { query: { enabled: !!chipId, refetchInterval: 60_000 } },
  );
  const activity = data?.data;
  const buckets = useMemo(() => activity?.buckets ?? [], [activity]);
  const timeZone = activity?.timezone ?? DEFAULT_TIMEZONE;
  const granularity: ActivityGranularity = activity?.granularity ?? activityGranularity(days);
  const sixHour = granularity === "6h";

  const { scale, columns, rows, totals } = useMemo(() => {
    const blockSize = activityBlockScale(buckets, MAX_BLOCKS);
    const bucketColumns = buckets.map((bucket) => toActivityColumn(bucket, blockSize, timeZone));
    const tallest = bucketColumns.reduce((acc, column) => Math.max(acc, column.blocks.length), 0);
    return {
      scale: blockSize,
      columns: bucketColumns,
      rows: Math.max(MIN_ROWS, Math.ceil(tallest / GUIDE_STEP) * GUIDE_STEP),
      totals: activityStatusTotals(buckets),
    };
  }, [buckets, timeZone]);

  const total = totals.reduce((acc, item) => acc + item.count, 0);
  const failed = totals.find((item) => item.key === "failed")?.count ?? 0;
  const running = totals.find((item) => item.key === "running")?.count ?? 0;

  const blockStyle = activityBlockStyler(palette);

  // A 6-hour bucket selects its whole day, so every bucket of that day reads as selected.
  const selectedIndex = columns.findIndex((column) => column.compact === selectedDate);
  const selectedColumn = selectedIndex >= 0 ? columns[selectedIndex] : null;

  // Roving focus: the grid is one tab stop, arrow keys move between buckets.
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const activeIndex =
    focusIndex !== null && focusIndex < columns.length
      ? focusIndex
      : selectedIndex >= 0
        ? selectedIndex
        : columns.length - 1;
  const columnRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const moveFocus = useCallback(
    (index: number) => {
      const next = Math.min(Math.max(index, 0), columns.length - 1);
      setFocusIndex(next);
      columnRefs.current[next]?.focus();
    },
    [columns.length],
  );

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const targets: Record<string, number> = {
      ArrowLeft: index - 1,
      ArrowRight: index + 1,
      Home: 0,
      End: columns.length - 1,
    };
    if (!(event.key in targets)) return;
    event.preventDefault();
    moveFocus(targets[event.key]);
  };

  const toggleDay = (column: ActivityDayColumn) =>
    onDateSelect(column.compact === selectedDate ? "latest" : column.compact);

  const step = labelStep(columns.length);
  const showChart = !isError && !isLoading && total > 0;
  const gap = columns.length > 31 ? "gap-px" : "gap-0.5 sm:gap-1";

  /** Whether a column carries a date label: a day's first 6-hour bucket, or every step-th day. */
  const isLabeled = (index: number) => {
    const column = columns[index];
    if (index === selectedIndex) return true;
    if (!sixHour) return (columns.length - 1 - index) % step === 0;
    // The oldest bucket may start mid-day; only a bucket that opens its day gets the date.
    return index > 0 ? columns[index - 1].date !== column.date : column.hours.startsWith("00:");
  };

  return (
    <section
      aria-labelledby="execution-activity-heading"
      className="mb-6 rounded-box border border-base-300 bg-base-100 p-4"
    >
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="execution-activity-heading" className="text-sm font-medium">
            {sixHour ? "Executions per 6 hours" : "Executions per day"}
          </h2>
          <p className="text-sm text-base-content/60">
            {isLoading
              ? "Loading"
              : isError
                ? `Last ${days} days`
                : `${total} in the last ${days} days` +
                  (failed > 0 ? `, ${failed} failed` : "") +
                  (running > 0 ? `, ${running} in progress` : "") +
                  "."}
          </p>
        </div>
        <div
          className="tabs tabs-boxed w-fit bg-base-200"
          role="tablist"
          aria-label="Activity window"
        >
          {ACTIVITY_WINDOWS.map((window) => (
            <button
              key={window}
              type="button"
              role="tab"
              aria-selected={window === days}
              className={`tab ${window === days ? "tab-active" : ""}`}
              onClick={() => onDaysChange(window)}
            >
              {window}d
            </button>
          ))}
        </div>
      </div>
      {isError ? (
        <p role="alert" className="py-8 text-center text-sm text-base-content/60">
          Execution activity could not be loaded.
        </p>
      ) : isLoading ? (
        <div className="skeleton h-52 w-full" aria-hidden="true" />
      ) : !showChart ? (
        <p className="py-8 text-center text-sm text-base-content/60">
          No executions in the last {days} days
        </p>
      ) : (
        <>
          <p aria-hidden="true" className="mb-1 text-xs text-base-content/60">
            Executions
          </p>
          <div className="flex items-start gap-1.5">
            <ActivityYAxis rows={rows} scale={scale} />
            <div className="min-w-0 flex-1 overflow-x-auto pb-1">
              <div
                role="toolbar"
                aria-label={
                  sixHour
                    ? "Executions per 6 hours. Select a 6-hour bucket to show its whole day in the list"
                    : "Executions per day. Select a day to show it in the list"
                }
                className={`flex min-w-full ${gap}`}
              >
                {columns.map((column, index) => {
                  const selected = column.compact === selectedDate;
                  return (
                    <Tooltip key={column.start}>
                      <TooltipTrigger asChild>
                        <button
                          ref={(node) => {
                            columnRefs.current[index] = node;
                          }}
                          type="button"
                          tabIndex={index === activeIndex ? 0 : -1}
                          aria-pressed={selected}
                          aria-label={describeActivityDay(column, granularity)}
                          data-date={column.date}
                          data-start={column.start}
                          onClick={() => toggleDay(column)}
                          onFocus={() => setFocusIndex(index)}
                          onKeyDown={(event) => handleKeyDown(event, index)}
                          className={`flex h-40 min-w-1.5 flex-1 cursor-pointer justify-center rounded-sm px-px py-1 transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary ${
                            selected ? "bg-primary/12" : "hover:bg-base-200"
                          }`}
                        >
                          <ActivityBlockStack
                            column={column}
                            rows={rows}
                            scale={scale}
                            blockStyle={blockStyle}
                            className="max-w-4"
                          />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <p className="font-medium">{activityBucketTitle(column, granularity)}</p>
                        <p className="text-base-content/60">
                          {pluralize(column.total, "execution")}
                        </p>
                        {column.total > 0 && (
                          <ul className="mt-1 space-y-0.5">
                            {column.counts
                              .filter((item) => item.count > 0)
                              .map((item) => (
                                <li key={item.key} className="flex items-center gap-1.5">
                                  <span
                                    aria-hidden="true"
                                    className="size-2 rounded-xs"
                                    style={blockStyle(item.key)}
                                  />
                                  <span>{item.label}</span>
                                  <span className="ml-auto pl-3 font-mono">{item.count}</span>
                                </li>
                              ))}
                          </ul>
                        )}
                        {sixHour && (
                          <p className="mt-1 text-base-content/60">
                            {selected
                              ? `Select to stop showing ${shortActivityDate.format(parseActivityDay(column.date))}`
                              : `Select to show all of ${shortActivityDate.format(parseActivityDay(column.date))} in the list`}
                          </p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
              <div
                aria-hidden="true"
                className={`mt-1 flex min-w-full text-xs text-base-content/60 ${gap}`}
              >
                {columns.map((column, index) => {
                  const fromEnd = columns.length - 1 - index;
                  const selected = index === selectedIndex;
                  // Keep edge labels inside the chart instead of centering them past its border;
                  // a 6-hour label starts where its day starts.
                  const align =
                    fromEnd === 0
                      ? "right-0"
                      : index === 0 || sixHour
                        ? "left-0"
                        : "left-1/2 -translate-x-1/2";
                  return (
                    <span key={column.start} className="relative h-4 min-w-1.5 flex-1">
                      {isLabeled(index) && (
                        <span
                          className={`absolute top-0 whitespace-nowrap ${align} ${
                            selected ? "z-10 rounded-sm bg-base-100 px-0.5 text-primary" : ""
                          }`}
                        >
                          {shortActivityDate.format(parseActivityDay(column.date))}
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-col gap-2 text-xs text-base-content/60 sm:flex-row sm:items-center sm:justify-between">
            <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Executions by status">
              {totals
                .filter((item) => item.count > 0)
                .map((item) => (
                  <li key={item.key} className="flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="size-2 rounded-xs"
                      style={blockStyle(item.key)}
                    />
                    <span>
                      {item.label} <span className="font-mono">{item.count}</span>
                    </span>
                  </li>
                ))}
            </ul>
            <p data-testid="activity-scale">{activityScaleNote(scale)}</p>
          </div>
          <p className="mt-2 text-xs text-base-content/60" aria-live="polite">
            {selectedColumn
              ? `Showing ${longActivityDate.format(parseActivityDay(selectedColumn.date))} in the list. ` +
                (sixHour
                  ? "Select any of its 6-hour buckets again to show the latest executions."
                  : "Select it again to show the latest executions.")
              : sixHour
                ? "Select a 6-hour bucket to show all executions of its day in the list."
                : "Select a day to show its executions in the list."}
          </p>
        </>
      )}
    </section>
  );
}
