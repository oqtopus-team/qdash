"use client";

import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";

import { useMemo } from "react";
import { History } from "lucide-react";

import {
  getGetExecutionActivityQueryKey,
  useGetExecutionActivity,
} from "@/client/execution/execution";
import { ExecutionActivityHeatmap } from "@/components/features/execution/ExecutionActivityHeatmap";
import {
  activityBlockStyler,
  activityStatusTotals,
} from "@/components/features/execution/executionActivityBlocks";
import { useProject } from "@/contexts/ProjectContext";
import { DEFAULT_TIMEZONE } from "@/lib/utils/datetime";

/** Home shows a fixed quarter; the Execution page offers other windows. */
export const HOME_ACTIVITY_DAYS = 90;

/** Execution page filtered to one day, YYYYMMDD, in the page's `date` query parameter. */
const executionDayHref = (date: string) => `/execution?date=${date}`;

/**
 * Executions started per day across every chip of the current project over the last 90 days,
 * as a compact calendar heatmap. Hovering or focusing a day shows its exact counts per status;
 * selecting it opens the Execution page filtered to that day.
 */
export function HomeExecutionActivity() {
  const { projectId } = useProject();
  const blockStyle = activityBlockStyler(chartTheme(useIsDarkTheme()));
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
  const totals = useMemo(() => activityStatusTotals(buckets), [buckets]);
  const total = totals.reduce((acc, item) => acc + item.count, 0);
  const failed = totals.find((item) => item.key === "failed")?.count ?? 0;

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
                {item.label} <span className="font-mono">{item.count}</span>
              </li>
            ))}
        </ul>
      </div>
      <p className="mb-3 text-xs text-base-content/60">
        Across all project chips. Open a day, then choose a chip to inspect its runs.
      </p>
      <ExecutionActivityHeatmap
        buckets={buckets}
        density="compact"
        label={`Executions per day over the last ${HOME_ACTIVITY_DAYS} days. Each day opens the Execution page filtered to it`}
        dayHref={executionDayHref}
        dayHint={() => "Select to open this day on the Execution page"}
      />
    </div>
  );
}
