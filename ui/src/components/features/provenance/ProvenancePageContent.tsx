"use client";

import { useCallback, useMemo } from "react";

import {
  GitBranch,
  History,
  GitCompare,
  BarChart3,
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
  Database,
} from "lucide-react";

import {
  useGetProvenanceStats,
  useGetRecentChanges,
} from "@/client/provenance/provenance";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { formatRelativeTime } from "@/utils/datetime";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useProvenanceUrlState } from "@/hooks/useUrlState";

import { ParameterHistoryPanel } from "./ParameterHistoryPanel";
import { ExecutionComparisonPanel } from "./ExecutionComparisonPanel";
import { LineageExplorerPanel } from "./LineageExplorerPanel";
import { SeedParametersPanel } from "./SeedParametersPanel";

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

function formatDeltaPercent(percent: number | null | undefined): string {
  if (percent === null || percent === undefined) return "";
  const sign = percent >= 0 ? "+" : "";
  return `${sign}${percent.toFixed(1)}%`;
}

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
  } else if (deltaPercent < 0) {
    return (
      <TrendingDown
        className={`h-4 w-4 ${isSignificant ? "text-warning" : "text-error"}`}
      />
    );
  }
  return <Minus className="h-4 w-4 text-base-content/40" />;
}

export function ProvenancePageContent() {
  const {
    activeTab,
    parameter,
    qid,
    entityId,
    setActiveTab,
    setParameter,
    setQid,
    setEntityId,
    isInitialized,
    hasSearchParams,
  } = useProvenanceUrlState();

  const { data: statsResponse, isLoading } = useGetProvenanceStats();
  const stats = statsResponse?.data;

  const { allMetrics, isLoading: isLoadingConfig } = useMetricsConfig();

  // Get parameter names from metrics config
  const parameterNames = useMemo(() => {
    return allMetrics.map((m) => m.key);
  }, [allMetrics]);

  const { data: changesResponse, isLoading: isLoadingChanges } =
    useGetRecentChanges(
      {
        limit: 15,
        within_hours: 48,
        parameter_names: parameterNames.length > 0 ? parameterNames : undefined,
      },
      {
        query: {
          staleTime: 30000,
          enabled: !isLoadingConfig && parameterNames.length > 0,
        },
      },
    );
  const changes = changesResponse?.data?.changes || [];

  const handleExploreLineage = useCallback(
    (newEntityId: string) => {
      setEntityId(newEntityId);
      setActiveTab("lineage");
    },
    [setEntityId, setActiveTab],
  );

  const handleSearchHistory = useCallback(
    (parameterName: string, newQid: string) => {
      setParameter(parameterName);
      setQid(newQid);
      setActiveTab("history");
    },
    [setParameter, setQid, setActiveTab],
  );

  // Show loading state while URL state is initializing
  if (!isInitialized || isLoading) {
    return (
      <PageContainer maxWidth>
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer maxWidth>
      <div className="space-y-4 sm:space-y-6">
        {/* Header */}
        <PageHeader
          title="Data Provenance"
          description="Track calibration parameter history and lineage following W3C PROV-DM standards"
        />

        {/* Stats Cards */}
        {stats && stats.total_entities > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            <div className="stat bg-base-200 rounded-box p-4">
              <div className="stat-figure text-primary">
                <History className="h-6 w-6 sm:h-8 sm:w-8" />
              </div>
              <div className="stat-title text-xs sm:text-sm">
                Parameter Versions
              </div>
              <div className="stat-value text-lg sm:text-2xl text-primary">
                {stats.total_entities.toLocaleString()}
              </div>
              <div className="stat-desc text-xs">Tracked parameter values</div>
            </div>
            <div className="stat bg-base-200 rounded-box p-4">
              <div className="stat-figure text-secondary">
                <BarChart3 className="h-6 w-6 sm:h-8 sm:w-8" />
              </div>
              <div className="stat-title text-xs sm:text-sm">Activities</div>
              <div className="stat-value text-lg sm:text-2xl text-secondary">
                {stats.total_activities.toLocaleString()}
              </div>
              <div className="stat-desc text-xs">Task executions</div>
            </div>
            <div className="stat bg-base-200 rounded-box p-4">
              <div className="stat-figure text-accent">
                <GitBranch className="h-6 w-6 sm:h-8 sm:w-8" />
              </div>
              <div className="stat-title text-xs sm:text-sm">Relations</div>
              <div className="stat-value text-lg sm:text-2xl text-accent">
                {stats.total_relations.toLocaleString()}
              </div>
              <div className="stat-desc text-xs">Provenance links</div>
            </div>
          </div>
        )}

        {/* Recent Changes with Delta */}
        {!isLoadingChanges && changes.length > 0 && (
          <div className="card bg-base-200">
            <div className="card-body p-4 sm:p-6">
              <div className="flex items-center justify-between">
                <h3 className="card-title text-base sm:text-lg gap-2">
                  <Clock className="h-4 w-4 sm:h-5 sm:w-5" />
                  Recent Parameter Changes (48h)
                  <span className="badge badge-primary badge-sm">
                    {changes.length}
                  </span>
                </h3>
              </div>
              <div className="overflow-x-auto -mx-4 sm:mx-0">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th className="w-8"></th>
                      <th>Parameter</th>
                      <th>Qubit</th>
                      <th className="hidden sm:table-cell">Previous → Value</th>
                      <th className="hidden md:table-cell">Delta</th>
                      <th className="hidden lg:table-cell">Task</th>
                      <th className="hidden sm:table-cell">Updated</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {changes.map((change) => {
                      const isSignificant =
                        change.delta_percent !== null &&
                        change.delta_percent !== undefined &&
                        Math.abs(change.delta_percent) > 10;

                      return (
                        <tr
                          key={change.entity_id}
                          className={`hover cursor-pointer ${
                            isSignificant ? "bg-warning/5" : ""
                          }`}
                          onClick={() => handleExploreLineage(change.entity_id)}
                        >
                          <td>
                            <DeltaIndicator
                              deltaPercent={change.delta_percent}
                            />
                          </td>
                          <td className="font-medium">
                            {change.parameter_name}
                          </td>
                          <td>
                            <span className="badge badge-ghost badge-sm">
                              Q{change.qid || "?"}
                            </span>
                          </td>
                          <td className="font-mono text-xs hidden sm:table-cell">
                            <span className="text-base-content/60">
                              {formatValue(change.previous_value ?? "-")}
                            </span>
                            <span className="mx-1 text-base-content/40">→</span>
                            <span className="font-medium">
                              {formatValue(change.value)}
                            </span>
                            {change.unit && (
                              <span className="text-base-content/50 ml-1">
                                {change.unit}
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
                          <td className="text-sm hidden lg:table-cell">
                            {change.task_name || "-"}
                          </td>
                          <td className="text-sm text-base-content/70 hidden sm:table-cell">
                            {formatRelativeTime(change.valid_from as string)}
                          </td>
                          <td>
                            <div className="flex gap-1">
                              <button
                                className="btn btn-xs btn-ghost"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleExploreLineage(change.entity_id);
                                }}
                                title="Explore lineage"
                              >
                                <GitBranch className="h-3 w-3" />
                              </button>
                              <button
                                className="btn btn-xs btn-ghost"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSearchHistory(
                                    change.parameter_name,
                                    change.qid || "",
                                  );
                                }}
                                title="View history"
                              >
                                <History className="h-3 w-3" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Empty State */}
        {stats && stats.total_entities === 0 && (
          <div className="card bg-base-200">
            <div className="card-body text-center py-12">
              <GitBranch className="h-12 w-12 sm:h-16 sm:w-16 mx-auto text-base-content/30 mb-4" />
              <h3 className="text-base sm:text-lg font-medium">
                No Provenance Data Yet
              </h3>
              <p className="text-sm text-base-content/70 max-w-md mx-auto">
                Provenance tracking is enabled. Run a calibration workflow to
                start tracking parameter lineage and history.
              </p>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="tabs tabs-boxed w-full sm:w-fit gap-1 p-1 overflow-x-auto flex-nowrap">
          <button
            className={`tab tab-sm sm:tab-md gap-1 sm:gap-2 whitespace-nowrap ${
              activeTab === "history" ? "tab-active" : ""
            }`}
            onClick={() => setActiveTab("history")}
          >
            <History className="h-3 w-3 sm:h-4 sm:w-4" />
            <span className="hidden xs:inline">Parameter</span> History
          </button>
          <button
            className={`tab tab-sm sm:tab-md gap-1 sm:gap-2 whitespace-nowrap ${
              activeTab === "lineage" ? "tab-active" : ""
            }`}
            onClick={() => setActiveTab("lineage")}
          >
            <GitBranch className="h-3 w-3 sm:h-4 sm:w-4" />
            Lineage
          </button>
          <button
            className={`tab tab-sm sm:tab-md gap-1 sm:gap-2 whitespace-nowrap ${
              activeTab === "compare" ? "tab-active" : ""
            }`}
            onClick={() => setActiveTab("compare")}
          >
            <GitCompare className="h-3 w-3 sm:h-4 sm:w-4" />
            Compare
          </button>
          <button
            className={`tab tab-sm sm:tab-md gap-1 sm:gap-2 whitespace-nowrap ${
              activeTab === "seeds" ? "tab-active" : ""
            }`}
            onClick={() => setActiveTab("seeds")}
          >
            <Database className="h-3 w-3 sm:h-4 sm:w-4" />
            Seeds
          </button>
        </div>

        {/* Tab Content */}
        <div className="min-h-[400px] sm:min-h-[500px]">
          {activeTab === "history" && (
            <ParameterHistoryPanel
              initialParameter={parameter}
              initialQid={qid}
              autoSearch={hasSearchParams}
              onExploreLineage={handleExploreLineage}
              onParameterChange={setParameter}
              onQidChange={setQid}
            />
          )}
          {activeTab === "lineage" && (
            <LineageExplorerPanel
              initialEntityId={entityId}
              initialParameter={parameter}
              initialQid={qid}
              onEntityChange={setEntityId}
            />
          )}
          {activeTab === "compare" && <ExecutionComparisonPanel />}
          {activeTab === "seeds" && <SeedParametersPanel />}
        </div>
      </div>
    </PageContainer>
  );
}
