"use client";

import { useCallback } from "react";

import {
  GitBranch,
  History,
  GitCompare,
  BarChart3,
  Database,
} from "lucide-react";

import { useGetProvenanceStats } from "@/client/provenance/provenance";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useProvenanceUrlState } from "@/hooks/useUrlState";

import { ParameterHistoryPanel } from "./ParameterHistoryPanel";
import { ExecutionComparisonPanel } from "./ExecutionComparisonPanel";
import { LineageExplorerPanel } from "./LineageExplorerPanel";
import { SeedParametersPanel } from "./SeedParametersPanel";

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

  const handleExploreLineage = useCallback(
    (newEntityId: string) => {
      setEntityId(newEntityId);
      setActiveTab("lineage");
    },
    [setEntityId, setActiveTab],
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
