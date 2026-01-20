"use client";

import { useMemo, useState } from "react";

import Link from "next/link";
import {
  Bell,
  AlertTriangle,
  GitBranch,
  History,
  Clock,
  Search,
  TrendingDown,
  TrendingUp,
  Minus,
  ChevronDown,
} from "lucide-react";

import { useGetRecentChanges } from "@/client/provenance/provenance";
import {
  useGetPolicyImpactViolations,
  useGetPolicyViolations,
} from "@/client/provenance/policy";
import { RecalibrationRecommendationsPanel } from "@/components/features/provenance/RecalibrationRecommendationsPanel";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { formatRelativeTime } from "@/utils/datetime";

type WindowHours = 24 | 48 | 168;

const formatValue = (value: number | string) => {
  if (typeof value === "number") {
    if (value === 0) return "0";
    if (Math.abs(value) < 0.0001 || Math.abs(value) > 10000) {
      return value.toExponential(4);
    }
    return value.toFixed(6);
  }
  return String(value);
};

function DeltaIndicator({
  deltaPercent,
}: {
  deltaPercent: number | null | undefined;
}) {
  if (deltaPercent === null || deltaPercent === undefined) {
    return <Minus className="h-4 w-4 text-base-content/40" />;
  }

  const isSignificant = Math.abs(deltaPercent) > 10;

  if (deltaPercent > 0) {
    return (
      <TrendingUp
        className={`h-4 w-4 ${isSignificant ? "text-warning" : "text-success"}`}
      />
    );
  }
  if (deltaPercent < 0) {
    return (
      <TrendingDown
        className={`h-4 w-4 ${isSignificant ? "text-warning" : "text-error"}`}
      />
    );
  }
  return <Minus className="h-4 w-4 text-base-content/40" />;
}

function formatDeltaPercent(percent: number | null | undefined): string {
  if (percent === null || percent === undefined) return "";
  const sign = percent >= 0 ? "+" : "";
  return `${sign}${percent.toFixed(1)}%`;
}

