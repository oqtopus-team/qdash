"use client";

import { useState, useMemo, useEffect } from "react";

import {
  Search,
  Circle,
  Activity,
  ChevronRight,
  LayoutGrid,
  GitBranch as GraphIcon,
  Clock,
} from "lucide-react";

import {
  useGetProvenanceLineage,
  useGetProvenanceStats,
  useGetParameterHistory,
} from "@/client/provenance/provenance";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";

import { ProvenanceGraph } from "./ProvenanceGraph";

type ViewMode = "graph" | "list";

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
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [searchFilter, setSearchFilter] = useState("");

  // Get metrics config for parameter filtering
  const { allMetrics, isLoading: isLoadingConfig } = useMetricsConfig();
  const validParameterNames = useMemo(
    () => new Set(allMetrics.map((m) => m.key)),
    [allMetrics],
  );

  // Get recent entities for quick selection (filtered by metrics config)
  const { data: statsResponse, isLoading: isLoadingStats } =
    useGetProvenanceStats();
  const recentEntities = useMemo(() => {
    // Wait for both stats and config to be loaded before showing entities
    if (isLoadingConfig || isLoadingStats) return [];
    const entities = statsResponse?.data?.recent_entities || [];
    // Filter to only show parameters defined in metrics.yaml
    // If config is loaded but empty, show nothing (not unfiltered)
    if (validParameterNames.size === 0) return [];
    return entities.filter((e) => validParameterNames.has(e.parameter_name));
  }, [
    statsResponse?.data?.recent_entities,
    validParameterNames,
    isLoadingConfig,
    isLoadingStats,
  ]);

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

  // Fallback: Auto-select entity from recentEntities when parameter and qid provided
  useEffect(() => {
    if (
      !entityId &&
      initialParameter &&
      initialQid &&
      !shouldFetchHistory &&
      recentEntities.length > 0
    ) {
      // Find matching entity from recent entities
      const matchingEntity = recentEntities.find(
        (e) => e.parameter_name === initialParameter && e.qid === initialQid,
      );
      if (matchingEntity) {
        setEntityId(matchingEntity.entity_id);
        onEntityChange?.(matchingEntity.entity_id);
      }
    }
  }, [
    entityId,
    initialParameter,
    initialQid,
    shouldFetchHistory,
    recentEntities,
    onEntityChange,
  ]);

  // Filter recent entities based on search
  const filteredEntities = useMemo(() => {
    if (!searchFilter) return recentEntities.slice(0, 8);
    const lower = searchFilter.toLowerCase();
    return recentEntities
      .filter(
        (e) =>
          e.parameter_name?.toLowerCase().includes(lower) ||
          e.qid?.toLowerCase().includes(lower) ||
          e.task_name?.toLowerCase().includes(lower),
      )
      .slice(0, 8);
  }, [recentEntities, searchFilter]);

  // Use maximum depth (20) to capture full lineage
  // Auto-search when entityId is available
  const {
    data: lineageResponse,
    isLoading,
    error,
  } = useGetProvenanceLineage(
    entityId,
    { max_depth: 20 },
    { query: { enabled: !!entityId } },
  );

  const data = lineageResponse?.data;

  const handleQuickSelect = (selectedEntityId: string) => {
    setEntityId(selectedEntityId);
    setSearchFilter("");
    onEntityChange?.(selectedEntityId);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && entityId) {
      onEntityChange?.(entityId);
    }
  };

  const formatRelativeTime = (dateString: string | null | undefined) => {
    if (!dateString) return "";
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
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

  const handleNodeClick = (nodeId: string, nodeType: string) => {
    // Navigate to clicked entity
    if (nodeType === "entity" && nodeId !== entityId) {
      setEntityId(nodeId);
      onEntityChange?.(nodeId);
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Quick Select */}
      <div className="card bg-base-200">
        <div className="card-body p-4 sm:p-6">
          <h3 className="card-title text-base sm:text-lg">
            Select a Parameter to Explore
          </h3>
          <p className="text-sm text-base-content/70 mb-4">
            Click a parameter to trace its origins (what tasks produced it and
            what inputs were used).
          </p>

          {/* Quick Select Grid */}
          {(isLoadingConfig || isLoadingStats) && (
            <div className="flex items-center gap-2 py-4">
              <span className="loading loading-spinner loading-sm"></span>
              <span className="text-sm text-base-content/60">
                Loading parameters...
              </span>
            </div>
          )}
          {!isLoadingConfig && !isLoadingStats && recentEntities.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Clock className="h-4 w-4 text-base-content/60" />
                <span className="text-sm font-medium text-base-content/80">
                  Recent Parameters
                </span>
                <input
                  type="text"
                  placeholder="Filter..."
                  className="input input-bordered input-sm ml-auto w-32 sm:w-40"
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                {filteredEntities.map((entity) => (
                  <button
                    key={entity.entity_id}
                    className={`
                      p-2 sm:p-3 rounded-lg text-left transition-colors
                      border
                      ${
                        entityId === entity.entity_id
                          ? "bg-primary/20 border-primary"
                          : "bg-base-100 border-base-300 hover:border-primary/50 hover:bg-base-100/80"
                      }
                    `}
                    onClick={() => handleQuickSelect(entity.entity_id)}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-2 h-2 rounded-full bg-primary/60 flex-shrink-0" />
                      <span className="font-medium text-xs sm:text-sm truncate">
                        {entity.parameter_name}
                      </span>
                    </div>
                    <div className="text-[10px] sm:text-xs text-base-content/60 truncate">
                      {entity.qid} • {formatRelativeTime(entity.valid_from)}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Advanced: Manual Entity ID Input */}
          <details className="collapse collapse-arrow bg-base-100 rounded-lg mt-4">
            <summary className="collapse-title text-sm font-medium py-2 min-h-0">
              Advanced: Enter Entity ID manually
            </summary>
            <div className="collapse-content pb-2">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g., qubit_frequency:0:exec-001:task-001"
                  className="input input-bordered input-sm flex-1 font-mono text-xs"
                  value={entityId}
                  onChange={(e) => setEntityId(e.target.value)}
                  onKeyDown={handleKeyDown}
                />
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => entityId && onEntityChange?.(entityId)}
                  disabled={!entityId}
                >
                  <Search className="h-4 w-4" />
                </button>
              </div>
            </div>
          </details>
        </div>
      </div>

      {/* Results */}
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
          {/* View Mode Toggle */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
            <h3 className="text-base sm:text-lg font-medium">
              Lineage Graph
              <span className="badge badge-primary badge-sm sm:badge-md ml-2">
                {data.nodes.length} nodes
              </span>
            </h3>
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
            </div>
          </div>

          {/* Graph View */}
          {viewMode === "graph" && (
            <ProvenanceGraph
              nodes={data.nodes}
              edges={data.edges}
              originId={entityId}
              onNodeClick={handleNodeClick}
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
                          className={`p-3 rounded-lg border cursor-pointer hover:bg-base-300/50 ${
                            node.node_type === "entity"
                              ? "border-primary/30 bg-primary/5"
                              : "border-secondary/30 bg-secondary/5"
                          }`}
                          onClick={() =>
                            handleNodeClick(node.node_id, node.node_type)
                          }
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
                              className={`badge badge-xs ${node.node_type === "entity" ? "badge-primary" : "badge-secondary"}`}
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
        </div>
      )}

      {!entityId && !data && (
        <div className="text-center py-12 text-base-content/50">
          <Search className="h-10 w-10 sm:h-12 sm:w-12 mx-auto mb-4 opacity-50" />
          <p className="text-sm sm:text-base">
            Select a parameter above to explore its lineage
          </p>
        </div>
      )}
    </div>
  );
}
