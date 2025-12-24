"use client";

import { useState, useCallback } from "react";

import { GitBranch, History, GitCompare, BarChart3, Clock } from "lucide-react";

import { useGetProvenanceStats } from "@/client/provenance/provenance";

import { ParameterHistoryPanel } from "./ParameterHistoryPanel";
import { ExecutionComparisonPanel } from "./ExecutionComparisonPanel";
import { LineageExplorerPanel } from "./LineageExplorerPanel";

type TabType = "history" | "lineage" | "compare";

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

const formatDate = (dateString: string | null | undefined) => {
  if (!dateString) return "-";
  return new Date(dateString).toLocaleString();
};

export function ProvenancePageContent() {
  const [activeTab, setActiveTab] = useState<TabType>("history");
  const [selectedEntityId, setSelectedEntityId] = useState<string>("");
  const { data: statsResponse } = useGetProvenanceStats();
  const stats = statsResponse?.data;

  const handleExploreLineage = useCallback((entityId: string) => {
    setSelectedEntityId(entityId);
    setActiveTab("lineage");
  }, []);

  const handleSearchHistory = useCallback((_parameterName: string, _qid: string) => {
    // For now, just switch to the history tab
    // Future: could pre-fill the search form with _parameterName and _qid
    setActiveTab("history");
  }, []);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <GitBranch className="h-6 w-6" />
          Data Provenance
        </h1>
        <p className="text-base-content/70">
          Track calibration parameter history and lineage following W3C PROV-DM
          standards
        </p>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-figure text-primary">
              <History className="h-8 w-8" />
            </div>
            <div className="stat-title">Parameter Versions</div>
            <div className="stat-value text-primary">
              {stats.total_entities.toLocaleString()}
            </div>
            <div className="stat-desc">Tracked parameter values</div>
          </div>
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-figure text-secondary">
              <BarChart3 className="h-8 w-8" />
            </div>
            <div className="stat-title">Activities</div>
            <div className="stat-value text-secondary">
              {stats.total_activities.toLocaleString()}
            </div>
            <div className="stat-desc">Task executions</div>
          </div>
          <div className="stat bg-base-200 rounded-lg">
            <div className="stat-figure text-accent">
              <GitBranch className="h-8 w-8" />
            </div>
            <div className="stat-title">Relations</div>
            <div className="stat-value text-accent">
              {stats.total_relations.toLocaleString()}
            </div>
            <div className="stat-desc">Provenance links</div>
          </div>
        </div>
      )}

      {/* Recent Entities - Always visible as quick access */}
      {stats && stats.recent_entities && stats.recent_entities.length > 0 && (
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title text-lg">
              <Clock className="h-5 w-5" />
              Recent Parameter Updates
              <span className="text-sm font-normal text-base-content/70">
                (click to explore lineage)
              </span>
            </h3>
            <div className="overflow-x-auto">
              <table className="table table-zebra table-sm">
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Qubit</th>
                    <th>Value</th>
                    <th>Unit</th>
                    <th>Task</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_entities.map((entity) => (
                    <tr
                      key={entity.entity_id}
                      className="hover cursor-pointer"
                      onClick={() => handleExploreLineage(entity.entity_id)}
                    >
                      <td className="font-medium">{entity.parameter_name}</td>
                      <td>{entity.qid}</td>
                      <td className="font-mono text-sm">{formatValue(entity.value)}</td>
                      <td>{entity.unit || "-"}</td>
                      <td className="text-sm">{entity.task_name || "-"}</td>
                      <td className="text-sm text-base-content/70">
                        {formatDate(entity.valid_from)}
                      </td>
                      <td>
                        <div className="flex gap-1">
                          <button
                            className="btn btn-xs btn-ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleExploreLineage(entity.entity_id);
                            }}
                            title="Explore lineage"
                          >
                            <GitBranch className="h-3 w-3" />
                          </button>
                          <button
                            className="btn btn-xs btn-ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSearchHistory(entity.parameter_name, entity.qid || "");
                            }}
                            title="View history"
                          >
                            <History className="h-3 w-3" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Empty State for New Users */}
      {stats && stats.total_entities === 0 && (
        <div className="card bg-base-200">
          <div className="card-body text-center py-12">
            <GitBranch className="h-16 w-16 mx-auto text-base-content/30 mb-4" />
            <h3 className="text-lg font-medium">No Provenance Data Yet</h3>
            <p className="text-base-content/70 max-w-md mx-auto">
              Provenance tracking is enabled. Run a calibration workflow to start
              tracking parameter lineage and history.
            </p>
            <div className="mt-4 text-sm text-base-content/50">
              <p>When workflows run, you&apos;ll see:</p>
              <ul className="list-disc list-inside mt-2 text-left max-w-xs mx-auto">
                <li>Parameter version history</li>
                <li>Data lineage graphs</li>
                <li>Execution comparisons</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div role="tablist" className="tabs tabs-bordered">
        <button
          role="tab"
          className={`tab gap-2 ${activeTab === "history" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("history")}
        >
          <History className="h-4 w-4" />
          Parameter History
        </button>
        <button
          role="tab"
          className={`tab gap-2 ${activeTab === "lineage" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("lineage")}
        >
          <GitBranch className="h-4 w-4" />
          Lineage Explorer
        </button>
        <button
          role="tab"
          className={`tab gap-2 ${activeTab === "compare" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("compare")}
        >
          <GitCompare className="h-4 w-4" />
          Compare Executions
        </button>
      </div>

      {/* Tab Content */}
      <div className="min-h-[500px]">
        {activeTab === "history" && <ParameterHistoryPanel />}
        {activeTab === "lineage" && (
          <LineageExplorerPanel
            key={selectedEntityId}
            initialEntityId={selectedEntityId}
          />
        )}
        {activeTab === "compare" && <ExecutionComparisonPanel />}
      </div>
    </div>
  );
}
