"use client";

import { useMemo, useEffect, useCallback } from "react";

import Select, { type SingleValue, type StylesConfig } from "react-select";

import { useListChips } from "@/client/chip/chip";
import { useGetChipMetrics } from "@/client/metrics/metrics";
import { PlotCard } from "@/components/charts/PlotCard";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DataTable } from "@/components/ui/DataTable";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { useCSVExport } from "@/hooks/useCSVExport";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useCorrelationUrlState } from "@/hooks/useUrlState";

type MetricOption = {
  value: string;
  label: string;
};

type MetricType = "qubit" | "coupling";

interface CorrelationDataPoint {
  entityId: string;
  xValue: number;
  yValue: number;
}

// Helper function to check if a metric uses percentage unit
function isPercentageMetric(unit: string | undefined): boolean {
  return unit === "%";
}

// Calculate Pearson correlation coefficient
function calculatePearsonCorrelation(
  x: number[],
  y: number[],
): { r: number; n: number } {
  if (x.length !== y.length || x.length < 2) {
    return { r: 0, n: x.length };
  }

  const n = x.length;
  const meanX = x.reduce((sum, val) => sum + val, 0) / n;
  const meanY = y.reduce((sum, val) => sum + val, 0) / n;

  let numerator = 0;
  let sumXSq = 0;
  let sumYSq = 0;

  for (let i = 0; i < n; i++) {
    const deltaX = x[i] - meanX;
    const deltaY = y[i] - meanY;
    numerator += deltaX * deltaY;
    sumXSq += deltaX * deltaX;
    sumYSq += deltaY * deltaY;
  }

  const denominator = Math.sqrt(sumXSq * sumYSq);
  const r = denominator === 0 ? 0 : numerator / denominator;

  return { r, n };
}

