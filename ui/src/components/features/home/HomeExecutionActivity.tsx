"use client";

import { type KeyboardEvent, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { History } from "lucide-react";

import {
  getGetExecutionActivityQueryKey,
  useGetExecutionActivity,
} from "@/client/execution/execution";
import { ActivityBlockStack } from "@/components/features/execution/ActivityBlockStack";
import {
  activityBlockScale,
  activityBlockStyler,
  activityScaleNote,
  activityStatusTotals,
  describeActivityDay,
  longActivityDate,
  parseActivityDay,
  pluralize,
  shortActivityDate,
  toActivityColumn,
} from "@/components/features/execution/executionActivityBlocks";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useProject } from "@/contexts/ProjectContext";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";
import { DEFAULT_TIMEZONE } from "@/lib/utils/datetime";

/** Home shows a fixed month; the Execution page offers other windows. */
export const HOME_ACTIVITY_DAYS = 30;
/** Home is a glance, so a column is shorter than the Execution page's 20 blocks. */
const MAX_BLOCKS = 12;
/** Shortest grid, so a quiet month still reads as a grid of small blocks. */
const MIN_ROWS = 6;
const EXECUTION_HREF = "/execution";

/**
 * Executions started per day across every chip of the current project over the last 30 days,
 * as a compact column of status-colored blocks per day. One block is one execution until the
 * busiest day no longer fits, after which each block stands for a labeled number of executions.
 * Every day links to the Execution page; hovering or focusing a day shows its exact counts.
 */
export function HomeExecutionActivity() {
  const blockStyle = activityBlockStyler(chartTheme(useIsDarkTheme()));
  const { projectId } = useProject();
  const params = { days: HOME_ACTIVITY_DAYS, timezone: DEFAULT_TIMEZONE };
  // The request has no chip, so only the project header tells projects apart. Key the cache by
  // project and pin the header to that key's project: switching projects invalidates every
  // query before this one unmounts, and that refetch must not store the new project's counts
  // under the old project's key.
  const { data, isLoading, isError } = useGetExecutionActivity(params, {
    query: {
      queryKey: [...getGetExecutionActivityQueryKey(params), projectId],
      enabled: Boolean(projectId),
      staleTime: 30_000,
      refetchInterval: 60_000,
    },
    request: projectId ? { headers: { "X-Project-Id": projectId } } : undefined,
  });
  const buckets = useMemo(() => data?.data?.buckets ?? [], [data]);

  const { scale, columns, rows, totals } = useMemo(() => {
    const blockSize = activityBlockScale(buckets, MAX_BLOCKS);
    const dayColumns = buckets.map((bucket) => toActivityColumn(bucket, blockSize));
    const tallest = dayColumns.reduce((acc, column) => Math.max(acc, column.blocks.length), 0);
    return {
      scale: blockSize,
      columns: dayColumns,
      rows: Math.max(MIN_ROWS, tallest),
      totals: activityStatusTotals(buckets),
    };
  }, [buckets]);
  const total = totals.reduce((acc, item) => acc + item.count, 0);
  const failed = totals.find((item) => item.key === "failed")?.count ?? 0;

  // Roving focus: the day grid is one tab stop, arrow keys move between days.
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const activeIndex =
    focusIndex !== null && focusIndex < columns.length ? focusIndex : columns.length - 1;
  const dayRefs = useRef<Array<HTMLAnchorElement | null>>([]);

  const handleKeyDown = (event: KeyboardEvent<HTMLAnchorElement>, index: number) => {
    const targets: Record<string, number> = {
      ArrowLeft: index - 1,
      ArrowRight: index + 1,
      Home: 0,
      End: columns.length - 1,
    };
    if (!(event.key in targets)) return;
    event.preventDefault();
    const next = Math.min(Math.max(targets[event.key], 0), columns.length - 1);
    setFocusIndex(next);
    dayRefs.current[next]?.focus();
  };

  if (!projectId || isLoading) {
    return <div className="skeleton h-40 w-full" aria-hidden="true" />;
  }
  if (isError) {
    return (
      <div role="alert" className="alert alert-error py-3 text-sm">
        Failed to load execution activity.
      </div>
    );
  }
  if (total === 0) {
    return (
      <div className="flex items-center gap-3 rounded-lg bg-base-100/60 p-4">
        <History className="h-6 w-6 shrink-0 text-base-content/40" aria-hidden="true" />
        <div>
          <p className="font-medium">No executions in the last {HOME_ACTIVITY_DAYS} days</p>
          <p className="text-sm text-base-content/55">
            Runs started from Tasks or Workflows will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-4">
      <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <p className="flex items-baseline gap-2" data-testid="home-activity-total">
          <span className="text-2xl font-semibold leading-none tabular-nums">{total}</span>
          <span className="text-sm text-base-content/60">
            {total === 1 ? "execution" : "executions"}
            {failed > 0 && (
              <>
                {" · "}
                <span className="text-error">{failed} failed</span>
              </>
            )}
          </span>
        </p>
        <ul
          className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-base-content/60"
          aria-label="Executions by status"
        >
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
      </div>

      <div
        role="group"
        aria-label={`Executions per day over the last ${HOME_ACTIVITY_DAYS} days. Each day opens the Execution page`}
        className="flex min-w-full gap-px sm:gap-0.5"
      >
        {columns.map((column, index) => {
          return (
            <Tooltip key={column.date}>
              <TooltipTrigger asChild>
                <Link
                  ref={(node) => {
                    dayRefs.current[index] = node;
                  }}
                  href={EXECUTION_HREF}
                  tabIndex={index === activeIndex ? 0 : -1}
                  aria-label={describeActivityDay(column)}
                  data-date={column.date}
                  onFocus={() => setFocusIndex(index)}
                  onKeyDown={(event) => handleKeyDown(event, index)}
                  className="flex h-24 min-w-1 flex-1 justify-center rounded-sm px-px py-0.5 transition-colors hover:bg-base-200 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
                >
                  <ActivityBlockStack
                    column={column}
                    rows={rows}
                    scale={scale}
                    blockStyle={blockStyle}
                    className="max-w-3"
                  />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="top">
                <p className="font-medium">
                  {longActivityDate.format(parseActivityDay(column.date))}
                </p>
                <p className="text-base-content/60">{pluralize(column.total, "execution")}</p>
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
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
      <div
        aria-hidden="true"
        className="mt-1 flex min-w-full gap-px text-xs text-base-content/60 sm:gap-0.5"
      >
        {columns.map((column, index) => {
          const fromEnd = columns.length - 1 - index;
          // Weekly ticks counted back from today keep the compact axis quiet.
          const align = fromEnd === 0 ? "right-0" : "left-1/2 -translate-x-1/2";
          return (
            <span key={column.date} className="relative h-4 min-w-1 flex-1">
              {fromEnd % 7 === 0 && (
                <span className={`absolute top-0 whitespace-nowrap ${align}`}>
                  {fromEnd === 0
                    ? "Today"
                    : shortActivityDate.format(parseActivityDay(column.date))}
                </span>
              )}
            </span>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-base-content/60" data-testid="home-activity-scale">
        {activityScaleNote(scale)}
      </p>
    </div>
  );
}
