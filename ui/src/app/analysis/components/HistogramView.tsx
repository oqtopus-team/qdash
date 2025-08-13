"use client";

import { useMemo, useEffect, useCallback } from "react";
import {
  useListChips,
  useFetchLatestQubitTaskGroupedByChip,
  useFetchHistoricalQubitTaskGroupedByChip,
  useFetchLatestCouplingTaskGroupedByChip,
  useFetchHistoricalCouplingTaskGroupedByChip,
} from "@/client/chip/chip";
import { PlotCard } from "@/shared/components/PlotCard";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { DataTable } from "@/shared/components/DataTable";
import { useCSVExport } from "@/shared/hooks/useCSVExport";
import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import { useHistogramUrlState } from "@/app/hooks/useUrlState";
import Select from "react-select";

import {
  TASK_CONFIG,
  PARAMETER_CONFIG,
  OUTPUT_PARAM_NAMES,
  PARAMETER_GROUPS,
  getParameterRange,
  convertThresholdForDisplay,
  convertDisplayToThreshold,
  formatThresholdValue,
} from "@/shared/config/analysis";
import { naturalSortQIDs } from "@/shared/utils/qid";

interface HistogramDataPoint {
  qid: string;
  value: number;
  error?: number;
}

// Helper functions for threshold slider configuration
function getSliderMin(parameter: string, showAsErrorRate: boolean): number {
  const range = getParameterRange(parameter, showAsErrorRate);
  return range.min;
}

function getSliderMax(parameter: string, showAsErrorRate: boolean): number {
  const range = getParameterRange(parameter, showAsErrorRate);
  return range.max;
}

function getSliderStep(parameter: string, showAsErrorRate: boolean): number {
  const range = getParameterRange(parameter, showAsErrorRate);
  return range.step;
}

function getSliderValue(
  parameter: string,
  activeThreshold: number | undefined,
  showAsErrorRate: boolean,
): number {
  if (!activeThreshold) return 0;
  return convertThresholdForDisplay(
    parameter,
    activeThreshold,
    showAsErrorRate,
  );
}

function handleSliderChange(
  parameter: string,
  value: string,
  showAsErrorRate: boolean,
  setCustomThreshold: (threshold: number | null) => void,
): void {
  const numericValue = parseFloat(value);
  const thresholdValue = convertDisplayToThreshold(
    parameter,
    numericValue,
    showAsErrorRate,
  );
  setCustomThreshold(thresholdValue);
}

function formatSliderDisplay(
  parameter: string,
  activeThreshold: number | undefined,
  showAsErrorRate: boolean,
): string {
  if (!activeThreshold) return "0";
  return formatThresholdValue(parameter, activeThreshold, showAsErrorRate);
}

