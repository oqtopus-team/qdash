"use client";

import { useState, useEffect, useMemo } from "react";

import {
  Circle,
  Activity,
  ChevronRight,
  LayoutGrid,
  GitBranch as GraphIcon,
  GitCompare,
  History,
  X,
} from "lucide-react";

import {
  useGetProvenanceLineage,
  useGetParameterHistory,
} from "@/client/provenance/provenance";

import { LineagePathComparison } from "./LineagePathComparison";
import { ProvenanceGraph } from "./ProvenanceGraph";
import { RecalibrationRecommendationsPanel } from "./RecalibrationRecommendationsPanel";

type ViewMode = "graph" | "list" | "compare";

/** Maximum graph traversal depth for lineage queries.
 *  Set high enough to capture full calibration chains (typically 10-15 hops). */
const LINEAGE_MAX_DEPTH = 20;

interface LineageExplorerPanelProps {
  initialEntityId?: string;
  initialParameter?: string;
  initialQid?: string;
  onEntityChange?: (entityId: string) => void;
}

export function LineageExplorerPanel({
  initialEntityId = "",
  initialParameter = "",
  initialQid = "",
  onEntityChange,
}: LineageExplorerPanelProps) {
  const [entityId, setEntityId] = useState(initialEntityId);
  const [compareEntityId, setCompareEntityId] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("graph");

  // Fetch parameter history when parameter and qid are provided via URL
  // This enables navigation from Metrics page with ?parameter=t1&qid=5&tab=lineage
  const shouldFetchHistory = !!(
    initialParameter &&
    initialQid &&
    !initialEntityId &&
    !entityId
  );
  const { data: historyResponse, isLoading: isHistoryLoading } =
    useGetParameterHistory(
      {
        parameter_name: initialParameter || "",
        qid: initialQid || "",
        limit: 1,
      },
      { query: { enabled: shouldFetchHistory } },
    );

  // Sync with URL state when initialEntityId changes
  useEffect(() => {
    if (initialEntityId && initialEntityId !== entityId) {
      setEntityId(initialEntityId);
    }
  }, [initialEntityId, entityId]);

  // Auto-select entity from parameter history when fetched
  useEffect(() => {
    if (
      historyResponse?.data?.versions &&
      historyResponse.data.versions.length > 0 &&
      !entityId
    ) {
      const latestVersion = historyResponse.data.versions[0];
      setEntityId(latestVersion.entity_id);
      onEntityChange?.(latestVersion.entity_id);
    }
  }, [historyResponse, entityId, onEntityChange]);

  // Use maximum depth (20) to capture full lineage
  // Auto-search when entityId is available
  const {
    data: lineageResponse,
    isLoading,
    error,
  } = useGetProvenanceLineage(
    entityId,
    { max_depth: LINEAGE_MAX_DEPTH },
    { query: { enabled: !!entityId } },
  );

  const data = lineageResponse?.data;

  // Fetch lineage for comparison version
  const {
    data: compareLineageResponse,
    isLoading: isCompareLoading,
    error: compareError,
  } = useGetProvenanceLineage(
    compareEntityId,
    { max_depth: LINEAGE_MAX_DEPTH },
    { query: { enabled: viewMode === "compare" && !!compareEntityId } },
  );
  const compareData = compareLineageResponse?.data;

  // Derive parameter_name and qid from the current origin entity
  const originEntity = useMemo(() => {
    if (!data || !entityId) return null;
    const node = data.nodes.find((n) => n.node_id === entityId);
    if (node?.node_type === "entity" && node.entity) {
      return {
        parameterName: node.entity.parameter_name,
        qid: node.entity.qid,
      };
    }
    return null;
  }, [data, entityId]);

  // Fetch version history for the current parameter to enable version switching
  const canFetchVersions = !!(originEntity?.parameterName && originEntity?.qid);
  const { data: versionHistoryResponse } = useGetParameterHistory(
    {
      parameter_name: originEntity?.parameterName || "",
      qid: originEntity?.qid || "",
      limit: 100,
    },
    { query: { enabled: canFetchVersions } },
  );
  const versions = versionHistoryResponse?.data?.versions ?? [];

  const handleVersionChange = (newEntityId: string) => {
    setEntityId(newEntityId);
    onEntityChange?.(newEntityId);
  };

  const getVersionLabel = (eId: string) => {
    const v = versions.find((ver) => ver.entity_id === eId);
    if (!v) return eId.slice(0, 8);
    return `v${v.version}`;
  };

  const getNodeIcon = (nodeType: string) => {
    if (nodeType === "activity") {
      return <Activity className="h-4 w-4 text-secondary" />;
    }
    return <Circle className="h-4 w-4 text-primary" />;
  };

  const formatNodeLabel = (node: {
    node_type: string;
    node_id: string;
    entity?: {
      parameter_name?: string;
      qid?: string;
      value?: number | string;
    } | null;
    activity?: { task_name?: string; status?: string } | null;
  }) => {
    if (node.node_type === "entity" && node.entity) {
      return `${node.entity.parameter_name || "Unknown"} (${node.entity.qid || "?"})`;
    }
    if (node.node_type === "activity" && node.activity) {
      return node.activity.task_name || node.node_id;
    }
    return node.node_id;
  };

  const formatNodeValue = (node: {
    node_type: string;
    entity?: { value?: number | string; unit?: string } | null;
    activity?: { status?: string } | null;
  }) => {
    if (node.node_type === "entity" && node.entity?.value !== undefined) {
      const value = node.entity.value;
      if (typeof value === "number") {
        return `${value.toExponential(4)} ${node.entity.unit || ""}`.trim();
      }
      return String(value);
    }
    if (node.node_type === "activity" && node.activity) {
      return node.activity.status || "";
    }
    return "";
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Loading */}
      {(isLoading || isHistoryLoading) && (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      )}

      {error && (
        <div className="alert alert-error">
          <span>Failed to load lineage data</span>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {/* View Mode Toggle & Version Selector */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-base sm:text-lg font-medium">
                Lineage Graph
                <span className="badge badge-primary badge-sm sm:badge-md ml-2">
                  {data.nodes.length} nodes
                </span>
              </h3>
              {versions.length > 1 && (
                <div className="flex items-center gap-1.5">
                  <History className="h-3.5 w-3.5 text-base-content/50" />
                  <select
                    className="select select-bordered select-xs sm:select-sm font-mono"
                    value={entityId}
                    onChange={(e) => handleVersionChange(e.target.value)}
                  >
                    {versions.map((v) => (
                      <option key={v.entity_id} value={v.entity_id}>
                        v{v.version}
                        {v.valid_from
                          ? ` — ${new Date(v.valid_from).toLocaleDateString()}`
                          : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
            <div className="join">
              <button
                className={`btn btn-xs sm:btn-sm join-item ${viewMode === "graph" ? "btn-active" : ""}`}
                onClick={() => setViewMode("graph")}
              >
                <GraphIcon className="h-3 w-3 sm:h-4 sm:w-4" />
                Graph
              </button>
              <button
                className={`btn btn-xs sm:btn-sm join-item ${viewMode === "list" ? "btn-active" : ""}`}
                onClick={() => setViewMode("list")}
              >
                <LayoutGrid className="h-3 w-3 sm:h-4 sm:w-4" />
                List
              </button>
              {versions.length > 1 && (
                <button
                  className={`btn btn-xs sm:btn-sm join-item ${viewMode === "compare" ? "btn-active" : ""}`}
                  onClick={() => setViewMode("compare")}
                >
                  <GitCompare className="h-3 w-3 sm:h-4 sm:w-4" />
                  Compare
                </button>
              )}
            </div>
          </div>

          {/* Compare View - version selector and path diff */}
          {viewMode === "compare" && (
            <div className="space-y-4">
              {/* Compare version selector */}
              <div className="card bg-base-200">
                <div className="card-body p-4">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                    <span className="text-sm font-medium">
                      Compare {getVersionLabel(entityId)} with:
                    </span>
                    <select
                      className="select select-bordered select-sm font-mono flex-1 max-w-xs"
                      value={compareEntityId}
                      onChange={(e) => setCompareEntityId(e.target.value)}
                    >
                      <option value="">Select version...</option>
                      {versions
                        .filter((v) => v.entity_id !== entityId)
                        .map((v) => (
                          <option key={v.entity_id} value={v.entity_id}>
                            v{v.version}
                            {v.valid_from
                              ? ` — ${new Date(v.valid_from).toLocaleDateString()}`
                              : ""}
                          </option>
                        ))}
                    </select>
                    {compareEntityId && (
                      <button
                        className="btn btn-xs btn-ghost"
                        onClick={() => setCompareEntityId("")}
                      >
                        <X className="h-3 w-3" />
                        Clear
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Loading / Error */}
              {isCompareLoading && (
                <div className="flex justify-center py-8">
                  <span className="loading loading-spinner loading-md"></span>
                </div>
              )}
              {compareError && (
                <div className="alert alert-error">
                  <span>Failed to load comparison lineage</span>
                </div>
              )}

              {/* Path comparison — old version on the left, new on the right */}
              {compareData && data && (
                <LineagePathComparison
                  lineageBefore={compareData}
                  lineageAfter={data}
                  labelBefore={getVersionLabel(compareEntityId)}
                  labelAfter={getVersionLabel(entityId)}
                />
              )}

              {!compareEntityId && (
                <div className="text-center py-8 text-base-content/50">
                  <GitCompare className="h-10 w-10 mx-auto mb-3 opacity-50" />
                  <p className="text-sm">
                    Select a version to compare lineage paths and figures
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Graph View - full width for maximum visibility */}
          {viewMode === "graph" && (
            <ProvenanceGraph
              nodes={data.nodes}
              edges={data.edges}
              originId={entityId}
            />
          )}

          {/* List View */}
          {viewMode === "list" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Nodes List */}
              <div className="card bg-base-200">
                <div className="card-body p-4 sm:p-6">
                  <h3 className="card-title text-base sm:text-lg">
                    Nodes
                    <span className="badge badge-primary badge-sm ml-2">
                      {data.nodes.length}
                    </span>
                  </h3>
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {data.nodes.length === 0 ? (
                      <div className="text-center py-8 text-base-content/50">
                        No nodes found
                      </div>
                    ) : (
                      data.nodes.map((node) => (
                        <div
                          key={node.node_id}
                          className={`p-3 rounded-lg border ${
                            node.node_type === "entity"
                              ? "border-primary/30 bg-primary/5"
                              : "border-secondary/30 bg-secondary/5"
                          }`}
                        >
                          <div className="flex items-start gap-2">
                            {getNodeIcon(node.node_type)}
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-sm truncate">
                                {formatNodeLabel(node)}
                              </div>
                              <div className="text-xs text-base-content/70">
                                {formatNodeValue(node)}
                              </div>
                            </div>
                            <span
                              className={`badge badge-xs ${
                                node.node_type === "entity"
                                  ? "badge-primary"
                                  : "badge-secondary"
                              }`}
                            >
                              {node.node_type === "entity" ? "param" : "task"}
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Edges List */}
              <div className="card bg-base-200">
                <div className="card-body p-4 sm:p-6">
                  <h3 className="card-title text-base sm:text-lg">
                    Relations
                    <span className="badge badge-accent badge-sm ml-2">
                      {data.edges.length}
                    </span>
                  </h3>
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {data.edges.length === 0 ? (
                      <div className="text-center py-8 text-base-content/50">
                        No relations found
                      </div>
                    ) : (
                      data.edges.map((edge, index) => (
                        <div
                          key={index}
                          className="p-2 rounded-lg border border-accent/30 bg-accent/5"
                        >
                          <div className="flex items-center gap-1 text-xs">
                            <span className="font-mono truncate max-w-[100px]">
                              {edge.source_id.split(":").slice(0, 2).join(":")}
                            </span>
                            <ChevronRight className="h-3 w-3 text-accent flex-shrink-0" />
                            <span className="badge badge-accent badge-xs">
                              {edge.relation_type}
                            </span>
                            <ChevronRight className="h-3 w-3 text-accent flex-shrink-0" />
                            <span className="font-mono truncate max-w-[100px]">
                              {edge.target_id.split(":").slice(0, 2).join(":")}
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Recalibration Recommendations - below the graph */}
          <RecalibrationRecommendationsPanel entityId={entityId} />
        </div>
      )}
    </div>
  );
}
