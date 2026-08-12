"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import { ArrowRightLeft, ChevronDown } from "lucide-react";

import { useListChips, useGetChip } from "@/client/chip/chip";
import { useListCooldowns } from "@/client/cooldown/cooldown";
import { useListForumPosts } from "@/client/forum/forum";
import { useGetChipMetrics } from "@/client/metrics/metrics";
import { useGetChipNotesSummary } from "@/client/note/note";
import { useListProjectMembers } from "@/client/projects/projects";
import type {
  GetChipNotesSummaryParams,
  TargetNoteEntry as SummaryTargetNoteEntry,
} from "@/schemas";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { CooldownSelector } from "@/components/selectors/CooldownSelector";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { LinearGauge } from "@/components/ui/LinearGauge";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { TimeRangeSelector } from "@/components/ui/TimeRangeSelector";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import type { MentionCandidate } from "@/components/ui/MarkdownEditor";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useMetricsQueryParams } from "@/hooks/useMetricsQueryParams";
import { useMetricsUrlState, useRangeModeUrlState } from "@/hooks/useUrlState";
import { dateToDateTimeLocal } from "@/lib/utils/datetime";

import { DashboardCdfChart } from "./DashboardCdfChart";
import { DashboardCouplingGrid } from "./DashboardCouplingGrid";
import { DashboardQubitGrid } from "./DashboardQubitGrid";
import { DashboardSummaryTable } from "./DashboardSummaryTable";
import {
  DashboardTargetNoteModal,
  type TargetNoteEntry as DashboardTargetNoteEntry,
} from "./DashboardTargetNoteModal";
import { DashboardChipNoteCard } from "./DashboardChipNoteCard";
import { DashboardMetricModal } from "./DashboardMetricModal";
import type { ForumLinkEntry } from "./DashboardNoteTooltip";
import { type NoteEntry, type NoteEntryWithMetric } from "./MetricNotePanel";

interface MetricValueLike {
  value: number | null;
  stddev?: number | null;
}

type MetricMap = { [key: string]: MetricValueLike };

const FALLBACK_COLORS = ["#440154", "#31688e", "#35b779", "#fde724"];
const SUMMARY_TOPOLOGY_VIEWPORT_CLASS = "grow rounded-md border border-base-300 bg-base-100/60 p-3";
const SUMMARY_TOPOLOGY_HEADER_CLASS = "flex flex-wrap items-center justify-between gap-2 min-h-8";
const MIGRATED_METRIC_NOTES_TO_LATEST_CD_MARKER =
  "<!-- qdash:migrated-metric-notes-to-latest-cooldown -->";

const FORUM_LABEL_PRIORITY = [
  "anomaly",
  "review",
  "discussion",
  "mtg",
  "info",
  "resolved",
] as const;

function representativeForumLabel(labels: string[] | undefined): string {
  const values = new Set(labels ?? []);
  const label = FORUM_LABEL_PRIORITY.find((item) => values.has(item));
  if (label === "discussion" || label === "mtg" || label === "info" || label === "resolved") {
    return "review";
  }
  return label ?? "review";
}

function mergeForumMarkerLabel(current: string | undefined, labels: string[] | undefined): string {
  const next = representativeForumLabel(labels);
  return current === "anomaly" || next === "anomaly" ? "anomaly" : next;
}

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

function EmptyMetricDisclosure({ children }: { children: ReactNode }) {
  return (
    <details className="group rounded-lg border border-dashed border-base-300 bg-base-200/40">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">No values in the selected range</p>
          <p className="text-xs text-base-content/50">
            Try a wider time range, or open the topology to inspect individual targets.
          </p>
        </div>
        <span className="text-xs font-medium text-primary group-open:hidden">Show topology</span>
        <span className="hidden text-xs font-medium text-primary group-open:inline">
          Hide topology
        </span>
        <ChevronDown
          className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="border-t border-base-300 p-4">{children}</div>
    </details>
  );
}

