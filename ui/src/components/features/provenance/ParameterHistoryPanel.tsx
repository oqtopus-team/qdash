"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import Select from "react-select";
import type { SingleValue, GroupBase } from "react-select";

import {
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  GitBranch,
  BarChart3,
  X,
  Image,
} from "lucide-react";

import { useGetParameterHistory } from "@/client/provenance/provenance";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import {
  getDaisySelectStyles,
  getDaisySelectStylesSm,
} from "@/lib/react-select-theme";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { formatDateTime } from "@/lib/utils/datetime";
import type { ParameterVersionResponse } from "@/schemas/parameterVersionResponse";

interface ParameterOption {
  value: string;
  label: string;
}

const Plot = dynamic(() => import("@/components/charts/Plot"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[300px]">
      <div className="loading loading-spinner loading-lg text-primary"></div>
    </div>
  ),
});

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
  const [prevInitialParameter, setPrevInitialParameter] =
    useState(initialParameter);
  const [localQid, setLocalQid] = useState(initialQid);
  const [prevInitialQid, setPrevInitialQid] = useState(initialQid);
  const [isSearching, setIsSearching] = useState(autoSearch);

  // Sync with URL state during render (React recommended pattern)
  if (initialParameter !== prevInitialParameter) {
    setPrevInitialParameter(initialParameter);
    setLocalParameter(initialParameter);
  }
  if (initialQid !== prevInitialQid) {
    setPrevInitialQid(initialQid);
    setLocalQid(initialQid);
  }

  // Version diff state
  const [diffSelection, setDiffSelection] = useState<[string, string | null]>([
    "",
    null,
  ]);
  const [prevDiffKey, setPrevDiffKey] = useState(
    `${initialParameter}:${initialQid}`,
  );

  // Parallel comparison state
  const [compareParameter, setCompareParameter] = useState("");
  const [compareQid, setCompareQid] = useState("");
  const [isComparing, setIsComparing] = useState(false);

  // Metrics config for parameter dropdown
  const { qubitMetrics, couplingMetrics } = useMetricsConfig();

  const parameterOptions = useMemo<GroupBase<ParameterOption>[]>(() => {
    if (qubitMetrics.length === 0 && couplingMetrics.length === 0) return [];
    return [
      {
        label: "1Q Metrics",
        options: qubitMetrics.map((m) => ({ value: m.key, label: m.title })),
      },
      {
        label: "2Q Metrics",
        options: couplingMetrics.map((m) => ({ value: m.key, label: m.title })),
      },
    ];
  }, [qubitMetrics, couplingMetrics]);

  const allMetricOptions = useMemo(
    () =>
      [...qubitMetrics, ...couplingMetrics].map((m) => ({
        value: m.key,
        label: m.title,
      })),
    [qubitMetrics, couplingMetrics],
  );

  const selectStyles = useMemo(
    () =>
      getDaisySelectStyles<
        ParameterOption,
        false,
        GroupBase<ParameterOption>
      >(),
    [],
  );
  const selectStylesSm = useMemo(
    () =>
      getDaisySelectStylesSm<
        ParameterOption,
        false,
        GroupBase<ParameterOption>
      >(),
    [],
  );

  // Auto-search when coming from URL with params
  useEffect(() => {
    if (autoSearch && initialParameter && initialQid) {
      setIsSearching(true);
    }
  }, [autoSearch, initialParameter, initialQid]);

  // Reset diff selection when parameter/qid changes (during render)
  const diffKey = `${localParameter}:${localQid}`;
  if (diffKey !== prevDiffKey) {
    setPrevDiffKey(diffKey);
    setDiffSelection(["", null]);
  }

  const {
    data: response,
    isLoading,
    error,
  } = useGetParameterHistory(
    { parameter_name: localParameter, qid: localQid, limit: 50 },
    { query: { enabled: isSearching && !!localParameter && !!localQid } },
  );
  const data = response?.data;

  // Comparison parameter fetch
  const { data: compareResponse, isLoading: isCompareLoading } =
    useGetParameterHistory(
      {
        parameter_name: compareParameter,
        qid: compareQid || localQid,
        limit: 50,
      },
      {
        query: {
          enabled:
            isComparing && !!compareParameter && !!(compareQid || localQid),
        },
      },
    );
  const compareData = compareResponse?.data;

  // --- Auto-search: trigger search whenever both parameter and qid are set ---
  const triggerSearch = useCallback(
    (param: string, qid: string) => {
      if (param && qid) {
        setIsSearching(true);
        onParameterChange?.(param);
        onQidChange?.(qid);
      } else {
        setIsSearching(false);
      }
    },
    [onParameterChange, onQidChange],
  );

  const handleParameterSelect = (value: string) => {
    setLocalParameter(value);
    triggerSearch(value, localQid);
  };

  const handleQidChange = (value: string) => {
    setLocalQid(value);
    onQidChange?.(value);
    // Don't auto-search on every keystroke; wait for Enter or blur
  };

  const handleSearch = () => {
    triggerSearch(localParameter, localQid);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  const handleQidBlur = () => {
    if (localParameter && localQid) {
      triggerSearch(localParameter, localQid);
    }
  };

  const handleCompare = () => {
    if (compareParameter) {
      setIsComparing(true);
    }
  };

  const handleRemoveCompare = () => {
    setIsComparing(false);
    setCompareParameter("");
    setCompareQid("");
  };

  const handleCompareKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleCompare();
    }
  };

  const handleDiffToggle = (entityId: string) => {
    setDiffSelection((prev) => {
      if (prev[0] === entityId) return [prev[1] ?? "", null];
      if (prev[1] === entityId) return [prev[0], null];
      if (!prev[0]) return [entityId, null];
      if (!prev[1]) return [prev[0], entityId];
      return [prev[1]!, entityId];
    });
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

  // Chart data
  const chartVersions = useMemo(
    () => [...(data?.versions ?? [])].reverse(),
    [data],
  );
  const compareChartVersions = useMemo(
    () => [...(compareData?.versions ?? [])].reverse(),
    [compareData],
  );

  const hasNumericValues = chartVersions.some(
    (v) => typeof v.value === "number",
  );
  const showChart = hasNumericValues && chartVersions.length >= 2;
  const showCompareColumns = isComparing && !!compareData;

  // --- Compare version matching by closest valid_from ---
  const compareVersionMap = useMemo(() => {
    if (!showCompareColumns || !compareData?.versions || !data?.versions)
      return new Map<string, ParameterVersionResponse>();

    const map = new Map<string, ParameterVersionResponse>();
    const compareVers = compareData.versions;
    if (compareVers.length === 0) return map;

    // Build sorted list of compare timestamps for binary-search-like matching
    const compareWithTs = compareVers
      .map((v) => ({
        version: v,
        ts: v.valid_from ? new Date(v.valid_from).getTime() : 0,
      }))
      .sort((a, b) => a.ts - b.ts);

    for (const mainVer of data.versions) {
      const mainTs = mainVer.valid_from
        ? new Date(mainVer.valid_from).getTime()
        : 0;
      // Find closest compare version
      let best = compareWithTs[0];
      let bestDiff = Math.abs(mainTs - best.ts);
      for (let i = 1; i < compareWithTs.length; i++) {
        const diff = Math.abs(mainTs - compareWithTs[i].ts);
        if (diff < bestDiff) {
          best = compareWithTs[i];
          bestDiff = diff;
        }
      }
      map.set(mainVer.entity_id, best.version);
    }
    return map;
  }, [showCompareColumns, compareData, data]);

  const compareLabel = useMemo(() => {
    if (!compareData) return "";
    const metricOpt = allMetricOptions.find(
      (o) => o.value === compareData.parameter_name,
    );
    return metricOpt?.label ?? compareData.parameter_name;
  }, [compareData, allMetricOptions]);

  const plotData = useMemo(() => {
    const traces: Plotly.Data[] = [];
    if (!showChart) return traces;

    const hasErrors = chartVersions.some(
      (v) => v.error !== undefined && v.error !== null,
    );

    traces.push({
      x: chartVersions.map((v) =>
        v.valid_from ? new Date(v.valid_from).toISOString() : "",
      ),
      y: chartVersions.map((v) =>
        typeof v.value === "number" ? v.value : null,
      ),
      error_y: hasErrors
        ? {
            type: "data" as const,
            array: chartVersions.map((v) => v.error ?? 0),
            visible: true,
          }
        : undefined,
      type: "scatter" as const,
      mode: "lines+markers" as const,
      name: `${data?.parameter_name} (${data?.qid})`,
      marker: { size: 7, symbol: "circle" },
      line: { width: 2, color: "#1f77b4" },
      yaxis: "y",
    });

    if (isComparing && compareChartVersions.length >= 2) {
      const hasCompareErrors = compareChartVersions.some(
        (v) => v.error !== undefined && v.error !== null,
      );
      traces.push({
        x: compareChartVersions.map((v) =>
          v.valid_from ? new Date(v.valid_from).toISOString() : "",
        ),
        y: compareChartVersions.map((v) =>
          typeof v.value === "number" ? v.value : null,
        ),
        error_y: hasCompareErrors
          ? {
              type: "data" as const,
              array: compareChartVersions.map((v) => v.error ?? 0),
              visible: true,
            }
          : undefined,
        type: "scatter" as const,
        mode: "lines+markers" as const,
        name: `${compareLabel} (${compareData?.qid})`,
        marker: { size: 7, symbol: "diamond" },
        line: { width: 2, dash: "dash", color: "#e377c2" },
        yaxis: "y2",
      });
    }
    return traces;
  }, [
    showChart,
    chartVersions,
    compareChartVersions,
    isComparing,
    data,
    compareData,
    compareLabel,
  ]);

  const plotLayout = useMemo(() => {
    const showDual = isComparing && compareChartVersions.length >= 2;
    const layout: Record<string, unknown> = {
      xaxis: {
        title: "Time",
        type: "date",
        tickformat: "%Y-%m-%d %H:%M",
        gridcolor: "#eee",
        zeroline: false,
        domain: showDual ? [0, 0.92] : [0, 1],
      },
      yaxis: {
        title: data
          ? `${data.parameter_name}${data.versions[0]?.unit ? ` [${data.versions[0].unit}]` : ""}`
          : "",
        type: "linear",
        gridcolor: "#eee",
        zeroline: false,
        exponentformat: "e",
        titlefont: { color: "#1f77b4" },
        tickfont: { color: "#1f77b4" },
      },
      showlegend: showDual,
      legend: {
        x: 1.02,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(255, 255, 255, 0.8)",
      },
      autosize: true,
      margin: { l: 80, r: showDual ? 180 : 40, t: 30, b: 60 },
      plot_bgcolor: "transparent",
      paper_bgcolor: "transparent",
      hovermode: "closest",
    };

    if (showDual && compareData) {
      layout.yaxis2 = {
        title: `${compareLabel}${compareData.versions[0]?.unit ? ` [${compareData.versions[0].unit}]` : ""}`,
        type: "linear",
        overlaying: "y",
        side: "right",
        gridcolor: "rgba(227, 119, 194, 0.2)",
        zeroline: false,
        exponentformat: "e",
        titlefont: { color: "#e377c2" },
        tickfont: { color: "#e377c2" },
      };
    }

    return layout;
  }, [
    data,
    compareData,
    compareLabel,
    isComparing,
    compareChartVersions.length,
  ]);

  // Version diff computation
  const diffVersions = useMemo(() => {
    if (!diffSelection[0] || !diffSelection[1] || !data?.versions) return null;
    const a = data.versions.find((v) => v.entity_id === diffSelection[0]);
    const b = data.versions.find((v) => v.entity_id === diffSelection[1]);
    if (!a || !b) return null;
    const [older, newer] = a.version < b.version ? [a, b] : [b, a];
    const delta =
      typeof newer.value === "number" && typeof older.value === "number"
        ? newer.value - older.value
        : null;
    const deltaPercent =
      delta !== null && typeof older.value === "number" && older.value !== 0
        ? (delta / Math.abs(older.value)) * 100
        : null;
    return { older, newer, delta, deltaPercent };
  }, [diffSelection, data]);

  const isDiffSelected = (entityId: string) =>
    diffSelection[0] === entityId || diffSelection[1] === entityId;

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
              <Select<ParameterOption, false, GroupBase<ParameterOption>>
                options={parameterOptions}
                value={
                  allMetricOptions.find((o) => o.value === localParameter) ??
                  null
                }
                onChange={(option: SingleValue<ParameterOption>) => {
                  handleParameterSelect(option?.value ?? "");
                }}
                placeholder="Select parameter..."
                styles={selectStyles}
                isClearable
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
                onBlur={handleQidBlur}
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

      {/* Parallel Comparison Form */}
      {data && (
        <div className="card bg-base-200">
          <div className="card-body p-4 sm:p-6">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              <h3 className="card-title text-sm sm:text-base">
                Compare with another parameter
              </h3>
            </div>
            {isComparing && compareData ? (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="badge badge-secondary gap-1">
                  {compareLabel} ({compareData.qid})
                </span>
                {isCompareLoading && (
                  <span className="loading loading-spinner loading-xs"></span>
                )}
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={handleRemoveCompare}
                >
                  <X className="h-3 w-3" />
                  Remove
                </button>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
                <div className="form-control flex-1">
                  <Select<ParameterOption, false, GroupBase<ParameterOption>>
                    options={parameterOptions}
                    value={
                      allMetricOptions.find(
                        (o) => o.value === compareParameter,
                      ) ?? null
                    }
                    onChange={(option: SingleValue<ParameterOption>) => {
                      setCompareParameter(option?.value ?? "");
                    }}
                    placeholder="Select parameter..."
                    styles={selectStylesSm}
                    isClearable
                  />
                </div>
                <div className="form-control flex-1">
                  <input
                    type="text"
                    placeholder={`Qubit ID (default: ${localQid})`}
                    className="input input-bordered input-sm w-full"
                    value={compareQid}
                    onChange={(e) => setCompareQid(e.target.value)}
                    onKeyDown={handleCompareKeyDown}
                  />
                </div>
                <button
                  className="btn btn-secondary btn-sm gap-1"
                  onClick={handleCompare}
                  disabled={!compareParameter}
                >
                  <BarChart3 className="h-4 w-4" />
                  Compare
                </button>
              </div>
            )}
          </div>
        </div>
      )}

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

            {/* Time Series Chart */}
            {showChart && (
              <div className="bg-base-200/50 rounded-xl p-2">
                <Plot
                  data={plotData}
                  layout={plotLayout}
                  config={{
                    responsive: true,
                    displayModeBar: true,
                    modeBarButtonsToRemove: [
                      "lasso2d",
                      "select2d",
                    ] as Plotly.ModeBarDefaultButtons[],
                  }}
                  style={{ width: "100%", height: "300px" }}
                  useResizeHandler
                />
              </div>
            )}

            {/* Version Diff Card */}
            {diffVersions && (
              <DiffCard
                diffVersions={diffVersions}
                formatValue={formatValue}
                formatDate={formatDate}
                onExploreLineage={onExploreLineage}
                onClear={() => setDiffSelection(["", null])}
              />
            )}

            {data.versions.length === 0 ? (
              <div className="text-center py-8 text-base-content/50">
                No version history found for this parameter
              </div>
            ) : (
              <div className="overflow-x-auto -mx-4 sm:mx-0">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th className="w-8">
                        <span className="text-xs text-base-content/50">
                          Diff
                        </span>
                      </th>
                      <th>Version</th>
                      <th>Value</th>
                      <th className="hidden sm:table-cell">Unit</th>
                      <th className="hidden md:table-cell">Error</th>
                      <th className="hidden sm:table-cell">Trend</th>
                      {showCompareColumns && (
                        <>
                          <th className="border-l border-base-300">
                            <span
                              className="text-xs"
                              style={{ color: "#e377c2" }}
                            >
                              {compareLabel}
                            </span>
                          </th>
                          <th className="hidden md:table-cell">
                            <span
                              className="text-xs"
                              style={{ color: "#e377c2" }}
                            >
                              Error
                            </span>
                          </th>
                          <th className="hidden sm:table-cell">
                            <span
                              className="text-xs"
                              style={{ color: "#e377c2" }}
                            >
                              Trend
                            </span>
                          </th>
                        </>
                      )}
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
                      const selected = isDiffSelected(version.entity_id);
                      const matched = showCompareColumns
                        ? compareVersionMap.get(version.entity_id)
                        : undefined;
                      return (
                        <tr
                          key={version.entity_id}
                          className={selected ? "bg-primary/10" : ""}
                        >
                          <td>
                            <input
                              type="checkbox"
                              className="checkbox checkbox-xs checkbox-primary"
                              checked={selected}
                              onChange={() =>
                                handleDiffToggle(version.entity_id)
                              }
                            />
                          </td>
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
                          {showCompareColumns &&
                            (() => {
                              const matchedPrev =
                                index < data.versions.length - 1
                                  ? compareVersionMap.get(
                                      data.versions[index + 1].entity_id,
                                    )
                                  : undefined;
                              return (
                                <>
                                  <td
                                    className="font-mono text-xs sm:text-sm border-l border-base-300"
                                    style={{ color: "#e377c2" }}
                                  >
                                    {matched ? formatValue(matched.value) : "-"}
                                  </td>
                                  <td
                                    className="font-mono text-xs hidden md:table-cell"
                                    style={{ color: "#e377c2" }}
                                  >
                                    {matched?.error
                                      ? `±${matched.error.toExponential(2)}`
                                      : "-"}
                                  </td>
                                  <td className="hidden sm:table-cell">
                                    {matched &&
                                      typeof matched.value === "number" &&
                                      getTrendIcon(
                                        matched.value,
                                        matchedPrev &&
                                          typeof matchedPrev.value === "number"
                                          ? matchedPrev.value
                                          : null,
                                      )}
                                  </td>
                                </>
                              );
                            })()}
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
            Select a parameter and enter a qubit ID to view version history
          </p>
        </div>
      )}
    </div>
  );
}