export function InboxPageContent() {
  const [withinHours, setWithinHours] = useState<WindowHours>(48);
  const [expandedSelection, setExpandedSelection] = useState<{
    kind: "change" | "policy";
    entityId: string;
    parameterName: string;
    qid: string;
  } | null>(null);
  const [query, setQuery] = useState("");
  const [qidType, setQidType] = useState<"all" | "qubit" | "coupling">("all");
  const [showSignificantOnly, setShowSignificantOnly] = useState(true);
  const [minAbsDeltaPercent, setMinAbsDeltaPercent] = useState(10);
  const [showAllRows, setShowAllRows] = useState(false);

  const { allMetrics, isLoading: isLoadingConfig } = useMetricsConfig();

  const parameterNames = useMemo(() => {
    return allMetrics.map((m) => m.key);
  }, [allMetrics]);
  const validParameterNames = useMemo(
    () => new Set(parameterNames),
    [parameterNames],
  );

  const { data: changesResponse, isLoading } = useGetRecentChanges(
    {
      limit: 50,
      within_hours: withinHours,
      parameter_names: parameterNames.length > 0 ? parameterNames : undefined,
    },
    {
      query: {
        staleTime: 30000,
        enabled: !isLoadingConfig && parameterNames.length > 0,
      },
    },
  );

  const { data: policyResponse, isLoading: isPolicyLoading } =
    useGetPolicyViolations(
      {
        limit: 200,
        parameter_names: parameterNames.length > 0 ? parameterNames : undefined,
      },
      {
        query: {
          staleTime: 30000,
          enabled: !isLoadingConfig && parameterNames.length > 0,
        },
      },
    );

  const changes = useMemo(
    () => changesResponse?.data?.changes ?? [],
    [changesResponse],
  );

  const changeById = useMemo(() => {
    const map = new Map<string, (typeof changes)[number]>();
    for (const c of changes) map.set(c.entity_id, c);
    return map;
  }, [changes]);

  const dedupedChanges = useMemo(() => {
    const seen = new Set<string>();
    const result: (typeof changes)[number][] = [];
    for (const c of changes) {
      const key = `${c.parameter_name}::${c.qid ?? ""}`;
      if (seen.has(key)) continue;
      seen.add(key);
      result.push(c);
    }
    return result;
  }, [changes]);

  const filteredChanges = useMemo(() => {
    const q = query.trim().toLowerCase();
    const isCoupling = (qid: string | undefined) => !!qid && qid.includes("-");

    const filtered = dedupedChanges.filter((c) => {
      const qid = c.qid ?? "";

      // Enforce: only show parameters defined in metrics.yaml (via metrics config)
      if (
        validParameterNames.size > 0 &&
        !validParameterNames.has(c.parameter_name)
      ) {
        return false;
      }

      if (qidType === "coupling" && !isCoupling(qid)) return false;
      if (qidType === "qubit" && (qid === "" || isCoupling(qid))) return false;

      if (showSignificantOnly) {
        const dp = c.delta_percent;
        if (dp === null || dp === undefined) return false;
        if (Math.abs(dp) < minAbsDeltaPercent) return false;
      }

      if (!q) return true;
      return (
        c.parameter_name.toLowerCase().includes(q) ||
        qid.toLowerCase().includes(q) ||
        (c.task_name ?? "").toLowerCase().includes(q) ||
        (c.execution_id ?? "").toLowerCase().includes(q)
      );
    });

    filtered.sort((a, b) => {
      const as = Math.abs(a.delta_percent ?? 0);
      const bs = Math.abs(b.delta_percent ?? 0);
      if (bs !== as) return bs - as;
      const at = a.valid_from ? new Date(a.valid_from as any).getTime() : 0;
      const bt = b.valid_from ? new Date(b.valid_from as any).getTime() : 0;
      return bt - at;
    });

    return filtered;
  }, [
    dedupedChanges,
    validParameterNames,
    minAbsDeltaPercent,
    qidType,
    query,
    showSignificantOnly,
  ]);

  const formatUncertainty = (change: any) => {
    const value = change?.value;
    const error = change?.error;
    if (typeof value !== "number" || typeof error !== "number" || error === 0) {
      return null;
    }
    if (value === 0) return `±${error.toExponential(2)}`;
    const rel = Math.abs(error / value) * 100;
    const relStr = rel >= 0.1 ? `${rel.toFixed(1)}%` : `${rel.toFixed(2)}%`;
    return `±${error.toExponential(2)} (${relStr})`;
  };

  const visibleChanges = useMemo(() => {
    if (showAllRows) return filteredChanges;
    return filteredChanges.slice(0, 30);
  }, [filteredChanges, showAllRows]);

  const selectedChange = useMemo(() => {
    if (!expandedSelection || expandedSelection.kind !== "change") return null;
    return changeById.get(expandedSelection.entityId) ?? null;
  }, [changeById, expandedSelection]);

  const policyViolations = useMemo(
    () => policyResponse?.data?.violations ?? [],
    [policyResponse],
  );

  const policyCounts = useMemo(() => {
    return { warn: policyViolations.length, total: policyViolations.length };
  }, [policyViolations]);

  const selectedPolicyEntityId = useMemo(() => {
    if (!expandedSelection || expandedSelection.kind !== "policy") return null;
    return expandedSelection.entityId;
  }, [expandedSelection]);

  const {
    data: impactViolationsResponse,
    isLoading: isImpactViolationsLoading,
  } = useGetPolicyImpactViolations(
    selectedPolicyEntityId,
    {
      max_depth: 10,
      limit: 200,
    },
    {
      query: {
        staleTime: 30000,
        enabled: !!selectedPolicyEntityId,
      },
    },
  );

  const impactViolations = useMemo(() => {
    return impactViolationsResponse?.data?.violations ?? [];
  }, [impactViolationsResponse]);

  const impactViolationCounts = useMemo(() => {
    return { warn: impactViolations.length, total: impactViolations.length };
  }, [impactViolations]);

  return (
    <PageContainer maxWidth>
      <div className="space-y-4 sm:space-y-6">
        <PageHeader
          title="Inbox"
          description="Review recent calibration parameter changes and take next actions"
        />

        <div className="card bg-base-200">
          <div className="card-body p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-warning" />
                <h3 className="card-title text-base sm:text-lg">
                  Policy Violations
                </h3>
                <span className="badge badge-sm">{policyCounts.total}</span>
                {policyCounts.warn > 0 && (
                  <span className="badge badge-warning badge-sm">
                    warn {policyCounts.warn}
                  </span>
                )}
              </div>
            </div>

            {isPolicyLoading && (
              <div className="flex justify-center py-10">
                <span className="loading loading-spinner loading-lg"></span>
              </div>
            )}

            {!isPolicyLoading && policyViolations.length === 0 && (
              <div className="text-center py-8 text-base-content/60">
                No current policy violations.
              </div>
            )}

            {!isPolicyLoading && policyViolations.length > 0 && (
              <div className="overflow-x-auto -mx-4 sm:mx-0 mt-4">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Parameter</th>
                      <th>QID</th>
                      <th className="hidden md:table-cell">Value</th>
                      <th>Message</th>
                      <th className="hidden sm:table-cell">Updated</th>
                      <th className="w-24">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {policyViolations.slice(0, 20).map((v) => {
                      const isExpanded =
                        expandedSelection?.entityId === v.entity_id;
                      return (
                        <tr key={v.entity_id}>
                          <td>
                            <span className="badge badge-warning badge-sm">
                              warn
                            </span>
                          </td>
                          <td className="font-medium">{v.parameter_name}</td>
                          <td className="font-mono text-xs">{v.qid || "-"}</td>
                          <td className="hidden md:table-cell font-mono text-xs">
                            {formatValue(v.value)} {v.unit || ""}
                          </td>
                          <td className="text-sm">
                            {v.message || v.check_type}
                          </td>
                          <td className="hidden sm:table-cell text-sm text-base-content/70">
                            {v.valid_from
                              ? formatRelativeTime(v.valid_from)
                              : "-"}
                          </td>
                          <td>
                            <div className="flex gap-1 justify-end">
                              <Link
                                className="btn btn-xs btn-ghost"
                                href={`/provenance?tab=lineage&entity=${encodeURIComponent(
                                  v.entity_id,
                                )}`}
                                title="Open lineage"
                              >
                                <GitBranch className="h-3 w-3" />
                              </Link>
                              <Link
                                className="btn btn-xs btn-ghost"
                                href={`/provenance?tab=history&parameter=${encodeURIComponent(
                                  v.parameter_name,
                                )}&qid=${encodeURIComponent(v.qid || "")}`}
                                title="Open history"
                              >
                                <History className="h-3 w-3" />
                              </Link>
                              <button
                                className="btn btn-xs btn-ghost"
                                onClick={() =>
                                  setExpandedSelection(
                                    isExpanded
                                      ? null
                                      : {
                                          kind: "policy",
                                          entityId: v.entity_id,
                                          parameterName: v.parameter_name,
                                          qid: v.qid || "",
                                        },
                                  )
                                }
                                title="Show suggested next actions"
                              >
                                <ChevronDown
                                  className={`h-3 w-3 transition-transform ${
                                    isExpanded ? "rotate-180" : ""
                                  }`}
                                />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {policyViolations.length > 20 && (
                  <div className="mt-3 flex justify-center">
                    <Link className="btn btn-sm btn-ghost" href="/provenance">
                      View more in Provenance
                    </Link>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="card bg-base-200">
          <div className="card-body p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-primary" />
                <h3 className="card-title text-base sm:text-lg">
                  Recent Changes
                </h3>
                <span className="badge badge-primary badge-sm">
                  {filteredChanges.length}
                </span>
                <span className="text-xs text-base-content/50">
                  / {dedupedChanges.length} shown ({changes.length} raw)
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2 justify-end">
                <div className="join">
                  <select
                    className="select select-sm select-bordered join-item"
                    value={qidType}
                    onChange={(e) =>
                      setQidType(e.target.value as "all" | "qubit" | "coupling")
                    }
                    title="Filter by QID type"
                  >
                    <option value="all">all</option>
                    <option value="qubit">qubit</option>
                    <option value="coupling">coupling</option>
                  </select>
                  <label className="btn btn-sm btn-outline join-item gap-2">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-xs"
                      checked={showSignificantOnly}
                      onChange={(e) => setShowSignificantOnly(e.target.checked)}
                    />
                    significant
                  </label>
                  <select
                    className="select select-sm select-bordered join-item"
                    value={minAbsDeltaPercent}
                    onChange={(e) =>
                      setMinAbsDeltaPercent(Number(e.target.value))
                    }
                    disabled={!showSignificantOnly}
                    title="Min |delta %|"
                  >
                    <option value={5}>≥5%</option>
                    <option value={10}>≥10%</option>
                    <option value={20}>≥20%</option>
                    <option value={50}>≥50%</option>
                  </select>
                </div>

                <div className="join">
                  <label className="input input-sm input-bordered join-item flex items-center gap-2">
                    <Search className="h-4 w-4 text-base-content/50" />
                    <input
                      className="grow"
                      placeholder="search param / qid / task"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </label>
                </div>

                <span className="text-xs text-base-content/60">window</span>
                <select
                  className="select select-sm select-bordered"
                  value={withinHours}
                  onChange={(e) =>
                    setWithinHours(Number(e.target.value) as WindowHours)
                  }
                >
                  <option value={24}>24h</option>
                  <option value={48}>48h</option>
                  <option value={168}>7d</option>
                </select>
              </div>
            </div>

            {isLoading && (
              <div className="flex justify-center py-12">
                <span className="loading loading-spinner loading-lg"></span>
              </div>
            )}

            {!isLoading && changes.length === 0 && (
              <div className="text-center py-10 text-base-content/60">
                No recent changes found.
              </div>
            )}

            {!isLoading && changes.length > 0 && (
              <div className="overflow-x-auto -mx-4 sm:mx-0 mt-4">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th className="w-8"></th>
                      <th>Parameter</th>
                      <th>QID</th>
                      <th className="hidden sm:table-cell">Previous → Value</th>
                      <th className="hidden md:table-cell">Delta</th>
                      <th className="hidden lg:table-cell">Task</th>
                      <th className="hidden sm:table-cell">Updated</th>
                      <th className="w-24">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleChanges.map((change) => {
                      const isExpanded =
                        change.entity_id === expandedSelection?.entityId;
                      const isSignificant =
                        Math.abs(change.delta_percent ?? 0) > 10;
                      const uncertainty = formatUncertainty(change as any);
                      const isLowConfidence = (() => {
                        const value = (change as any)?.value;
                        const error = (change as any)?.error;
                        if (
                          typeof value !== "number" ||
                          typeof error !== "number" ||
                          error <= 0
                        ) {
                          return false;
                        }
                        if (value === 0) return true;
                        return Math.abs(error / value) >= 0.05;
                      })();
                      return (
                        <tr
                          key={change.entity_id}
                          className={isExpanded ? "bg-base-300/40" : ""}
                        >
                          <td>
                            <DeltaIndicator
                              deltaPercent={change.delta_percent}
                            />
                          </td>
                          <td className="font-medium">
                            {change.parameter_name}
                          </td>
                          <td className="font-mono text-xs">
                            {change.qid || "-"}
                          </td>
                          <td className="hidden sm:table-cell font-mono text-xs">
                            {change.previous_value !== null &&
                            change.previous_value !== undefined ? (
                              <>
                                {formatValue(change.previous_value as any)}{" "}
                                →{" "}
                              </>
                            ) : (
                              <span className="text-base-content/40">- → </span>
                            )}
                            {formatValue(change.value as any)}{" "}
                            {change.unit || ""}
                            {uncertainty && (
                              <span
                                className={`ml-2 ${
                                  isLowConfidence
                                    ? "text-warning"
                                    : "text-base-content/60"
                                }`}
                                title="Measurement uncertainty (error)"
                              >
                                {uncertainty}
                              </span>
                            )}
                          </td>
                          <td className="hidden md:table-cell">
                            {change.delta_percent !== null &&
                            change.delta_percent !== undefined ? (
                              <span
                                className={`font-medium text-sm ${
                                  isSignificant
                                    ? "text-warning"
                                    : change.delta_percent >= 0
                                      ? "text-success"
                                      : "text-error"
                                }`}
                              >
                                {formatDeltaPercent(change.delta_percent)}
                              </span>
                            ) : (
                              <span className="text-base-content/40">-</span>
                            )}
                          </td>
                          <td className="hidden lg:table-cell text-sm">
                            {change.task_name || "-"}
                          </td>
                          <td className="hidden sm:table-cell text-sm text-base-content/70">
                            {formatRelativeTime(change.valid_from as string)}
                          </td>
                          <td>
                            <div className="flex gap-1 justify-end">
                              <Link
                                className="btn btn-xs btn-ghost"
                                href={`/provenance?tab=lineage&parameter=${encodeURIComponent(
                                  change.parameter_name,
                                )}&qid=${encodeURIComponent(change.qid || "")}`}
                                title="Open lineage"
                              >
                                <GitBranch className="h-3 w-3" />
                              </Link>
                              <Link
                                className="btn btn-xs btn-ghost"
                                href={`/provenance?tab=history&parameter=${encodeURIComponent(
                                  change.parameter_name,
                                )}&qid=${encodeURIComponent(change.qid || "")}`}
                                title="Open history"
                              >
                                <History className="h-3 w-3" />
                              </Link>
                              <button
                                className="btn btn-xs btn-ghost"
                                onClick={() =>
                                  setExpandedSelection(
                                    isExpanded
                                      ? null
                                      : {
                                          kind: "change",
                                          entityId: change.entity_id,
                                          parameterName: change.parameter_name,
                                          qid: change.qid || "",
                                        },
                                  )
                                }
                                title="Show suggested next actions"
                              >
                                <ChevronDown
                                  className={`h-3 w-3 transition-transform ${
                                    isExpanded ? "rotate-180" : ""
                                  }`}
                                />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {!showAllRows &&
                  filteredChanges.length > visibleChanges.length && (
                    <div className="mt-3 flex justify-center">
                      <button
                        className="btn btn-sm btn-ghost"
                        onClick={() => setShowAllRows(true)}
                      >
                        Show all ({filteredChanges.length})
                      </button>
                    </div>
                  )}
                {showAllRows && filteredChanges.length > 30 && (
                  <div className="mt-3 flex justify-center">
                    <button
                      className="btn btn-sm btn-ghost"
                      onClick={() => setShowAllRows(false)}
                    >
                      Show top 30
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {expandedSelection && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm text-base-content/70">
                <Clock className="h-4 w-4 inline mr-2" />
                Selected:{" "}
                <span className="font-medium text-base-content">
                  {expandedSelection.parameterName ??
                    selectedChange?.parameter_name ??
                    "?"}
                </span>{" "}
                <span className="text-base-content/60">
                  ({expandedSelection.qid ?? selectedChange?.qid ?? "?"})
                </span>
                <span className="ml-2 text-xs text-base-content/50">
                  {expandedSelection.kind === "policy"
                    ? "policy violation"
                    : "recent change"}
                </span>
              </div>
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => setExpandedSelection(null)}
              >
                Close
              </button>
            </div>

            {expandedSelection.kind === "policy" && (
              <div className="card bg-base-200">
                <div className="card-body p-4 sm:p-6">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="card-title text-base sm:text-lg">
                      Impact Violations
                    </h3>
                    <div className="flex items-center gap-2">
                      <span className="badge badge-sm">
                        {impactViolationCounts.total}
                      </span>
                      {impactViolationCounts.warn > 0 && (
                        <span className="badge badge-warning badge-sm">
                          warn {impactViolationCounts.warn}
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-base-content/70">
                    Violations evaluated on current values for parameters in the
                    downstream impact set.
                  </p>

                  {isImpactViolationsLoading && (
                    <div className="flex justify-center py-8">
                      <span className="loading loading-spinner loading-lg"></span>
                    </div>
                  )}

                  {!isImpactViolationsLoading &&
                    impactViolations.length === 0 && (
                      <div className="text-center py-6 text-base-content/60">
                        No downstream policy violations found.
                      </div>
                    )}

                  {!isImpactViolationsLoading &&
                    impactViolations.length > 0 && (
                      <div className="overflow-x-auto -mx-4 sm:mx-0 mt-3">
                        <table className="table table-sm">
                          <thead>
                            <tr>
                              <th>Severity</th>
                              <th>Parameter</th>
                              <th>QID</th>
                              <th className="hidden md:table-cell">Value</th>
                              <th>Message</th>
                              <th className="w-20"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {impactViolations.slice(0, 10).map((v) => (
                              <tr key={`${v.entity_id}::impact`}>
                                <td>
                                  <span className="badge badge-warning badge-sm">
                                    warn
                                  </span>
                                </td>
                                <td className="font-medium">
                                  {v.parameter_name}
                                </td>
                                <td className="font-mono text-xs">
                                  {v.qid || "-"}
                                </td>
                                <td className="hidden md:table-cell font-mono text-xs">
                                  {formatValue(v.value)} {v.unit || ""}
                                </td>
                                <td className="text-sm">
                                  {v.message || v.check_type}
                                </td>
                                <td>
                                  <div className="flex gap-1 justify-end">
                                    <Link
                                      className="btn btn-xs btn-ghost"
                                      href={`/provenance?tab=lineage&entity=${encodeURIComponent(
                                        v.entity_id,
                                      )}`}
                                      title="Open lineage"
                                    >
                                      <GitBranch className="h-3 w-3" />
                                    </Link>
                                    <Link
                                      className="btn btn-xs btn-ghost"
                                      href={`/provenance?tab=history&parameter=${encodeURIComponent(
                                        v.parameter_name,
                                      )}&qid=${encodeURIComponent(v.qid || "")}`}
                                      title="Open history"
                                    >
                                      <History className="h-3 w-3" />
                                    </Link>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>

                        {impactViolations.length > 10 && (
                          <div className="mt-3 flex justify-center">
                            <Link
                              className="btn btn-sm btn-ghost"
                              href={`/provenance?tab=lineage&entity=${encodeURIComponent(
                                expandedSelection.entityId,
                              )}`}
                            >
                              View full impact in Provenance
                            </Link>
                          </div>
                        )}
                      </div>
                    )}
                </div>
              </div>
            )}

            <RecalibrationRecommendationsPanel
              entityId={expandedSelection.entityId}
            />
          </div>
        )}
      </div>
    </PageContainer>
  );
}
