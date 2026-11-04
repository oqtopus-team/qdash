"use client";

import { useCallback, useMemo } from "react";

import type { Layout, PlotMouseEvent } from "plotly.js";

import { useGetExecutionActivity } from "@/client/execution/execution";
import Plot from "@/components/charts/Plot";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";
import { DEFAULT_TIMEZONE } from "@/lib/utils/datetime";
import type { ExecutionActivityDay } from "@/schemas";

const ACTIVITY_WINDOWS = [7, 30, 90] as const;
export type ActivityWindow = (typeof ACTIVITY_WINDOWS)[number];

const SERIES: ReadonlyArray<{
  key: Exclude<keyof ExecutionActivityDay, "date" | "total">;
  label: string;
}> = [
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
  { key: "running", label: "Running" },
  { key: "scheduled", label: "Scheduled" },
  { key: "cancelled", label: "Cancelled" },
  { key: "other", label: "Other" },
];

interface ExecutionActivityChartProps {
  chipId: string;
  days: ActivityWindow;
  onDaysChange: (days: ActivityWindow) => void;
  /** Date filter of the list below, `latest` or YYYYMMDD; the matching bar is highlighted. */
  selectedDate: string;
  /** Called with YYYYMMDD when a bar is selected, so the list can show that day. */
  onDateSelect: (date: string) => void;
}

/** Plotly options shared by every render, so the plot is not rebuilt for a new object. */
const PLOT_CONFIG = { displayModeBar: false, responsive: true } as const;

/**
 * Executions per day for the selected chip, stacked by status, over the last 7, 30 or 90 days.
 * Selecting a bar filters the execution list to that day.
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

  const totals = useMemo(() => {
    const sum = (key: keyof ExecutionActivityDay) =>
      buckets.reduce((acc, bucket) => acc + ((bucket[key] as number | undefined) ?? 0), 0);
    return { total: sum("total"), failed: sum("failed"), running: sum("running") };
  }, [buckets]);

  // Keyed on the palette strings, not the palette object, so the memo survives re-renders.
  const colors = useMemo<Record<(typeof SERIES)[number]["key"], string>>(
    () => ({
      completed: palette.pass,
      failed: palette.fail,
      running: palette.accent,
      scheduled: palette.warn,
      cancelled: palette.muted,
      other: palette.grid,
    }),
    [palette.pass, palette.fail, palette.accent, palette.warn, palette.muted, palette.grid],
  );

  const selectedIso =
    selectedDate.length === 8
      ? `${selectedDate.slice(0, 4)}-${selectedDate.slice(4, 6)}-${selectedDate.slice(6, 8)}`
      : null;

  // Stable between renders: Plot purges and redraws whenever it receives a new data array.
  const traces = useMemo(
    () =>
      SERIES.filter((series) => buckets.some((bucket) => (bucket[series.key] ?? 0) > 0)).map(
        (series) => ({
          type: "bar" as const,
          name: series.label,
          x: buckets.map((bucket) => bucket.date),
          y: buckets.map((bucket) => bucket[series.key] ?? 0),
          marker: { color: colors[series.key] },
          hovertemplate: `%{x}<br>${series.label}: %{y}<extra></extra>`,
        }),
      ),
    [buckets, colors],
  );

  const layout = useMemo<Partial<Layout>>(
    () => ({
      barmode: "stack",
      bargap: 0.25,
      height: 220,
      margin: { l: 36, r: 12, t: 8, b: 36 },
      showlegend: true,
      legend: { orientation: "h", y: -0.25, x: 0 },
      xaxis: { type: "category", tickangle: days > 30 ? -45 : 0, nticks: 12, fixedrange: true },
      yaxis: { rangemode: "tozero", tickformat: "d", fixedrange: true },
      hovermode: "x unified",
      shapes: selectedIso
        ? [
            {
              type: "rect",
              xref: "x",
              yref: "paper",
              x0: selectedIso,
              x1: selectedIso,
              y0: 0,
              y1: 1,
              line: { width: 0 },
              fillcolor: palette.accent,
              opacity: 0.12,
              layer: "below",
            },
          ]
        : [],
    }),
    [days, palette.accent, selectedIso],
  );

  const handleClick = useCallback(
    (event: PlotMouseEvent) => {
      const date = event.points?.[0]?.x;
      if (typeof date !== "string") return;
      const compact = date.replace(/-/g, "");
      onDateSelect(compact === selectedDate ? "latest" : compact);
    },
    [onDateSelect, selectedDate],
  );

  return (
    <section
      aria-labelledby="execution-activity-heading"
      className="mb-6 rounded-box border border-base-300 bg-base-100 p-4"
    >
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="execution-activity-heading" className="text-sm font-medium">
            Executions per day
          </h2>
          <p className="text-sm text-base-content/60">
            {isLoading
              ? "Loading"
              : `${totals.total} in the last ${days} days` +
                (totals.failed > 0 ? `, ${totals.failed} failed` : "") +
                (totals.running > 0 ? `, ${totals.running} in progress` : "") +
                ". Select a bar to show that day."}
          </p>
        </div>
        <div className="tabs tabs-boxed bg-base-200" role="tablist" aria-label="Activity window">
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
      ) : !isLoading && totals.total === 0 ? (
        <p className="py-8 text-center text-sm text-base-content/60">
          No executions in the last {days} days
        </p>
      ) : (
        <div className={isLoading ? "skeleton h-[220px] w-full" : ""}>
          {!isLoading && (
            <Plot
              data={traces}
              layout={layout}
              config={PLOT_CONFIG}
              useResizeHandler
              style={{ width: "100%", height: "220px" }}
              onClick={handleClick}
            />
          )}
        </div>
      )}
    </section>
  );
}