export function DashboardPageContent() {
  const { user } = useAuth();
  const { projectId } = useProject();
  const { selectedChip, selectionMode, setSelectedChip, setSelectionMode } = useMetricsUrlState();

  const { startDate, endDate, setStartDate, setEndDate, setQuickRange } = useRangeModeUrlState();

  const {
    qubitMetrics,
    couplingMetrics,
    colorScale,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  const { data: chipsData, isLoading: isChipsLoading } = useListChips();
  const { data: chipData } = useGetChip(selectedChip);
  const { data: cooldownsData } = useListCooldowns(
    { chip_id: selectedChip || undefined },
    { query: { enabled: !!selectedChip, staleTime: 30_000 } },
  );
  const { data: membersResponse } = useListProjectMembers(projectId ?? "", {
    query: { enabled: !!projectId },
  });

  const topologyId = useMemo(
    () => chipData?.data?.topology_id ?? `square-lattice-mux-${chipData?.data?.size ?? 64}`,
    [chipData?.data?.topology_id, chipData?.data?.size],
  );
  const currentCooldownId = chipData?.data?.current_cooldown_id ?? null;
  const cooldowns = cooldownsData?.data?.cooldowns ?? [];
  const activeCooldown =
    cooldowns.find((cooldown) => cooldown.cooldown_id === currentCooldownId) ?? null;

  const qubitCount = chipData?.data?.size ?? 64;
  const [selectedCooldownId, setSelectedCooldownId] = useState<string | null>(null);
  const [hasInitializedCooldownSelection, setHasInitializedCooldownSelection] = useState(false);
  const forumCooldownId = selectedCooldownId ?? activeCooldown?.cooldown_id ?? null;

  const mentionCandidates: MentionCandidate[] = useMemo(
    () => [
      { id: "qdash", label: "QDash" },
      {
        id: "project",
        label: "Project",
        secondaryLabel: "Notify all project members",
      },
      ...(membersResponse?.data.members
        ?.filter((member) => member.username !== user?.username)
        .map((member) => ({
          id: member.username,
          label: member.display_name || member.username,
          secondaryLabel: member.organization ?? undefined,
          avatarKey: member.avatar_key,
        })) ?? []),
    ],
    [membersResponse?.data.members, user?.username],
  );

  // Default chip
  useEffect(() => {
    if (!selectedChip && chipsData?.data?.chips && chipsData.data.chips.length > 0) {
      const sorted = [...chipsData.data.chips].sort((a, b) => {
        const da = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const db = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return db - da;
      });
      setSelectedChip(sorted[0].chip_id);
    }
  }, [selectedChip, chipsData, setSelectedChip]);

  useEffect(() => {
    setHasInitializedCooldownSelection(false);
  }, [selectedChip]);

  useEffect(() => {
    if (hasInitializedCooldownSelection) return;
    if (!currentCooldownId || !activeCooldown) return;
    setSelectedCooldownId(currentCooldownId);
    setStartDate(dateToDateTimeLocal(new Date(activeCooldown.started_at)));
    setEndDate(
      dateToDateTimeLocal(activeCooldown.ended_at ? new Date(activeCooldown.ended_at) : new Date()),
    );
    setHasInitializedCooldownSelection(true);
  }, [
    activeCooldown,
    currentCooldownId,
    hasInitializedCooldownSelection,
    setEndDate,
    setStartDate,
  ]);

  const { queryParams, canFetch } = useMetricsQueryParams({
    selectionMode,
    startDate,
    endDate,
    selectedChip,
  });

  const noteScopeParams = useMemo<GetChipNotesSummaryParams>(
    () =>
      selectedCooldownId
        ? { cooldown_id: selectedCooldownId }
        : {
            start_at: queryParams.start_at,
            end_at: queryParams.end_at,
          },
    [queryParams.end_at, queryParams.start_at, selectedCooldownId],
  );

  const { data, isLoading, isError } = useGetChipMetrics(selectedChip, queryParams, {
    query: { enabled: canFetch, staleTime: 30000 },
  });

  const colors = useMemo(
    () => (colorScale.colors && colorScale.colors.length > 0 ? colorScale.colors : FALLBACK_COLORS),
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
  const { data: summaryData } = useGetChipNotesSummary(selectedChip, noteScopeParams, {
    query: { enabled: !!selectedChip, staleTime: 30_000 },
  });
  const summary = summaryData?.data;
  const { data: forumPostsResponse } = useListForumPosts(
    {
      chip_id: selectedChip || undefined,
      cooldown_id: forumCooldownId || undefined,
      status: null,
      limit: 200,
    },
    { query: { enabled: !!selectedChip, staleTime: 30_000 } },
  );

  const forumLinkedQids = useMemo(() => {
    const targets: Record<string, string> = {};
    (forumPostsResponse?.data.posts ?? []).forEach((post) => {
      if (post.target_type === "qubit" && post.target_id) {
        targets[post.target_id] = mergeForumMarkerLabel(targets[post.target_id], post.labels);
      }
    });
    return targets;
  }, [forumPostsResponse?.data.posts]);

  const forumLinkedCouplings = useMemo(() => {
    const targets: Record<string, string> = {};
    (forumPostsResponse?.data.posts ?? []).forEach((post) => {
      if (post.target_type === "coupling" && post.target_id) {
        targets[post.target_id] = mergeForumMarkerLabel(targets[post.target_id], post.labels);
      }
    });
    return targets;
  }, [forumPostsResponse?.data.posts]);

  const forumLinksByTarget = useMemo(() => {
    const targets: Record<string, ForumLinkEntry[]> = {};
    (forumPostsResponse?.data.posts ?? []).forEach((post) => {
      if (!post.target_id || (post.target_type !== "qubit" && post.target_type !== "coupling")) {
        return;
      }
      const entries = targets[post.target_id] ?? [];
      entries.push({
        id: post.id,
        number: post.number,
        title: post.title,
        labels: post.labels ?? [],
        status: post.status,
        replyCount: post.reply_count ?? 0,
      });
      targets[post.target_id] = entries;
    });
    return targets;
  }, [forumPostsResponse?.data.posts]);

  const notesByMetric = useMemo(() => {
    const map: Record<string, Record<string, NoteEntry>> = {};
    const collect = (entries: SummaryTargetNoteEntry[] | undefined) => {
      (entries ?? []).forEach((entry) => {
        if (entry.note?.content?.includes(MIGRATED_METRIC_NOTES_TO_LATEST_CD_MARKER)) return;
        Object.entries(entry.metric_notes ?? {}).forEach(([metricKey, note]) => {
          const content = stripAiGeneratedNoteSections(note?.content ?? "");
          if (!content) return;
          if (!map[metricKey]) map[metricKey] = {};
          map[metricKey][entry.target_id] = {
            targetId: entry.target_id,
            metricKey,
            content,
            username: note?.updated_by ?? "",
            updatedAt: note?.updated_at ?? "",
          };
        });
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
    const collect = (entries: SummaryTargetNoteEntry[] | undefined) => {
      (entries ?? []).forEach((entry) => {
        if (entry.note?.content?.includes(MIGRATED_METRIC_NOTES_TO_LATEST_CD_MARKER)) return;
        Object.entries(entry.metric_notes ?? {}).forEach(([metricKey, note]) => {
          const content = stripAiGeneratedNoteSections(note?.content ?? "");
          if (!content) return;
          if (!map[entry.target_id]) map[entry.target_id] = [];
          map[entry.target_id].push({
            targetId: entry.target_id,
            metricKey,
            metricTitle: titleByKey.get(metricKey) ?? metricKey,
            content,
            username: note?.updated_by ?? "",
            updatedAt: note?.updated_at ?? "",
          });
        });
      });
    };
    collect(summary?.qubits);
    collect(summary?.couplings);
    return map;
  }, [summary, qubitMetrics, couplingMetrics]);

  const targetNotesByTarget = useMemo(() => {
    const map: Record<string, DashboardTargetNoteEntry> = {};
    const collect = (entries: SummaryTargetNoteEntry[] | undefined) => {
      (entries ?? []).forEach((entry) => {
        const content = stripAiGeneratedNoteSections(entry.note?.content ?? "");
        const comments = entry.comments ?? [];
        if (!content && comments.length === 0) return;
        map[entry.target_id] = {
          targetId: entry.target_id,
          content,
          username: entry.note?.updated_by ?? "",
          updatedAt: entry.note?.updated_at ?? "",
          comments,
        };
      });
    };
    collect(summary?.qubits);
    collect(summary?.couplings);
    return map;
  }, [summary]);

  const targetNotedQids = useMemo(
    () => new Set(Object.keys(targetNotesByTarget).filter((targetId) => !targetId.includes("-"))),
    [targetNotesByTarget],
  );

  const targetNotedCouplings = useMemo(
    () => new Set(Object.keys(targetNotesByTarget).filter((targetId) => targetId.includes("-"))),
    [targetNotesByTarget],
  );

  const noteCouplingTopologyData = useMemo<MetricMap | null>(() => {
    const couplingIds = new Set<string>();
    Object.values(couplingMetricData).forEach((metricMap) => {
      Object.keys(metricMap ?? {}).forEach((targetId) => couplingIds.add(targetId));
    });
    Object.keys(notesByTarget).forEach((targetId) => {
      if (targetId.includes("-")) couplingIds.add(targetId);
    });
    Object.keys(targetNotesByTarget).forEach((targetId) => {
      if (targetId.includes("-")) couplingIds.add(targetId);
    });
    if (couplingIds.size === 0) return null;
    return Object.fromEntries(
      [...couplingIds].map((targetId) => [targetId, { value: null }]),
    ) as MetricMap;
  }, [couplingMetricData, notesByTarget, targetNotesByTarget]);

  const [editingNote, setEditingNote] = useState<{
    targetId: string;
    metricKey: string;
    metricTitle: string;
    metricUnit: string;
  } | null>(null);
  const [editingTargetNote, setEditingTargetNote] = useState<string | null>(null);
  const [couplingDirection, setCouplingDirection] = useState<"forward" | "reverse">("forward");
  const [showTargetSummaries, setShowTargetSummaries] = useState(false);
  const [showEmptyQubitMetrics, setShowEmptyQubitMetrics] = useState(false);
  const [showEmptyCouplingMetrics, setShowEmptyCouplingMetrics] = useState(false);
  const isReverseCouplingDirection = couplingDirection === "reverse";

  const editingLegacyMetricNote =
    editingNote && notesByMetric[editingNote.metricKey]?.[editingNote.targetId]
      ? notesByMetric[editingNote.metricKey][editingNote.targetId]
      : undefined;

  const editingLegacyMetricNotes = editingNote
    ? (notesByTarget[editingNote.targetId] ?? []).filter(
        (n) => n.metricKey !== editingNote.metricKey,
      )
    : [];

  const editingTargetExisting = editingNote ? targetNotesByTarget[editingNote.targetId] : undefined;

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
  }, [qubitMetrics, couplingMetrics, qubitMetricData, couplingMetricData, qubitCount]);

  const metricsWithData = useMemo(
    () =>
      summaryRows.filter((row) =>
        Object.values(row.data ?? {}).some(
          (metric) => metric.value !== null && metric.value !== undefined,
        ),
      ).length,
    [summaryRows],
  );
  const emptyMetricCount = summaryRows.length - metricsWithData;
  const emptyQubitMetricCount = qubitMetrics.filter(
    (metric) => coverageOf(qubitMetricData[metric.key], qubitCount).current === 0,
  ).length;
  const emptyCouplingMetricCount = couplingMetrics.filter((metric) => {
    const metricData = couplingMetricData[metric.key];
    return coverageOf(metricData, metricData ? Object.keys(metricData).length : 0).current === 0;
  }).length;

  if (isConfigLoading || isChipsLoading) {
    return <MetricsPageSkeleton />;
  }

  return (
    <PageContainer>
      <div className="h-full flex flex-col gap-4 md:gap-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <PageHeader
            title="Chip Dashboard"
            description="One-page summary of every metric on the selected chip. Click any qubit or coupling to update its pinned summary or start a forum topic."
            className="mb-0"
          />
        </div>

        {/* Filters */}
        <section
          aria-labelledby="dashboard-data-scope"
          className="rounded-xl border border-base-300 bg-base-200/45 p-3 sm:p-4"
        >
          <h2
            id="dashboard-data-scope"
            className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-base-content/55"
          >
            Data scope
          </h2>
          <div className="flex flex-col gap-4">
            <PageFiltersBar className="gap-3">
              <PageFiltersBar.Group className="gap-3">
                <PageFiltersBar.Item label="Chip" className="sm:w-64">
                  <ChipSelector
                    selectedChip={selectedChip}
                    onChipSelect={(chipId) => {
                      setSelectedCooldownId(null);
                      setHasInitializedCooldownSelection(false);
                      setSelectedChip(chipId);
                    }}
                  />
                </PageFiltersBar.Item>
                <PageFiltersBar.Item
                  label="Cooldown"
                  className="sm:w-56 [&:not(:has(.cooldown-selector-control))]:hidden"
                >
                  <CooldownSelector
                    chipId={selectedChip}
                    selectedCooldownId={selectedCooldownId}
                    onPick={(cd) => {
                      setSelectedCooldownId(cd.cooldown_id);
                      setHasInitializedCooldownSelection(true);
                      setStartDate(dateToDateTimeLocal(new Date(cd.started_at)));
                      setEndDate(
                        dateToDateTimeLocal(cd.ended_at ? new Date(cd.ended_at) : new Date()),
                      );
                    }}
                  />
                </PageFiltersBar.Item>
              </PageFiltersBar.Group>

              <PageFiltersBar.Group position="end" className="items-start sm:items-end">
                <PageFiltersBar.Item label="Value selection">
                  <div className="space-y-1">
                    <span className="hidden text-xs font-medium text-base-content/55 sm:block">
                      Value selection
                    </span>
                    <div className="join overflow-hidden rounded-lg">
                      {(["latest", "best", "average"] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          aria-pressed={selectionMode === mode}
                          className={`join-item btn btn-sm ${
                            selectionMode === mode ? "btn-primary" : ""
                          }`}
                          onClick={() => setSelectionMode(mode)}
                        >
                          {mode[0].toUpperCase() + mode.slice(1)}
                        </button>
                      ))}
                    </div>
                  </div>
                </PageFiltersBar.Item>
              </PageFiltersBar.Group>
            </PageFiltersBar>

            <div className="border-t border-base-300 pt-3">
              <TimeRangeSelector
                collapsible
                startDate={startDate}
                endDate={endDate}
                onStartDateChange={(value) => {
                  setSelectedCooldownId(null);
                  setHasInitializedCooldownSelection(true);
                  setStartDate(value);
                }}
                onEndDateChange={(value) => {
                  setSelectedCooldownId(null);
                  setHasInitializedCooldownSelection(true);
                  setEndDate(value);
                }}
                onQuickRange={(range) => {
                  setSelectedCooldownId(null);
                  setHasInitializedCooldownSelection(true);
                  setQuickRange(range);
                }}
              />
            </div>
          </div>
        </section>

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
            <DashboardChipNoteCard chipId={selectedChip} noteScopeParams={noteScopeParams} />

            {/* Pinned summary topology */}
            <Card variant="default" padding="md">
              <button
                type="button"
                className="flex w-full items-center gap-3 rounded-lg text-left focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
                aria-expanded={showTargetSummaries}
                aria-controls="dashboard-target-summaries"
                onClick={() => setShowTargetSummaries((visible) => !visible)}
              >
                <div className="min-w-0 flex-1">
                  <h3 className="text-lg font-semibold">Target Summaries</h3>
                  <p className="mt-0.5 text-sm text-base-content/60">
                    Pin shared context to individual qubits and couplings.
                  </p>
                </div>
                <div className="hidden flex-wrap justify-end gap-2 sm:flex">
                  <span className="badge badge-ghost badge-sm">
                    {targetNotedQids.size} qubit {targetNotedQids.size === 1 ? "note" : "notes"}
                  </span>
                  <span className="badge badge-ghost badge-sm">
                    {targetNotedCouplings.size} coupling{" "}
                    {targetNotedCouplings.size === 1 ? "note" : "notes"}
                  </span>
                </div>
                <span className="text-xs font-medium text-primary">
                  {showTargetSummaries ? "Hide" : "Show"}
                </span>
                <ChevronDown
                  className={`h-4 w-4 shrink-0 transition-transform ${showTargetSummaries ? "rotate-180" : ""}`}
                  aria-hidden="true"
                />
              </button>

              {showTargetSummaries && (
                <div
                  id="dashboard-target-summaries"
                  className="mt-5 grid grid-cols-1 items-stretch gap-6 border-t border-base-300 pt-5 xl:grid-cols-2"
                >
                  <div className="flex flex-col gap-2">
                    <div className={SUMMARY_TOPOLOGY_HEADER_CLASS}>
                      <h4 className="text-sm font-semibold">Qubit summaries</h4>
                    </div>
                    <div className={SUMMARY_TOPOLOGY_VIEWPORT_CLASS}>
                      <DashboardQubitGrid
                        metricData={null}
                        unit=""
                        topologyId={topologyId}
                        colors={colors}
                        maxCellSize={48}
                        presentation="summary"
                        targetNotedQids={targetNotedQids}
                        forumLinkedQids={forumLinkedQids}
                        forumLinksByTarget={forumLinksByTarget}
                        notesByTarget={notesByTarget}
                        targetNotesByTarget={targetNotesByTarget}
                        metricKey=""
                        onQubitClick={setEditingTargetNote}
                      />
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <div className={SUMMARY_TOPOLOGY_HEADER_CLASS}>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-semibold">Coupling summaries</h4>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          setCouplingDirection(isReverseCouplingDirection ? "forward" : "reverse")
                        }
                        className={`btn btn-sm gap-1.5 ${isReverseCouplingDirection ? "btn-secondary" : "btn-outline"}`}
                        title={
                          isReverseCouplingDirection
                            ? "Showing reverse direction"
                            : "Showing forward direction"
                        }
                      >
                        <ArrowRightLeft className="h-3.5 w-3.5" />
                        <span className="text-xs">
                          {isReverseCouplingDirection ? "Reverse" : "Forward"}
                        </span>
                      </button>
                    </div>
                    <div className={SUMMARY_TOPOLOGY_VIEWPORT_CLASS}>
                      <DashboardCouplingGrid
                        metricData={noteCouplingTopologyData}
                        unit=""
                        topologyId={topologyId}
                        colors={colors}
                        maxCellSize={48}
                        presentation="summary"
                        reverseDirection={isReverseCouplingDirection}
                        targetNotedTargets={targetNotedCouplings}
                        forumLinkedTargets={forumLinkedCouplings}
                        forumLinksByTarget={forumLinksByTarget}
                        notesByTarget={notesByTarget}
                        targetNotesByTarget={targetNotesByTarget}
                        metricKey=""
                        onCouplingClick={setEditingTargetNote}
                      />
                    </div>
                  </div>
                </div>
              )}
            </Card>

            {/* Summary table — collapsed by default */}
            <Card variant="default" padding="md">
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-lg font-semibold">All Metrics Summary</h3>
                    <p className="text-sm text-base-content/60">
                      Coverage, median, min and max for every metric in the active time range.
                    </p>
                  </div>
                  <div className="hidden flex-wrap justify-end gap-2 sm:flex">
                    <span className="badge badge-success badge-sm">
                      {metricsWithData} with data
                    </span>
                    {emptyMetricCount > 0 && (
                      <span className="badge badge-ghost badge-sm">{emptyMetricCount} empty</span>
                    )}
                  </div>
                  <span className="text-xs font-medium text-primary group-open:hidden">Show</span>
                  <span className="hidden text-xs font-medium text-primary group-open:inline">
                    Hide
                  </span>
                  <ChevronDown
                    className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180"
                    aria-hidden="true"
                  />
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
                description="Click any qubit to update its pinned summary while inspecting the selected metric."
              >
                {emptyQubitMetricCount > 0 && (
                  <button
                    type="button"
                    className="mb-5 flex w-full items-center justify-between gap-3 rounded-lg border border-dashed border-base-300 bg-base-200/40 px-4 py-3 text-left transition-colors hover:bg-base-200/70"
                    aria-expanded={showEmptyQubitMetrics}
                    onClick={() => setShowEmptyQubitMetrics((visible) => !visible)}
                  >
                    <span>
                      <span className="block text-sm font-medium">
                        {emptyQubitMetricCount} qubit{" "}
                        {emptyQubitMetricCount === 1 ? "metric" : "metrics"} without data
                      </span>
                      <span className="block text-xs text-base-content/50">
                        Hidden to keep this dashboard focused on available results.
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-primary">
                      {showEmptyQubitMetrics ? "Hide" : "Show"}
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${showEmptyQubitMetrics ? "rotate-180" : ""}`}
                        aria-hidden="true"
                      />
                    </span>
                  </button>
                )}
                <div className="space-y-8">
                  {qubitMetrics.map((m) => {
                    const noted = new Set(Object.keys(notesByMetric[m.key] ?? {}));
                    const crossMetricNoted = new Set<string>();
                    Object.keys(notesByTarget).forEach((targetId) => {
                      if (targetId.includes("-")) return; // coupling
                      if (!noted.has(targetId)) crossMetricNoted.add(targetId);
                    });
                    const cov = coverageOf(qubitMetricData[m.key], qubitCount);
                    if (cov.current === 0 && !showEmptyQubitMetrics) return null;
                    return (
                      <div
                        key={m.key}
                        id={`dashboard-qubit-metric-${m.key}`}
                        className="scroll-mt-32 space-y-2"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-base font-semibold">{m.title}</h4>
                          <span className="badge badge-outline badge-sm">{m.unit}</span>
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
                        {cov.current === 0 ? (
                          <EmptyMetricDisclosure>
                            <DashboardQubitGrid
                              metricData={qubitMetricData[m.key]}
                              unit={m.unit}
                              topologyId={topologyId}
                              colors={colors}
                              notedQids={noted}
                              targetNotedQids={targetNotedQids}
                              forumLinkedQids={forumLinkedQids}
                              forumLinksByTarget={forumLinksByTarget}
                              crossMetricNotedQids={crossMetricNoted}
                              notesByTarget={notesByTarget}
                              targetNotesByTarget={targetNotesByTarget}
                              metricKey={m.key}
                              onQubitClick={(qid) => {
                                setEditingNote({
                                  targetId: qid,
                                  metricKey: m.key,
                                  metricTitle: m.title,
                                  metricUnit: m.unit,
                                });
                              }}
                            />
                          </EmptyMetricDisclosure>
                        ) : (
                          <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-3">
                            <div className="min-w-0 xl:col-span-2">
                              <DashboardQubitGrid
                                metricData={qubitMetricData[m.key]}
                                unit={m.unit}
                                topologyId={topologyId}
                                colors={colors}
                                notedQids={noted}
                                targetNotedQids={targetNotedQids}
                                forumLinkedQids={forumLinkedQids}
                                forumLinksByTarget={forumLinksByTarget}
                                crossMetricNotedQids={crossMetricNoted}
                                notesByTarget={notesByTarget}
                                targetNotesByTarget={targetNotesByTarget}
                                metricKey={m.key}
                                onQubitClick={(qid) => {
                                  setEditingNote({
                                    targetId: qid,
                                    metricKey: m.key,
                                    metricTitle: m.title,
                                    metricUnit: m.unit,
                                  });
                                }}
                              />
                            </div>
                            <div className="min-w-0 xl:col-span-1">
                              <DashboardCdfChart
                                metricData={qubitMetricData[m.key]}
                                title={m.title}
                                unit={m.unit}
                                height={260}
                              />
                            </div>
                          </div>
                        )}
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
                description="Click any coupling to update its pinned summary while inspecting the selected metric."
              >
                {emptyCouplingMetricCount > 0 && (
                  <button
                    type="button"
                    className="mb-4 flex w-full items-center justify-between gap-3 rounded-lg border border-dashed border-base-300 bg-base-200/40 px-4 py-3 text-left transition-colors hover:bg-base-200/70"
                    aria-expanded={showEmptyCouplingMetrics}
                    onClick={() => setShowEmptyCouplingMetrics((visible) => !visible)}
                  >
                    <span>
                      <span className="block text-sm font-medium">
                        {emptyCouplingMetricCount} coupling{" "}
                        {emptyCouplingMetricCount === 1 ? "metric" : "metrics"} without data
                      </span>
                      <span className="block text-xs text-base-content/50">
                        Hidden to keep this dashboard focused on available results.
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-primary">
                      {showEmptyCouplingMetrics ? "Hide" : "Show"}
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${showEmptyCouplingMetrics ? "rotate-180" : ""}`}
                        aria-hidden="true"
                      />
                    </span>
                  </button>
                )}
                <div className="mb-4 flex justify-end">
                  <button
                    type="button"
                    onClick={() =>
                      setCouplingDirection(isReverseCouplingDirection ? "forward" : "reverse")
                    }
                    className={`btn btn-sm gap-1.5 ${isReverseCouplingDirection ? "btn-secondary" : "btn-outline"}`}
                    title={
                      isReverseCouplingDirection
                        ? "Showing reverse direction"
                        : "Showing forward direction"
                    }
                  >
                    <ArrowRightLeft className="h-3.5 w-3.5" />
                    <span className="text-xs">
                      {isReverseCouplingDirection ? "Reverse" : "Forward"}
                    </span>
                  </button>
                </div>
                <div className="space-y-6">
                  {couplingMetrics.map((m) => {
                    const noted = new Set(Object.keys(notesByMetric[m.key] ?? {}));
                    const crossMetricNoted = new Set<string>();
                    Object.keys(notesByTarget).forEach((targetId) => {
                      if (!targetId.includes("-")) return; // qubit
                      if (!noted.has(targetId)) crossMetricNoted.add(targetId);
                    });
                    const couplingTotal = couplingMetricData[m.key]
                      ? Object.keys(couplingMetricData[m.key] ?? {}).length
                      : 0;
                    const cov = coverageOf(couplingMetricData[m.key], couplingTotal);
                    if (cov.current === 0 && !showEmptyCouplingMetrics) return null;
                    return (
                      <div
                        key={m.key}
                        id={`dashboard-coupling-metric-${m.key}`}
                        className="scroll-mt-32 space-y-2"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-base font-semibold">{m.title}</h4>
                          <span className="badge badge-outline badge-sm">{m.unit}</span>
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
                        {cov.current === 0 ? (
                          <EmptyMetricDisclosure>
                            <DashboardCouplingGrid
                              metricData={couplingMetricData[m.key]}
                              unit={m.unit}
                              topologyId={topologyId}
                              colors={colors}
                              reverseDirection={isReverseCouplingDirection}
                              notedTargets={noted}
                              targetNotedTargets={targetNotedCouplings}
                              forumLinkedTargets={forumLinkedCouplings}
                              forumLinksByTarget={forumLinksByTarget}
                              crossMetricNotedTargets={crossMetricNoted}
                              notesByTarget={notesByTarget}
                              targetNotesByTarget={targetNotesByTarget}
                              metricKey={m.key}
                              onCouplingClick={(couplingId) => {
                                setEditingNote({
                                  targetId: couplingId,
                                  metricKey: m.key,
                                  metricTitle: m.title,
                                  metricUnit: m.unit,
                                });
                              }}
                            />
                          </EmptyMetricDisclosure>
                        ) : (
                          <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-3">
                            <div className="min-w-0 xl:col-span-2">
                              <DashboardCouplingGrid
                                metricData={couplingMetricData[m.key]}
                                unit={m.unit}
                                topologyId={topologyId}
                                colors={colors}
                                reverseDirection={isReverseCouplingDirection}
                                notedTargets={noted}
                                targetNotedTargets={targetNotedCouplings}
                                forumLinkedTargets={forumLinkedCouplings}
                                forumLinksByTarget={forumLinksByTarget}
                                crossMetricNotedTargets={crossMetricNoted}
                                notesByTarget={notesByTarget}
                                targetNotesByTarget={targetNotesByTarget}
                                metricKey={m.key}
                                onCouplingClick={(couplingId) => {
                                  setEditingNote({
                                    targetId: couplingId,
                                    metricKey: m.key,
                                    metricTitle: m.title,
                                    metricUnit: m.unit,
                                  });
                                }}
                              />
                            </div>
                            <div className="min-w-0 xl:col-span-1">
                              <DashboardCdfChart
                                metricData={couplingMetricData[m.key]}
                                title={m.title}
                                unit={m.unit}
                                height={260}
                              />
                            </div>
                          </div>
                        )}
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
          startAt={queryParams.start_at}
          endAt={queryParams.end_at}
          cooldownId={selectedCooldownId}
          cooldownLabel={selectedCooldownId}
          noteScopeParams={noteScopeParams}
          targetNote={editingTargetExisting}
          legacyMetricNote={editingLegacyMetricNote}
          legacyMetricNotes={editingLegacyMetricNotes}
          mentionCandidates={mentionCandidates}
          onClose={() => setEditingNote(null)}
        />
      )}

      {editingTargetNote && selectedChip && (
        <DashboardTargetNoteModal
          chipId={selectedChip}
          targetId={editingTargetNote}
          cooldownId={selectedCooldownId}
          noteScopeParams={noteScopeParams}
          existing={targetNotesByTarget[editingTargetNote]}
          mentionCandidates={mentionCandidates}
          currentUsername={user?.username ?? null}
          currentSystemRole={user?.system_role ?? null}
          onClose={() => setEditingTargetNote(null)}
        />
      )}
    </PageContainer>
  );
}

function stripAiGeneratedNoteSections(content: string): string {
  const aiGeneratedNotePattern = new RegExp(
    "^\\s*(?:(?:#{1,6}\\s*)?AI\\s+(?:review|triage)|\\*\\*AI\\s+(?:review|triage)\\*\\*)\\b[\\s\\S]*?(?:\\r?\\n\\r?\\n---\\r?\\n\\r?\\n|$)",
    "i",
  );
  return content.replace(aiGeneratedNotePattern, "").trim();
}
