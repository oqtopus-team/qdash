"use client";

import { useMemo, useEffect } from "react";

import Select from "react-select";

import type { ParameterKey, TagKey } from "@/types/analysis";
import type { Layout } from "plotly.js";

import { useListChips } from "@/client/chip/chip";
import { useListTags } from "@/client/tag/tag";
import { useGetTimeseriesTaskResults } from "@/client/task-result/task-result";
import { PlotCard } from "@/components/charts/PlotCard";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { TagSelector } from "@/components/selectors/TagSelector";
import { DataTable } from "@/components/ui/DataTable";
import { DateTimePicker } from "@/components/ui/DateTimePicker";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { useCSVExport } from "@/hooks/useCSVExport";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useTimeRange } from "@/hooks/useTimeRange";
import { useAnalysisUrlState } from "@/hooks/useUrlState";

// Color palette for secondary axis traces
const SECONDARY_AXIS_COLORS = [
  "#e377c2", // pink
  "#7f7f7f", // gray
  "#bcbd22", // olive
  "#17becf", // cyan
];

export function TimeSeriesView() {
  // URL state management
  const {
    selectedChip,
    selectedParameter,
    selectedParameters,
    selectedTag,
    setSelectedChip,
    setSelectedParameter,
    setSelectedParameters,
    setSelectedTag,
    isInitialized,
  } = useAnalysisUrlState();

  // Secondary axis state (derived from URL state)
  const secondaryParameter =
    selectedParameters.length > 0 ? selectedParameters[0] : null;
  const showSecondaryAxis = secondaryParameter !== null;
  // Time range management with manual refresh
  const {
    timeRange,
    updateStartAt,
    updateEndAt,
    toggleStartAtLock,
    toggleEndAtLock,
    refreshTimeRange,
    getLockStatusDescription,
  } = useTimeRange({ initialDays: 7 });

  // Load metrics configuration from backend
  const {
    qubitMetrics,
    couplingMetrics,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  // Available parameter options for selection (grouped by type)
  const availableParameters = useMemo(() => {
    if (qubitMetrics.length === 0 && couplingMetrics.length === 0) {
      return [];
    }

    return [
      {
        label: "1Q Metrics",
        options: qubitMetrics.map((metric) => ({
          value: metric.key,
          label: metric.title,
        })),
      },
      {
        label: "2Q Metrics",
        options: couplingMetrics.map((metric) => ({
          value: metric.key,
          label: metric.title,
        })),
      },
    ];
  }, [qubitMetrics, couplingMetrics]);

  // Get current metric configuration for selected parameter
  const currentMetricConfig = useMemo(() => {
    return (
      qubitMetrics.find((m) => m.key === selectedParameter) ||
      couplingMetrics.find((m) => m.key === selectedParameter)
    );
  }, [qubitMetrics, couplingMetrics, selectedParameter]);

  // Get secondary metric configuration
  const secondaryMetricConfig = useMemo(() => {
    if (!secondaryParameter) return null;
    return (
      qubitMetrics.find((m) => m.key === secondaryParameter) ||
      couplingMetrics.find((m) => m.key === secondaryParameter)
    );
  }, [qubitMetrics, couplingMetrics, secondaryParameter]);

  // Available parameters for secondary axis (exclude primary)
  const availableSecondaryParameters = useMemo(() => {
    if (qubitMetrics.length === 0 && couplingMetrics.length === 0) {
      return [];
    }

    return [
      {
        label: "1Q Metrics",
        options: qubitMetrics
          .filter((metric) => metric.key !== selectedParameter)
          .map((metric) => ({
            value: metric.key,
            label: metric.title,
          })),
      },
      {
        label: "2Q Metrics",
        options: couplingMetrics
          .filter((metric) => metric.key !== selectedParameter)
          .map((metric) => ({
            value: metric.key,
            label: metric.title,
          })),
      },
    ].filter((group) => group.options.length > 0);
  }, [qubitMetrics, couplingMetrics, selectedParameter]);

  // Fetch chips data for default selection
  const { data: chipsResponse } = useListChips();

  // Fetch tags
  const { data: tagsResponse, isLoading: isLoadingTags } = useListTags();

  // Set default chip when URL is initialized and no chip is selected
  useEffect(() => {
    if (
      isInitialized &&
      !selectedChip &&
      chipsResponse?.data?.chips &&
      chipsResponse.data.chips.length > 0
    ) {
      // Sort chips by installation date and select the most recent one
      const sortedChips = [...chipsResponse.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [isInitialized, selectedChip, chipsResponse, setSelectedChip]);

  // Set default parameter when metrics load
  useEffect(() => {
    if (qubitMetrics.length === 0) return;

    // Check if current parameter is valid
    const allMetrics = [...qubitMetrics, ...couplingMetrics];
    const isCurrentValid = allMetrics.some((m) => m.key === selectedParameter);

    if (!isCurrentValid && allMetrics.length > 0) {
      // Set default: t1 if available, otherwise first metric
      const t1Metric = qubitMetrics.find((m) => m.key === "t1");
      if (t1Metric) {
        setSelectedParameter("t1");
      } else {
        setSelectedParameter(allMetrics[0].key);
      }
    }
  }, [qubitMetrics, couplingMetrics, selectedParameter, setSelectedParameter]);

  // Fetch time series data directly (Analysis page doesn't have qubitId)
  const {
    data: timeseriesResponse,
    isLoading: isLoadingTimeseries,
    error,
    refetch,
  } = useGetTimeseriesTaskResults(
    {
      chip_id: selectedChip,
      parameter: selectedParameter as ParameterKey,
      tag: selectedTag as TagKey,
      start_at: timeRange.startAt,
      end_at: timeRange.endAt,
    },
    {
      query: {
        enabled: Boolean(selectedChip && selectedParameter && selectedTag),
        staleTime: 30000, // Keep data fresh for 30 seconds
      },
    },
  );

  // Fetch secondary parameter data
  const {
    data: secondaryTimeseriesResponse,
    isLoading: isLoadingSecondary,
    error: secondaryError,
    refetch: refetchSecondary,
  } = useGetTimeseriesTaskResults(
    {
      chip_id: selectedChip,
      parameter: secondaryParameter as ParameterKey,
      tag: selectedTag as TagKey,
      start_at: timeRange.startAt,
      end_at: timeRange.endAt,
    },
    {
      query: {
        enabled: Boolean(selectedChip && secondaryParameter && selectedTag),
        staleTime: 30000,
      },
    },
  );

  // Process primary data
  const { tableData, primaryTraces, metadata } = useMemo(() => {
    if (!timeseriesResponse?.data?.data) {
      return {
        tableData: [],
        primaryTraces: [],
        metadata: { unit: "a.u.", description: "" },
      };
    }

    // Table data processing
    const tableRows: any[] = [];
    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          dataPoints.forEach((point: any) => {
            tableRows.push({
              qid,
              time: point.calibrated_at || "",
              parameter: selectedParameter,
              value: point.value || 0,
              error: point.error,
              unit: point.unit || "a.u.",
            });
          });
        }
      },
    );

    // Sort by QID and time
    const sortedTableData = tableRows.sort((a, b) => {
      const qidCompare = parseInt(a.qid) - parseInt(b.qid);
      if (qidCompare !== 0) return qidCompare;
      return a.time.localeCompare(b.time);
    });

    // Plot data processing
    const qidData: Record<
      string,
      { x: string[]; y: number[]; error: number[] }
    > = {};

    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          qidData[qid] = {
            x: dataPoints.map((point: any) => point.calibrated_at || ""),
            y: dataPoints.map((point: any) => {
              const value = point.value;
              if (typeof value === "number") return value;
              if (typeof value === "string") return Number(value) || 0;
              return 0;
            }),
            error: dataPoints.map((point: any) => point.error || 0),
          };
        }
      },
    );

    // Sort QIDs numerically and create traces
    const sortedQids = Object.keys(qidData).sort(
      (a, b) => parseInt(a) - parseInt(b),
    );
    const traces = sortedQids.map((qid) => ({
      x: qidData[qid].x,
      y: qidData[qid].y,
      error_y: {
        type: "data" as const,
        array: qidData[qid].error as Plotly.Datum[],
        visible: true,
      },
      type: "scatter" as const,
      mode: "lines+markers" as const,
      name: `${currentMetricConfig?.title || selectedParameter} Q${qid}`,
      legendgroup: "primary",
      yaxis: "y",
      line: { shape: "linear" as const, width: 2 },
      marker: { size: 8, symbol: "circle" },
      hovertemplate:
        `<b>${currentMetricConfig?.title || selectedParameter}</b><br>` +
        "Time: %{x}<br>Value: %{y:.6g}" +
        (qidData[qid].error[0] ? "<br>Error: ±%{error_y.array:.6g}" : "") +
        "<br>QID: " +
        qid +
        "<extra></extra>",
    }));

    // Extract metadata
    const firstEntry = Object.entries(timeseriesResponse.data.data)[0];
    let metaInfo = { unit: "a.u.", description: "" };
    if (
      firstEntry &&
      Array.isArray(firstEntry[1]) &&
      firstEntry[1].length > 0
    ) {
      const firstPoint = firstEntry[1][0] as any;
      metaInfo = {
        unit: firstPoint.unit || "a.u.",
        description: firstPoint.description || "",
      };
    }

    return {
      tableData: sortedTableData,
      primaryTraces: traces,
      metadata: metaInfo,
    };
  }, [timeseriesResponse, selectedParameter, currentMetricConfig]);

  // Process secondary data
  const { secondaryTableData, secondaryTraces, secondaryMetadata } =
    useMemo(() => {
      if (!secondaryTimeseriesResponse?.data?.data || !secondaryParameter) {
        return {
          secondaryTableData: [],
          secondaryTraces: [],
          secondaryMetadata: { unit: "a.u.", description: "" },
        };
      }

      // Table data processing
      const tableRows: any[] = [];
      Object.entries(secondaryTimeseriesResponse.data.data).forEach(
        ([qid, dataPoints]) => {
          if (Array.isArray(dataPoints)) {
            dataPoints.forEach((point: any) => {
              tableRows.push({
                qid,
                time: point.calibrated_at || "",
                parameter: secondaryParameter,
                value: point.value || 0,
                error: point.error,
                unit: point.unit || "a.u.",
              });
            });
          }
        },
      );

      // Sort by QID and time
      const sortedTableData = tableRows.sort((a, b) => {
        const qidCompare = parseInt(a.qid) - parseInt(b.qid);
        if (qidCompare !== 0) return qidCompare;
        return a.time.localeCompare(b.time);
      });

      // Plot data processing
      const qidData: Record<
        string,
        { x: string[]; y: number[]; error: number[] }
      > = {};

      Object.entries(secondaryTimeseriesResponse.data.data).forEach(
        ([qid, dataPoints]) => {
          if (Array.isArray(dataPoints)) {
            qidData[qid] = {
              x: dataPoints.map((point: any) => point.calibrated_at || ""),
              y: dataPoints.map((point: any) => {
                const value = point.value;
                if (typeof value === "number") return value;
                if (typeof value === "string") return Number(value) || 0;
                return 0;
              }),
              error: dataPoints.map((point: any) => point.error || 0),
            };
          }
        },
      );

      // Sort QIDs numerically and create traces for secondary axis
      const sortedQids = Object.keys(qidData).sort(
        (a, b) => parseInt(a) - parseInt(b),
      );
      const traces = sortedQids.map((qid, index) => ({
        x: qidData[qid].x,
        y: qidData[qid].y,
        error_y: {
          type: "data" as const,
          array: qidData[qid].error as Plotly.Datum[],
          visible: true,
          color: SECONDARY_AXIS_COLORS[index % SECONDARY_AXIS_COLORS.length],
        },
        type: "scatter" as const,
        mode: "lines+markers" as const,
        name: `${secondaryMetricConfig?.title || secondaryParameter} Q${qid}`,
        legendgroup: "secondary",
        yaxis: "y2",
        line: {
          shape: "linear" as const,
          width: 2,
          dash: "dash" as const,
          color: SECONDARY_AXIS_COLORS[index % SECONDARY_AXIS_COLORS.length],
        },
        marker: {
          size: 8,
          symbol: "diamond",
          color: SECONDARY_AXIS_COLORS[index % SECONDARY_AXIS_COLORS.length],
        },
        hovertemplate:
          `<b>${secondaryMetricConfig?.title || secondaryParameter}</b><br>` +
          "Time: %{x}<br>Value: %{y:.6g}" +
          (qidData[qid].error[0] ? "<br>Error: ±%{error_y.array:.6g}" : "") +
          "<br>QID: " +
          qid +
          "<extra></extra>",
      }));

      // Extract metadata
      const firstEntry = Object.entries(
        secondaryTimeseriesResponse.data.data,
      )[0];
      let metaInfo = { unit: "a.u.", description: "" };
      if (
        firstEntry &&
        Array.isArray(firstEntry[1]) &&
        firstEntry[1].length > 0
      ) {
        const firstPoint = firstEntry[1][0] as any;
        metaInfo = {
          unit: firstPoint.unit || "a.u.",
          description: firstPoint.description || "",
        };
      }

      return {
        secondaryTableData: sortedTableData,
        secondaryTraces: traces,
        secondaryMetadata: metaInfo,
      };
    }, [
      secondaryTimeseriesResponse,
      secondaryParameter,
      secondaryMetricConfig,
    ]);

  // Combined plot data
  const plotData = useMemo(() => {
    return [...primaryTraces, ...secondaryTraces];
  }, [primaryTraces, secondaryTraces]);

  // Combined table data
  const combinedTableData = useMemo(() => {
    return [...tableData, ...secondaryTableData].sort((a, b) => {
      const qidCompare = parseInt(a.qid) - parseInt(b.qid);
      if (qidCompare !== 0) return qidCompare;
      return a.time.localeCompare(b.time);
    });
  }, [tableData, secondaryTableData]);

  // CSV export functionality
  const { exportTimeSeriesCSV } = useCSVExport();

  // Plot layout configuration with dual-axis support
  const layout = useMemo<Partial<Layout>>(() => {
    const baseLayout: Partial<Layout> = {
      title: {
        text: showSecondaryAxis
          ? `${currentMetricConfig?.title || selectedParameter} & ${secondaryMetricConfig?.title || secondaryParameter}`
          : `${currentMetricConfig?.title || selectedParameter} Time Series by QID`,
        font: { size: 24 },
      },
      xaxis: {
        title: "Time",
        type: "date",
        tickformat: "%Y-%m-%d %H:%M",
        gridcolor: "#eee",
        zeroline: false,
        domain: showSecondaryAxis ? [0, 0.92] : [0, 1],
      },
      yaxis: {
        title: `${currentMetricConfig?.title || metadata.description} [${currentMetricConfig?.unit || metadata.unit}]`,
        type: "linear",
        gridcolor: "#eee",
        zeroline: false,
        exponentformat: "e" as const,
        titlefont: { color: "#1f77b4" },
        tickfont: { color: "#1f77b4" },
      },
      showlegend: true,
      legend: {
        x: 1.02,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(255, 255, 255, 0.8)",
      },
      autosize: true,
      margin: { l: 80, r: showSecondaryAxis ? 180 : 150, t: 100, b: 80 },
      plot_bgcolor: "white",
      paper_bgcolor: "white",
      hovermode: "closest",
    };

    // Add secondary y-axis if enabled
    if (showSecondaryAxis) {
      baseLayout.yaxis2 = {
        title: `${secondaryMetricConfig?.title || secondaryMetadata.description} [${secondaryMetricConfig?.unit || secondaryMetadata.unit}]`,
        type: "linear",
        overlaying: "y",
        side: "right",
        gridcolor: "rgba(227, 119, 194, 0.2)",
        zeroline: false,
        exponentformat: "e" as const,
        titlefont: { color: "#e377c2" },
        tickfont: { color: "#e377c2" },
      };
    }

    return baseLayout;
  }, [
    selectedParameter,
    secondaryParameter,
    metadata,
    secondaryMetadata,
    currentMetricConfig,
    secondaryMetricConfig,
    showSecondaryAxis,
  ]);

  const tags = tagsResponse?.data?.tags || [];

  // Handle CSV download
  const handleDownloadCSV = () => {
    exportTimeSeriesCSV(
      tableData,
      selectedParameter as ParameterKey,
      selectedChip,
      selectedTag as TagKey,
    );
  };

  // Manual refresh handler
  const handleRefresh = () => {
    refreshTimeRange();
    refetch();
    if (secondaryParameter) {
      refetchSecondary();
    }
  };

  // Add secondary axis handler
  const handleAddSecondaryAxis = (parameter: string) => {
    setSelectedParameters([parameter]);
  };

  // Remove secondary axis handler
  const handleRemoveSecondaryAxis = () => {
    setSelectedParameters([]);
  };

  // Table columns definition (includes parameter column when dual-axis)
  // NOTE: This must be before any conditional returns to maintain hooks order
  const tableColumns = useMemo(() => {
    const baseColumns = [
      { key: "qid", label: "QID", sortable: true, className: "text-left" },
      { key: "time", label: "Time", sortable: true, className: "text-left" },
    ];

    if (showSecondaryAxis) {
      baseColumns.push({
        key: "parameter",
        label: "Parameter",
        sortable: true,
        className: "text-left",
      });
    }

    return [
      ...baseColumns,
      {
        key: "value",
        label: "Value",
        sortable: false,
        className: "text-center",
        render: (value: any) =>
          typeof value === "number" ? value.toFixed(4) : String(value),
      },
      {
        key: "error",
        label: "Error",
        sortable: false,
        className: "text-center",
        render: (value: any) =>
          value !== undefined && value !== null ? `±${value.toFixed(4)}` : "-",
      },
      { key: "unit", label: "Unit", sortable: false, className: "text-center" },
    ];
  }, [showSecondaryAxis]);

  // Error handling
  if (isConfigError) {
    return (
      <ErrorCard
        title="Configuration Error"
        message="Failed to load metrics configuration"
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (error) {
    return (
      <ErrorCard
        title="Time Series Data Error"
        message={(error as Error)?.message || "Failed to load time series data"}
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (secondaryError) {
    return (
      <ErrorCard
        title="Secondary Axis Data Error"
        message={
          (secondaryError as Error)?.message ||
          "Failed to load secondary parameter data"
        }
        onRetry={() => window.location.reload()}
      />
    );
  }

  // Show loading state while config is loading
  if (isConfigLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <QuantumLoader size="lg" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-8">
      {/* Parameter Selection Card */}
      <div className="col-span-1 lg:col-span-3 card bg-base-100 shadow-xl rounded-xl p-4 sm:p-8 border border-base-300">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-4 sm:mb-6">
          <h2 className="text-lg sm:text-xl font-semibold flex items-center gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4 sm:w-5 sm:h-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 3v18h18"></path>
              <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
            </svg>
            Parameter Selection
          </h2>
          <button
            onClick={handleRefresh}
            disabled={isLoadingTimeseries || isLoadingTags}
            className="btn btn-xs sm:btn-sm btn-outline gap-1 sm:gap-2"
            title="Refresh data and time range"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3 h-3 sm:w-4 sm:h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M3 21v-5h5" />
            </svg>
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
          <div>
            <ChipSelector
              selectedChip={selectedChip}
              onChipSelect={setSelectedChip}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-base-content/70">
              Parameter
              <span className="ml-1 text-xs text-primary">(Left Y)</span>
            </label>
            <Select<{ value: string; label: string }, false>
              options={availableParameters}
              value={
                currentMetricConfig
                  ? {
                      value: currentMetricConfig.key,
                      label: currentMetricConfig.title,
                    }
                  : null
              }
              onChange={(option) => {
                if (option) {
                  setSelectedParameter(option.value);
                  // Clear secondary if it's the same as new primary
                  if (secondaryParameter === option.value) {
                    handleRemoveSecondaryAxis();
                  }
                }
              }}
              placeholder="Select parameter"
              className="text-base-content"
              styles={{
                control: (base) => ({
                  ...base,
                  minHeight: "38px",
                  height: "auto",
                  borderRadius: "0.5rem",
                  borderColor: "#1f77b4",
                  borderWidth: "2px",
                }),
                valueContainer: (base) => ({
                  ...base,
                  padding: "2px 8px",
                }),
                menu: (base) => ({
                  ...base,
                  zIndex: 50,
                }),
              }}
            />
          </div>
          <div>
            <TagSelector
              tags={tags}
              selectedTag={selectedTag}
              onTagSelect={setSelectedTag}
              disabled={isLoadingTags}
            />
          </div>
        </div>

        {/* Secondary Axis Section */}
        <div className="mt-4 pt-4 border-t border-base-300">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
            <div className="space-y-1">
              <label className="text-sm font-medium text-base-content/70">
                Secondary Parameter
                <span className="ml-1 text-xs" style={{ color: "#e377c2" }}>
                  (Right Y)
                </span>
              </label>
              {!showSecondaryAxis ? (
                <Select<{ value: string; label: string }, false>
                  options={availableSecondaryParameters}
                  value={null}
                  onChange={(option) => {
                    if (option) {
                      handleAddSecondaryAxis(option.value);
                    }
                  }}
                  placeholder="+ Add to compare..."
                  className="text-base-content"
                  isClearable={false}
                  styles={{
                    control: (base) => ({
                      ...base,
                      minHeight: "38px",
                      height: "auto",
                      borderRadius: "0.5rem",
                      borderStyle: "dashed",
                      borderColor: "#e377c2",
                    }),
                    valueContainer: (base) => ({
                      ...base,
                      padding: "2px 8px",
                    }),
                    menu: (base) => ({
                      ...base,
                      zIndex: 50,
                    }),
                    placeholder: (base) => ({
                      ...base,
                      color: "#e377c2",
                    }),
                  }}
                />
              ) : (
                <div className="flex items-center gap-2">
                  <Select<{ value: string; label: string }, false>
                    options={availableSecondaryParameters}
                    value={
                      secondaryMetricConfig
                        ? {
                            value: secondaryMetricConfig.key,
                            label: secondaryMetricConfig.title,
                          }
                        : null
                    }
                    onChange={(option) => {
                      if (option) {
                        handleAddSecondaryAxis(option.value);
                      }
                    }}
                    placeholder="Select parameter"
                    className="text-base-content flex-1"
                    styles={{
                      control: (base) => ({
                        ...base,
                        minHeight: "38px",
                        height: "auto",
                        borderRadius: "0.5rem",
                        borderColor: "#e377c2",
                        borderWidth: "2px",
                      }),
                      valueContainer: (base) => ({
                        ...base,
                        padding: "2px 8px",
                      }),
                      menu: (base) => ({
                        ...base,
                        zIndex: 50,
                      }),
                    }}
                  />
                  <button
                    onClick={handleRemoveSecondaryAxis}
                    className="btn btn-sm btn-ghost text-error"
                    title="Remove secondary axis"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="w-4 h-4"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                  {isLoadingSecondary && (
                    <span className="loading loading-spinner loading-sm text-secondary"></span>
                  )}
                </div>
              )}
            </div>
            {showSecondaryAxis && (
              <div className="sm:col-span-2 flex items-end pb-2">
                <div className="text-xs text-base-content/60 flex items-center gap-2">
                  <span
                    className="inline-block w-6 border-t-2 border-dashed"
                    style={{ borderColor: "#e377c2" }}
                  ></span>
                  <span>Dashed lines & diamond markers</span>
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="mt-4">
          <span className="text-sm font-medium mb-2 block">Time Range</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <DateTimePicker
                  label="From"
                  value={timeRange.startAt}
                  onChange={updateStartAt}
                  disabled={isLoadingTags}
                />
              </div>
              <button
                className={`btn btn-sm mt-8 gap-2 ${
                  timeRange.isStartAtLocked ? "btn-primary" : "btn-ghost"
                }`}
                onClick={toggleStartAtLock}
                title={
                  timeRange.isStartAtLocked
                    ? "Unlock start time"
                    : "Lock start time"
                }
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {timeRange.isStartAtLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </>
                  ) : (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </>
                  )}
                </svg>
                {timeRange.isStartAtLocked ? "Fixed" : "Auto"}
              </button>
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <DateTimePicker
                  label="To"
                  value={timeRange.endAt}
                  onChange={updateEndAt}
                  disabled={isLoadingTags}
                />
              </div>
              <button
                className={`btn btn-sm mt-8 gap-2 ${
                  timeRange.isEndAtLocked ? "btn-primary" : "btn-ghost"
                }`}
                onClick={toggleEndAtLock}
                title={
                  timeRange.isEndAtLocked ? "Unlock end time" : "Lock end time"
                }
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {timeRange.isEndAtLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </>
                  ) : (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </>
                  )}
                </svg>
                {timeRange.isEndAtLocked ? "Fixed" : "Auto"}
              </button>
            </div>
          </div>
          <div className="mt-2 text-xs text-base-content/70 flex items-center gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12" y2="8" />
            </svg>
            {getLockStatusDescription()}
          </div>
        </div>
      </div>

      {/* Plot Area */}
      <PlotCard
        title="Time Series Plot"
        icon={
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-6 h-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 3v18h18"></path>
            <path d="M3 12h18"></path>
            <path d="M12 3v18"></path>
          </svg>
        }
        isLoading={isLoadingTimeseries || isLoadingSecondary}
        hasData={Boolean(
          selectedChip &&
          selectedParameter &&
          selectedTag &&
          plotData.length > 0,
        )}
        emptyStateMessage={
          !selectedChip || !selectedParameter || !selectedTag
            ? "Select chip and parameters to visualize data"
            : "No data available for the selected parameters"
        }
        plotData={plotData}
        layout={layout}
        config={{
          toImageButtonOptions: {
            format: "svg",
            filename: "time_series",
            height: 600,
            width: 800,
            scale: 2,
          },
        }}
        className="col-span-1 lg:col-span-3"
      />

      {/* Data Table */}
      <DataTable
        title="Data Table"
        data={showSecondaryAxis ? combinedTableData : tableData}
        columns={tableColumns}
        searchable={true}
        searchPlaceholder="Filter by QID..."
        searchKey="qid"
        pageSize={50}
        actions={
          <button
            className="btn btn-sm btn-outline gap-2"
            onClick={handleDownloadCSV}
            disabled={
              (showSecondaryAxis ? combinedTableData : tableData).length === 0
            }
            title="Download all data as CSV"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download CSV
          </button>
        }
        className="col-span-1 lg:col-span-3"
        emptyMessage="Select parameters to view data table"
      />
    </div>
  );
}
