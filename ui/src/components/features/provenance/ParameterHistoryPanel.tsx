"use client";

import { useState } from "react";

import { Search, TrendingUp, TrendingDown, Minus } from "lucide-react";

import { useGetParameterHistory } from "@/client/provenance/provenance";

export function ParameterHistoryPanel() {
  const [parameterName, setParameterName] = useState("");
  const [qid, setQid] = useState("");
  const [isSearching, setIsSearching] = useState(false);

  const { data: response, isLoading, error } = useGetParameterHistory(
    { parameter_name: parameterName, qid: qid, limit: 50 },
    { query: { enabled: isSearching && !!parameterName && !!qid } },
  );
  const data = response?.data;

  const handleSearch = () => {
    if (parameterName && qid) {
      setIsSearching(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  const formatValue = (value: number | string) => {
    if (typeof value === "number") {
      return value.toExponential(4);
    }
    return String(value);
  };

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return "-";
    return new Date(dateString).toLocaleString();
  };

  const getTrendIcon = (current: number, previous: number | null) => {
    if (previous === null) return <Minus className="h-4 w-4 text-base-content/50" />;
    if (current > previous) return <TrendingUp className="h-4 w-4 text-success" />;
    if (current < previous) return <TrendingDown className="h-4 w-4 text-error" />;
    return <Minus className="h-4 w-4 text-base-content/50" />;
  };

  return (
    <div className="space-y-6">
      {/* Search Form */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h3 className="card-title text-lg">Search Parameter History</h3>
          <div className="flex flex-col md:flex-row gap-4">
            <div className="form-control flex-1">
              <label className="label">
                <span className="label-text">Parameter Name</span>
              </label>
              <input
                type="text"
                placeholder="e.g., qubit_frequency, t1, t2_echo"
                className="input input-bordered w-full"
                value={parameterName}
                onChange={(e) => {
                  setParameterName(e.target.value);
                  setIsSearching(false);
                }}
                onKeyDown={handleKeyDown}
              />
            </div>
            <div className="form-control flex-1">
              <label className="label">
                <span className="label-text">Qubit ID</span>
              </label>
              <input
                type="text"
                placeholder="e.g., Q0, Q1, Q0-Q1"
                className="input input-bordered w-full"
                value={qid}
                onChange={(e) => {
                  setQid(e.target.value);
                  setIsSearching(false);
                }}
                onKeyDown={handleKeyDown}
              />
            </div>
            <div className="form-control">
              <label className="label">
                <span className="label-text">&nbsp;</span>
              </label>
              <button
                className="btn btn-primary"
                onClick={handleSearch}
                disabled={!parameterName || !qid}
              >
                <Search className="h-4 w-4" />
                Search
              </button>
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
          <span>Failed to load parameter history</span>
        </div>
      )}

      {data && (
        <div className="card bg-base-200">
          <div className="card-body">
            <div className="flex justify-between items-center">
              <h3 className="card-title text-lg">
                {data.parameter_name} ({data.qid})
              </h3>
              <span className="badge badge-primary">
                {data.total_versions} versions
              </span>
            </div>

            {data.versions.length === 0 ? (
              <div className="text-center py-8 text-base-content/50">
                No version history found for this parameter
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="table table-zebra">
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Value</th>
                      <th>Unit</th>
                      <th>Error</th>
                      <th>Trend</th>
                      <th>Task</th>
                      <th>Valid From</th>
                      <th>Execution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.versions.map((version, index) => {
                      const previousValue =
                        index < data.versions.length - 1
                          ? data.versions[index + 1].value
                          : null;
                      return (
                        <tr key={version.entity_id}>
                          <td>
                            <span className="badge badge-outline">
                              v{version.version}
                            </span>
                          </td>
                          <td className="font-mono">
                            {formatValue(version.value)}
                          </td>
                          <td>{version.unit || "-"}</td>
                          <td className="font-mono">
                            {version.error ? `±${version.error.toExponential(2)}` : "-"}
                          </td>
                          <td>
                            {typeof version.value === "number" &&
                              getTrendIcon(
                                version.value,
                                typeof previousValue === "number"
                                  ? previousValue
                                  : null,
                              )}
                          </td>
                          <td>
                            <span className="text-sm">
                              {version.task_name || "-"}
                            </span>
                          </td>
                          <td className="text-sm">
                            {formatDate(version.valid_from)}
                          </td>
                          <td>
                            <span className="text-xs font-mono text-base-content/70">
                              {version.execution_id.slice(0, 8)}...
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {!isSearching && !data && (
        <div className="text-center py-12 text-base-content/50">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Enter a parameter name and qubit ID to view version history</p>
        </div>
      )}
    </div>
  );
}
