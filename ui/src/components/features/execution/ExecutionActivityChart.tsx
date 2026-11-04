"use client";

import {
  type CSSProperties,
  type KeyboardEvent,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";

import { useGetExecutionActivity } from "@/client/execution/execution";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";
import { DEFAULT_TIMEZONE } from "@/lib/utils/datetime";
import type { ExecutionActivityDay } from "@/schemas";

const ACTIVITY_WINDOWS = [7, 30, 90] as const;
export type ActivityWindow = (typeof ACTIVITY_WINDOWS)[number];

type StatusKey = Exclude<keyof ExecutionActivityDay, "date" | "total">;

/** Stacking order, bottom to top. */
const SERIES: ReadonlyArray<{ key: StatusKey; label: string }> = [
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
  { key: "running", label: "Running" },
  { key: "scheduled", label: "Scheduled" },
  { key: "cancelled", label: "Cancelled" },
  { key: "other", label: "Other" },
];

/** Tallest column in blocks; denser days are drawn with one block per several executions. */
const MAX_BLOCKS = 20;
/** Shortest grid, so a quiet window still reads as a grid of small blocks. */
const MIN_ROWS = 10;
/** Opacity of a block that stands for fewer executions than the scale. */
const PARTIAL_OPACITY = 0.45;

interface Block {
  status: StatusKey;
  /** Executions this block stands for: the scale, or the remainder for a partial block. */
  executions: number;
  partial: boolean;
}

interface DayColumn {
  date: string;
  compact: string;
  total: number;
  counts: ReadonlyArray<{ key: StatusKey; label: string; count: number }>;
  blocks: Block[];
}

const count = (bucket: ExecutionActivityDay, key: StatusKey) => bucket[key] ?? 0;

/** Blocks a day needs when one block stands for `scale` executions; each status rounds up. */
const blocksNeeded = (bucket: ExecutionActivityDay, scale: number) =>
  SERIES.reduce((acc, { key }) => acc + Math.ceil(count(bucket, key) / scale), 0);

/**
 * Smallest 1-2-5 step that keeps every day within MAX_BLOCKS. A step always exists because a
 * day needs at most one block per status once the step exceeds its largest count.
 */
function blockScale(buckets: readonly ExecutionActivityDay[]): number {
  for (let magnitude = 1; ; magnitude *= 10) {
    for (const step of [1, 2, 5]) {
      const scale = step * magnitude;
      if (buckets.every((bucket) => blocksNeeded(bucket, scale) <= MAX_BLOCKS)) return scale;
    }
  }
}

function toColumn(bucket: ExecutionActivityDay, scale: number): DayColumn {
  const blocks: Block[] = [];
  for (const { key } of SERIES) {
    const value = count(bucket, key);
    for (let i = 0; i < Math.floor(value / scale); i += 1) {
      blocks.push({ status: key, executions: scale, partial: false });
    }
    const remainder = value % scale;
    if (remainder > 0) blocks.push({ status: key, executions: remainder, partial: true });
  }
  const counts = SERIES.map((series) => ({ ...series, count: count(bucket, series.key) }));
  return {
    date: bucket.date,
    compact: bucket.date.replace(/-/g, ""),
    total: counts.reduce((acc, item) => acc + item.count, 0),
    counts,
    blocks,
  };
}

function parseDay(date: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

// Bucket dates are calendar days in the requested zone, so they are formatted as UTC midnight.
const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const longDate = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const plural = (value: number, noun: string) => `${value} ${noun}${value === 1 ? "" : "s"}`;

function describeDay(column: DayColumn): string {
  const parts = column.counts
    .filter((item) => item.count > 0)
    .map((item) => `${item.count} ${item.label.toLowerCase()}`);
  const summary = plural(column.total, "execution");
  return `${longDate.format(parseDay(column.date))}: ${summary}${parts.length ? `, ${parts.join(", ")}` : ""}`;
}

/** Every `step`-th column from the latest backwards carries a date under it. */
const labelStep = (columns: number) => (columns <= 7 ? 1 : columns <= 31 ? 5 : 15);

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
 * Executions per day for the selected chip over the last 7, 30 or 90 days, drawn as a column
 * of small blocks per day stacked by status. One block is one execution until the busiest day
 * no longer fits, after which each block stands for a labeled number of executions.
 * Selecting a day filters the execution list to that day; selecting it again clears the filter.
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
    { chip_id: chipId, days, timezone: DEFAULT_TIMEZONE },
    { query: { enabled: !!chipId, refetchInterval: 60_000 } },
  );
  const activity = data?.data;
  const buckets = useMemo(() => activity?.buckets ?? [], [activity]);

  const { scale, columns, rows, totals } = useMemo(() => {
    const blockSize = blockScale(buckets);
    const dayColumns = buckets.map((bucket) => toColumn(bucket, blockSize));
    const tallest = dayColumns.reduce((acc, column) => Math.max(acc, column.blocks.length), 0);
    const statusTotals = SERIES.map((series) => ({
      ...series,
      count: buckets.reduce((acc, bucket) => acc + count(bucket, series.key), 0),
    }));
    return {
      scale: blockSize,
      columns: dayColumns,
      rows: Math.max(MIN_ROWS, tallest),
      totals: statusTotals,
    };
  }, [buckets]);

  const total = totals.reduce((acc, item) => acc + item.count, 0);
  const failed = totals.find((item) => item.key === "failed")?.count ?? 0;
  const running = totals.find((item) => item.key === "running")?.count ?? 0;

  const colors: Record<StatusKey, string> = {
    completed: palette.pass,
    failed: palette.fail,
    running: palette.accent,
    scheduled: palette.warn,
    cancelled: palette.muted,
    other: palette.muted,
  };
  // "Other" is outlined so it stays apart from cancelled, which shares the muted color.
  const blockStyle = (status: StatusKey, partial: boolean): CSSProperties => ({
    ...(status === "other"
      ? { border: `1px solid ${colors.other}` }
      : { backgroundColor: colors[status] }),
    opacity: partial ? PARTIAL_OPACITY : 1,
  });

  const selectedIndex = columns.findIndex((column) => column.compact === selectedDate);
  const selectedColumn = selectedIndex >= 0 ? columns[selectedIndex] : null;

  // Roving focus: the day grid is one tab stop, arrow keys move between days.
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

  const toggleDay = (column: DayColumn) =>
    onDateSelect(column.compact === selectedDate ? "latest" : column.compact);

  const step = labelStep(columns.length);
  const showChart = !isError && !isLoading && total > 0;

  return (
    <section
      aria-labelledby="execution-activity-heading"
      className="mb-6 rounded-box border border-base-300 bg-base-100 p-4"
    >
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="execution-activity-heading" className="text-sm font-medium">
            Executions per day
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
          <div className="overflow-x-auto pb-1">
            <div
              role="toolbar"
              aria-label="Executions per day. Select a day to show it in the list"
              className={`flex min-w-full ${columns.length > 31 ? "gap-px" : "gap-0.5 sm:gap-1"}`}
            >
              {columns.map((column, index) => {
                const selected = index === selectedIndex;
                const empties = rows - column.blocks.length;
                return (
                  <Tooltip key={column.date}>
                    <TooltipTrigger asChild>
                      <button
                        ref={(node) => {
                          columnRefs.current[index] = node;
                        }}
                        type="button"
                        tabIndex={index === activeIndex ? 0 : -1}
                        aria-pressed={selected}
                        aria-label={describeDay(column)}
                        data-date={column.date}
                        onClick={() => toggleDay(column)}
                        onFocus={() => setFocusIndex(index)}
                        onKeyDown={(event) => handleKeyDown(event, index)}
                        className={`flex h-40 min-w-1.5 flex-1 cursor-pointer justify-center rounded-sm px-px py-1 transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary ${
                          selected ? "bg-primary/12" : "hover:bg-base-200"
                        }`}
                      >
                        <span className="flex h-full w-full max-w-4 flex-col-reverse gap-px">
                          {column.blocks.map((block, blockIndex) => (
                            <span
                              key={blockIndex}
                              data-status={block.status}
                              data-executions={block.executions}
                              data-partial={block.partial || undefined}
                              className="min-h-0 flex-1 rounded-xs"
                              style={blockStyle(block.status, block.partial)}
                            />
                          ))}
                          {Array.from({ length: empties }, (_, emptyIndex) => (
                            <span
                              key={`empty-${emptyIndex}`}
                              className="min-h-0 flex-1 rounded-xs bg-base-content/5"
                            />
                          ))}
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <p className="font-medium">{longDate.format(parseDay(column.date))}</p>
                      <p className="text-base-content/60">{plural(column.total, "execution")}</p>
                      {column.total > 0 && (
                        <ul className="mt-1 space-y-0.5">
                          {column.counts
                            .filter((item) => item.count > 0)
                            .map((item) => (
                              <li key={item.key} className="flex items-center gap-1.5">
                                <span
                                  aria-hidden="true"
                                  className="size-2 rounded-xs"
                                  style={blockStyle(item.key, false)}
                                />
                                <span>{item.label}</span>
                                <span className="ml-auto pl-3 font-mono">{item.count}</span>
                              </li>
                            ))}
                        </ul>
                      )}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
            <div
              aria-hidden="true"
              className={`mt-1 flex min-w-full text-xs text-base-content/60 ${
                columns.length > 31 ? "gap-px" : "gap-0.5 sm:gap-1"
              }`}
            >
              {columns.map((column, index) => {
                const fromEnd = columns.length - 1 - index;
                const selected = index === selectedIndex;
                const labeled = selected || fromEnd % step === 0;
                // Keep edge labels inside the chart instead of centering them past its border.
                const align =
                  index === 0 ? "left-0" : fromEnd === 0 ? "right-0" : "left-1/2 -translate-x-1/2";
                return (
                  <span key={column.date} className="relative h-4 min-w-1.5 flex-1">
                    {labeled && (
                      <span
                        className={`absolute top-0 whitespace-nowrap ${align} ${
                          selected ? "z-10 rounded-sm bg-base-100 px-0.5 text-primary" : ""
                        }`}
                      >
                        {shortDate.format(parseDay(column.date))}
                      </span>
                    )}
                  </span>
                );
              })}
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
                      style={blockStyle(item.key, false)}
                    />
                    <span>
                      {item.label} <span className="font-mono">{item.count}</span>
                    </span>
                  </li>
                ))}
            </ul>
            <p data-testid="activity-scale">
              {scale === 1
                ? "1 block = 1 execution"
                : `1 block = ${scale} executions, a lighter block holds fewer`}
            </p>
          </div>
          <p className="mt-2 text-xs text-base-content/60" aria-live="polite">
            {selectedColumn
              ? `Showing ${longDate.format(parseDay(selectedColumn.date))} in the list. Select it again to show the latest executions.`
              : "Select a day to show its executions in the list."}
          </p>
        </>
      )}
    </section>
  );
}
