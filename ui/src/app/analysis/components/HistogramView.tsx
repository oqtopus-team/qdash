"use client";

import { useMemo, useEffect, useCallback } from "react";

import Select, { type SingleValue, type StylesConfig } from "react-select";

import { ChipSelector } from "@/app/components/ChipSelector";
import { useHistogramUrlState } from "@/app/hooks/useUrlState";
import { useListChips } from "@/client/chip/chip";
import { useMetricsGetChipMetrics } from "@/client/metrics/metrics";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { DataTable } from "@/shared/components/DataTable";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { PlotCard } from "@/shared/components/PlotCard";
import { useCSVExport } from "@/shared/hooks/useCSVExport";
import { naturalSortQIDs } from "@/shared/utils/qid";

interface HistogramDataPoint {
  qid: string;
  value: number;
}

type MetricOption = {
  value: string;
  label: string;
};

type MetricType = "qubit" | "coupling";

// Helper function to check if a metric uses percentage unit
function isPercentageMetric(unit: string | undefined): boolean {
  return unit === "%";
}

export function HistogramView() {
  // URL state management
  const {
    selectedChip,
    timeRange,
    selectionMode,
    selectedParameter,
    showAsErrorRate,
    customThreshold,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setSelectedParameter,
    setShowAsErrorRate,
    setCustomThreshold,
    isInitialized,
  } = useHistogramUrlState();

  // Load metrics configuration from backend
  const {
    qubitMetrics,
    couplingMetrics,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  // Determine metric type based on selected parameter
  const metricType: MetricType = useMemo(() => {
    if (couplingMetrics.some((m) => m.key === selectedParameter)) {
      return "coupling";
    }
    return "qubit";
  }, [couplingMetrics, selectedParameter]);

  // Generate metric options for qubit metrics
  const qubitMetricOptions: MetricOption[] = useMemo(
    () =>
      qubitMetrics
        .filter((m) => m.threshold)
        .map((metric) => ({
          value: metric.key,
          label: metric.title,
        })),
    [qubitMetrics],
  );

  // Generate metric options for coupling metrics
  const couplingMetricOptions: MetricOption[] = useMemo(
    () =>
      couplingMetrics
        .filter((m) => m.threshold)
        .map((metric) => ({
          value: metric.key,
          label: metric.title,
        })),
    [couplingMetrics],
  );

  // Select appropriate metrics options based on type
  const metricOptions =
    metricType === "qubit" ? qubitMetricOptions : couplingMetricOptions;

  // Get current metric configuration (search both qubit and coupling)
  const currentMetricConfig = useMemo(() => {
    return (
      qubitMetrics.find((m) => m.key === selectedParameter) ||
      couplingMetrics.find((m) => m.key === selectedParameter)
    );
  }, [qubitMetrics, couplingMetrics, selectedParameter]);

  // Check if best mode is supported for current metric
  const isBestModeSupported = useMemo(
    () => currentMetricConfig?.evaluationMode !== "none",
    [currentMetricConfig],
  );

  // Select styles (same as metrics page)
  const metricSelectStyles = useMemo<StylesConfig<MetricOption, false>>(
    () => ({
      control: (provided) => ({
        ...provided,
        minHeight: 38,
        height: 38,
      }),
      valueContainer: (provided) => ({
        ...provided,
        padding: "2px 8px",
      }),
      indicatorsContainer: (provided) => ({
        ...provided,
        height: 38,
      }),
      menu: (provided) => ({
        ...provided,
        zIndex: 50,
      }),
    }),
    [],
  );

  // Auto-switch to latest mode when metric doesn't support best mode
  useEffect(() => {
    if (!isBestModeSupported && selectionMode === "best") {
      setSelectionMode("latest");
    }
  }, [isBestModeSupported, selectionMode, setSelectionMode]);

  // Set default parameter when metrics load
  useEffect(() => {
    if (qubitMetrics.length === 0) return;

    // Check if current parameter is valid
    const allMetricsWithThreshold = [
      ...qubitMetrics.filter((m) => m.threshold),
      ...couplingMetrics.filter((m) => m.threshold),
    ];
    const isCurrentValid = allMetricsWithThreshold.some(
      (m) => m.key === selectedParameter,
    );

    if (!isCurrentValid && allMetricsWithThreshold.length > 0) {
      setSelectedParameter(allMetricsWithThreshold[0].key);
    }
  }, [qubitMetrics, couplingMetrics, selectedParameter, setSelectedParameter]);

  // Fetch chips data
  const { data: chipsResponse } = useListChips();

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

  // Fetch metrics data using the same API as metrics page
  const {
    data: metricsData,
    isLoading,
    isError,
    error,
  } = useMetricsGetChipMetrics(
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

  // Extract and transform raw data from metrics API for histogram (single metric)
  const histogramData = useMemo(() => {
    if (!metricsData?.data || !currentMetricConfig) {
      return [];
    }

    const isCoupling = metricType === "coupling";
    const metricsSource = isCoupling
      ? metricsData.data.coupling_metrics
      : metricsData.data.qubit_metrics;

    if (!metricsSource) return [];

    const rawData =
      metricsSource[selectedParameter as keyof typeof metricsSource];
    if (!rawData) return [];

    const allValues: HistogramDataPoint[] = [];

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
        let scaledValue = value * currentMetricConfig.scale;

        // For percentage metrics, convert to error rate if needed
        if (isPercentageMetric(currentMetricConfig.unit)) {
          if (showAsErrorRate) {
            // Convert scaled percentage to error rate
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

    // Sort by QID for consistent ordering
    allValues.sort((a, b) => naturalSortQIDs(a.qid, b.qid));
    return allValues;
  }, [
    metricsData,
    currentMetricConfig,
    selectedParameter,
    metricType,
    showAsErrorRate,
  ]);

  // Extract all metrics data for table display (all metrics for current type)
  const allMetricsTableData = useMemo(() => {
    if (!metricsData?.data) {
      return [];
    }

    const isCoupling = metricType === "coupling";
    const metricsSource = isCoupling
      ? metricsData.data.coupling_metrics
      : metricsData.data.qubit_metrics;
    const metricsConfig = isCoupling ? couplingMetrics : qubitMetrics;

    if (!metricsSource) return [];

    // Collect all entity IDs
    const entityIds = new Set<string>();
    Object.values(metricsSource).forEach((metricData: any) => {
      if (metricData) {
        Object.keys(metricData).forEach((id) => entityIds.add(id));
      }
    });

    // Build table data with all metrics for each entity
    const tableData: Record<string, any>[] = [];

    entityIds.forEach((entityId) => {
      const formattedId = isCoupling
        ? entityId
        : entityId.startsWith("Q")
          ? entityId
          : `Q${entityId.padStart(2, "0")}`;

      const row: Record<string, any> = { entityId: formattedId };

      metricsConfig.forEach((metric) => {
        const metricData = metricsSource[
          metric.key as keyof typeof metricsSource
        ] as any;
        const value = metricData?.[entityId]?.value;

        if (
          value !== null &&
          value !== undefined &&
          typeof value === "number"
        ) {
          // Apply scale
          let scaledValue = value * metric.scale;

          // For percentage metrics with error rate display
          if (isPercentageMetric(metric.unit) && showAsErrorRate) {
            scaledValue = 100 - scaledValue;
          }

          row[metric.key] = scaledValue;
        } else {
          row[metric.key] = null;
        }
      });

      tableData.push(row);
    });

    // Sort by entity ID
    tableData.sort((a, b) => naturalSortQIDs(a.entityId, b.entityId));
    return tableData;
  }, [metricsData, metricType, qubitMetrics, couplingMetrics, showAsErrorRate]);

  // Calculate basic statistics
  const statistics = useMemo(() => {
    if (histogramData.length === 0) {
      return {
        mean: 0,
        median: 0,
        min: 0,
        max: 0,
        count: 0,
        yieldPercent: 0,
      };
    }

    const values = histogramData.map((item) => item.value);
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;

    const sortedValues = [...values].sort((a, b) => a - b);
    const median =
      sortedValues.length % 2 === 1
        ? sortedValues[Math.floor(sortedValues.length / 2)]
        : (sortedValues[Math.floor(sortedValues.length / 2) - 1] +
            sortedValues[Math.floor(sortedValues.length / 2)]) /
          2;

    // Calculate yield percentage
    let yieldCount = 0;
    const activeThreshold =
      customThreshold ?? currentMetricConfig?.threshold?.value;

    if (activeThreshold !== undefined && activeThreshold !== null) {
      const isPercent = isPercentageMetric(currentMetricConfig?.unit);

      if (!isPercent) {
        // For non-percentage metrics (e.g. coherence times), compare directly with threshold
        yieldCount = values.filter((v) => v >= activeThreshold).length;
      } else {
        // For percentage metrics, convert threshold to display format
        const thresholdPercent = showAsErrorRate
          ? (1 - activeThreshold) * 100 // Error rate threshold
          : activeThreshold * 100; // Fidelity threshold

        yieldCount = values.filter((v) =>
          showAsErrorRate ? v <= thresholdPercent : v >= thresholdPercent,
        ).length;
      }
    }

    const yieldPercent =
      histogramData.length > 0 ? (yieldCount / histogramData.length) * 100 : 0;

    return {
      mean,
      median,
      min: sortedValues[0] || 0,
      max: sortedValues[sortedValues.length - 1] || 0,
      count: values.length,
      yieldPercent,
    };
  }, [
    histogramData,
    selectedParameter,
    showAsErrorRate,
    customThreshold,
    currentMetricConfig,
  ]);

  // Create Plotly traces
  const plotData = useMemo(() => {
    if (histogramData.length === 0) return [];

    const isPercent = isPercentageMetric(currentMetricConfig?.unit);
    const activeThreshold =
      customThreshold ?? currentMetricConfig?.threshold?.value;

    // Bar chart with QID on x-axis
    const barTrace = {
      x: histogramData.map((item) => item.qid),
      y: histogramData.map((item) => item.value),
      type: "bar" as const,
      name: currentMetricConfig?.title || selectedParameter,
      marker: {
        color: histogramData.map((item) => {
          if (!activeThreshold) return "#3b82f6"; // Default blue

          if (!isPercent) {
            // Non-percentage metrics: higher is better
            return item.value >= activeThreshold ? "#10b981" : "#ef4444";
          } else {
            // Percentage metrics
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
        "Entity: %{x}<br>" + "Value: %{y:.4f}<br>" + "<extra></extra>",
    };

    // Mean line
    const meanLine = {
      x: histogramData.map((item) => item.qid),
      y: Array(histogramData.length).fill(statistics.mean),
      type: "scatter" as const,
      mode: "lines" as const,
      line: {
        color: "red",
        width: 2,
        dash: "dash" as const,
      },
      name: `Mean: ${statistics.mean.toFixed(4)}`,
      hovertemplate: "Mean: %{y:.4f}<br><extra></extra>",
    };

    const traces: any[] = [barTrace, meanLine];

    // Threshold line (if applicable)
    if (activeThreshold) {
      const thresholdValue = !isPercent
        ? activeThreshold
        : showAsErrorRate
          ? (1 - activeThreshold) * 100
          : activeThreshold * 100;

      const thresholdLine = {
        x: histogramData.map((item) => item.qid),
        y: Array(histogramData.length).fill(thresholdValue),
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
  }, [
    histogramData,
    selectedParameter,
    showAsErrorRate,
    customThreshold,
    currentMetricConfig,
    statistics,
  ]);

  // Plot layout
  const layout = useMemo(() => {
    const isPercent = isPercentageMetric(currentMetricConfig?.unit);
    const isCoupling = metricType === "coupling";

    return {
      title: {
        text: `${currentMetricConfig?.title || selectedParameter} Distribution`,
        font: { size: 18 },
      },
      xaxis: {
        title: isCoupling ? "Coupling Pair" : "Qubit ID",
        gridcolor: "#e5e7eb",
        showgrid: false,
        tickangle: -45,
        automargin: true,
      },
      yaxis: {
        title: !isPercent
          ? `${currentMetricConfig?.title || selectedParameter} (${currentMetricConfig?.unit || ""})`
          : showAsErrorRate
            ? "Error Rate (%)"
            : `${currentMetricConfig?.title || selectedParameter} (%)`,
        gridcolor: "#e5e7eb",
        showgrid: true,
        zeroline: false,
        type:
          isPercent && showAsErrorRate ? ("log" as const) : ("linear" as const),
        tickformat: isPercent && showAsErrorRate ? ".1e" : undefined,
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
      margin: { t: 60, r: 50, b: 120, l: 80 },
      plot_bgcolor: "#ffffff",
      paper_bgcolor: "#ffffff",
      bargap: 0.1,
      annotations: [
        {
          text: `Time range: ${timeRange === "1d" ? "Last 1 Day" : timeRange === "7d" ? "Last 7 Days" : "Last 30 Days"} | Mode: ${selectionMode === "latest" ? "Latest" : "Best"}<br>Sample size: ${histogramData.length} ${isCoupling ? "coupling pairs" : "qubits"}`,
          showarrow: false,
          xref: "paper" as const,
          yref: "paper" as const,
          x: 0.02,
          y: -0.18,
          xanchor: "left" as const,
          yanchor: "top" as const,
          font: { size: 11, color: "#666" },
        },
      ],
    };
  }, [
    selectedParameter,
    currentMetricConfig,
    couplingMetrics,
    timeRange,
    selectionMode,
    histogramData,
    showAsErrorRate,
  ]);

  // CSV Export
  const { exportToCSV } = useCSVExport();

  const handleExportCSV = () => {
    if (histogramData.length === 0) return;

    const isCoupling = metricType === "coupling";
    const headers = [
      "Entity_ID",
      "Value",
      "Parameter",
      "Entity_Type",
      "Time_Range",
      "Selection_Mode",
      "Timestamp",
    ];
    const timestamp = new Date().toISOString();
    const rows = histogramData.map((row: HistogramDataPoint) => [
      row.qid,
      String(row.value.toFixed(6)),
      selectedParameter,
      isCoupling ? "coupling_pair" : "qubit",
      timeRange,
      selectionMode,
      timestamp,
    ]);

    const filename = `histogram_${selectedParameter}_${selectedChip}_${timeRange}_${selectionMode}_${timestamp
      .slice(0, 19)
      .replace(/[:-]/g, "")}.csv`;

    exportToCSV({ filename, headers, data: rows });
  };

  // Error handling with retry
  const handleRetry = useCallback(() => {
    window.location.reload();
  }, []);

  // Get slider configuration from metrics config, converted to display units
  const sliderDisplayConfig = useMemo(() => {
    if (!currentMetricConfig?.threshold) {
      return { min: 0, max: 100, step: 1 };
    }

    const rawRange = currentMetricConfig.threshold.range;
    const isPercent = isPercentageMetric(currentMetricConfig.unit);

    if (!isPercent) {
      // Non-percentage metrics: use raw values directly
      return rawRange;
    }

    if (showAsErrorRate) {
      // Error rate: convert fidelity range to error rate
      // fidelity 0.9 -> error rate 10%, fidelity 0.999 -> error rate 0.1%
      return {
        min: (1 - rawRange.max) * 100,
        max: (1 - rawRange.min) * 100,
        step: rawRange.step * 100,
      };
    }

    // Fidelity percentage
    return {
      min: rawRange.min * 100,
      max: rawRange.max * 100,
      step: rawRange.step * 100,
    };
  }, [currentMetricConfig, showAsErrorRate]);

  // Get current slider value from threshold
  const sliderValue = useMemo(() => {
    const activeThreshold =
      customThreshold ?? currentMetricConfig?.threshold?.value;
    if (activeThreshold === undefined || activeThreshold === null) {
      return sliderDisplayConfig.min;
    }

    const isPercent = isPercentageMetric(currentMetricConfig?.unit);

    if (!isPercent) {
      return activeThreshold;
    }

    if (showAsErrorRate) {
      return (1 - activeThreshold) * 100;
    }

    return activeThreshold * 100;
  }, [
    customThreshold,
    currentMetricConfig,
    showAsErrorRate,
    sliderDisplayConfig,
  ]);

  // Convert slider value to threshold and update state
  const handleSliderChange = useCallback(
    (displayValue: number) => {
      const isPercent = isPercentageMetric(currentMetricConfig?.unit);

      if (!isPercent) {
        setCustomThreshold(displayValue);
      } else if (showAsErrorRate) {
        // Error rate to fidelity: error 1% -> fidelity 0.99
        setCustomThreshold(1 - displayValue / 100);
      } else {
        // Percentage to raw: 99% -> 0.99
        setCustomThreshold(displayValue / 100);
      }
    },
    [currentMetricConfig, showAsErrorRate, setCustomThreshold],
  );

  // Format threshold for display
  const thresholdDisplayText = useMemo(() => {
    const activeThreshold =
      customThreshold ?? currentMetricConfig?.threshold?.value;
    if (activeThreshold === undefined || activeThreshold === null) return "N/A";

    const isPercent = isPercentageMetric(currentMetricConfig?.unit);

    if (!isPercent) {
      return `${activeThreshold.toFixed(0)} ${currentMetricConfig?.unit || ""}`;
    }

    if (showAsErrorRate) {
      return `${((1 - activeThreshold) * 100).toFixed(2)}%`;
    }

    return `${(activeThreshold * 100).toFixed(2)}%`;
  }, [customThreshold, currentMetricConfig, showAsErrorRate]);

  // Handle metric type change
  const handleMetricTypeChange = useCallback(
    (newType: MetricType) => {
      const newMetrics = newType === "qubit" ? qubitMetrics : couplingMetrics;
      const firstMetricWithThreshold = newMetrics.find((m) => m.threshold);
      if (firstMetricWithThreshold) {
        setSelectedParameter(firstMetricWithThreshold.key);
      }
    },
    [qubitMetrics, couplingMetrics, setSelectedParameter],
  );

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
        title="Failed to load histogram data"
        message={error?.message || "An unexpected error occurred"}
        onRetry={handleRetry}
      />
    );
  }

  if (!isInitialized || isConfigLoading) {
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
        <div className="card-body p-4 gap-4">
          {/* Row 1: Main Controls */}
          <div className="flex flex-col lg:flex-row lg:items-center gap-4">
            {/* Left: Type + Chip + Metric */}
            <div className="flex items-center gap-3">
              <div className="tabs tabs-boxed bg-base-200 h-9">
                <button
                  className={`tab h-full ${metricType === "qubit" ? "tab-active" : ""}`}
                  onClick={() => handleMetricTypeChange("qubit")}
                >
                  1Q
                </button>
                <button
                  className={`tab h-full ${metricType === "coupling" ? "tab-active" : ""}`}
                  onClick={() => handleMetricTypeChange("coupling")}
                >
                  2Q
                </button>
              </div>

              <div className="w-36">
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </div>

              <div className="w-52">
                <Select<MetricOption, false>
                  className="text-base-content"
                  classNamePrefix="react-select"
                  options={metricOptions}
                  value={
                    metricOptions.find(
                      (option) => option.value === selectedParameter,
                    ) ?? null
                  }
                  onChange={(option: SingleValue<MetricOption>) => {
                    if (option) {
                      setSelectedParameter(option.value);
                    }
                  }}
                  placeholder="Select metric"
                  isSearchable={false}
                  styles={metricSelectStyles}
                />
              </div>
            </div>

            {/* Center: Time Range + Mode */}
            <div className="flex items-center gap-3">
              <div className="join h-9">
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

              <div className="join h-9">
                <button
                  className={`join-item btn btn-sm h-full ${selectionMode === "latest" ? "btn-active" : ""}`}
                  onClick={() => setSelectionMode("latest")}
                >
                  Latest
                </button>
                <button
                  className={`join-item btn btn-sm h-full ${selectionMode === "best" ? "btn-active" : ""} ${!isBestModeSupported ? "btn-disabled" : ""}`}
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
            </div>

            {/* Right: Display Toggle + Export */}
            <div className="flex items-center gap-3 lg:ml-auto">
              {isPercentageMetric(currentMetricConfig?.unit) && (
                <label className="cursor-pointer flex items-center gap-2 h-9">
                  <span className="text-sm">Fidelity</span>
                  <input
                    type="checkbox"
                    className="toggle toggle-primary toggle-sm"
                    checked={showAsErrorRate}
                    onChange={(e) => setShowAsErrorRate(e.target.checked)}
                  />
                  <span className="text-sm">Error</span>
                </label>
              )}

              <button
                className="btn btn-outline btn-sm h-9"
                onClick={handleExportCSV}
                disabled={histogramData.length === 0}
              >
                Export
              </button>
            </div>
          </div>

          {/* Row 2: Threshold Slider */}
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium shrink-0">
              Threshold: {thresholdDisplayText}
            </span>
            <span className="text-xs text-base-content/60">
              {!isPercentageMetric(currentMetricConfig?.unit)
                ? `${sliderDisplayConfig.min}`
                : `${sliderDisplayConfig.min.toFixed(0)}%`}
            </span>
            <input
              type="range"
              className="range range-primary range-sm w-48"
              min={sliderDisplayConfig.min}
              max={sliderDisplayConfig.max}
              step={sliderDisplayConfig.step}
              value={sliderValue}
              onChange={(e) => handleSliderChange(parseFloat(e.target.value))}
            />
            <span className="text-xs text-base-content/60">
              {!isPercentageMetric(currentMetricConfig?.unit)
                ? `${sliderDisplayConfig.max}`
                : `${sliderDisplayConfig.max.toFixed(0)}%`}
            </span>
          </div>

          {/* Statistics Display */}
          {statistics.count > 0 && (
            <div className="mt-4">
              <div className="stats stats-vertical lg:stats-horizontal shadow w-full">
                <div className="stat py-2">
                  <div className="stat-title text-xs">Count</div>
                  <div className="stat-value text-primary text-lg">
                    {statistics.count}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">Mean</div>
                  <div className="stat-value text-secondary text-lg">
                    {statistics.mean.toFixed(4)}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">Median</div>
                  <div className="stat-value text-accent text-lg">
                    {statistics.median.toFixed(4)}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">Min / Max</div>
                  <div className="stat-value text-base">
                    {statistics.min.toFixed(2)} / {statistics.max.toFixed(2)}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">Yield</div>
                  <div className="stat-value text-warning text-lg">
                    {statistics.yieldPercent.toFixed(1)}%
                  </div>
                  <div className="stat-desc text-xs">
                    {customThreshold !== null ? "Custom" : "Default"}
                  </div>
                </div>
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
        title="Parameter Distribution"
      />

      {/* Data Table - All Metrics */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          <DataTable
            title={`${metricType === "coupling" ? "2Q" : "1Q"} Metrics Data`}
            data={allMetricsTableData}
            columns={[
              {
                key: "entityId",
                label: metricType === "coupling" ? "Coupling" : "Qubit",
                sortable: true,
              },
              ...(metricType === "qubit" ? qubitMetrics : couplingMetrics).map(
                (metric) => ({
                  key: metric.key,
                  label: `${metric.title} (${
                    !isPercentageMetric(metric.unit)
                      ? metric.unit
                      : showAsErrorRate
                        ? "Err%"
                        : "%"
                  })`,
                  sortable: true,
                  render: (v: number | null) =>
                    v !== null ? v.toFixed(4) : "-",
                }),
              ),
            ]}
            pageSize={20}
          />
        </div>
      </div>
    </div>
  );
}
