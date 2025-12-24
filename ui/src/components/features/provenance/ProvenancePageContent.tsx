"use client";

import { useState } from "react";

import { GitBranch, History, GitCompare, BarChart3 } from "lucide-react";

import { useGetProvenanceStats } from "@/client/provenance/provenance";

import { ParameterHistoryPanel } from "./ParameterHistoryPanel";
import { ExecutionComparisonPanel } from "./ExecutionComparisonPanel";
import { LineageExplorerPanel } from "./LineageExplorerPanel";

type TabType = "history" | "lineage" | "compare";

export function ProvenancePageContent() {
  const [activeTab, setActiveTab] = useState<TabType>("history");
  const { data: statsResponse } = useGetProvenanceStats();
  const stats = statsResponse?.data;

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
        {activeTab === "lineage" && <LineageExplorerPanel />}
        {activeTab === "compare" && <ExecutionComparisonPanel />}
      </div>
    </div>
  );
}