export function CorrelationView() {
  // URL state management
  const {
    selectedChip,
    timeRange,
    selectionMode,
    xParameter,
    yParameter,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setXParameter,
    setYParameter,
    isInitialized,
  } = useCorrelationUrlState();

  // Load metrics configuration from backend
  const {
    qubitMetrics,
    couplingMetrics,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  // Determine metric type based on selected X parameter
  const metricType: MetricType = useMemo(() => {
    if (couplingMetrics.some((m) => m.key === xParameter)) {
      return "coupling";
    }
    return "qubit";
  }, [couplingMetrics, xParameter]);

  // Generate metric options
  const qubitMetricOptions: MetricOption[] = useMemo(
    () =>
      qubitMetrics.map((metric) => ({
        value: metric.key,
        label: metric.title,
      })),
    [qubitMetrics],
  );

  const couplingMetricOptions: MetricOption[] = useMemo(
    () =>
      couplingMetrics.map((metric) => ({
        value: metric.key,
        label: metric.title,
      })),
    [couplingMetrics],
  );

  // Select appropriate metrics options based on type
  const metricOptions =
    metricType === "qubit" ? qubitMetricOptions : couplingMetricOptions;

  // Get current metric configurations
  const xMetricConfig = useMemo(() => {
    return (
      qubitMetrics.find((m) => m.key === xParameter) ||
      couplingMetrics.find((m) => m.key === xParameter)
    );
  }, [qubitMetrics, couplingMetrics, xParameter]);

  const yMetricConfig = useMemo(() => {
    return (
      qubitMetrics.find((m) => m.key === yParameter) ||
      couplingMetrics.find((m) => m.key === yParameter)
    );
  }, [qubitMetrics, couplingMetrics, yParameter]);

  // Check if best mode is supported for either metric
  const isBestModeSupported = useMemo(() => {
    const xSupports = xMetricConfig?.evaluationMode !== "none";
    const ySupports = yMetricConfig?.evaluationMode !== "none";
    return xSupports || ySupports;
  }, [xMetricConfig, yMetricConfig]);

  // Select styles
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

  // Auto-switch to latest mode when metrics don't support best mode
  useEffect(() => {
    if (!isBestModeSupported && selectionMode === "best") {
      setSelectionMode("latest");
    }
  }, [isBestModeSupported, selectionMode, setSelectionMode]);

  // Set default parameters when metrics load
  useEffect(() => {
    if (qubitMetrics.length === 0) return;

    const allMetrics = [...qubitMetrics, ...couplingMetrics];

    // Validate X parameter
    const isXValid = allMetrics.some((m) => m.key === xParameter);
    if (!isXValid && qubitMetrics.length > 0) {
      const t1Metric = qubitMetrics.find((m) => m.key === "t1");
      setXParameter(t1Metric?.key || qubitMetrics[0].key);
    }

    // Validate Y parameter
    const isYValid = allMetrics.some((m) => m.key === yParameter);
    if (!isYValid && qubitMetrics.length > 1) {
      const t2Metric = qubitMetrics.find((m) => m.key === "t2_echo");
      setYParameter(
        t2Metric?.key || qubitMetrics[1]?.key || qubitMetrics[0].key,
      );
    }
  }, [
    qubitMetrics,
    couplingMetrics,
    xParameter,
    yParameter,
    setXParameter,
    setYParameter,
  ]);

  // Fetch chips data
  const { data: chipsResponse } = useListChips();

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

  // Fetch metrics data
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

  // Process correlation data
  const { correlationData, statistics } = useMemo(() => {
    if (!metricsData?.data || !xMetricConfig || !yMetricConfig) {
      return { correlationData: [], statistics: null };
    }

    const isCoupling = metricType === "coupling";
    const metricsSource = isCoupling
      ? metricsData.data.coupling_metrics
      : metricsData.data.qubit_metrics;

    if (!metricsSource) {
      return { correlationData: [], statistics: null };
    }

    const xRawData = metricsSource[xParameter as keyof typeof metricsSource];
    const yRawData = metricsSource[yParameter as keyof typeof metricsSource];

    if (!xRawData || !yRawData) {
      return { correlationData: [], statistics: null };
    }

    // Collect data points where both X and Y values exist
    const dataPoints: CorrelationDataPoint[] = [];
    const entityIds = new Set([
      ...Object.keys(xRawData),
      ...Object.keys(yRawData),
    ]);

    entityIds.forEach((entityId) => {
      const xMetric = (xRawData as any)[entityId];
      const yMetric = (yRawData as any)[entityId];

      const xValue = xMetric?.value;
      const yValue = yMetric?.value;

      if (
        xValue !== null &&
        xValue !== undefined &&
        typeof xValue === "number" &&
        yValue !== null &&
        yValue !== undefined &&
        typeof yValue === "number"
      ) {
        // Apply scale from config
        const scaledX = xValue * xMetricConfig.scale;
        const scaledY = yValue * yMetricConfig.scale;

        // Format entity ID
        const formattedId = isCoupling
          ? entityId
          : entityId.startsWith("Q")
            ? entityId
            : `Q${entityId.padStart(2, "0")}`;

        dataPoints.push({
          entityId: formattedId,
          xValue: scaledX,
          yValue: scaledY,
        });
      }
    });

    // Sort by entity ID
    dataPoints.sort((a, b) => {
      const aNum = parseInt(a.entityId.replace(/\D/g, "")) || 0;
      const bNum = parseInt(b.entityId.replace(/\D/g, "")) || 0;
      return aNum - bNum;
    });

    // Calculate statistics
    if (dataPoints.length < 2) {
      return { correlationData: dataPoints, statistics: null };
    }

    const xValues = dataPoints.map((d) => d.xValue);
    const yValues = dataPoints.map((d) => d.yValue);

    const { r, n } = calculatePearsonCorrelation(xValues, yValues);

    const xMean = xValues.reduce((sum, v) => sum + v, 0) / n;
    const yMean = yValues.reduce((sum, v) => sum + v, 0) / n;

    const statistics = {
      correlation: r,
      sampleSize: n,
      xMean,
      yMean,
      xMin: Math.min(...xValues),
      xMax: Math.max(...xValues),
      yMin: Math.min(...yValues),
      yMax: Math.max(...yValues),
    };

    return { correlationData: dataPoints, statistics };
  }, [
    metricsData,
    xParameter,
    yParameter,
    xMetricConfig,
    yMetricConfig,
    metricType,
  ]);

  // Generate scatter plot data
  const plotData = useMemo(() => {
    if (correlationData.length === 0 || xParameter === yParameter) return [];

    return [
      {
        x: correlationData.map((d) => d.xValue),
        y: correlationData.map((d) => d.yValue),
        text: correlationData.map((d) => d.entityId),
        type: "scatter" as const,
        mode: "text+markers" as const,
        textposition: "top center" as const,
        textfont: { size: 9 },
        marker: {
          size: 10,
          color: correlationData.map((_, i) => i),
          colorscale: "Viridis",
          opacity: 0.8,
          line: {
            width: 1,
            color: "white",
          },
        },
        hovertemplate:
          `Entity: %{text}<br>` +
          `${xMetricConfig?.title || xParameter}: %{x:.4f}<br>` +
          `${yMetricConfig?.title || yParameter}: %{y:.4f}<br>` +
          `<extra></extra>`,
      },
    ];
  }, [correlationData, xParameter, yParameter, xMetricConfig, yMetricConfig]);

  // Plot layout
  const layout = useMemo(() => {
    const xIsPercent = isPercentageMetric(xMetricConfig?.unit);
    const yIsPercent = isPercentageMetric(yMetricConfig?.unit);

    const xUnit = xIsPercent ? "%" : xMetricConfig?.unit || "";
    const yUnit = yIsPercent ? "%" : yMetricConfig?.unit || "";

    return {
      title: {
        text: `${xMetricConfig?.title || xParameter} vs ${yMetricConfig?.title || yParameter}`,
        font: { size: 18 },
      },
      xaxis: {
        title: `${xMetricConfig?.title || xParameter} (${xUnit})`,
        gridcolor: "#e5e7eb",
        showgrid: true,
        zeroline: false,
      },
      yaxis: {
        title: `${yMetricConfig?.title || yParameter} (${yUnit})`,
        gridcolor: "#e5e7eb",
        showgrid: true,
        zeroline: false,
      },
      hovermode: "closest" as const,
      showlegend: false,
      margin: { t: 60, r: 50, b: 100, l: 80 },
      plot_bgcolor: "#ffffff",
      paper_bgcolor: "#ffffff",
      annotations: [
        {
          text: statistics
            ? `Correlation: r = ${statistics.correlation.toFixed(3)} (n = ${statistics.sampleSize})<br>` +
              `Time range: ${timeRange === "1d" ? "Last 1 Day" : timeRange === "7d" ? "Last 7 Days" : "Last 30 Days"} | ` +
              `Mode: ${selectionMode === "latest" ? "Latest" : "Best"}`
            : `Time range: ${timeRange === "1d" ? "Last 1 Day" : timeRange === "7d" ? "Last 7 Days" : "Last 30 Days"} | ` +
              `Mode: ${selectionMode === "latest" ? "Latest" : "Best"}`,
          showarrow: false,
          xref: "paper" as const,
          yref: "paper" as const,
          x: 0.02,
          y: 0.98,
          xanchor: "left" as const,
          yanchor: "top" as const,
          font: { size: 11, color: "#666" },
          bgcolor: "rgba(255, 255, 255, 0.8)",
          bordercolor: "#e5e7eb",
          borderwidth: 1,
        },
      ],
    };
  }, [
    xParameter,
    yParameter,
    xMetricConfig,
    yMetricConfig,
    statistics,
    timeRange,
    selectionMode,
  ]);

  // CSV Export
  const { exportToCSV } = useCSVExport();

  const handleExportCSV = useCallback(() => {
    if (correlationData.length === 0) return;

    const isCoupling = metricType === "coupling";
    const headers = [
      "Entity_ID",
      `${xMetricConfig?.title || xParameter}`,
      `${yMetricConfig?.title || yParameter}`,
      "Entity_Type",
      "Time_Range",
      "Selection_Mode",
      "Correlation",
      "Timestamp",
    ];
    const timestamp = new Date().toISOString();
    const rows = correlationData.map((row) => [
      row.entityId,
      String(row.xValue.toFixed(6)),
      String(row.yValue.toFixed(6)),
      isCoupling ? "coupling_pair" : "qubit",
      timeRange,
      selectionMode,
      statistics?.correlation.toFixed(6) || "N/A",
      timestamp,
    ]);

    const filename = `correlation_${xParameter}_${yParameter}_${selectedChip}_${timeRange}_${selectionMode}_${timestamp
      .slice(0, 19)
      .replace(/[:-]/g, "")}.csv`;

    exportToCSV({ filename, headers, data: rows });
  }, [
    correlationData,
    xParameter,
    yParameter,
    xMetricConfig,
    yMetricConfig,
    metricType,
    selectedChip,
    timeRange,
    selectionMode,
    statistics,
    exportToCSV,
  ]);

  // Handle metric type change
  const handleMetricTypeChange = useCallback(
    (newType: MetricType) => {
      const newMetrics = newType === "qubit" ? qubitMetrics : couplingMetrics;
      if (newMetrics.length >= 2) {
        setXParameter(newMetrics[0].key);
        setYParameter(newMetrics[1].key);
      } else if (newMetrics.length === 1) {
        setXParameter(newMetrics[0].key);
        setYParameter(newMetrics[0].key);
      }
    },
    [qubitMetrics, couplingMetrics, setXParameter, setYParameter],
  );

  // Error handling with retry
  const handleRetry = useCallback(() => {
    window.location.reload();
  }, []);

  // Same parameter warning
  const isSameParameter = xParameter === yParameter;

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
        title="Failed to load correlation data"
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
            {/* Row 1a: Type + Chip */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <div className="tabs tabs-boxed bg-base-200 h-8 sm:h-9">
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

              <div className="w-28 sm:w-36">
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </div>

              {/* X Parameter Selection - inline */}
              <span className="text-xs sm:text-sm font-medium">X:</span>
              <div className="w-32 sm:w-48">
                <Select<MetricOption, false>
                  className="text-base-content"
                  classNamePrefix="react-select"
                  options={metricOptions}
                  value={
                    metricOptions.find(
                      (option) => option.value === xParameter,
                    ) ?? null
                  }
                  onChange={(option: SingleValue<MetricOption>) => {
                    if (option) {
                      setXParameter(option.value);
                    }
                  }}
                  placeholder="X parameter"
                  isSearchable={false}
                  styles={metricSelectStyles}
                />
              </div>

              {/* Y Parameter Selection - inline */}
              <span className="text-xs sm:text-sm font-medium">Y:</span>
              <div className="w-32 sm:w-48">
                <Select<MetricOption, false>
                  className="text-base-content"
                  classNamePrefix="react-select"
                  options={metricOptions}
                  value={
                    metricOptions.find(
                      (option) => option.value === yParameter,
                    ) ?? null
                  }
                  onChange={(option: SingleValue<MetricOption>) => {
                    if (option) {
                      setYParameter(option.value);
                    }
                  }}
                  placeholder="Y parameter"
                  isSearchable={false}
                  styles={metricSelectStyles}
                />
              </div>
            </div>

            {/* Row 1b: Time Range + Mode + Export */}
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

              <button
                className="btn btn-outline btn-xs sm:btn-sm h-8 sm:h-9 ml-auto sm:ml-0"
                onClick={handleExportCSV}
                disabled={correlationData.length === 0 || isSameParameter}
              >
                Export
              </button>
            </div>
          </div>

          {/* Warning for same parameter */}
          {isSameParameter && xParameter && yParameter && (
            <div className="alert alert-warning py-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="stroke-current shrink-0 h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
              <span className="text-sm">
                Select different parameters for X and Y axes to see correlation
              </span>
            </div>
          )}

          {/* Statistics Display */}
          {statistics && !isSameParameter && (
            <>
              {/* Mobile: Grid layout */}
              <div className="grid grid-cols-2 gap-2 sm:hidden">
                <div className="bg-base-200 rounded-lg p-2 text-center">
                  <div className="text-xs text-base-content/60">
                    Sample Size
                  </div>
                  <div className="text-sm font-bold text-primary">
                    {statistics.sampleSize}
                  </div>
                </div>
                <div className="bg-base-200 rounded-lg p-2 text-center">
                  <div className="text-xs text-base-content/60">
                    Correlation (r)
                  </div>
                  <div
                    className={`text-sm font-bold ${
                      statistics.correlation >= 0.7
                        ? "text-success"
                        : statistics.correlation >= 0.3
                          ? "text-warning"
                          : statistics.correlation <= -0.7
                            ? "text-error"
                            : statistics.correlation <= -0.3
                              ? "text-warning"
                              : "text-info"
                    }`}
                  >
                    {statistics.correlation.toFixed(3)}
                  </div>
                  <div className="text-xs text-base-content/60">
                    {Math.abs(statistics.correlation) >= 0.7
                      ? "Strong"
                      : Math.abs(statistics.correlation) >= 0.3
                        ? "Moderate"
                        : "Weak"}
                  </div>
                </div>
                <div className="bg-base-200 rounded-lg p-2 text-center">
                  <div className="text-xs text-base-content/60 truncate">
                    {xMetricConfig?.title || xParameter}
                  </div>
                  <div className="text-sm font-bold text-secondary">
                    {statistics.xMean.toFixed(2)}
                  </div>
                  <div className="text-xs text-base-content/60">
                    {statistics.xMin.toFixed(1)}-{statistics.xMax.toFixed(1)}
                  </div>
                </div>
                <div className="bg-base-200 rounded-lg p-2 text-center">
                  <div className="text-xs text-base-content/60 truncate">
                    {yMetricConfig?.title || yParameter}
                  </div>
                  <div className="text-sm font-bold text-accent">
                    {statistics.yMean.toFixed(2)}
                  </div>
                  <div className="text-xs text-base-content/60">
                    {statistics.yMin.toFixed(1)}-{statistics.yMax.toFixed(1)}
                  </div>
                </div>
              </div>
              {/* Desktop: Stats component */}
              <div className="stats stats-horizontal shadow w-full hidden sm:inline-grid">
                <div className="stat py-2">
                  <div className="stat-title text-xs">Sample Size</div>
                  <div className="stat-value text-primary text-lg">
                    {statistics.sampleSize}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">Correlation (r)</div>
                  <div
                    className={`stat-value text-lg ${
                      statistics.correlation >= 0.7
                        ? "text-success"
                        : statistics.correlation >= 0.3
                          ? "text-warning"
                          : statistics.correlation <= -0.7
                            ? "text-error"
                            : statistics.correlation <= -0.3
                              ? "text-warning"
                              : "text-info"
                    }`}
                  >
                    {statistics.correlation.toFixed(3)}
                  </div>
                  <div className="stat-desc text-xs">
                    {Math.abs(statistics.correlation) >= 0.7
                      ? "Strong"
                      : Math.abs(statistics.correlation) >= 0.3
                        ? "Moderate"
                        : "Weak"}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">
                    {xMetricConfig?.title || xParameter} (Mean)
                  </div>
                  <div className="stat-value text-secondary text-lg">
                    {statistics.xMean.toFixed(2)}
                  </div>
                  <div className="stat-desc text-xs">
                    Range: {statistics.xMin.toFixed(2)} -{" "}
                    {statistics.xMax.toFixed(2)}
                  </div>
                </div>
                <div className="stat py-2">
                  <div className="stat-title text-xs">
                    {yMetricConfig?.title || yParameter} (Mean)
                  </div>
                  <div className="stat-value text-accent text-lg">
                    {statistics.yMean.toFixed(2)}
                  </div>
                  <div className="stat-desc text-xs">
                    Range: {statistics.yMin.toFixed(2)} -{" "}
                    {statistics.yMax.toFixed(2)}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Plot Section */}
      <PlotCard
        plotData={plotData}
        layout={layout}
        isLoading={isLoading}
        hasData={!isSameParameter && plotData.length > 0}
        emptyStateMessage={
          isSameParameter
            ? "Select different parameters for X and Y axes"
            : !selectedChip
              ? "Select a chip to visualize data"
              : "No correlation data available for selected parameters"
        }
        title="Parameter Correlation Scatter Plot"
      />

      {/* Data Table */}
      {correlationData.length > 0 && !isSameParameter && (
        <div className="card bg-base-100 shadow-md">
          <div className="card-body">
            <DataTable
              title="Correlation Data"
              data={correlationData}
              columns={[
                {
                  key: "entityId",
                  label: metricType === "coupling" ? "Coupling" : "Qubit",
                  sortable: true,
                },
                {
                  key: "xValue",
                  label: `${xMetricConfig?.title || xParameter} (${
                    isPercentageMetric(xMetricConfig?.unit)
                      ? "%"
                      : xMetricConfig?.unit || ""
                  })`,
                  sortable: true,
                  render: (v: number) => v.toFixed(4),
                },
                {
                  key: "yValue",
                  label: `${yMetricConfig?.title || yParameter} (${
                    isPercentageMetric(yMetricConfig?.unit)
                      ? "%"
                      : yMetricConfig?.unit || ""
                  })`,
                  sortable: true,
                  render: (v: number) => v.toFixed(4),
                },
              ]}
              pageSize={20}
            />
          </div>
        </div>
      )}
    </div>
  );
}
