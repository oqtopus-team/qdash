"use client";

import { useState } from "react";

import {
  Search,
  ArrowUp,
  ArrowDown,
  Circle,
  Activity,
  ChevronRight,
  LayoutGrid,
  GitBranch as GraphIcon,
} from "lucide-react";

import {
  useGetProvenanceLineage,
  useGetProvenanceImpact,
} from "@/client/provenance/provenance";

import { ProvenanceGraph } from "./ProvenanceGraph";

type Direction = "lineage" | "impact";
type ViewMode = "graph" | "list";

interface LineageExplorerPanelProps {
  initialEntityId?: string;
}

export function LineageExplorerPanel({ initialEntityId = "" }: LineageExplorerPanelProps) {
  const [entityId, setEntityId] = useState(initialEntityId);
  const [maxDepth, setMaxDepth] = useState(5);
  const [direction, setDirection] = useState<Direction>("lineage");
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [isSearching, setIsSearching] = useState(!!initialEntityId);

  const {
    data: lineageResponse,
    isLoading: lineageLoading,
    error: lineageError,
  } = useGetProvenanceLineage(
    entityId,
    { max_depth: maxDepth },
    { query: { enabled: isSearching && direction === "lineage" && !!entityId } },
  );

  const {
    data: impactResponse,
    isLoading: impactLoading,
    error: impactError,
  } = useGetProvenanceImpact(
    entityId,
    { max_depth: maxDepth },
    { query: { enabled: isSearching && direction === "impact" && !!entityId } },
  );

  const data = direction === "lineage" ? lineageResponse?.data : impactResponse?.data;
  const isLoading = direction === "lineage" ? lineageLoading : impactLoading;
  const error = direction === "lineage" ? lineageError : impactError;

  const handleSearch = () => {
    if (entityId) {
      setIsSearching(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
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
    entity?: { parameter_name?: string; qid?: string; value?: number | string } | null;
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
    // Future: Could open a detail modal or navigate to the entity
    console.log("Clicked node:", nodeId, nodeType);
  };

  return (
    <div className="space-y-6">
      {/* Search Form */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h3 className="card-title text-lg">Explore Parameter Lineage</h3>
          <p className="text-sm text-base-content/70 mb-4">
            Enter an entity ID to trace its origins (lineage) or see what
            parameters were derived from it (impact).
          </p>
          <div className="flex flex-col gap-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text">Entity ID</span>
              </label>
              <input
                type="text"
                placeholder="e.g., qubit_frequency:Q0:exec-001:task-001"
                className="input input-bordered w-full font-mono text-sm"
                value={entityId}
                onChange={(e) => {
                  setEntityId(e.target.value);
                  setIsSearching(false);
                }}
                onKeyDown={handleKeyDown}
              />
              <label className="label">
                <span className="label-text-alt">
                  Format: parameter_name:qid:execution_id:task_id
                </span>
              </label>
            </div>

            <div className="flex flex-col md:flex-row gap-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Direction</span>
                </label>
                <div className="join">
                  <button
                    className={`btn join-item ${direction === "lineage" ? "btn-primary" : "btn-outline"}`}
                    onClick={() => {
                      setDirection("lineage");
                      setIsSearching(false);
                    }}
                  >
                    <ArrowUp className="h-4 w-4" />
                    Lineage (Origins)
                  </button>
                  <button
                    className={`btn join-item ${direction === "impact" ? "btn-primary" : "btn-outline"}`}
                    onClick={() => {
                      setDirection("impact");
                      setIsSearching(false);
                    }}
                  >
                    <ArrowDown className="h-4 w-4" />
                    Impact (Derived)
                  </button>
                </div>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Max Depth</span>
                </label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(Number(e.target.value))}
                  className="range range-primary"
                />
                <div className="w-full flex justify-between text-xs px-2">
                  <span>1</span>
                  <span>{maxDepth}</span>
                  <span>10</span>
                </div>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">&nbsp;</span>
                </label>
                <button
                  className="btn btn-primary"
                  onClick={handleSearch}
                  disabled={!entityId}
                >
                  <Search className="h-4 w-4" />
                  Explore
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Results */}
      {isLoading && (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      )}

      {error && (
        <div className="alert alert-error">
          <span>Failed to load {direction} data</span>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {/* View Mode Toggle */}
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-medium">
              {direction === "lineage" ? "Lineage Graph" : "Impact Graph"}
              <span className="badge badge-primary ml-2">
                {data.nodes.length} nodes, {data.edges.length} edges
              </span>
            </h3>
            <div className="join">
              <button
                className={`btn btn-sm join-item ${viewMode === "graph" ? "btn-active" : ""}`}
                onClick={() => setViewMode("graph")}
              >
                <GraphIcon className="h-4 w-4" />
                Graph
              </button>
              <button
                className={`btn btn-sm join-item ${viewMode === "list" ? "btn-active" : ""}`}
                onClick={() => setViewMode("list")}
              >
                <LayoutGrid className="h-4 w-4" />
                List
              </button>
            </div>
          </div>

          {/* Graph View */}
          {viewMode === "graph" && (
            <div className="relative">
              <ProvenanceGraph
                nodes={data.nodes}
                edges={data.edges}
                originId={entityId}
                onNodeClick={handleNodeClick}
              />
            </div>
          )}

          {/* List View */}
          {viewMode === "list" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Nodes List */}
              <div className="card bg-base-200">
                <div className="card-body">
                  <h3 className="card-title text-lg">
                    {direction === "lineage" ? "Ancestors" : "Descendants"}
                    <span className="badge badge-primary ml-2">
                      {data.nodes.length} nodes
                    </span>
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {data.nodes.length === 0 ? (
                      <div className="text-center py-8 text-base-content/50">
                        No {direction === "lineage" ? "ancestors" : "descendants"}{" "}
                        found
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
                              <div className="font-medium truncate">
                                {formatNodeLabel(node)}
                              </div>
                              <div className="text-sm text-base-content/70">
                                {formatNodeValue(node)}
                              </div>
                              <div className="text-xs font-mono text-base-content/50 truncate mt-1">
                                {node.node_id}
                              </div>
                            </div>
                            <span
                              className={`badge badge-sm ${node.node_type === "entity" ? "badge-primary" : "badge-secondary"}`}
                            >
                              {node.node_type}
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
                <div className="card-body">
                  <h3 className="card-title text-lg">
                    Relations
                    <span className="badge badge-accent ml-2">
                      {data.edges.length} edges
                    </span>
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {data.edges.length === 0 ? (
                      <div className="text-center py-8 text-base-content/50">
                        No relations found
                      </div>
                    ) : (
                      data.edges.map((edge, index) => (
                        <div
                          key={index}
                          className="p-3 rounded-lg border border-accent/30 bg-accent/5"
                        >
                          <div className="flex items-center gap-2 text-sm">
                            <span className="font-mono text-xs truncate max-w-[120px]">
                              {edge.source_id.split(":").slice(0, 2).join(":")}
                            </span>
                            <ChevronRight className="h-4 w-4 text-accent flex-shrink-0" />
                            <span className="badge badge-accent badge-sm">
                              {edge.relation_type}
                            </span>
                            <ChevronRight className="h-4 w-4 text-accent flex-shrink-0" />
                            <span className="font-mono text-xs truncate max-w-[120px]">
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

      {!isSearching && !data && (
        <div className="text-center py-12 text-base-content/50">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Enter an entity ID to explore its lineage or impact</p>
          <p className="text-sm mt-2">
            Tip: Click on a recent entity in the table above to explore its lineage
          </p>
        </div>
      )}
    </div>
  );
}