export function HistogramView() {
  // URL state management
  const {
    selectedChip,
    selectedDate,
    selectedParameter,
    showAsErrorRate,
    customThreshold,
    setSelectedChip,
    setSelectedDate,
    setSelectedParameter,
    setShowAsErrorRate,
    setCustomThreshold,
    isInitialized,
  } = useHistogramUrlState();

  // Parameter options generated from shared configuration
  const parameterOptions = [
    {
      label: "Coherence Times",
      options: PARAMETER_GROUPS.coherence.map((key) => ({
        value: key as string,
        label: PARAMETER_CONFIG[key].label,
      })),
    },
    {
      label: "Gate Fidelities",
      options: PARAMETER_GROUPS.fidelity.map((key) => ({
        value: key as string,
        label: PARAMETER_CONFIG[key].label,
      })),
    },
  ];

  // Fetch chips data
  const { data: chipsResponse } = useListChips();

  // Date navigation
  const {
    navigateToPreviousDay,
    navigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
  } = useDateNavigation(selectedChip, selectedDate, setSelectedDate);

  // Set default chip on mount
  useEffect(() => {
    if (!selectedChip && chipsResponse?.data && chipsResponse.data.length > 0) {
      const sortedChips = [...chipsResponse.data].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });

      if (sortedChips.length > 0 && sortedChips[0]?.chip_id) {
        setSelectedChip(sortedChips[0].chip_id);
      }
    }
  }, [selectedChip, chipsResponse, setSelectedChip]);

  const taskConfig = TASK_CONFIG[selectedParameter];
  const taskName = taskConfig?.name;
  const taskType = taskConfig?.type;

  // Fetch data based on task type
  const {
    data: latestQubitResponse,
    isLoading: latestQubitLoading,
    error: latestQubitError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, taskName || "", {
    query: {
      enabled: Boolean(
        selectedChip &&
          taskName &&
          taskType === "qubit" &&
          selectedDate === "latest",
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: historicalQubitResponse,
    isLoading: historicalQubitLoading,
    error: historicalQubitError,
  } = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    taskName || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            taskName &&
            taskType === "qubit" &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  const {
    data: latestCouplingResponse,
    isLoading: latestCouplingLoading,
    error: latestCouplingError,
  } = useFetchLatestCouplingTaskGroupedByChip(selectedChip, taskName || "", {
    query: {
      enabled: Boolean(
        selectedChip &&
          taskName &&
          taskType === "coupling" &&
          selectedDate === "latest",
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: historicalCouplingResponse,
    isLoading: historicalCouplingLoading,
    error: historicalCouplingError,
  } = useFetchHistoricalCouplingTaskGroupedByChip(
    selectedChip,
    taskName || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            taskName &&
            taskType === "coupling" &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // Combine loading and error states
  const isLoading =
    latestQubitLoading ||
    historicalQubitLoading ||
    latestCouplingLoading ||
    historicalCouplingLoading;

  const error =
    latestQubitError ||
    historicalQubitError ||
    latestCouplingError ||
    historicalCouplingError;

  // Get response data based on task type and date
  const response = useMemo(() => {
    if (taskType === "qubit") {
      return selectedDate === "latest"
        ? latestQubitResponse
        : historicalQubitResponse;
    } else if (taskType === "coupling") {
      return selectedDate === "latest"
        ? latestCouplingResponse
        : historicalCouplingResponse;
    }
    return null;
  }, [
    taskType,
    selectedDate,
    latestQubitResponse,
    historicalQubitResponse,
    latestCouplingResponse,
    historicalCouplingResponse,
  ]);

  // Extract and transform raw data
  const histogramData = useMemo(() => {
    if (!response?.data?.result) {
      return [];
    }

    const outputParamName = OUTPUT_PARAM_NAMES[selectedParameter];
    const allValues: HistogramDataPoint[] = [];

    Object.entries(response.data.result).forEach(([qid, taskResultItem]) => {
      const taskResult = taskResultItem as any;
      if (taskResult?.output_parameters) {
        const paramValue = taskResult.output_parameters[outputParamName];

        if (paramValue !== null && paramValue !== undefined) {
          let value: number;

          // Handle different data structures
          if (typeof paramValue === "number") {
            value = paramValue;
          } else if (typeof paramValue === "string") {
            value = Number(paramValue);
          } else if (typeof paramValue === "object" && paramValue !== null) {
            if ("value" in paramValue && typeof paramValue.value === "number") {
              value = paramValue.value;
            } else if (
              "mean" in paramValue &&
              typeof paramValue.mean === "number"
            ) {
              value = paramValue.mean;
            } else if (
              "result" in paramValue &&
              typeof paramValue.result === "number"
            ) {
              value = paramValue.result;
            } else {
              return;
            }
          } else {
            return;
          }

          // Extract error if available
          let errorValue: number | undefined = undefined;
          const errorParamName = `${outputParamName}_err`;
          if (
            taskResult.output_parameters[errorParamName] !== null &&
            taskResult.output_parameters[errorParamName] !== undefined
          ) {
            errorValue = Number(taskResult.output_parameters[errorParamName]);
          }

          // Apply conversion for display
          const isCoherence = ["t1", "t2_echo", "t2_star"].includes(
            selectedParameter,
          );
          const isFidelity = !isCoherence;

          if (isFidelity) {
            if (showAsErrorRate) {
              value = (1 - value) * 100; // Convert to error rate percentage
            } else {
              value = value * 100; // Convert to fidelity percentage
            }
          }

          if (!isNaN(value) && value >= 0) {
            allValues.push({ qid, value, error: errorValue });
          }
        }
      }
    });

    // Sort by QID for consistent ordering using robust natural sort
    allValues.sort((a, b) => naturalSortQIDs(a.qid, b.qid));
    return allValues;
  }, [response, selectedParameter, showAsErrorRate]);

  // Calculate basic statistics
  const basicStatistics = useMemo(() => {
    if (histogramData.length === 0) {
      return {
        mean: 0,
        median: 0,
        stdDev: 0,
        min: 0,
        max: 0,
        count: 0,
      };
    }

    const values = histogramData.map((item) => item.value);
    const mean =
      values.length > 0
        ? values.reduce((sum, val) => sum + val, 0) / values.length
        : 0;
    
    const sortedValues = [...values].sort((a, b) => a - b);
    const median =
      sortedValues.length > 0
        ? sortedValues.length % 2 === 1
          ? sortedValues[Math.floor(sortedValues.length / 2)]
          : (sortedValues[Math.floor(sortedValues.length / 2) - 1] +
              sortedValues[Math.floor(sortedValues.length / 2)]) /
            2
        : 0;

    const stdDev =
      values.length > 0
        ? Math.sqrt(
            values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) /
              values.length,
          )
        : 0;

    return {
      mean,
      median,
      stdDev,
      min: sortedValues[0] || 0,
      max: sortedValues[sortedValues.length - 1] || 0,
      count: values.length,
    };
  }, [histogramData]);

  // Calculate yield percentage
  const yieldStatistics = useMemo(() => {
    if (histogramData.length === 0) {
      return { yieldPercent: 0 };
    }

    const defaultThreshold = PARAMETER_CONFIG[selectedParameter]?.threshold;
    const activeThreshold = customThreshold ?? defaultThreshold;
    let yieldCount = 0;

    if (activeThreshold) {
      const values = histogramData.map((item) => item.value);
      const isCoherence = ["t1", "t2_echo", "t2_star"].includes(
        selectedParameter,
      );

      if (isCoherence) {
        // For coherence times, compare directly with threshold
        yieldCount = values.filter((v) => v >= activeThreshold).length;
      } else {
        // For fidelities, convert threshold to percentage if needed
        const thresholdPercent = showAsErrorRate
          ? (1 - activeThreshold) * 100 // Convert fidelity threshold to error rate
          : activeThreshold * 100; // Convert to percentage

        yieldCount = values.filter((v) =>
          showAsErrorRate ? v <= thresholdPercent : v >= thresholdPercent,
        ).length;
      }
    }

    const yieldPercent =
      histogramData.length > 0 ? (yieldCount / histogramData.length) * 100 : 0;

    return { yieldPercent };
  }, [histogramData, selectedParameter, showAsErrorRate, customThreshold]);

  // Combine all data for components that need the complete structure
  const processedData = useMemo(() => {
    return {
      histogramData,
      tableData: histogramData,
      statistics: {
        ...basicStatistics,
        ...yieldStatistics,
      },
    };
  }, [histogramData, basicStatistics, yieldStatistics]);

  // Create Plotly traces
  const plotData = useMemo(() => {
    if (processedData.histogramData.length === 0) return [];

    const isCoherence = ["t1", "t2_echo", "t2_star"].includes(
      selectedParameter,
    );

    // Bar chart with QID on x-axis
    const barTrace = {
      x: processedData.histogramData.map((item) => item.qid),
      y: processedData.histogramData.map((item) => item.value),
      error_y: processedData.histogramData.some(
        (item) => item.error !== undefined,
      )
        ? {
            type: "data" as const,
            array: processedData.histogramData.map((item) => item.error || 0),
            visible: true,
          }
        : undefined,
      type: "bar" as const,
      name: PARAMETER_CONFIG[selectedParameter].label,
      marker: {
        color: processedData.histogramData.map((item) => {
          const defaultThreshold =
            PARAMETER_CONFIG[selectedParameter]?.threshold;
          const activeThreshold = customThreshold ?? defaultThreshold;
          if (!activeThreshold) return "#3b82f6"; // Default blue

          if (isCoherence) {
            return item.value >= activeThreshold ? "#10b981" : "#ef4444"; // Green if above, red if below
          } else {
            const thresholdPercent = showAsErrorRate
              ? (1 - activeThreshold) * 100
              : activeThreshold * 100;
            return showAsErrorRate
              ? item.value <= thresholdPercent
                ? "#10b981"
                : "#ef4444"
              : item.value >= thresholdPercent
                ? "#10b981"
                : "#ef4444";
          }
        }),
      },
      hovertemplate:
        "Qubit: %{x}<br>" + "Value: %{y:.4f}<br>" + "<extra></extra>",
    };

    // Mean line
    const meanLine = {
      x: processedData.histogramData.map((item) => item.qid),
      y: Array(processedData.histogramData.length).fill(
        processedData.statistics.mean,
      ),
      type: "scatter" as const,
      mode: "lines" as const,
      line: {
        color: "red",
        width: 2,
        dash: "dash" as const,
      },
      name: `Mean: ${processedData.statistics.mean.toFixed(4)}`,
      hovertemplate: "Mean: %{y:.4f}<br><extra></extra>",
    };

    // Threshold line (if applicable)
    const traces: any[] = [barTrace, meanLine];
    const defaultThreshold = PARAMETER_CONFIG[selectedParameter]?.threshold;
    const activeThreshold = customThreshold ?? defaultThreshold;

    if (activeThreshold) {
      const thresholdValue = isCoherence
        ? activeThreshold
        : showAsErrorRate
          ? (1 - activeThreshold) * 100
          : activeThreshold * 100;

      const thresholdLine = {
        x: processedData.histogramData.map((item) => item.qid),
        y: Array(processedData.histogramData.length).fill(thresholdValue),
        type: "scatter" as const,
        mode: "lines" as const,
        line: {
          color: "orange",
          width: 2,
          dash: "dot" as const,
        },
        name: `Threshold: ${thresholdValue.toFixed(4)}${customThreshold ? " (Custom)" : " (Default)"}`,
        hovertemplate: "Threshold: %{y:.4f}<br><extra></extra>",
      };
      traces.push(thresholdLine);
    }

    return traces;
  }, [processedData, selectedParameter, showAsErrorRate, customThreshold]);

  // Plot layout
  const layout = useMemo(() => {
    const isCoherence = ["t1", "t2_echo", "t2_star"].includes(
      selectedParameter,
    );
    const isFidelity = !isCoherence;

    return {
      title: {
        text: `${PARAMETER_CONFIG[selectedParameter].label} Distribution by Qubit`,
        font: { size: 18 },
      },
      xaxis: {
        title: taskType === "coupling" ? "Coupling Pair" : "Qubit ID",
        gridcolor: "#e5e7eb",
        showgrid: false,
        tickangle: -45,
        automargin: true,
      },
      yaxis: {
        title: isCoherence
          ? `${PARAMETER_CONFIG[selectedParameter].label} (${PARAMETER_CONFIG[selectedParameter].displayUnit})`
          : isFidelity
            ? showAsErrorRate
              ? "Gate Error Rate (%)"
              : "Gate Fidelity (%)"
            : "Value",
        gridcolor: "#e5e7eb",
        showgrid: true,
        zeroline: false,
        type:
          isFidelity && showAsErrorRate
            ? ("log" as const)
            : ("linear" as const),
        tickformat: isFidelity && showAsErrorRate ? ".1e" : undefined,
      },
      hovermode: "closest" as const,
      showlegend: true,
      legend: {
        x: 1,
        y: 1,
        xanchor: "right" as const,
        bgcolor: "rgba(255, 255, 255, 0.8)",
        bordercolor: "#e5e7eb",
        borderwidth: 1,
      },
      margin: { t: 60, r: 50, b: 100, l: 80 },
      plot_bgcolor: "#ffffff",
      paper_bgcolor: "#ffffff",
      bargap: 0.1,
      annotations: [
        {
          text: `Data snapshot: ${
            selectedDate === "latest"
              ? "Latest calibration"
              : `Date: ${formatDate(selectedDate)}`
          }<br>Sample size: ${processedData.histogramData.length} ${
            taskType === "coupling" ? "coupling pairs" : "qubits"
          }`,
          showarrow: false,
          xref: "paper" as const,
          yref: "paper" as const,
          x: 0.02,
          y: -0.25,
          xanchor: "left" as const,
          yanchor: "top" as const,
          font: { size: 11, color: "#666" },
        },
      ],
    };
  }, [
    selectedParameter,
    taskType,
    selectedDate,
    formatDate,
    processedData,
    showAsErrorRate,
  ]);

  // CSV Export
  const { exportToCSV } = useCSVExport();

  const handleExportCSV = () => {
    if (processedData.tableData.length === 0) return;

    const headers = [
      "Entity_ID",
      "Value",
      "Error",
      "Parameter",
      "Task",
      "Entity_Type",
      "Timestamp",
    ];
    const timestamp = new Date().toISOString();
    const rows = processedData.tableData.map((row: HistogramDataPoint) => [
      row.qid,
      String(row.value.toFixed(6)),
      row.error !== undefined ? String(row.error.toFixed(6)) : "N/A",
      selectedParameter,
      taskName,
      taskType === "coupling" ? "coupling_pair" : "qubit",
      timestamp,
    ]);

    const dateStr = selectedDate === "latest" ? "latest" : selectedDate;
    const filename = `histogram_${selectedParameter}_${selectedChip}_${dateStr}_${timestamp
      .slice(0, 19)
      .replace(/[:-]/g, "")}.csv`;

    exportToCSV({ filename, headers, data: rows });
  };

  // Improved error handling with targeted retry
  const handleRetry = useCallback(() => {
    // Clear error state and refetch data based on current parameters
    if (taskType === "qubit") {
      if (selectedDate === "latest") {
        // Trigger refetch for latest qubit data
        console.log("Retrying latest qubit data fetch");
      } else {
        // Trigger refetch for historical qubit data
        console.log("Retrying historical qubit data fetch");
      }
    } else if (taskType === "coupling") {
      if (selectedDate === "latest") {
        // Trigger refetch for latest coupling data
        console.log("Retrying latest coupling data fetch");
      } else {
        // Trigger refetch for historical coupling data
        console.log("Retrying historical coupling data fetch");
      }
    }
    // Note: TanStack Query automatically handles retries, this is for user-initiated retry
    window.location.reload(); // Fallback for now, can be improved with query invalidation
  }, [taskType, selectedDate]);

  if (error) {
    return (
      <ErrorCard
        title="Failed to load histogram data"
        message={error.message || "An unexpected error occurred"}
        onRetry={handleRetry}
      />
    );
  }

  if (!isInitialized) {
    return (
      <div className="flex justify-center items-center h-64">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Controls Section */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          <div className="flex flex-wrap items-end gap-4">
            {/* Chip Selection */}
            <div className="form-control min-w-48">
              <label className="label h-8">
                <span className="label-text font-semibold">Chip</span>
              </label>
              <div className="h-10">
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </div>
            </div>

            {/* Date Selection */}
            <div className="form-control min-w-48">
              <div className="flex justify-center gap-1 h-8 items-center">
                <button
                  onClick={navigateToPreviousDay}
                  disabled={!canNavigatePrevious}
                  className="btn btn-xs btn-ghost"
                  title="Previous Day"
                >
                  ←
                </button>
                <button
                  onClick={navigateToNextDay}
                  disabled={!canNavigateNext}
                  className="btn btn-xs btn-ghost"
                  title="Next Day"
                >
                  →
                </button>
              </div>
              <div className="h-10">
                <DateSelector
                  chipId={selectedChip}
                  selectedDate={selectedDate}
                  onDateSelect={setSelectedDate}
                  disabled={!selectedChip}
                />
              </div>
            </div>

            {/* Parameter Selection */}
            <div className="form-control min-w-64">
              <label className="label h-8">
                <span className="label-text font-semibold">Parameter</span>
              </label>
              <div className="h-10">
                <Select
                  options={parameterOptions}
                  value={parameterOptions
                    .flatMap((group) => group.options)
                    .find((option) => option.value === selectedParameter) || null}
                  onChange={(option) => {
                    if (option) {
                      setSelectedParameter(option.value);
                    }
                  }}
                  placeholder="Select parameter"
                  className="text-base-content"
                  styles={{
                    control: (base) => ({
                      ...base,
                      minHeight: "40px",
                      height: "40px",
                      borderRadius: "0.5rem",
                    }),
                    valueContainer: (base) => ({
                      ...base,
                      height: "40px",
                      padding: "0 8px",
                    }),
                    input: (base) => ({
                      ...base,
                      margin: "0px",
                      padding: "0px",
                    }),
                    indicatorsContainer: (base) => ({
                      ...base,
                      height: "40px",
                    }),
                  }}
                />
              </div>
            </div>

            {/* Display Format Toggle - Only for fidelity parameters */}
            {!["t1", "t2_echo", "t2_star"].includes(selectedParameter) && (
              <div className="form-control min-w-48">
                <div className="flex justify-between items-center h-8">
                  <span className="label-text font-semibold">
                    Display Format
                  </span>
                </div>
                <div className="h-10 flex items-center">
                  <label className="cursor-pointer label flex items-center gap-2">
                    <span className="text-sm">Fidelity %</span>
                    <input
                      type="checkbox"
                      className="toggle toggle-primary"
                      checked={showAsErrorRate}
                      onChange={(e) => setShowAsErrorRate(e.target.checked)}
                    />
                    <span className="text-sm">Error Rate %</span>
                  </label>
                </div>
              </div>
            )}

            {/* Threshold Slider */}
            <div className="form-control min-w-64">
              <div className="flex justify-between items-center h-8">
                <span className="label-text font-semibold">Threshold</span>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={() => setCustomThreshold(null)}
                  disabled={customThreshold === null}
                  title="Reset to default threshold"
                >
                  Reset
                </button>
              </div>
              <div className="h-10 flex items-center gap-2">
                <input
                  type="range"
                  className="range range-primary flex-1"
                  min={getSliderMin(selectedParameter, showAsErrorRate)}
                  max={getSliderMax(selectedParameter, showAsErrorRate)}
                  step={getSliderStep(selectedParameter, showAsErrorRate)}
                  value={getSliderValue(
                    selectedParameter,
                    customThreshold ??
                      PARAMETER_CONFIG[selectedParameter]?.threshold,
                    showAsErrorRate,
                  )}
                  onChange={(e) =>
                    handleSliderChange(
                      selectedParameter,
                      e.target.value,
                      showAsErrorRate,
                      setCustomThreshold,
                    )
                  }
                />
                <span className="text-xs min-w-16 text-center">
                  {formatSliderDisplay(
                    selectedParameter,
                    customThreshold ??
                      PARAMETER_CONFIG[selectedParameter]?.threshold,
                    showAsErrorRate,
                  )}
                </span>
              </div>
            </div>

            {/* Export Button */}
            <div className="form-control min-w-32">
              <label className="label h-8">
                <span className="label-text font-semibold">Export</span>
              </label>
              <div className="h-10">
                <button
                  className="btn btn-outline btn-sm h-full w-full"
                  onClick={handleExportCSV}
                  disabled={processedData.tableData.length === 0}
                >
                  Export CSV
                </button>
              </div>
            </div>
          </div>

          {/* Statistics Display */}
          {processedData.statistics.count > 0 && (
            <div className="mt-4">
              <div className="stats shadow w-full">
                <div className="stat">
                  <div className="stat-title">Count</div>
                  <div className="stat-value text-primary text-lg">
                    {processedData.statistics.count}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Mean</div>
                  <div className="stat-value text-secondary text-lg">
                    {processedData.statistics.mean.toFixed(4)}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Median</div>
                  <div className="stat-value text-accent text-lg">
                    {processedData.statistics.median.toFixed(4)}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Std Dev</div>
                  <div className="stat-value text-info text-lg">
                    {processedData.statistics.stdDev.toFixed(4)}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Min</div>
                  <div className="stat-value text-error text-lg">
                    {processedData.statistics.min.toFixed(4)}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Max</div>
                  <div className="stat-value text-success text-lg">
                    {processedData.statistics.max.toFixed(4)}
                  </div>
                </div>
                {(PARAMETER_CONFIG[selectedParameter].threshold ||
                  customThreshold) && (
                  <div className="stat">
                    <div className="stat-title">Yield</div>
                    <div className="stat-value text-warning text-lg">
                      {processedData.statistics.yieldPercent.toFixed(1)}%
                    </div>
                    <div className="stat-desc">
                      {customThreshold
                        ? "Custom threshold"
                        : "Default threshold"}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Plot Section */}
      <PlotCard
        plotData={plotData}
        layout={layout}
        isLoading={isLoading}
        title="Parameter Distribution by Qubit"
      />

      {/* Data Table */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          <DataTable
            title="Data Points"
            data={processedData.tableData}
            columns={[
              {
                key: "qid",
                label: taskType === "coupling" ? "Coupling Pair" : "Qubit ID",
                sortable: true,
              },
              {
                key: "value",
                label: `${PARAMETER_CONFIG[selectedParameter].label} (${
                  ["t1", "t2_echo", "t2_star"].includes(selectedParameter)
                    ? PARAMETER_CONFIG[selectedParameter].displayUnit
                    : showAsErrorRate
                      ? "Error %"
                      : "%"
                })`,
                sortable: true,
                render: (v: number, row: HistogramDataPoint) => {
                  const errorStr =
                    row.error !== undefined ? ` ± ${row.error.toFixed(6)}` : "";
                  return `${v.toFixed(6)}${errorStr}`;
                },
              },
            ]}
            pageSize={20}
          />
        </div>
      </div>
    </div>
  );
}
