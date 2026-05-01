"use client";

import { useEffect, useMemo, useState } from "react";

import { SlidersHorizontal } from "lucide-react";

import { useListChips, useGetChip } from "@/client/chip/chip";
import { useGetChipMetrics } from "@/client/metrics/metrics";
import { useGetChipNotesSummary } from "@/client/note/note";
import type { TargetNoteEntry } from "@/schemas";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { LinearGauge } from "@/components/ui/LinearGauge";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useMetricsUrlState } from "@/hooks/useUrlState";

import { DashboardCdfChart } from "./DashboardCdfChart";
import { DashboardCouplingList } from "./DashboardCouplingList";
import { DashboardNotesSummary } from "./DashboardNotesSummary";
import { DashboardQubitGrid } from "./DashboardQubitGrid";
import { DashboardSummaryTable } from "./DashboardSummaryTable";
import { type NoteEntry, type NoteEntryWithMetric } from "./ChipNoteEditor";
import { DashboardMetricModal } from "./DashboardMetricModal";

interface MetricValueLike {
  value: number | null;
  stddev?: number | null;
}

type MetricMap = { [key: string]: MetricValueLike };

const FALLBACK_COLORS = ["#440154", "#31688e", "#35b779", "#fde724"];

function coverageOf(
  metricData: MetricMap | null,
  total: number,
): { current: number; total: number; pct: number } {
  if (!metricData || total === 0) return { current: 0, total, pct: 0 };
  const current = Object.values(metricData).filter(
    (v) => v.value !== null && v.value !== undefined,
  ).length;
  return { current, total, pct: (current / total) * 100 };
}

function scaleData(
  raw: { [key: string]: MetricValueLike } | undefined,
  scale: number,
  metricType: "qubit" | "coupling",
): MetricMap | null {
  if (!raw) return null;
  const out: MetricMap = {};
  Object.entries(raw).forEach(([key, m]) => {
    const formattedKey =
      metricType === "qubit"
        ? key.startsWith("Q")
          ? String(parseInt(key.slice(1), 10))
          : String(parseInt(key, 10))
        : key;
    const v = m?.value;
    const sd = m?.stddev;
    out[formattedKey] = {
      value: typeof v === "number" ? v * scale : null,
      stddev: typeof sd === "number" ? sd * scale : null,
    };
  });
  return out;
}

