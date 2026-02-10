"use client";

import React, { useEffect, useMemo, useState } from "react";

import Select, { type GroupBase, type SingleValue } from "react-select";

import { CouplingMetricsGrid } from "./CouplingMetricsGrid";
import { MetricsCdfChart } from "./MetricsCdfChart";
import { MetricsPdfDownloadButton } from "./MetricsPdfDownloadButton";
import { MetricsYamlDownloadButton } from "./MetricsYamlDownloadButton";
import { MetricsStatsCards, useMetricStats } from "./MetricsStatsCards";
import { QubitMetricsGrid } from "./QubitMetricsGrid";
import { LinearGauge } from "@/components/ui/LinearGauge";

import { useListChips, useGetChip } from "@/client/chip/chip";
import { useGetChipMetrics } from "@/client/metrics/metrics";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useChatMetrics } from "@/hooks/useChatMetrics";
import { getDaisySelectStyles } from "@/lib/reactSelectTheme";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";

type TimeRange = "1d" | "7d" | "30d";
type SelectionMode = "latest" | "best" | "average";

type MetricOption = {
  value: string;
  label: string;
};

type MetricType = "qubit" | "coupling";

export function MetricsPageContent() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("latest");
  const [metricType, setMetricType] = useState<MetricType>("qubit");
  const [selectedMetric, setSelectedMetric] = useState<string>("t1");
  const [gridSize, setGridSize] = useState<number>(8);

  // Load metrics configuration from backend
  const {
    qubitMetrics,
    couplingMetrics,
    colorScale,
    cdfGroups,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  // Select appropriate metrics config based on type
  const metricsConfig = metricType === "qubit" ? qubitMetrics : couplingMetrics;

  const { data: chipsData, isLoading: isChipsLoading } = useListChips();
  const { data: chipData } = useGetChip(selectedChip);

  // Get topology ID from chip data
  const topologyId = useMemo(() => {
    return (
      chipData?.data?.topology_id ??
      `square-lattice-mux-${chipData?.data?.size ?? 64}`
    );
  }, [chipData?.data?.topology_id, chipData?.data?.size]);

  // Set default chip when data loads
  useEffect(() => {
    if (
      !selectedChip &&
      chipsData?.data?.chips &&
      chipsData.data.chips.length > 0
    ) {
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [selectedChip, chipsData]);

  // Calculate grid size from chip data
  useEffect(() => {
    if (chipData?.data?.size) {
      setGridSize(Math.sqrt(chipData.data.size));
    }
  }, [chipData?.data?.size]);

  // Fetch metrics data
  const withinHours =
    timeRange === "1d"
      ? 24
      : timeRange === "7d"
        ? 24 * 7
        : timeRange === "30d"
          ? 24 * 30
          : 24 * 7; // Default to 7 days
  const { data, isLoading, isError } = useGetChipMetrics(
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

  // Get color scale as hex values for inline styles
  const hexColors = useMemo(() => {
    if (!colorScale.colors || colorScale.colors.length === 0) {
      // Fallback to default Viridis-like colors
      return [
        "#440154", // Dark purple
        "#31688e", // Blue
        "#35b779", // Green
        "#fde724", // Yellow
      ];
    }
    return colorScale.colors;
  }, [colorScale]);

  const currentMetricConfig = useMemo(
    () => metricsConfig.find((m) => m.key === selectedMetric),
    [metricsConfig, selectedMetric],
  );

  // Check if current metric supports best mode
  const isBestModeSupported = useMemo(
    () => currentMetricConfig?.evaluationMode !== "none",
    [currentMetricConfig],
  );

  // Auto-switch to latest mode when metric doesn't support best mode
  useEffect(() => {
    if (!isBestModeSupported && selectionMode === "best") {
      setSelectionMode("latest");
    }
  }, [isBestModeSupported, selectionMode]);

  const metricOptions: MetricOption[] = useMemo(
    () =>
      metricsConfig.map((metric) => ({
        value: metric.key,
        label: metric.title,
      })),
    [metricsConfig],
  );

  const groupedMetricOptions: GroupBase<MetricOption>[] = useMemo(
    () => [
      {
        label: "Qubit Metrics",
        options: metricOptions,
      },
    ],
    [metricOptions],
  );

  // Use shared DaisyUI-compatible styles for React-Select
  const metricSelectStyles = useMemo(
    () => getDaisySelectStyles<MetricOption, false, GroupBase<MetricOption>>(),
    [],
  );

  // Process metric data
  const metricData = useMemo(() => {
    if (!data?.data || !currentMetricConfig) return null;

    const metricsSource =
      metricType === "qubit"
        ? data.data.qubit_metrics
        : data.data.coupling_metrics;

    if (!metricsSource) return null;

    const rawData =
      metricsSource[currentMetricConfig.key as keyof typeof metricsSource];

    if (!rawData) return null;

    // Convert keys and apply scale, preserving metadata
    const scaledData: {
      [key: string]: {
        value: number | null;
        task_id?: string | null;
        execution_id?: string | null;
        stddev?: number | null;
      };
    } = {};
    Object.entries(rawData).forEach(([key, metricValue]: [string, any]) => {
      // Use simple numeric format for qubit metrics (e.g., "0", "1"), keep "0-1" format for coupling
      const formattedKey =
        metricType === "qubit"
          ? key.startsWith("Q")
            ? String(parseInt(key.slice(1), 10))
            : String(parseInt(key, 10))
          : key;
      const value = metricValue?.value;
      const stddev = metricValue?.stddev;
      scaledData[formattedKey] = {
        value:
          value !== null && value !== undefined && typeof value === "number"
            ? value * currentMetricConfig.scale
            : null,
        task_id: metricValue?.task_id,
        execution_id: metricValue?.execution_id,
        stddev:
          stddev !== null && stddev !== undefined && typeof stddev === "number"
            ? stddev * currentMetricConfig.scale
            : null,
      };
    });

    return scaledData;
  }, [data, currentMetricConfig, metricType]);

  // Process all metrics data for CDF groups
  const allMetricsData = useMemo(() => {
    if (!data?.data) return {};

    const metricsSource =
      metricType === "qubit"
        ? data.data.qubit_metrics
        : data.data.coupling_metrics;

    if (!metricsSource) return {};

    const result: Record<string, { [key: string]: { value: number | null } }> =
      {};

    const configList = metricType === "qubit" ? qubitMetrics : couplingMetrics;

    configList.forEach((metricConfig) => {
      const rawData =
        metricsSource[metricConfig.key as keyof typeof metricsSource];
      if (!rawData) return;

      const scaledData: { [key: string]: { value: number | null } } = {};
      Object.entries(rawData).forEach(([key, metricValue]: [string, any]) => {
        const formattedKey =
          metricType === "qubit"
            ? key.startsWith("Q")
              ? String(parseInt(key.slice(1), 10))
              : String(parseInt(key, 10))
            : key;
        const value = metricValue?.value;
        scaledData[formattedKey] = {
          value:
            value !== null && value !== undefined && typeof value === "number"
              ? value * metricConfig.scale
              : null,
        };
      });
      result[metricConfig.key] = scaledData;
    });

    return result;
  }, [data, metricType, qubitMetrics, couplingMetrics]);

  // Get CDF group that contains the selected metric
  const currentCdfGroup = useMemo(() => {
    const groups =
      metricType === "qubit" ? cdfGroups.qubit : cdfGroups.coupling;
    return (
      groups.find((group) => group.metrics.includes(selectedMetric)) || null
    );
  }, [metricType, cdfGroups, selectedMetric]);

  // Chat integration for AI-assisted analysis
  useChatMetrics({
    chipId: selectedChip,
    metricType,
    selectedMetric,
    metricsConfig,
    metricData,
    timeRange,
    onMetricChange: setSelectedMetric,
    onTimeRangeChange: (range) => setTimeRange(range as TimeRange),
  });

  // Show skeleton during initial loading
  if (isConfigLoading || isChipsLoading) {
    return <MetricsPageSkeleton />;
  }

  return (
    <PageContainer>
      <div className="h-full flex flex-col space-y-3 md:space-y-4">
        {/* Header Section */}
        <div className="flex flex-col gap-3 md:gap-4">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <PageHeader
              title="Chip Metrics Dashboard"
              description="View and compare qubit performance metrics"
              className="mb-0"
            />
            <div className="flex items-start gap-2">
              <MetricsYamlDownloadButton
                chipId={selectedChip}
                metricData={metricData}
                metricConfig={currentMetricConfig}
                selectionMode={selectionMode}
                timeRange={timeRange}
                disabled={!selectedChip || isLoading}
              />
              <MetricsPdfDownloadButton
                chipId={selectedChip}
                withinHours={withinHours}
                selectionMode={selectionMode}
                disabled={!selectedChip || isLoading}
              />
            </div>
          </div>

          {/* Metric Type Tabs */}
          <div className="tabs tabs-boxed bg-base-200 w-fit">
            <button
              className={`tab ${metricType === "qubit" ? "tab-active" : ""}`}
              onClick={() => {
                setMetricType("qubit");
                setSelectedMetric("t1"); // Reset to default qubit metric
              }}
            >
              Qubit
            </button>
            <button
              className={`tab ${metricType === "coupling" ? "tab-active" : ""}`}
              onClick={() => {
                setMetricType("coupling");
                setSelectedMetric("zx90_gate_fidelity"); // Reset to default coupling metric
              }}
            >
              Coupling
            </button>
          </div>

          {/* Time Range and Selection Mode Row */}
          <PageFiltersBar>
            <PageFiltersBar.Group>
              {/* Time Range Selector */}
              <PageFiltersBar.Item>
                <div className="join rounded-lg overflow-hidden">
                  <button
                    className={`join-item btn btn-sm ${
                      timeRange === "1d" ? "btn-active" : ""
                    }`}
                    onClick={() => setTimeRange("1d")}
                  >
                    <span className="hidden sm:inline">Last 1 Day</span>
                    <span className="sm:hidden">1D</span>
                  </button>
                  <button
                    className={`join-item btn btn-sm ${
                      timeRange === "7d" ? "btn-active" : ""
                    }`}
                    onClick={() => setTimeRange("7d")}
                  >
                    <span className="hidden sm:inline">Last 7 Days</span>
                    <span className="sm:hidden">7D</span>
                  </button>
                  <button
                    className={`join-item btn btn-sm ${
                      timeRange === "30d" ? "btn-active" : ""
                    }`}
                    onClick={() => setTimeRange("30d")}
                  >
                    <span className="hidden sm:inline">Last 30 Days</span>
                    <span className="sm:hidden">30D</span>
                  </button>
                </div>
              </PageFiltersBar.Item>

              {/* Latest/Best Toggle */}
              <PageFiltersBar.Item>
                <div className="join rounded-lg overflow-hidden">
                  <button
                    className={`join-item btn btn-sm ${
                      selectionMode === "latest" ? "btn-active" : ""
                    }`}
                    onClick={() => setSelectionMode("latest")}
                  >
                    <span>Latest</span>
                  </button>
                  <button
                    className={`join-item btn btn-sm ${
                      selectionMode === "best" ? "btn-active" : ""
                    } ${!isBestModeSupported ? "btn-disabled" : ""}`}
                    onClick={() => setSelectionMode("best")}
                    disabled={!isBestModeSupported}
                    title={
                      !isBestModeSupported
                        ? "Best mode not available for this metric"
                        : "Show best values within time range"
                    }
                  >
                    <span>Best</span>
                  </button>
                  <button
                    className={`join-item btn btn-sm ${
                      selectionMode === "average" ? "btn-active" : ""
                    }`}
                    onClick={() => setSelectionMode("average")}
                    title="Show average values within time range"
                  >
                    <span>Average</span>
                  </button>
                </div>
              </PageFiltersBar.Item>
            </PageFiltersBar.Group>

            <PageFiltersBar.Group position="end">
              <PageFiltersBar.Item>
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </PageFiltersBar.Item>

              <PageFiltersBar.Item>
                <Select<MetricOption, false, GroupBase<MetricOption>>
                  className="w-full sm:w-64 text-base-content"
                  classNamePrefix="react-select"
                  options={groupedMetricOptions}
                  value={
                    metricOptions.find(
                      (option) => option.value === selectedMetric,
                    ) ?? null
                  }
                  onChange={(option: SingleValue<MetricOption>) => {
                    if (option) {
                      setSelectedMetric(option.value);
                    }
                  }}
                  placeholder="Select a metric"
                  isSearchable={false}
                  styles={metricSelectStyles}
                />
              </PageFiltersBar.Item>
            </PageFiltersBar.Group>
          </PageFiltersBar>
        </div>

        {/* Metrics Grid */}
        {!selectedChip ? (
          <EmptyState
            title="No chip selected"
            description="Select a chip from the dropdown above to view metrics"
            emoji="microchip"
            size="lg"
          />
        ) : isLoading ? (
          <div className="flex items-center justify-center h-96">
            <QuantumLoader
              size="lg"
              showLabel
              label="Loading metrics data..."
            />
          </div>
        ) : isConfigLoading ? (
          <div className="flex items-center justify-center h-96">
            <QuantumLoader
              size="lg"
              showLabel
              label="Loading metrics configuration..."
            />
          </div>
        ) : isConfigError ? (
          <EmptyState
            title="Configuration error"
            description="Failed to load metrics configuration. Please try refreshing the page."
            emoji="warning"
            size="lg"
          />
        ) : isError ? (
          <EmptyState
            title="Data loading failed"
            description="Failed to load metrics data. Please try again later."
            emoji="warning"
            size="lg"
          />
        ) : currentMetricConfig ? (
          <>
            {/* Metric Title */}
            <div className="flex items-center gap-3">
              <h2 className="text-xl md:text-2xl font-bold">
                {currentMetricConfig.title}
              </h2>
              <span className="badge badge-outline badge-sm">
                {currentMetricConfig.unit}
              </span>
            </div>

            {/* Stats Summary Cards */}
            <MetricsStatsCards
              metricData={metricData}
              title={currentMetricConfig.title}
              unit={currentMetricConfig.unit}
              gridSize={gridSize}
              metricType={metricType}
            />

            {/* CDF Chart + Coverage Progress */}
            {currentCdfGroup && (
              <CdfWithCoverage
                currentCdfGroup={currentCdfGroup}
                metricsConfig={metricsConfig}
                allMetricsData={allMetricsData}
                metricData={metricData}
                gridSize={gridSize}
                metricType={metricType}
              />
            )}

            {/* Metric Grid */}
            {metricType === "qubit" ? (
              <QubitMetricsGrid
                metricData={metricData}
                title={currentMetricConfig.title}
                metricKey={currentMetricConfig.key}
                unit={currentMetricConfig.unit}
                colorScale={{ min: 0, max: 0, colors: hexColors }}
                gridSize={gridSize}
                chipId={selectedChip}
                topologyId={topologyId}
                selectedDate="latest"
              />
            ) : (
              <CouplingMetricsGrid
                metricData={metricData}
                title={currentMetricConfig.title}
                metricKey={currentMetricConfig.key}
                unit={currentMetricConfig.unit}
                colorScale={{ min: 0, max: 0, colors: hexColors }}
                gridSize={gridSize}
                chipId={selectedChip}
                topologyId={topologyId}
                selectedDate="latest"
              />
            )}
          </>
        ) : (
          <EmptyState
            title="No metric selected"
            description="Select a metric from the dropdown to display data"
            emoji="chart-bar"
            size="lg"
          />
        )}
      </div>
    </PageContainer>
  );
}

// CDF Chart with Coverage Progress side by side
interface CdfWithCoverageProps {
  currentCdfGroup: {
    title: string;
    unit: string;
    metrics: string[];
  };
  metricsConfig: { key: string; title: string }[];
  allMetricsData: Record<
    string,
    { [key: string]: { value: number | null } } | null
  >;
  metricData: { [key: string]: { value: number | null } } | null;
  gridSize: number;
  metricType: "qubit" | "coupling";
}

function CdfWithCoverage({
  currentCdfGroup,
  metricsConfig,
  allMetricsData,
  metricData,
  gridSize,
  metricType,
}: CdfWithCoverageProps) {
  const stats = useMetricStats(metricData, gridSize, metricType);

  return (
    <div className="space-y-2">
      {/* Linear Gauge for Coverage */}
      <Card variant="compact" padding="sm">
        <LinearGauge
          value={stats.coverage}
          current={stats.withData}
          total={stats.total}
          duration={800}
        />
      </Card>

      {/* CDF Chart */}
      <MetricsCdfChart
        metricsData={
          currentCdfGroup.metrics
            .map((metricKey) => {
              const config = metricsConfig.find((m) => m.key === metricKey);
              return config
                ? {
                    key: metricKey,
                    title: config.title,
                    data: allMetricsData[metricKey] || null,
                  }
                : null;
            })
            .filter(Boolean) as {
            key: string;
            title: string;
            data: { [key: string]: { value: number | null } } | null;
          }[]
        }
        groupTitle={currentCdfGroup.title}
        unit={currentCdfGroup.unit}
      />
    </div>
  );
}
