"use client";

import { useState } from "react";

import {
  GitCompare,
  Plus,
  Minus,
  ArrowRight,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

import { useCompareExecutions } from "@/client/provenance/provenance";

export function ExecutionComparisonPanel() {
  const [executionBefore, setExecutionBefore] = useState("");
  const [executionAfter, setExecutionAfter] = useState("");
  const [isComparing, setIsComparing] = useState(false);

  const { data: response, isLoading, error } = useCompareExecutions(
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleCompare();
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
          <div className="flex flex-col md:flex-row gap-4 items-end">
            <div className="form-control flex-1">
              <label className="label">
                <span className="label-text">Before (Execution ID)</span>
              </label>
              <input
                type="text"
                placeholder="e.g., exec-001"
                className="input input-bordered w-full font-mono"
                value={executionBefore}
                onChange={(e) => {
                  setExecutionBefore(e.target.value);
                  setIsComparing(false);
                }}
                onKeyDown={handleKeyDown}
              />
            </div>

            <div className="hidden md:flex items-center pb-3">
              <ArrowRight className="h-6 w-6 text-base-content/50" />
            </div>

            <div className="form-control flex-1">
              <label className="label">
                <span className="label-text">After (Execution ID)</span>
              </label>
              <input
                type="text"
                placeholder="e.g., exec-002"
                className="input input-bordered w-full font-mono"
                value={executionAfter}
                onChange={(e) => {
                  setExecutionAfter(e.target.value);
                  setIsComparing(false);
                }}
                onKeyDown={handleKeyDown}
              />
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
                          <td className="font-medium">{param.parameter_name}</td>
                          <td>{param.qid}</td>
                          <td className="font-mono">
                            {formatValue(param.value_before)}
                          </td>
                          <td className="font-mono">
                            {formatValue(param.value_after)}
                          </td>
                          <td>
                            <div className="flex items-center gap-1">
                              {param.delta !== null && param.delta !== undefined && (
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
                          <td className="font-medium">{param.parameter_name}</td>
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
                          <td className="font-medium">{param.parameter_name}</td>
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