export function DashboardPageContent() {
  const {
    selectedChip,
    rangeMode,
    timeRange,
    selectionMode,
    customDays,
    startDate,
    endDate,
    setSelectedChip,
    setRangeMode,
    setTimeRange,
    setSelectionMode,
    setCustomDays,
    setStartDate,
    setEndDate,
  } = useMetricsUrlState();

  const {
    qubitMetrics,
    couplingMetrics,
    colorScale,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  const { data: chipsData, isLoading: isChipsLoading } = useListChips();
  const { data: chipData } = useGetChip(selectedChip);

  const topologyId = useMemo(
    () =>
      chipData?.data?.topology_id ??
      `square-lattice-mux-${chipData?.data?.size ?? 64}`,
    [chipData?.data?.topology_id, chipData?.data?.size],
  );

  const qubitCount = chipData?.data?.size ?? 64;

  // Default chip
  useEffect(() => {
    if (
      !selectedChip &&
      chipsData?.data?.chips &&
      chipsData.data.chips.length > 0
    ) {
      const sorted = [...chipsData.data.chips].sort((a, b) => {
        const da = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const db = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return db - da;
      });
      setSelectedChip(sorted[0].chip_id);
    }
  }, [selectedChip, chipsData, setSelectedChip]);

  const isAbsolute = rangeMode === "absolute";
  const relativeWithinHours =
    timeRange === "custom"
      ? (customDays ?? 90) * 24
      : timeRange === "1d"
        ? 24
        : timeRange === "7d"
          ? 24 * 7
          : timeRange === "30d"
            ? 24 * 30
            : 24 * 7;

  const absoluteStartIso = startDate ? `${startDate}T00:00:00` : null;
  const absoluteEndIso = endDate ? `${endDate}T23:59:59` : null;

  const queryParams = isAbsolute
    ? {
        start_at: absoluteStartIso,
        end_at: absoluteEndIso,
        selection_mode: selectionMode,
      }
    : {
        within_hours: relativeWithinHours,
        selection_mode: selectionMode,
      };

  const hasAbsoluteBound = Boolean(startDate || endDate);
  const canFetch = !!selectedChip && (!isAbsolute || hasAbsoluteBound);

  const { data, isLoading, isError } = useGetChipMetrics(
    selectedChip,
    queryParams,
    {
      query: { enabled: canFetch, staleTime: 30000 },
    },
  );

  const colors = useMemo(
    () =>
      colorScale.colors && colorScale.colors.length > 0
        ? colorScale.colors
        : FALLBACK_COLORS,
    [colorScale],
  );

  // Pre-scale all metric data once
  const qubitMetricData = useMemo(() => {
    const result: Record<string, MetricMap | null> = {};
    const src = (data?.data?.qubit_metrics ?? {}) as Record<
      string,
      { [key: string]: MetricValueLike }
    >;
    qubitMetrics.forEach((m) => {
      // Backend uses qubit_frequency for the bare_frequency config key
      const schemaKey = m.key === "bare_frequency" ? "qubit_frequency" : m.key;
      result[m.key] = scaleData(src[schemaKey], m.scale, "qubit");
    });
    return result;
  }, [data, qubitMetrics]);

  const couplingMetricData = useMemo(() => {
    const result: Record<string, MetricMap | null> = {};
    const src = (data?.data?.coupling_metrics ?? {}) as Record<
      string,
      { [key: string]: MetricValueLike }
    >;
    couplingMetrics.forEach((m) => {
      result[m.key] = scaleData(src[m.key], m.scale, "coupling");
    });
    return result;
  }, [data, couplingMetrics]);

  // All notes for this chip (qubit/coupling general + per-metric + task) in one fetch.
  const { data: summaryData } = useGetChipNotesSummary(selectedChip, {
    query: { enabled: !!selectedChip, staleTime: 30_000 },
  });
  const summary = summaryData?.data;

  const taskNotes = useMemo(
    () =>
      (summary?.task_notes ?? []).map((t) => ({
        taskId: t.task_id,
        qid: t.qid,
        content: t.note?.content ?? "",
        username: t.note?.updated_by ?? "",
        updatedAt: t.note?.updated_at ?? "",
      })),
    [summary],
  );

  const notesByMetric = useMemo(() => {
    const map: Record<string, Record<string, NoteEntry>> = {};
    const collect = (entries: TargetNoteEntry[] | undefined) => {
      (entries ?? []).forEach((entry) => {
        Object.entries(entry.metric_notes ?? {}).forEach(
          ([metricKey, note]) => {
            if (!map[metricKey]) map[metricKey] = {};
            map[metricKey][entry.target_id] = {
              targetId: entry.target_id,
              metricKey,
              content: note?.content ?? "",
              username: note?.updated_by ?? "",
              updatedAt: note?.updated_at ?? "",
            };
          },
        );
      });
    };
    collect(summary?.qubits);
    collect(summary?.couplings);
    return map;
  }, [summary]);

  const notesByTarget = useMemo(() => {
    const titleByKey = new Map<string, string>();
    qubitMetrics.forEach((m) => titleByKey.set(m.key, m.title));
    couplingMetrics.forEach((m) => titleByKey.set(m.key, m.title));

    const map: Record<string, NoteEntryWithMetric[]> = {};
    const collect = (entries: TargetNoteEntry[] | undefined) => {
      (entries ?? []).forEach((entry) => {
        Object.entries(entry.metric_notes ?? {}).forEach(
          ([metricKey, note]) => {
            if (!map[entry.target_id]) map[entry.target_id] = [];
            map[entry.target_id].push({
              targetId: entry.target_id,
              metricKey,
              metricTitle: titleByKey.get(metricKey) ?? metricKey,
              content: note?.content ?? "",
              username: note?.updated_by ?? "",
              updatedAt: note?.updated_at ?? "",
            });
          },
        );
      });
    };
    collect(summary?.qubits);
    collect(summary?.couplings);
    return map;
  }, [summary, qubitMetrics, couplingMetrics]);

  const [editingNote, setEditingNote] = useState<{
    targetId: string;
    metricKey: string;
    metricTitle: string;
    metricUnit: string;
  } | null>(null);

  const editingExisting =
    editingNote && notesByMetric[editingNote.metricKey]?.[editingNote.targetId]
      ? notesByMetric[editingNote.metricKey][editingNote.targetId]
      : undefined;

  const editingOtherNotes = editingNote
    ? (notesByTarget[editingNote.targetId] ?? []).filter(
        (n) => n.metricKey !== editingNote.metricKey,
      )
    : [];

  // Summary table rows
  const summaryRows = useMemo(() => {
    const qubitRows = qubitMetrics.map((m) => ({
      key: m.key,
      title: m.title,
      unit: m.unit,
      type: "Qubit" as const,
      data: qubitMetricData[m.key] ?? null,
      expectedTotal: qubitCount,
    }));
    const couplingRows = couplingMetrics.map((m) => {
      const d = couplingMetricData[m.key];
      return {
        key: m.key,
        title: m.title,
        unit: m.unit,
        type: "Coupling" as const,
        data: d ?? null,
        expectedTotal: d ? Object.keys(d).length : 0,
      };
    });
    return [...qubitRows, ...couplingRows];
  }, [
    qubitMetrics,
    couplingMetrics,
    qubitMetricData,
    couplingMetricData,
    qubitCount,
  ]);

  if (isConfigLoading || isChipsLoading) {
    return <MetricsPageSkeleton />;
  }

  return (
    <PageContainer>
      <div className="h-full flex flex-col gap-4 md:gap-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <PageHeader
            title="Chip Dashboard"
            description="One-page summary of every metric on the selected chip. Click any qubit on a metric to leave a note."
            className="mb-0"
          />
        </div>

        {/* Filters */}
        <PageFiltersBar>
          <PageFiltersBar.Group>
            <PageFiltersBar.Item>
              <select
                className="select select-sm select-bordered"
                value={rangeMode}
                onChange={(e) =>
                  setRangeMode(e.target.value as "relative" | "absolute")
                }
                title="Switch between relative range (last N days) and absolute date range"
              >
                <option value="relative">Relative</option>
                <option value="absolute">Absolute</option>
              </select>
            </PageFiltersBar.Item>

            <PageFiltersBar.Item>
              {rangeMode === "relative" ? (
                <div className="flex items-center gap-2">
                  <div className="join rounded-lg overflow-hidden">
                    {(
                      [
                        ["1d", "1D", "Last 1 Day"],
                        ["7d", "7D", "Last 7 Days"],
                        ["30d", "30D", "Last 30 Days"],
                      ] as const
                    ).map(([value, mobile, desktop]) => (
                      <button
                        key={value}
                        className={`join-item btn btn-sm ${
                          timeRange === value ? "btn-primary" : ""
                        }`}
                        onClick={() => setTimeRange(value)}
                      >
                        <span className="hidden sm:inline">{desktop}</span>
                        <span className="sm:hidden">{mobile}</span>
                      </button>
                    ))}
                    <button
                      className={`join-item btn btn-sm gap-1 ${
                        timeRange === "custom" ? "btn-primary" : ""
                      }`}
                      onClick={() => setTimeRange("custom")}
                      title="Set a custom time range in days"
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Custom</span>
                    </button>
                  </div>
                  {timeRange === "custom" && (
                    <CustomDaysInput
                      value={customDays ?? 90}
                      onChange={setCustomDays}
                    />
                  )}
                </div>
              ) : (
                <AbsoluteDateRangePicker
                  startDate={startDate}
                  endDate={endDate}
                  onStartChange={setStartDate}
                  onEndChange={setEndDate}
                />
              )}
            </PageFiltersBar.Item>

            <PageFiltersBar.Item>
              <div className="join rounded-lg overflow-hidden">
                {(["latest", "best", "average"] as const).map((mode) => (
                  <button
                    key={mode}
                    className={`join-item btn btn-sm ${
                      selectionMode === mode ? "btn-primary" : ""
                    }`}
                    onClick={() => setSelectionMode(mode)}
                  >
                    {mode[0].toUpperCase() + mode.slice(1)}
                  </button>
                ))}
              </div>
            </PageFiltersBar.Item>
          </PageFiltersBar.Group>

          <PageFiltersBar.Group>
            <PageFiltersBar.Item>
              <ChipSelector
                selectedChip={selectedChip}
                onChipSelect={setSelectedChip}
              />
            </PageFiltersBar.Item>
          </PageFiltersBar.Group>
        </PageFiltersBar>

        {/* Body */}
        {!selectedChip ? (
          <EmptyState
            title="No chip selected"
            description="Select a chip from the dropdown above to view the dashboard"
            emoji="microchip"
            size="lg"
          />
        ) : isLoading ? (
          <div className="flex items-center justify-center h-96">
            <QuantumLoader size="lg" showLabel label="Loading dashboard…" />
          </div>
        ) : isConfigError ? (
          <EmptyState
            title="Configuration error"
            description="Failed to load metrics configuration. Please try refreshing the page."
            emoji="warning"
            size="lg"
          />
        ) : isError ? (
          <EmptyState
            title="Data loading failed"
            description="Failed to load metrics data. Please try again later."
            emoji="warning"
            size="lg"
          />
        ) : (
          <>
            {/* All notes overview */}
            <Card
              variant="default"
              padding="md"
              title="Notes"
              description="All notes left on this chip, grouped by qubit / coupling."
            >
              <DashboardNotesSummary
                notesByTarget={notesByTarget}
                taskNotes={taskNotes}
                onEdit={(entry) => {
                  const cfg =
                    qubitMetrics.find((m) => m.key === entry.metricKey) ??
                    couplingMetrics.find((m) => m.key === entry.metricKey);
                  setEditingNote({
                    targetId: entry.targetId,
                    metricKey: entry.metricKey,
                    metricTitle: entry.metricTitle,
                    metricUnit: cfg?.unit ?? "",
                  });
                }}
              />
            </Card>

            {/* Summary table — collapsed by default */}
            <Card variant="default" padding="md">
              <details>
                <summary className="cursor-pointer list-none flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold">
                      All Metrics Summary
                    </h3>
                    <p className="text-sm text-base-content/60">
                      Coverage, median, min and max for every metric in the
                      active time range.
                    </p>
                  </div>
                  <span className="text-xs text-base-content/50">
                    click to expand
                  </span>
                </summary>
                <div className="mt-4">
                  <DashboardSummaryTable rows={summaryRows} />
                </div>
              </details>
            </Card>

            {/* Qubit metrics grids */}
            {qubitMetrics.length > 0 && (
              <Card
                variant="default"
                padding="md"
                title="Qubit Metrics"
                description="Click any qubit to leave a note specific to that metric."
              >
                <div className="space-y-8">
                  {qubitMetrics.map((m) => {
                    const noted = new Set(
                      Object.keys(notesByMetric[m.key] ?? {}),
                    );
                    const crossMetricNoted = new Set<string>();
                    Object.keys(notesByTarget).forEach((targetId) => {
                      if (targetId.includes("-")) return; // coupling
                      if (!noted.has(targetId)) crossMetricNoted.add(targetId);
                    });
                    const cov = coverageOf(qubitMetricData[m.key], qubitCount);
                    return (
                      <div key={m.key} className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-base font-semibold">{m.title}</h4>
                          <span className="badge badge-outline badge-sm">
                            {m.unit}
                          </span>
                          {noted.size > 0 && (
                            <span className="badge badge-warning badge-sm">
                              {noted.size} note{noted.size > 1 ? "s" : ""}
                            </span>
                          )}
                          <div className="ml-auto">
                            <LinearGauge
                              value={cov.pct}
                              current={cov.current}
                              total={cov.total}
                              duration={400}
                              label="Coverage"
                            />
                          </div>
                        </div>
                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
                          <div className="xl:col-span-2 min-w-0">
                            <DashboardQubitGrid
                              metricData={qubitMetricData[m.key]}
                              unit={m.unit}
                              topologyId={topologyId}
                              colors={colors}
                              notedQids={noted}
                              crossMetricNotedQids={crossMetricNoted}
                              notesByTarget={notesByTarget}
                              metricKey={m.key}
                              onQubitClick={(qid) =>
                                setEditingNote({
                                  targetId: qid,
                                  metricKey: m.key,
                                  metricTitle: m.title,
                                  metricUnit: m.unit,
                                })
                              }
                            />
                          </div>
                          <div className="xl:col-span-1 min-w-0">
                            <DashboardCdfChart
                              metricData={qubitMetricData[m.key]}
                              title={m.title}
                              unit={m.unit}
                              height={260}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* Coupling metrics */}
            {couplingMetrics.length > 0 && (
              <Card
                variant="default"
                padding="md"
                title="Coupling Metrics"
                description="Click any coupling to leave a note specific to that metric."
              >
                <div className="space-y-6">
                  {couplingMetrics.map((m) => {
                    const noted = new Set(
                      Object.keys(notesByMetric[m.key] ?? {}),
                    );
                    const crossMetricNoted = new Set<string>();
                    Object.keys(notesByTarget).forEach((targetId) => {
                      if (!targetId.includes("-")) return; // qubit
                      if (!noted.has(targetId)) crossMetricNoted.add(targetId);
                    });
                    const couplingTotal = couplingMetricData[m.key]
                      ? Object.keys(couplingMetricData[m.key] ?? {}).length
                      : 0;
                    const cov = coverageOf(
                      couplingMetricData[m.key],
                      couplingTotal,
                    );
                    return (
                      <div key={m.key} className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-base font-semibold">{m.title}</h4>
                          <span className="badge badge-outline badge-sm">
                            {m.unit}
                          </span>
                          {noted.size > 0 && (
                            <span className="badge badge-warning badge-sm">
                              {noted.size} note{noted.size > 1 ? "s" : ""}
                            </span>
                          )}
                          <div className="ml-auto">
                            <LinearGauge
                              value={cov.pct}
                              current={cov.current}
                              total={cov.total}
                              duration={400}
                              label="Coverage"
                            />
                          </div>
                        </div>
                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
                          <div className="xl:col-span-2 min-w-0">
                            <DashboardCouplingList
                              metricData={couplingMetricData[m.key]}
                              unit={m.unit}
                              colors={colors}
                              notedTargets={noted}
                              crossMetricNotedTargets={crossMetricNoted}
                              notesByTarget={notesByTarget}
                              metricKey={m.key}
                              onCouplingClick={(couplingId) =>
                                setEditingNote({
                                  targetId: couplingId,
                                  metricKey: m.key,
                                  metricTitle: m.title,
                                  metricUnit: m.unit,
                                })
                              }
                            />
                          </div>
                          <div className="xl:col-span-1 min-w-0">
                            <DashboardCdfChart
                              metricData={couplingMetricData[m.key]}
                              title={m.title}
                              unit={m.unit}
                              height={260}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}
          </>
        )}
      </div>

      {editingNote && selectedChip && (
        <DashboardMetricModal
          chipId={selectedChip}
          targetId={editingNote.targetId}
          metricKey={editingNote.metricKey}
          metricTitle={editingNote.metricTitle}
          metricUnit={editingNote.metricUnit}
          startAt={isAbsolute ? absoluteStartIso : null}
          endAt={isAbsolute ? absoluteEndIso : null}
          chipNote={editingExisting}
          otherNotes={editingOtherNotes}
          onClose={() => setEditingNote(null)}
        />
      )}
    </PageContainer>
  );
}

function AbsoluteDateRangePicker({
  startDate,
  endDate,
  onStartChange,
  onEndChange,
}: {
  startDate: string | null;
  endDate: string | null;
  onStartChange: (value: string | null) => void;
  onEndChange: (value: string | null) => void;
}) {
  const inverted =
    startDate !== null && endDate !== null && startDate > endDate;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center gap-2">
          <span className="label-text">From</span>
          <input
            type="date"
            className="input input-sm input-bordered tabular-nums w-32"
            value={startDate ?? ""}
            onChange={(e) => onStartChange(e.target.value || null)}
            max={endDate ?? undefined}
            aria-label="Start date"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="label-text">To</span>
          <input
            type="date"
            className="input input-sm input-bordered tabular-nums w-32"
            value={endDate ?? ""}
            onChange={(e) => onEndChange(e.target.value || null)}
            min={startDate ?? undefined}
            aria-label="End date"
          />
        </label>
      </div>
      {inverted && (
        <span className="text-xs text-error">
          Start date must be on or before end date
        </span>
      )}
    </div>
  );
}

function CustomDaysInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (days: number) => void;
}) {
  const [local, setLocal] = useState(String(value));
  useEffect(() => {
    setLocal(String(value));
  }, [value]);
  const commit = () => {
    const parsed = parseInt(local, 10);
    if (parsed > 0 && parsed <= 3650) onChange(parsed);
    else setLocal(String(value));
  };
  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        min={1}
        max={3650}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            commit();
            (e.target as HTMLInputElement).blur();
          }
        }}
        className="input input-sm input-bordered w-20 text-center tabular-nums"
      />
      <span className="text-sm text-base-content/70">days</span>
    </div>
  );
}
