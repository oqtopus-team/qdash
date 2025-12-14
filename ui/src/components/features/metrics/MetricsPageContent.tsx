"use client";

import React, { useEffect, useMemo, useState } from "react";

import Select, {
  type GroupBase,
  type SingleValue,
  type StylesConfig,
} from "react-select";

import { CouplingMetricsGrid } from "./CouplingMetricsGrid";
import { MetricsCdfChart } from "./MetricsCdfChart";
import { MetricsPdfDownloadButton } from "./MetricsPdfDownloadButton";
import { MetricsStatsCards } from "./MetricsStatsCards";
import { QubitMetricsGrid } from "./QubitMetricsGrid";

import { useListChips, useGetChip } from "@/client/chip/chip";
import { useGetChipMetrics } from "@/client/metrics/metrics";
import { useGetTopologyById } from "@/client/topology/topology";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useCopilotConfig } from "@/hooks/useCopilotConfig";
import {
  COPILOT_ENABLED,
  MetricsCopilot,
  useMetricsCopilot,
} from "@/features/copilot";

type TimeRange = "1d" | "7d" | "30d";
type SelectionMode = "latest" | "best";

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

  // Load Copilot configuration
  const { config: aiConfig } = useCopilotConfig();

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

  // Fetch topology data for Copilot spatial analysis
  const { data: topologyResponse } = useGetTopologyById(topologyId, {
    query: {
      enabled: !!topologyId,
      staleTime: Infinity,
    },
  });

  // Extract topology data for Copilot
  const topologyData = useMemo(() => {
    // The API returns { data: TopologyDefinition }
    const responseData = topologyResponse?.data as { data?: Record<string, unknown> } | undefined;
    const data = responseData?.data;
    if (!data) return null;
    return {
      id: data.id as string,
      name: data.name as string,
      grid_size: data.grid_size as number,
      num_qubits: data.num_qubits as number,
      qubits: data.qubits as Record<string, { row: number; col: number }>,
      couplings: data.couplings as number[][],
    };
  }, [topologyResponse]);

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

  const metricSelectStyles = useMemo<StylesConfig<MetricOption, false>>(
    () => ({
      control: (provided) => ({
        ...provided,
        minHeight: 36,
        height: 36,
      }),
      valueContainer: (provided) => ({
        ...provided,
        padding: "2px 8px",
      }),
      indicatorsContainer: (provided) => ({
        ...provided,
        height: 36,
      }),
      menu: (provided) => ({
        ...provided,
        zIndex: 20,
      }),
    }),
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
      };
    } = {};
    Object.entries(rawData).forEach(([key, metricValue]: [string, any]) => {
      // For qubit metrics, format as "Q00", for coupling metrics keep "0-1" format
      const formattedKey =
        metricType === "qubit"
          ? key.startsWith("Q")
            ? key
            : `Q${key.padStart(2, "0")}`
          : key;
      const value = metricValue?.value;
      scaledData[formattedKey] = {
        value:
          value !== null && value !== undefined && typeof value === "number"
            ? value * currentMetricConfig.scale
            : null,
        task_id: metricValue?.task_id,
        execution_id: metricValue?.execution_id,
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
              ? key
              : `Q${key.padStart(2, "0")}`
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

  // CopilotKit integration for AI-assisted analysis
  useMetricsCopilot({
    chipId: selectedChip,
    metricType,
    selectedMetric,
    metricsConfig,
    metricData,
    allMetricsData,
    timeRange,
    selectionMode,
    aiConfig,
    topologyData,
    onMetricChange: setSelectedMetric,
    onTimeRangeChange: (range) => setTimeRange(range as TimeRange),
  });

  // Show skeleton during initial loading
  if (isConfigLoading || isChipsLoading) {
    return <MetricsPageSkeleton />;
  }

  return (
    <PageContainer>
      <div className="h-full flex flex-col space-y-4 md:space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-4 md:gap-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <PageHeader
              title="Chip Metrics Dashboard"
              description="View and compare qubit performance metrics"
              className="mb-0"
            />
            <MetricsPdfDownloadButton
              chipId={selectedChip}
              withinHours={withinHours}
              selectionMode={selectionMode}
              disabled={!selectedChip || isLoading}
            />
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
          <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4">
            <div className="flex flex-col sm:flex-row gap-4 flex-shrink-0">
              {/* Time Range Selector */}
              <div className="join rounded-lg overflow-hidden">
                <button
                  className={`join-item btn btn-sm ${
                    timeRange === "1d" ? "btn-active" : ""
                  }`}
                  onClick={() => setTimeRange("1d")}
                >
                  <span>Last 1 Day</span>
                </button>
                <button
                  className={`join-item btn btn-sm ${
                    timeRange === "7d" ? "btn-active" : ""
                  }`}
                  onClick={() => setTimeRange("7d")}
                >
                  <span>Last 7 Days</span>
                </button>
                <button
                  className={`join-item btn btn-sm ${
                    timeRange === "30d" ? "btn-active" : ""
                  }`}
                  onClick={() => setTimeRange("30d")}
                >
                  <span>Last 30 Days</span>
                </button>
              </div>

              {/* Latest/Best Toggle */}
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
              </div>
            </div>

            <div className="w-full sm:w-auto">
              <ChipSelector
                selectedChip={selectedChip}
                onChipSelect={setSelectedChip}
              />
            </div>

            <div className="w-full sm:w-auto">
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
            </div>
          </div>
        </div>

        {/* Metrics Grid */}
        {!selectedChip ? (
          <div className="alert alert-info">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="stroke-current shrink-0 w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Select a chip to view metrics</span>
          </div>
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
          <div className="alert alert-error">
            <span>Failed to load metrics configuration</span>
          </div>
        ) : isError ? (
          <div className="alert alert-error">
            <span>Failed to load metrics data</span>
          </div>
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

            {/* CDF Chart for current metric's group */}
            {currentCdfGroup && (
              <MetricsCdfChart
                metricsData={
                  currentCdfGroup.metrics
                    .map((metricKey) => {
                      const config = metricsConfig.find(
                        (m) => m.key === metricKey,
                      );
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
                topologyId={
                  chipData?.data?.topology_id ??
                  `square-lattice-mux-${chipData?.data?.size ?? 64}`
                }
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
                topologyId={
                  chipData?.data?.topology_id ??
                  `square-lattice-mux-${chipData?.data?.size ?? 64}`
                }
                selectedDate="latest"
              />
            )}
          </>
        ) : (
          <div className="alert alert-info">
            <span>Select a metric to display</span>
          </div>
        )}
      </div>

      {/* AI Analysis Assistant */}
      {COPILOT_ENABLED && (
        <div className="fixed bottom-6 right-6 z-50">
          <MetricsCopilot aiConfig={aiConfig} />
        </div>
      )}
    </PageContainer>
  );
}