// --- DiffCard sub-component ---

interface DiffCardProps {
  diffVersions: {
    older: ParameterVersionResponse;
    newer: ParameterVersionResponse;
    delta: number | null;
    deltaPercent: number | null;
  };
  formatValue: (value: number | string) => string;
  formatDate: (dateString: string | null | undefined) => string;
  onExploreLineage?: (entityId: string) => void;
  onClear: () => void;
}

function DiffCard({
  diffVersions,
  formatValue,
  formatDate,
  onExploreLineage,
  onClear,
}: DiffCardProps) {
  const { older, newer, delta, deltaPercent } = diffVersions;

  return (
    <div className="bg-base-300/50 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-sm flex items-center gap-2">
          Version Diff
          <span className="badge badge-outline badge-sm">
            v{older.version} → v{newer.version}
          </span>
        </h4>
        <button className="btn btn-xs btn-ghost" onClick={onClear}>
          Clear selection
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Older version */}
        <div className="bg-base-100 rounded-lg p-3 space-y-1">
          <div className="flex items-center justify-between">
            <span className="badge badge-outline badge-sm">
              v{older.version}
            </span>
            {onExploreLineage && (
              <button
                className="btn btn-xs btn-ghost"
                onClick={() => onExploreLineage(older.entity_id)}
                title="View lineage"
              >
                <GitBranch className="h-3 w-3" />
              </button>
            )}
          </div>
          <div className="font-mono text-sm">{formatValue(older.value)}</div>
          <div className="text-xs text-base-content/60">{older.unit || ""}</div>
          <div className="text-xs text-base-content/60">
            {older.task_name || "-"}
          </div>
          <div className="text-xs text-base-content/50">
            {formatDate(older.valid_from)}
          </div>
        </div>

        {/* Newer version */}
        <div className="bg-base-100 rounded-lg p-3 space-y-1">
          <div className="flex items-center justify-between">
            <span className="badge badge-outline badge-sm">
              v{newer.version}
            </span>
            {onExploreLineage && (
              <button
                className="btn btn-xs btn-ghost"
                onClick={() => onExploreLineage(newer.entity_id)}
                title="View lineage"
              >
                <GitBranch className="h-3 w-3" />
              </button>
            )}
          </div>
          <div className="font-mono text-sm">{formatValue(newer.value)}</div>
          <div className="text-xs text-base-content/60">{newer.unit || ""}</div>
          <div className="text-xs text-base-content/60">
            {newer.task_name || "-"}
          </div>
          <div className="text-xs text-base-content/50">
            {formatDate(newer.valid_from)}
          </div>
        </div>
      </div>

      {/* Delta summary */}
      {delta !== null && (
        <div className="flex items-center gap-3 text-sm">
          <span className="text-base-content/60">Delta:</span>
          <span
            className={`font-mono font-semibold ${delta > 0 ? "text-success" : delta < 0 ? "text-error" : "text-base-content/50"}`}
          >
            {delta > 0 ? "+" : ""}
            {delta.toExponential(4)}
          </span>
          {deltaPercent !== null && (
            <span
              className={`badge badge-sm ${deltaPercent > 0 ? "badge-success" : deltaPercent < 0 ? "badge-error" : "badge-ghost"}`}
            >
              {deltaPercent > 0 ? "+" : ""}
              {deltaPercent.toFixed(2)}%
            </span>
          )}
        </div>
      )}
      {delta === null && (
        <div className="text-xs text-base-content/50">
          Delta not available (non-numeric values)
        </div>
      )}

      {/* Figure Comparison */}
      <div className="space-y-2">
        <h4 className="font-semibold text-sm flex items-center gap-2">
          <Image className="h-4 w-4" />
          Figures
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="bg-base-100 rounded-lg p-2">
            <div className="text-xs text-base-content/60 mb-1">
              v{older.version} — {older.task_name || "-"}
            </div>
            <TaskFigure
              taskId={older.task_id}
              qid={older.qid ?? ""}
              className="w-full rounded"
            />
          </div>
          <div className="bg-base-100 rounded-lg p-2">
            <div className="text-xs text-base-content/60 mb-1">
              v{newer.version} — {newer.task_name || "-"}
            </div>
            <TaskFigure
              taskId={newer.task_id}
              qid={newer.qid ?? ""}
              className="w-full rounded"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
