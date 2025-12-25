"use client";

import { useState, useEffect } from "react";

import {
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  GitBranch,
} from "lucide-react";

import { useGetParameterHistory } from "@/client/provenance/provenance";
import { formatDateTime } from "@/utils/datetime";

interface ParameterHistoryPanelProps {
  initialParameter?: string;
  initialQid?: string;
  autoSearch?: boolean;
  onExploreLineage?: (entityId: string) => void;
  onParameterChange?: (parameter: string) => void;
  onQidChange?: (qid: string) => void;
}

export function ParameterHistoryPanel({
  initialParameter = "",
  initialQid = "",
  autoSearch = false,
  onExploreLineage,
  onParameterChange,
  onQidChange,
}: ParameterHistoryPanelProps) {
  // Use controlled state from URL when callbacks are provided
  const [localParameter, setLocalParameter] = useState(initialParameter);
  const [localQid, setLocalQid] = useState(initialQid);
  const [isSearching, setIsSearching] = useState(autoSearch);

  // Sync with URL state
  useEffect(() => {
    setLocalParameter(initialParameter);
  }, [initialParameter]);

  useEffect(() => {
    setLocalQid(initialQid);
  }, [initialQid]);

  // Auto-search when coming from URL with params
  useEffect(() => {
    if (autoSearch && initialParameter && initialQid) {
      setIsSearching(true);
    }
  }, [autoSearch, initialParameter, initialQid]);

  const {
    data: response,
    isLoading,
    error,
  } = useGetParameterHistory(
    { parameter_name: localParameter, qid: localQid, limit: 50 },
    { query: { enabled: isSearching && !!localParameter && !!localQid } },
  );
  const data = response?.data;

  const handleParameterChange = (value: string) => {
    setLocalParameter(value);
    setIsSearching(false);
    onParameterChange?.(value);
  };

  const handleQidChange = (value: string) => {
    setLocalQid(value);
    setIsSearching(false);
    onQidChange?.(value);
  };

  const handleSearch = () => {
    if (localParameter && localQid) {
      setIsSearching(true);
      // Sync to URL
      onParameterChange?.(localParameter);
      onQidChange?.(localQid);
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
    return formatDateTime(dateString);
  };

  const getTrendIcon = (current: number, previous: number | null) => {
    if (previous === null)
      return <Minus className="h-4 w-4 text-base-content/50" />;
    if (current > previous)
      return <TrendingUp className="h-4 w-4 text-success" />;
    if (current < previous)
      return <TrendingDown className="h-4 w-4 text-error" />;
    return <Minus className="h-4 w-4 text-base-content/50" />;
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Search Form */}
      <div className="card bg-base-200">
        <div className="card-body p-4 sm:p-6">
          <h3 className="card-title text-base sm:text-lg">
            Search Parameter History
          </h3>
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
            <div className="form-control flex-1">
              <label className="label py-1">
                <span className="label-text text-xs sm:text-sm">
                  Parameter Name
                </span>
              </label>
              <input
                type="text"
                placeholder="e.g., qubit_frequency, t1, t2_echo"
                className="input input-bordered input-sm sm:input-md w-full"
                value={localParameter}
                onChange={(e) => handleParameterChange(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>
            <div className="form-control flex-1">
              <label className="label py-1">
                <span className="label-text text-xs sm:text-sm">Qubit ID</span>
              </label>
              <input
                type="text"
                placeholder="e.g., 0, 1, 0-1"
                className="input input-bordered input-sm sm:input-md w-full"
                value={localQid}
                onChange={(e) => handleQidChange(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>
            <div className="form-control sm:self-end">
              <button
                className="btn btn-primary btn-sm sm:btn-md gap-1 sm:gap-2"
                onClick={handleSearch}
                disabled={!localParameter || !localQid}
              >
                <Search className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
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
          <div className="card-body p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
              <h3 className="card-title text-base sm:text-lg">
                {data.parameter_name} ({data.qid})
              </h3>
              <span className="badge badge-primary badge-sm sm:badge-md">
                {data.total_versions} versions
              </span>
            </div>

            {data.versions.length === 0 ? (
              <div className="text-center py-8 text-base-content/50">
                No version history found for this parameter
              </div>
            ) : (
              <div className="overflow-x-auto -mx-4 sm:mx-0">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Value</th>
                      <th className="hidden sm:table-cell">Unit</th>
                      <th className="hidden md:table-cell">Error</th>
                      <th className="hidden sm:table-cell">Trend</th>
                      <th className="hidden lg:table-cell">Task</th>
                      <th className="hidden md:table-cell">Valid From</th>
                      <th className="hidden lg:table-cell">Execution</th>
                      {onExploreLineage && <th>Actions</th>}
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
                            <span className="badge badge-outline badge-sm">
                              v{version.version}
                            </span>
                          </td>
                          <td className="font-mono text-xs sm:text-sm">
                            {formatValue(version.value)}
                          </td>
                          <td className="hidden sm:table-cell">
                            {version.unit || "-"}
                          </td>
                          <td className="font-mono text-xs hidden md:table-cell">
                            {version.error
                              ? `±${version.error.toExponential(2)}`
                              : "-"}
                          </td>
                          <td className="hidden sm:table-cell">
                            {typeof version.value === "number" &&
                              getTrendIcon(
                                version.value,
                                typeof previousValue === "number"
                                  ? previousValue
                                  : null,
                              )}
                          </td>
                          <td className="hidden lg:table-cell">
                            <span className="text-sm">
                              {version.task_name || "-"}
                            </span>
                          </td>
                          <td className="text-xs sm:text-sm hidden md:table-cell">
                            {formatDate(version.valid_from)}
                          </td>
                          <td className="hidden lg:table-cell">
                            <span className="text-xs font-mono text-base-content/70">
                              {version.execution_id.slice(0, 8)}...
                            </span>
                          </td>
                          {onExploreLineage && (
                            <td>
                              <button
                                className="btn btn-xs btn-ghost"
                                onClick={() =>
                                  onExploreLineage(version.entity_id)
                                }
                                title="View lineage graph"
                              >
                                <GitBranch className="h-3 w-3" />
                              </button>
                            </td>
                          )}
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
          <Search className="h-10 w-10 sm:h-12 sm:w-12 mx-auto mb-4 opacity-50" />
          <p className="text-sm sm:text-base">
            Enter a parameter name and qubit ID to view version history
          </p>
        </div>
      )}
    </div>
  );
}
