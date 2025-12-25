"use client";

import { useState, useEffect, useMemo } from "react";

import {
  GitCompare,
  Plus,
  Minus,
  ArrowRight,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

import {
  useCompareExecutions,
  useGetProvenanceStats,
  useGetRecentChanges,
} from "@/client/provenance/provenance";

export function ExecutionComparisonPanel() {
  const [executionBefore, setExecutionBefore] = useState("");
  const [executionAfter, setExecutionAfter] = useState("");
  const [isComparing, setIsComparing] = useState(false);
  const [initialized, setInitialized] = useState(false);

  // Fetch from both stats and changes to get complete execution ID list
  // Stats includes version 1 (initial values), changes includes version > 1
  const { data: statsResponse, isLoading: isLoadingStats } =
    useGetProvenanceStats();
  const { data: changesResponse, isLoading: isLoadingChanges } =
    useGetRecentChanges({ limit: 50, within_hours: 168 }); // Last 7 days

  const isLoadingExecutionList = isLoadingStats || isLoadingChanges;

  // Extract unique execution IDs from both sources
  const recentExecutions = useMemo(() => {
    const uniqueExecIds = new Map<
      string,
      { execution_id: string; valid_from: string | null }
    >();

    // From stats (includes initial versions)
    const entities = statsResponse?.data?.recent_entities || [];
    for (const entity of entities) {
      if (entity.execution_id && !uniqueExecIds.has(entity.execution_id)) {
        uniqueExecIds.set(entity.execution_id, {
          execution_id: entity.execution_id,
          valid_from: entity.valid_from as string | null,
        });
      }
    }

    // From changes (includes updates)
    const changes = changesResponse?.data?.changes || [];
    for (const change of changes) {
      if (change.execution_id && !uniqueExecIds.has(change.execution_id)) {
        uniqueExecIds.set(change.execution_id, {
          execution_id: change.execution_id,
          valid_from: change.valid_from as string | null,
        });
      }
    }

    // Return as array, sorted by valid_from (most recent first)
    return Array.from(uniqueExecIds.values())
      .sort((a, b) => {
        if (!a.valid_from) return 1;
        if (!b.valid_from) return -1;
        return (
          new Date(b.valid_from).getTime() - new Date(a.valid_from).getTime()
        );
      })
      .slice(0, 20);
  }, [statsResponse, changesResponse]);

  // Set default values when executions are loaded
  useEffect(() => {
    if (!initialized && recentExecutions.length >= 2) {
      // Use the two most recent executions as defaults
      setExecutionAfter(recentExecutions[0].execution_id);
      setExecutionBefore(recentExecutions[1].execution_id);
      setInitialized(true);
    }
  }, [recentExecutions, initialized]);

  const {
    data: response,
    isLoading,
    error,
  } = useCompareExecutions(
    {
      execution_id_before: executionBefore,
      execution_id_after: executionAfter,
    },
    {
      query: {
        enabled: isComparing && !!executionBefore && !!executionAfter,
      },
    },
  );
  const data = response?.data;

  const handleCompare = () => {
    if (executionBefore && executionAfter) {
      setIsComparing(true);
    }
  };

  const formatValue = (value: number | string | null | undefined) => {
    if (value === null || value === undefined) return "-";
    if (typeof value === "number") {
      return value.toExponential(4);
    }
    return String(value);
  };

  const formatDelta = (delta: number | null | undefined) => {
    if (delta === null || delta === undefined) return "";
    const sign = delta >= 0 ? "+" : "";
    return `${sign}${delta.toExponential(2)}`;
  };

  const formatDeltaPercent = (deltaPercent: number | null | undefined) => {
    if (deltaPercent === null || deltaPercent === undefined) return "";
    const sign = deltaPercent >= 0 ? "+" : "";
    return `(${sign}${deltaPercent.toFixed(2)}%)`;
  };

  return (
    <div className="space-y-6">
      {/* Comparison Form */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h3 className="card-title text-lg">Compare Executions</h3>
          <p className="text-sm text-base-content/70 mb-4">
            Compare parameter values between two calibration executions to see
            what changed.
          </p>
          {isLoadingExecutionList ? (
            <div className="flex items-center gap-2 py-4">
              <span className="loading loading-spinner loading-sm"></span>
              <span className="text-sm text-base-content/60">
                Loading executions...
              </span>
            </div>
          ) : recentExecutions.length < 2 ? (
            <div className="text-sm text-base-content/60 py-4">
              At least 2 executions are needed for comparison. Run more
              calibration workflows to enable this feature.
            </div>
          ) : (
            <div className="flex flex-col md:flex-row gap-4 items-end">
              <div className="form-control flex-1">
                <label className="label">
                  <span className="label-text">Before (Older)</span>
                </label>
                <select
                  className="select select-bordered w-full font-mono text-sm"
                  value={executionBefore}
                  onChange={(e) => {
                    setExecutionBefore(e.target.value);
                    setIsComparing(false);
                  }}
                >
                  <option value="" disabled>
                    Select execution...
                  </option>
                  {recentExecutions.map((exec) => (
                    <option key={exec.execution_id} value={exec.execution_id}>
                      {exec.execution_id.slice(0, 8)}...
                    </option>
                  ))}
                </select>
              </div>

              <div className="hidden md:flex items-center pb-3">
                <ArrowRight className="h-6 w-6 text-base-content/50" />
              </div>

              <div className="form-control flex-1">
                <label className="label">
                  <span className="label-text">After (Newer)</span>
                </label>
                <select
                  className="select select-bordered w-full font-mono text-sm"
                  value={executionAfter}
                  onChange={(e) => {
                    setExecutionAfter(e.target.value);
                    setIsComparing(false);
                  }}
                >
                  <option value="" disabled>
                    Select execution...
                  </option>
                  {recentExecutions.map((exec) => (
                    <option key={exec.execution_id} value={exec.execution_id}>
                      {exec.execution_id.slice(0, 8)}...
                    </option>
                  ))}
                </select>
              </div>

              <button
                className="btn btn-primary"
                onClick={handleCompare}
                disabled={!executionBefore || !executionAfter}
              >
                <GitCompare className="h-4 w-4" />
                Compare
              </button>
            </div>
          )}
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
          <span>Failed to compare executions</span>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {/* Summary Stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="stat bg-success/10 rounded-lg border border-success/20">
              <div className="stat-figure text-success">
                <Plus className="h-6 w-6" />
              </div>
              <div className="stat-title">Added</div>
              <div className="stat-value text-success text-2xl">
                {data.added_parameters.length}
              </div>
            </div>
            <div className="stat bg-error/10 rounded-lg border border-error/20">
              <div className="stat-figure text-error">
                <Minus className="h-6 w-6" />
              </div>
              <div className="stat-title">Removed</div>
              <div className="stat-value text-error text-2xl">
                {data.removed_parameters.length}
              </div>
            </div>
            <div className="stat bg-warning/10 rounded-lg border border-warning/20">
              <div className="stat-figure text-warning">
                <TrendingUp className="h-6 w-6" />
              </div>
              <div className="stat-title">Changed</div>
              <div className="stat-value text-warning text-2xl">
                {data.changed_parameters.length}
              </div>
            </div>
            <div className="stat bg-base-200 rounded-lg">
              <div className="stat-title">Unchanged</div>
              <div className="stat-value text-2xl">{data.unchanged_count}</div>
            </div>
          </div>

          {/* Changed Parameters */}
          {data.changed_parameters.length > 0 && (
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg text-warning">
                  <TrendingUp className="h-5 w-5" />
                  Changed Parameters
                </h3>
                <div className="overflow-x-auto">
                  <table className="table table-zebra">
                    <thead>
                      <tr>
                        <th>Parameter</th>
                        <th>Qubit</th>
                        <th>Before</th>
                        <th>After</th>
                        <th>Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.changed_parameters.map((param, index) => (
                        <tr key={index}>
                          <td className="font-medium">
                            {param.parameter_name}
                          </td>
                          <td>{param.qid}</td>
                          <td className="font-mono">
                            {formatValue(param.value_before)}
                          </td>
                          <td className="font-mono">
                            {formatValue(param.value_after)}
                          </td>
                          <td>
                            <div className="flex items-center gap-1">
                              {param.delta !== null &&
                                param.delta !== undefined && (
                                  <>
                                    {param.delta > 0 ? (
                                      <TrendingUp className="h-4 w-4 text-success" />
                                    ) : (
                                      <TrendingDown className="h-4 w-4 text-error" />
                                    )}
                                    <span
                                      className={`font-mono text-sm ${param.delta > 0 ? "text-success" : "text-error"}`}
                                    >
                                      {formatDelta(param.delta)}{" "}
                                      {formatDeltaPercent(param.delta_percent)}
                                    </span>
                                  </>
                                )}
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

          {/* Added Parameters */}
          {data.added_parameters.length > 0 && (
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg text-success">
                  <Plus className="h-5 w-5" />
                  Added Parameters
                </h3>
                <div className="overflow-x-auto">
                  <table className="table table-zebra">
                    <thead>
                      <tr>
                        <th>Parameter</th>
                        <th>Qubit</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.added_parameters.map((param, index) => (
                        <tr key={index}>
                          <td className="font-medium">
                            {param.parameter_name}
                          </td>
                          <td>{param.qid}</td>
                          <td className="font-mono">
                            {formatValue(param.value_after)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Removed Parameters */}
          {data.removed_parameters.length > 0 && (
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg text-error">
                  <Minus className="h-5 w-5" />
                  Removed Parameters
                </h3>
                <div className="overflow-x-auto">
                  <table className="table table-zebra">
                    <thead>
                      <tr>
                        <th>Parameter</th>
                        <th>Qubit</th>
                        <th>Previous Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.removed_parameters.map((param, index) => (
                        <tr key={index}>
                          <td className="font-medium">
                            {param.parameter_name}
                          </td>
                          <td>{param.qid}</td>
                          <td className="font-mono">
                            {formatValue(param.value_before)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* No Changes */}
          {data.changed_parameters.length === 0 &&
            data.added_parameters.length === 0 &&
            data.removed_parameters.length === 0 && (
              <div className="text-center py-8 text-base-content/50">
                No parameter differences found between these executions
              </div>
            )}
        </div>
      )}

      {!isComparing && !data && (
        <div className="text-center py-12 text-base-content/50">
          <GitCompare className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Enter two execution IDs to compare their parameter values</p>
        </div>
      )}
    </div>
  );
}
