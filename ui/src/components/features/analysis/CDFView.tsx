"use client";

import { useMemo, useEffect, useCallback } from "react";

import Select from "react-select";

import { useListChipsSummary } from "@/client/chip/chip";
import { useGetChipMetrics } from "@/client/metrics/metrics";
import { PlotCard } from "@/components/charts/PlotCard";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DataTable } from "@/components/ui/DataTable";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { useCSVExport } from "@/hooks/useCSVExport";
import { useMetricsConfig, type MetricConfig } from "@/hooks/useMetricsConfig";
import { useCDFUrlState } from "@/hooks/useUrlState";

interface CumulativeDataPoint {
  value: number;
  cdf: number;
  survivalFunction: number;
  qid: string;
}

type MetricType = "qubit" | "coupling";

// Helper function to check if a metric uses percentage unit
function isPercentageMetric(unit: string | undefined): boolean {
  return unit === "%";
}

export function CDFView() {
  // URL state management
  const {
    selectedChip,
    timeRange,
    selectionMode,
    selectedParameters,
    showAsErrorRate,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setSelectedParameters,
    setShowAsErrorRate,
    isInitialized,
  } = useCDFUrlState();

  // Load metrics configuration from backend
  const {
    qubitMetrics,
    couplingMetrics,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  // Determine current metric type based on first selected parameter
  const currentMetricType: MetricType = useMemo(() => {
    if (selectedParameters.length === 0) return "qubit";
    const firstParam = selectedParameters[0];
    if (couplingMetrics.some((m) => m.key === firstParam)) {
      return "coupling";
    }
    return "qubit";
  }, [couplingMetrics, selectedParameters]);

  // Available parameter options for selection
  const availableParameters = useMemo(() => {
    if (qubitMetrics.length === 0 && couplingMetrics.length === 0) {
      return [];
    }

    // Group options by type
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

  // Get current metric configurations for selected parameters
  const selectedMetricConfigs = useMemo(() => {
    const configs: Record<string, MetricConfig> = {};
    selectedParameters.forEach((param) => {
      const config =
        qubitMetrics.find((m) => m.key === param) ||
        couplingMetrics.find((m) => m.key === param);
      if (config) {
        configs[param] = config;
      }
    });
    return configs;
  }, [selectedParameters, qubitMetrics, couplingMetrics]);

  // Check if any selected parameter has best mode supported
  const isBestModeSupported = useMemo(() => {
    return selectedParameters.some((param) => {
      const config = selectedMetricConfigs[param];
      return config?.evaluationMode !== "none";
    });
  }, [selectedParameters, selectedMetricConfigs]);

  // Auto-switch to latest mode when no metrics support best mode
  useEffect(() => {
    if (!isBestModeSupported && selectionMode === "best") {
      setSelectionMode("latest");
    }
  }, [isBestModeSupported, selectionMode, setSelectionMode]);

  // Set default parameters when metrics load
  useEffect(() => {
    if (qubitMetrics.length === 0) return;

    // Check if current parameters are valid
    const allMetrics = [...qubitMetrics, ...couplingMetrics];
    const validParams = selectedParameters.filter((p) =>
      allMetrics.some((m) => m.key === p),
    );

    if (validParams.length === 0 && qubitMetrics.length > 0) {
      // Set default: t1 if available
      const t1Metric = qubitMetrics.find((m) => m.key === "t1");
      if (t1Metric) {
        setSelectedParameters(["t1"]);
      } else {
        setSelectedParameters([qubitMetrics[0].key]);
      }
    } else if (validParams.length !== selectedParameters.length) {
      setSelectedParameters(validParams);
    }
  }, [
    qubitMetrics,
    couplingMetrics,
    selectedParameters,
    setSelectedParameters,
  ]);

  // Fetch chips data
  const { data: chipsResponse } = useListChipsSummary();

  // Set default chip on mount
  useEffect(() => {
    if (
      !selectedChip &&
      chipsResponse?.data?.chips &&
      chipsResponse.data.chips.length > 0
    ) {
      const sortedChips = [...chipsResponse.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });

      if (sortedChips.length > 0 && sortedChips[0]?.chip_id) {
        setSelectedChip(sortedChips[0].chip_id);
      }
    }
  }, [selectedChip, chipsResponse, setSelectedChip]);

  // Convert time range to hours
  const withinHours = useMemo(() => {
    switch (timeRange) {
      case "1d":
        return 24;
      case "7d":
        return 24 * 7;
      case "30d":
        return 24 * 30;
      default:
        return 24 * 7;
    }
  }, [timeRange]);

  // Fetch metrics data using the same API as histogram/metrics pages
  const {
    data: metricsData,
    isLoading,
    isError,
    error,
  } = useGetChipMetrics(
    selectedChip,
    {
      within_hours: withinHours,
      selection_mode: selectionMode,
    },
    {
      query: {
        enabled: !!selectedChip,
        staleTime: 30000,
      },
    },
  );

  // Process data for CDF visualization
  const processedDataByParameter = useMemo(() => {
    if (!metricsData?.data) {
      return {};
    }

    const results: Record<string, any> = {};

    selectedParameters.forEach((paramKey) => {
      const config = selectedMetricConfigs[paramKey];
      if (!config) return;

      const isCoupling = couplingMetrics.some((m) => m.key === paramKey);
      const metricsSource = isCoupling
        ? metricsData.data.coupling_metrics
        : metricsData.data.qubit_metrics;

      if (!metricsSource) return;

      const rawData = metricsSource[paramKey as keyof typeof metricsSource];
      if (!rawData) return;

      const allValues: { value: number; qid: string }[] = [];

      Object.entries(rawData).forEach(
        ([entityId, metricValue]: [string, any]) => {
          const value = metricValue?.value;
          if (
            value === null ||
            value === undefined ||
            typeof value !== "number"
          ) {
            return;
          }

          // Apply scale from config
          let scaledValue = value * config.scale;

          // For percentage metrics, convert to error rate if needed
          if (isPercentageMetric(config.unit)) {
            if (showAsErrorRate) {
              scaledValue = 100 - scaledValue;
            }
          }

          // Format entity ID
          const formattedId = isCoupling
            ? entityId
            : entityId.startsWith("Q")
              ? entityId
              : `Q${entityId.padStart(2, "0")}`;

          allValues.push({ qid: formattedId, value: scaledValue });
        },
      );

      if (allValues.length === 0) {
        results[paramKey] = {
          plotData: [],
          tableData: [],
          median: null,
          mean: null,
          percentile10: null,
          percentile90: null,
        };
        return;
      }

      // Sort values for CDF calculation (always ascending)
      const sortedValues = [...allValues].sort((a, b) => a.value - b.value);

      // Calculate CDF
      const cdfData: CumulativeDataPoint[] = sortedValues.map(
        (item, index) => ({
          value: item.value,
          cdf: (index + 1) / sortedValues.length,
          survivalFunction: 1 - (index + 1) / sortedValues.length,
          qid: item.qid,
        }),
      );

      // Calculate statistics
      const valuesOnly = sortedValues.map((item) => item.value);
      const medianValue =
        valuesOnly.length % 2 === 1
          ? valuesOnly[Math.floor(valuesOnly.length / 2)]
          : (valuesOnly[Math.floor(valuesOnly.length / 2) - 1] +
              valuesOnly[Math.floor(valuesOnly.length / 2)]) /
            2;
      const meanValue =
        valuesOnly.reduce((sum, val) => sum + val, 0) / valuesOnly.length;

      const getPercentile = (values: number[], p: number): number => {
        if (values.length === 0) return 0;
        if (values.length === 1) return values[0];
        const index = (values.length - 1) * p;
        const lower = Math.floor(index);
        const upper = Math.ceil(index);
        const weight = index - lower;
        return values[lower] * (1 - weight) + values[upper] * weight;
      };

      const percentile10Value = getPercentile(valuesOnly, 0.1);
      const percentile90Value = getPercentile(valuesOnly, 0.9);

      // Create step plot data for CDF
      const xValues: number[] = [];
      const yValues: number[] = [];

      cdfData.forEach((point, index) => {
        if (index === 0) {
          xValues.push(point.value);
          yValues.push(0);
        }
        xValues.push(point.value);
        yValues.push(point.cdf);
      });

      const plotTrace = {
        x: xValues,
        y: yValues,
        type: "scatter" as const,
        mode: "lines" as const,
        line: {
          shape: "hv" as const,
          width: 2,
        },
        name: config.title,
        hovertemplate:
          "Value: %{x:.4f}<br>" +
          "P(X ≤ value): %{y:.2%}" +
          "<br>" +
          "<extra></extra>",
      };

      // Median line
      const medianTrace = {
        x: [medianValue, medianValue],
        y: [0, 1],
        type: "scatter" as const,
        mode: "lines" as const,
        line: {
          color: "red",
          width: 2,
          dash: "dash" as const,
        },
        name: `Median: ${medianValue.toFixed(4)}`,
        hovertemplate: "Median: %{x:.4f}<br>" + "<extra></extra>",
      };

      // Percentile lines
      const p10Trace = {
        x: [percentile10Value, percentile10Value],
        y: [0, 1],
        type: "scatter" as const,
        mode: "lines" as const,
        line: {
          color: "orange",
          width: 1,
          dash: "dot" as const,
        },
        name: `P10: ${percentile10Value.toFixed(4)}`,
        hovertemplate: "10th Percentile: %{x:.4f}<br><extra></extra>",
      };

      const p90Trace = {
        x: [percentile90Value, percentile90Value],
        y: [0, 1],
        type: "scatter" as const,
        mode: "lines" as const,
        line: {
          color: "orange",
          width: 1,
          dash: "dot" as const,
        },
        name: `P90: ${percentile90Value.toFixed(4)}`,
        hovertemplate: "90th Percentile: %{x:.4f}<br><extra></extra>",
      };

      results[paramKey] = {
        plotData: [plotTrace, medianTrace, p10Trace, p90Trace],
        tableData: cdfData,
        median: medianValue,
        mean: meanValue,
        percentile10: percentile10Value,
        percentile90: percentile90Value,
      };
    });

    return results;
  }, [
    metricsData,
    selectedParameters,
    selectedMetricConfigs,
    couplingMetrics,
    showAsErrorRate,
  ]);

  // Primary parameter data
  const primaryParameter = selectedParameters[0];
  const primaryData = useMemo(
    () =>
      processedDataByParameter[primaryParameter] || {
        plotData: [],
        tableData: [],
        median: null,
        mean: null,
        percentile10: null,
        percentile90: null,
      },
    [processedDataByParameter, primaryParameter],
  );

  // Create combined table data for all selected parameters
  const combinedTableData = useMemo(() => {
    if (selectedParameters.length === 0) return [];

    // Collect all entity IDs from all parameters
    const entityMap = new Map<string, Record<string, number | null>>();

    selectedParameters.forEach((param) => {
      const data = processedDataByParameter[param];
      if (!data?.tableData) return;

      data.tableData.forEach((item: CumulativeDataPoint) => {
        if (!entityMap.has(item.qid)) {
          entityMap.set(item.qid, { qid: item.qid } as any);
        }
        const row = entityMap.get(item.qid)!;
        row[param] = item.value;
      });
    });

    // Convert to array and sort by entity ID
    return Array.from(entityMap.values()).sort((a, b) => {
      const aQid = String(a.qid);
      const bQid = String(b.qid);
      // Natural sort for QIDs
      const aNum = parseInt(aQid.replace(/\D/g, "")) || 0;
      const bNum = parseInt(bQid.replace(/\D/g, "")) || 0;
      return aNum - bNum;
    });
  }, [selectedParameters, processedDataByParameter]);

  // Create combined plot data when multiple parameters are selected
  const combinedPlotData = useMemo(() => {
    const colors: Record<string, string> = {
      t1: "#3b82f6",
      t2_echo: "#f97316",
      t2_star: "#10b981",
      gate_fidelity: "#ef4444",
      x90_fidelity: "#8b5cf6",
      x180_fidelity: "#f59e0b",
      zx90_fidelity: "#84cc16",
      bell_state_fidelity: "#ec4899",
      readout_fidelity: "#06b6d4",
    };

    if (selectedParameters.length > 1) {
      return selectedParameters.flatMap((param) => {
        const data = processedDataByParameter[param];
        if (!data || !data.plotData || data.plotData.length === 0) return [];

        return data.plotData.map((trace: any, idx: number) => {
          const config = selectedMetricConfigs[param];
          if (idx === 0) {
            return {
              ...trace,
              line: {
                ...trace.line,
                color: colors[param] || "#6b7280",
              },
              name: config?.title || param,
            };
          } else if (idx === 1) {
            // Median line
            const unit = isPercentageMetric(config?.unit) ? "%" : "";
            return {
              ...trace,
              line: {
                ...trace.line,
                color: colors[param] || "#6b7280",
                dash: "dash",
              },
              name: `${config?.title || param} median: ${data.median?.toFixed(2)}${unit}`,
              showlegend: true,
            };
          } else {
            return { ...trace, showlegend: false };
          }
        });
      });
    }

    // Single parameter - add color
    if (primaryData.plotData.length > 0) {
      return primaryData.plotData.map((trace: any, idx: number) => {
        if (idx === 0) {
          return {
            ...trace,
            line: {
              ...trace.line,
              color: colors[primaryParameter] || "#3b82f6",
            },
          };
        }
        return trace;
      });
    }

    return [];
  }, [
    selectedParameters,
    processedDataByParameter,
    primaryData,
    primaryParameter,
    selectedMetricConfigs,
  ]);

  // Determine if we have percentage metrics selected
  const hasPercentageMetrics = useMemo(() => {
    return selectedParameters.some((param) => {
      const config = selectedMetricConfigs[param];
      return isPercentageMetric(config?.unit);
    });
  }, [selectedParameters, selectedMetricConfigs]);

  // Layout configuration
  const layout = useMemo(() => {
    const primaryConfig = selectedMetricConfigs[primaryParameter];
    const isCoupling = couplingMetrics.some((m) => m.key === primaryParameter);

    return {
      title: {
        text:
          selectedParameters.length > 1
            ? "Cumulative Distribution - Multiple Parameters"
            : `Cumulative Distribution - ${primaryConfig?.title || primaryParameter}`,
        font: { size: 18 },
      },
      xaxis: {
        title:
          selectedParameters.length > 1
            ? "Parameter Value"
            : `${primaryConfig?.title || primaryParameter} (${
                isPercentageMetric(primaryConfig?.unit)
                  ? showAsErrorRate
                    ? "Error Rate %"
                    : "%"
                  : primaryConfig?.unit || ""
              })`,
        gridcolor: "#e5e7eb",
        showgrid: true,
        zeroline: false,
        type:
          hasPercentageMetrics && showAsErrorRate
            ? ("log" as const)
            : ("linear" as const),
        tickformat: hasPercentageMetrics && showAsErrorRate ? ".1e" : undefined,
      },
      yaxis: {
        title: "Cumulative Probability P(X ≤ value)",
        gridcolor: "#e5e7eb",
        showgrid: true,
        zeroline: false,
        range: [0, 1],
      },
      hovermode: "closest" as const,
      showlegend: true,
      legend: {
        x: 0.02,
        y: 0.98,
        bgcolor: "rgba(255, 255, 255, 0.8)",
        bordercolor: "#e5e7eb",
        borderwidth: 1,
      },
      margin: { t: 60, r: 50, b: 100, l: 80 },
      plot_bgcolor: "#ffffff",
      paper_bgcolor: "#ffffff",
      annotations: primaryData.tableData
        ? [
            {
              text: `Time range: ${timeRange === "1d" ? "Last 1 Day" : timeRange === "7d" ? "Last 7 Days" : "Last 30 Days"} | Mode: ${selectionMode === "latest" ? "Latest" : "Best"}<br>Sample size: ${primaryData.tableData.length} ${isCoupling ? "coupling pairs" : "qubits"}`,
              showarrow: false,
              xref: "paper" as const,
              yref: "paper" as const,
              x: 0.02,
              y: -0.12,
              xanchor: "left" as const,
              yanchor: "top" as const,
              font: { size: 11, color: "#666" },
            },
          ]
        : [],
    };
  }, [
    selectedParameters,
    primaryParameter,
    selectedMetricConfigs,
    couplingMetrics,
    showAsErrorRate,
    hasPercentageMetrics,
    timeRange,
    selectionMode,
    primaryData,
  ]);

  // CSV Export
  const { exportToCSV } = useCSVExport();

  const handleExportCSV = useCallback(() => {
    if (!primaryData.tableData || primaryData.tableData.length === 0) return;

    const isCoupling = couplingMetrics.some((m) => m.key === primaryParameter);

    const headers = [
      "Entity_ID",
      "Value",
      "CDF",
      "Survival_Function",
      "Parameter",
      "Entity_Type",
      "Time_Range",
      "Selection_Mode",
      "Timestamp",
    ];
    const timestamp = new Date().toISOString();
    const rows = primaryData.tableData.map((row: CumulativeDataPoint) => [
      row.qid,
      String(row.value.toFixed(6)),
      String(row.cdf.toFixed(6)),
      String(row.survivalFunction.toFixed(6)),
      primaryParameter,
      isCoupling ? "coupling_pair" : "qubit",
      timeRange,
      selectionMode,
      timestamp,
    ]);

    const filename = `cdf_${primaryParameter}_${selectedChip}_${timeRange}_${selectionMode}_${timestamp
      .slice(0, 19)
      .replace(/[:-]/g, "")}.csv`;

    exportToCSV({ filename, headers, data: rows });
  }, [
    primaryData,
    primaryParameter,
    couplingMetrics,
    selectedChip,
    timeRange,
    selectionMode,
    exportToCSV,
  ]);

  // Handle metric type change
  const handleMetricTypeChange = useCallback(
    (newType: MetricType) => {
      const newMetrics = newType === "qubit" ? qubitMetrics : couplingMetrics;
      if (newMetrics.length > 0) {
        setSelectedParameters([newMetrics[0].key]);
      }
    },
    [qubitMetrics, couplingMetrics, setSelectedParameters],
  );

  // Error handling
  const handleRetry = useCallback(() => {
    window.location.reload();
  }, []);

  if (isConfigError) {
    return (
      <ErrorCard
        title="Failed to load metrics configuration"
        message="Could not load metrics configuration from server"
        onRetry={handleRetry}
      />
    );
  }

  if (isError) {
    return (
      <ErrorCard
        title="Failed to load cumulative data"
        message={(error as Error)?.message || "An unexpected error occurred"}
        onRetry={handleRetry}
      />
    );
  }

  if (!isInitialized || isConfigLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <QuantumLoader size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Controls Section */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body p-3 sm:p-4 gap-3 sm:gap-4">
          {/* Row 1: Main Controls */}
          <div className="flex flex-col gap-3 sm:gap-4">
            {/* Row 1a: Type + Chip + Parameters */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <div className="tabs tabs-boxed bg-base-200 h-8 sm:h-9">
                <button
                  className={`tab h-full ${currentMetricType === "qubit" ? "tab-active" : ""}`}
                  onClick={() => handleMetricTypeChange("qubit")}
                >
                  1Q
                </button>
                <button
                  className={`tab h-full ${currentMetricType === "coupling" ? "tab-active" : ""}`}
                  onClick={() => handleMetricTypeChange("coupling")}
                >
                  2Q
                </button>
              </div>

              <div className="w-28 sm:w-36">
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </div>

              {/* Parameter Selection - inline on mobile */}
              <div className="w-48 sm:w-80">
                <Select<{ value: string; label: string }, true>
                  isMulti
                  options={availableParameters}
                  value={selectedParameters
                    .map((p) => {
                      const config = selectedMetricConfigs[p];
                      return config ? { value: p, label: config.title } : null;
                    })
                    .filter(
                      (item): item is { value: string; label: string } =>
                        item !== null,
                    )}
                  onChange={(options) => {
                    const values = options
                      ? options.map((option) => option!.value)
                      : [];
                    setSelectedParameters(values);
                  }}
                  placeholder="Select parameters"
                  className="text-base-content"
                  styles={{
                    control: (base) => ({
                      ...base,
                      minHeight: "36px",
                      height: "auto",
                      borderRadius: "0.5rem",
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
            </div>

            {/* Row 1b: Time Range + Mode + Display Toggle + Export */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <div className="join h-8 sm:h-9">
                <button
                  className={`join-item btn btn-sm h-full ${timeRange === "1d" ? "btn-active" : ""}`}
                  onClick={() => setTimeRange("1d")}
                >
                  1D
                </button>
                <button
                  className={`join-item btn btn-sm h-full ${timeRange === "7d" ? "btn-active" : ""}`}
                  onClick={() => setTimeRange("7d")}
                >
                  7D
                </button>
                <button
                  className={`join-item btn btn-sm h-full ${timeRange === "30d" ? "btn-active" : ""}`}
                  onClick={() => setTimeRange("30d")}
                >
                  30D
                </button>
              </div>

              <div className="join h-8 sm:h-9">
                <button
                  className={`join-item btn btn-xs sm:btn-sm h-full ${selectionMode === "latest" ? "btn-active" : ""}`}
                  onClick={() => setSelectionMode("latest")}
                >
                  Latest
                </button>
                <button
                  className={`join-item btn btn-xs sm:btn-sm h-full ${selectionMode === "best" ? "btn-active" : ""} ${!isBestModeSupported ? "btn-disabled" : ""}`}
                  onClick={() => setSelectionMode("best")}
                  disabled={!isBestModeSupported}
                  title={
                    !isBestModeSupported
                      ? "Best mode not available"
                      : "Show best values"
                  }
                >
                  Best
                </button>
              </div>

              {hasPercentageMetrics && (
                <label className="cursor-pointer flex items-center gap-1 sm:gap-2 h-8 sm:h-9">
                  <span className="text-xs sm:text-sm">Fidelity</span>
                  <input
                    type="checkbox"
                    className="toggle toggle-primary toggle-xs sm:toggle-sm"
                    checked={showAsErrorRate}
                    onChange={(e) => setShowAsErrorRate(e.target.checked)}
                  />
                  <span className="text-xs sm:text-sm">Error</span>
                </label>
              )}

              <button
                className="btn btn-outline btn-xs sm:btn-sm h-8 sm:h-9 ml-auto sm:ml-0"
                onClick={handleExportCSV}
                disabled={
                  !primaryData.tableData || primaryData.tableData.length === 0
                }
              >
                Export
              </button>
            </div>
          </div>

          {/* Statistics Display */}
          {selectedParameters.length > 0 && (
            <div className="mt-2 sm:mt-4 space-y-2">
              {selectedParameters.map((param) => {
                const data = processedDataByParameter[param];
                const config = selectedMetricConfigs[param];
                if (!data || data.median === null || !config) return null;

                const colors: Record<string, string> = {
                  t1: "text-blue-600",
                  t2_echo: "text-orange-600",
                  t2_star: "text-green-600",
                  gate_fidelity: "text-red-600",
                  x90_fidelity: "text-violet-600",
                  x180_fidelity: "text-amber-600",
                  zx90_fidelity: "text-lime-600",
                  bell_state_fidelity: "text-pink-600",
                  readout_fidelity: "text-cyan-600",
                };

                const isPercent = isPercentageMetric(config.unit);
                const unit = isPercent ? "%" : ` ${config.unit}`;
                const colorClass = colors[param] || "text-gray-600";

                const formatValue = (value: number) => {
                  if (isPercent && showAsErrorRate) {
                    return value.toExponential(1);
                  }
                  return value.toFixed(2);
                };

                return (
                  <div key={param}>
                    {/* Mobile: Grid layout */}
                    <div className="sm:hidden">
                      <div className={`text-xs font-medium mb-1 ${colorClass}`}>
                        {config.title}
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="bg-base-200 rounded-lg p-2 text-center">
                          <div className="text-xs text-base-content/60">N</div>
                          <div className="text-sm font-bold text-success">
                            {data.tableData.length}
                          </div>
                        </div>
                        <div className="bg-base-200 rounded-lg p-2 text-center">
                          <div className="text-xs text-base-content/60">
                            Median
                          </div>
                          <div className="text-sm font-bold text-primary">
                            {formatValue(data.median)}
                            {unit}
                          </div>
                        </div>
                        <div className="bg-base-200 rounded-lg p-2 text-center">
                          <div className="text-xs text-base-content/60">
                            Mean
                          </div>
                          <div className="text-sm font-bold text-secondary">
                            {formatValue(data.mean)}
                            {unit}
                          </div>
                        </div>
                        <div className="bg-base-200 rounded-lg p-2 text-center col-span-3">
                          <div className="text-xs text-base-content/60">
                            P10 / P90
                          </div>
                          <div className="text-sm font-bold text-accent">
                            {formatValue(data.percentile10!)}
                            {unit} / {formatValue(data.percentile90!)}
                            {unit}
                          </div>
                        </div>
                      </div>
                    </div>
                    {/* Desktop: Stats component */}
                    <div className="stats shadow w-full hidden sm:inline-grid">
                      <div className="stat py-2 flex-1">
                        <div className="stat-title text-xs">Parameter</div>
                        <div className={`stat-value text-sm ${colorClass}`}>
                          {config.title}
                        </div>
                      </div>
                      <div className="stat py-2 flex-1">
                        <div className="stat-title text-xs">N_valid</div>
                        <div className="stat-value text-success text-sm">
                          {data.tableData.length}
                        </div>
                      </div>
                      <div className="stat py-2 flex-1">
                        <div className="stat-title text-xs">Median</div>
                        <div className="stat-value text-primary text-sm">
                          {formatValue(data.median)}
                          {unit}
                        </div>
                      </div>
                      <div className="stat py-2 flex-1">
                        <div className="stat-title text-xs">Mean</div>
                        <div className="stat-value text-secondary text-sm">
                          {formatValue(data.mean)}
                          {unit}
                        </div>
                      </div>
                      <div className="stat py-2 flex-1">
                        <div className="stat-title text-xs">10th %ile</div>
                        <div className="stat-value text-accent text-sm">
                          {formatValue(data.percentile10!)}
                          {unit}
                        </div>
                      </div>
                      <div className="stat py-2 flex-1">
                        <div className="stat-title text-xs">90th %ile</div>
                        <div className="stat-value text-accent text-sm">
                          {formatValue(data.percentile90!)}
                          {unit}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Plot Section */}
      <PlotCard
        plotData={combinedPlotData}
        layout={layout}
        isLoading={isLoading}
        title="Cumulative Distribution Function"
      />

      {/* Data Table */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          <DataTable
            title="Data Points"
            data={combinedTableData}
            columns={[
              { key: "qid", label: "Entity ID", sortable: true },
              ...selectedParameters.map((param) => {
                const config = selectedMetricConfigs[param];
                const isPercent = isPercentageMetric(config?.unit);
                const unit = isPercent ? "%" : ` ${config?.unit || ""}`;
                return {
                  key: param,
                  label: `${config?.title || param} (${unit.trim()})`,
                  sortable: true,
                  render: (v: number | null | undefined) =>
                    v != null ? v.toFixed(4) : "-",
                };
              }),
            ]}
            pageSize={10}
          />
        </div>
      </div>
    </div>
  );
}
