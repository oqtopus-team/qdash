"use client";

import type { ReactNode } from "react";
import { useMemo } from "react";

import { useGetExecutionActivity } from "@/client/execution/execution";
import { DEFAULT_TIMEZONE, isCompactActivityDate } from "@/lib/utils/datetime";

import { ExecutionActivityHeatmap } from "./ExecutionActivityHeatmap";
import {
  activityStatusTotals,
  activityWindowSummary,
  longActivityDate,
  parseActivityDay,
  shortActivityDate,
} from "./executionActivityBlocks";
import { formatCompactActivityDate } from "./executionActivityLevels";

const CALENDAR_WINDOWS = [30, 90, 365] as const;
export type CalendarWindow = (typeof CALENDAR_WINDOWS)[number];
export const DEFAULT_CALENDAR_WINDOW: CalendarWindow = 90;

interface ExecutionActivityCalendarProps {
  chipId: string;
  days: CalendarWindow;
  onDaysChange: (days: CalendarWindow) => void;
  /** Date filter of the list below, `latest` or YYYYMMDD; the matching day is outlined. */
  selectedDate: string;
  /** Called with YYYYMMDD when a day is selected, or `latest` when the selection is cleared. */
  onDateSelect: (date: string) => void;
  /** Control shown before the window tabs, such as the page's Activity/Chart switch. */
  modeSwitch?: ReactNode;
}

/**
 * Executions for the selected chip over the last 30, 90 or 365 days as a calendar heatmap.
 * Selecting a day filters the execution list to it; selecting it again clears the filter.
 */
export function ExecutionActivityCalendar({
  chipId,
  days,
  onDaysChange,
  selectedDate,
  onDateSelect,
  modeSwitch,
}: ExecutionActivityCalendarProps) {
  const { data, isLoading, isError } = useGetExecutionActivity(
    { chip_id: chipId, days, timezone: DEFAULT_TIMEZONE, granularity: "day" },
    { query: { enabled: !!chipId, refetchInterval: 60_000 } },
  );
  const buckets = useMemo(() => data?.data?.buckets ?? [], [data]);
  const totals = useMemo(() => activityStatusTotals(buckets), [buckets]);
  const total = totals.reduce((acc, item) => acc + item.count, 0);

  const hasSelection = isCompactActivityDate(selectedDate);
  const selectedInWindow =
    hasSelection && buckets.some((b) => b.date.replace(/-/g, "") === selectedDate);

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
                : activityWindowSummary(totals, days)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {modeSwitch}
          <div
            className="tabs tabs-boxed w-fit bg-base-200"
            role="tablist"
            aria-label="Activity window"
          >
            {CALENDAR_WINDOWS.map((window) => (
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
      </div>
      {isError ? (
        <p role="alert" className="py-8 text-center text-sm text-base-content/60">
          Execution activity could not be loaded.
        </p>
      ) : isLoading ? (
        <div className="skeleton h-36 w-full" aria-hidden="true" />
      ) : total === 0 ? (
        <p className="py-8 text-center text-sm text-base-content/60">
          No executions in the last {days} days
        </p>
      ) : (
        <ExecutionActivityHeatmap
          buckets={buckets}
          density="full"
          label="Executions per day. Select a day to show it in the list"
          selectedDate={selectedDate}
          onDaySelect={(date) => onDateSelect(date === selectedDate ? "latest" : date)}
          dayHint={(day, selected) =>
            selected
              ? "Select again to show the latest executions"
              : `Select to show ${shortActivityDate.format(parseActivityDay(day.date))} in the list`
          }
        />
      )}
      {!isError && !isLoading && (
        <div
          className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-base-content/60"
          aria-live="polite"
        >
          {hasSelection ? (
            <>
              <span>
                {`Showing ${formatCompactActivityDate(selectedDate, longActivityDate)} in the list` +
                  (selectedInWindow
                    ? ". Select it again to show the latest executions."
                    : ", outside this range.")}
              </span>
              {!selectedInWindow && (
                <button type="button" className="link" onClick={() => onDateSelect("latest")}>
                  Show latest
                </button>
              )}
            </>
          ) : (
            total > 0 && <span>Select a day to show its executions in the list.</span>
          )}
        </div>
      )}
    </section>
  );
}
