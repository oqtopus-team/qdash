"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

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
import { CooldownSelector } from "@/components/selectors/CooldownSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useMetricsUrlState } from "@/hooks/useUrlState";
import { getDaisySelectStyles } from "@/lib/react-select-theme";
import { toIsoSeconds } from "@/lib/utils/datetime";
import { TimeRangeSelector } from "@/components/ui/TimeRangeSelector";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";

type MetricOption = {
  value: string;
  label: string;
};

const STORAGE_KEY_QUBIT = "qdash:metrics:qubit:metric";
const STORAGE_KEY_COUPLING = "qdash:metrics:coupling:metric";

const saveToLocalStorage = (key: string, value: string) => {
  try {
    if (localStorage.getItem(key) === value) return;
    localStorage.setItem(key, value);
  } catch (error) {
    console.warn("Failed to save to localStorage:", key, error);
  }
};

const getFromLocalStorage = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch (error) {
    console.warn("Failed to read from localStorage:", key, error);
    return null;
  }
};

export function MetricsPageContent() {
  const {
    selectedChip,
    selectionMode,
    metricType,
    selectedMetric,
    startDate,
    endDate,
    setSelectedChip,
    setSelectionMode,
    setMetricType,
    setSelectedMetric,
    isInitialized,
    setStartDate,
    setEndDate,
    setQuickRange,
  } = useMetricsUrlState();
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
  }, [selectedChip, chipsData, setSelectedChip]);

  // Calculate grid size from chip data
  useEffect(() => {
    if (chipData?.data?.size) {
      setGridSize(Math.sqrt(chipData.data.size));
    }
  }, [chipData?.data?.size]);

  const startIso = toIsoSeconds(startDate);
  const endIso = toIsoSeconds(endDate);

  const metricsQueryParams = {
    start_at: startIso,
    end_at: endIso,
    selection_mode: selectionMode,
  };

  const canFetch = !!selectedChip;

  const { data, isLoading, isError } = useGetChipMetrics(
    selectedChip,
    metricsQueryParams,
    {
      query: {
        enabled: canFetch,
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
  }, [isBestModeSupported, selectionMode, setSelectionMode]);

  const selectedMetricRef = useRef(selectedMetric);
  useEffect(() => {
    selectedMetricRef.current = selectedMetric;
  });

  // Save current metric selection to localStorage when it changes
  useEffect(() => {
    if (!isInitialized || isConfigLoading) return;
    if (
      metricType === "qubit" &&
      qubitMetrics.some((m) => m.key === selectedMetric)
    ) {
      saveToLocalStorage(STORAGE_KEY_QUBIT, selectedMetric);
    } else if (
      metricType === "coupling" &&
      couplingMetrics.some((m) => m.key === selectedMetric)
    ) {
      saveToLocalStorage(STORAGE_KEY_COUPLING, selectedMetric);
    }
  }, [
    selectedMetric,
    metricType,
    qubitMetrics,
    couplingMetrics,
    isInitialized,
    isConfigLoading,
  ]);

  // Restore metric from localStorage when metric type changes and current metric is invalid
  useEffect(() => {
    if (!isInitialized || isConfigLoading) return;
    const metrics = metricType === "qubit" ? qubitMetrics : couplingMetrics;
    if (metrics.length === 0) return;
    if (metrics.some((m) => m.key === selectedMetricRef.current)) return;
    const key =
      metricType === "qubit" ? STORAGE_KEY_QUBIT : STORAGE_KEY_COUPLING;
    const defaultMetric =
      metricType === "qubit"
        ? "t1"
        : (couplingMetrics[0]?.key ?? "zx90_gate_fidelity");
    const saved = getFromLocalStorage(key);
    setSelectedMetric(
      saved && metrics.some((m) => m.key === saved) ? saved : defaultMetric,
    );
  }, [
    metricType,
    qubitMetrics,
    couplingMetrics,
    isInitialized,
    isConfigLoading,
    setSelectedMetric,
  ]);

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
        label: metricType === "qubit" ? "Qubit Metrics" : "Coupling Metrics",
        options: metricOptions,
      },
    ],
    [metricOptions, metricType],
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
    Object.entries(rawData).forEach(([key, metricValue]) => {
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
      Object.entries(rawData).forEach(([key, metricValue]) => {
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
                timeRange={`${startDate}..${endDate}`}
                disabled={!selectedChip || isLoading}
              />
              <MetricsPdfDownloadButton
                chipId={selectedChip}
                withinHours={undefined}
                startAt={startIso}
                endAt={endIso}
                selectionMode={selectionMode}
                disabled={!selectedChip || isLoading}
              />
            </div>
          </div>

          {/* Metric Type Tabs */}
          <div className="tabs tabs-boxed bg-base-200 w-fit">
            <button
              className={`tab ${metricType === "qubit" ? "tab-active" : ""}`}
              onClick={() => setMetricType("qubit")}
            >
              Qubit
            </button>
            <button
              className={`tab ${metricType === "coupling" ? "tab-active" : ""}`}
              onClick={() => setMetricType("coupling")}
            >
              Coupling
            </button>
          </div>

          {/* Chip and Metric Selectors */}
          <PageFiltersBar>
            <PageFiltersBar.Group>
              <PageFiltersBar.Item>
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </PageFiltersBar.Item>

              <PageFiltersBar.Item>
                <CooldownSelector
                  chipId={selectedChip}
                  onPick={(cd) => {
                    setRangeMode("absolute");
                    setStartDate(
                      new Date(cd.started_at).toISOString().slice(0, 10),
                    );
                    setEndDate(
                      cd.ended_at
                        ? new Date(cd.ended_at).toISOString().slice(0, 10)
                        : new Date().toISOString().slice(0, 10),
                    );
                  }}
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

          {/* Time Range */}
          <TimeRangeSelector
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            onQuickRange={setQuickRange}
          />

          {/* Latest/Best/Average Toggle */}
          <div className="join rounded-lg overflow-hidden">
            <button
              className={`join-item btn btn-sm ${
                selectionMode === "latest" ? "btn-primary" : ""
              }`}
              onClick={() => setSelectionMode("latest")}
            >
              <span>Latest</span>
            </button>
            <button
              className={`join-item btn btn-sm ${
                selectionMode === "best" ? "btn-primary" : ""
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
                selectionMode === "average" ? "btn-primary" : ""
              }`}
              onClick={() => setSelectionMode("average")}
              title="Show average values within time range"
            >
              <span>Average</span>
            </button>
          </div>
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
                startAt={startIso}
                endAt={endIso}
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
                startAt={startIso}
                endAt={endIso}
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
