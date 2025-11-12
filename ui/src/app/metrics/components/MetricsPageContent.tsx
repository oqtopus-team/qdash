"use client";

import React, { useEffect, useMemo, useState } from "react";

import Select, {
  type GroupBase,
  type SingleValue,
  type StylesConfig,
} from "react-select";

import { CouplingMetricsGrid } from "./CouplingMetricsGrid";
import { QubitMetricsGrid } from "./QubitMetricsGrid";

import { ChipSelector } from "@/app/components/ChipSelector";
import { useListChips, useFetchChip } from "@/client/chip/chip";
import { useMetricsGetChipMetrics } from "@/client/metrics/metrics";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";

type TimeRange = "1d" | "7d" | "30d";

type MetricOption = {
  value: string;
  label: string;
};

type MetricType = "qubit" | "coupling";

export function MetricsPageContent() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [metricType, setMetricType] = useState<MetricType>("qubit");
  const [selectedMetric, setSelectedMetric] = useState<string>("t1");
  const [gridSize, setGridSize] = useState<number>(8);

  // Load metrics configuration from backend
  const {
    qubitMetrics,
    couplingMetrics,
    colorScale,
    isLoading: isConfigLoading,
    isError: isConfigError,
  } = useMetricsConfig();

  // Select appropriate metrics config based on type
  const metricsConfig = metricType === "qubit" ? qubitMetrics : couplingMetrics;

  const { data: chipsData } = useListChips();
  const { data: chipData } = useFetchChip(selectedChip);

  // Set default chip when data loads
  useEffect(() => {
    if (!selectedChip && chipsData?.data && chipsData.data.length > 0) {
      const sortedChips = [...chipsData.data].sort((a, b) => {
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
  const { data, isLoading, isError } = useMetricsGetChipMetrics(
    selectedChip,
    withinHours ? { within_hours: withinHours } : undefined,
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
        label: "Single-Qubit Metrics",
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

  return (
    <div className="w-full min-h-screen bg-base-100/50 px-4 md:px-6 py-6 md:py-8">
      <div className="h-full flex flex-col space-y-4 md:space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-4 md:gap-6">
          <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4">
            <h1 className="text-xl md:text-2xl font-bold">
              Chip Metrics Dashboard
            </h1>
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
              Single-Qubit Metrics
            </button>
            <button
              className={`tab ${metricType === "coupling" ? "tab-active" : ""}`}
              onClick={() => {
                setMetricType("coupling");
                setSelectedMetric("zx90_gate_fidelity"); // Reset to default coupling metric
              }}
            >
              Two-Qubit Metrics
            </button>
          </div>

          {/* Time Range Selector and Chip Selector Row */}
          <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4">
            {/* Time Range Selector */}
            <div className="join rounded-lg overflow-hidden flex-shrink-0">
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

            <div className="flex flex-col gap-1 w-full sm:w-auto">
              <ChipSelector
                selectedChip={selectedChip}
                onChipSelect={setSelectedChip}
              />
            </div>

            <div className="flex flex-col gap-1 w-full sm:w-auto">
              <label className="text-xs text-base-content/60 font-medium">
                Metric
              </label>
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
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        ) : isConfigLoading ? (
          <div className="flex items-center justify-center h-96">
            <span className="loading loading-spinner loading-lg"></span>
            <span className="ml-2">Loading metrics configuration...</span>
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
          metricType === "qubit" ? (
            <QubitMetricsGrid
              metricData={metricData}
              title={currentMetricConfig.title}
              metricKey={currentMetricConfig.key}
              unit={currentMetricConfig.unit}
              colorScale={{ min: 0, max: 0, colors: hexColors }}
              gridSize={gridSize}
              chipId={selectedChip}
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
              selectedDate="latest"
            />
          )
        ) : (
          <div className="alert alert-info">
            <span>Select a metric to display</span>
          </div>
        )}
      </div>
    </div>
  );
}
