"use client";

import React, { useEffect, useMemo, useState } from "react";

import Select, {
  type GroupBase,
  type SingleValue,
  type StylesConfig,
} from "react-select";

import { QubitMetricsGrid } from "./QubitMetricsGrid";

import { ChipSelector } from "@/app/components/ChipSelector";
import { useListChips } from "@/client/chip/chip";
import { useMetricsGetChipMetrics } from "@/client/metrics/metrics";

type TimeRange = "1d" | "7d" | "30d";

type MetricConfig = {
  key: string;
  title: string;
  unit: string;
  scale: number;
  colorScale: {
    min: number;
    max: number;
    colors: string[];
  };
};

type MetricOption = {
  value: string;
  label: string;
};

// Unified color scale (Viridis-like)
const UNIFIED_COLORS = [
  "bg-[#440154]", // Dark purple
  "bg-[#31688e]", // Blue
  "bg-[#35b779]", // Green
  "bg-[#fde724]", // Yellow
];

export function MetricsPageContent() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [selectedMetric, setSelectedMetric] = useState<string>("t1");

  const { data: chipsData } = useListChips();

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

  // Metrics configuration with auto-adjusted colorscale
  const metricsConfig: MetricConfig[] = [
    {
      key: "qubit_frequency",
      title: "Qubit Frequency",
      unit: "GHz",
      scale: 1,
      colorScale: { min: 0, max: 0, colors: UNIFIED_COLORS }, // Auto-adjusted
    },
    {
      key: "anharmonicity",
      title: "Qubit Anharmonicity",
      unit: "MHz",
      scale: 1e3,
      colorScale: { min: 0, max: 0, colors: UNIFIED_COLORS }, // Auto-adjusted
    },
    {
      key: "t1",
      title: "T1",
      unit: "μs",
      scale: 1, // Data is already in μs
      colorScale: { min: 0, max: 0, colors: UNIFIED_COLORS }, // Auto-adjusted
    },
    {
      key: "t2_echo",
      title: "T2 Echo",
      unit: "μs",
      scale: 1, // Data is already in μs
      colorScale: { min: 0, max: 0, colors: UNIFIED_COLORS }, // Auto-adjusted
    },
    {
      key: "average_readout_fidelity",
      title: "Average Readout Fidelity",
      unit: "%",
      scale: 100,
      colorScale: { min: 0, max: 0, colors: UNIFIED_COLORS }, // Auto-adjusted
    },
    {
      key: "x90_gate_fidelity",
      title: "X90 Gate Fidelity",
      unit: "%",
      scale: 100,
      colorScale: { min: 0, max: 0, colors: UNIFIED_COLORS }, // Auto-adjusted
    },
  ];

  const currentMetricConfig = metricsConfig.find(
    (m) => m.key === selectedMetric,
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
    if (!data?.data?.qubit_metrics || !currentMetricConfig) return null;

    const rawData =
      data.data.qubit_metrics[
        currentMetricConfig.key as keyof typeof data.data.qubit_metrics
      ];

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
      const qid = key.startsWith("Q") ? key : `Q${key.padStart(2, "0")}`;
      const value = metricValue?.value;
      scaledData[qid] = {
        value:
          value !== null && value !== undefined && typeof value === "number"
            ? value * currentMetricConfig.scale
            : null,
        task_id: metricValue?.task_id,
        execution_id: metricValue?.execution_id,
      };
    });

    return scaledData;
  }, [data, currentMetricConfig]);

  return (
    <div className="w-full min-h-screen bg-base-100/50 px-4 md:px-6 py-6 md:py-8">
      <div className="h-full flex flex-col space-y-4 md:space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-4 md:gap-6">
          <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4">
            <h1 className="text-xl md:text-2xl font-bold">
              Chip Metrics Dashboard
            </h1>

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
          </div>

          {/* Chip Selector and Metric Selector */}
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
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
        ) : isError ? (
          <div className="alert alert-error">
            <span>Failed to load metrics data</span>
          </div>
        ) : currentMetricConfig ? (
          <QubitMetricsGrid
            metricData={metricData}
            title={currentMetricConfig.title}
            metricKey={currentMetricConfig.key}
            unit={currentMetricConfig.unit}
            colorScale={currentMetricConfig.colorScale}
            chipId={selectedChip}
            selectedDate="latest"
          />
        ) : (
          <div className="alert alert-info">
            <span>Select a metric to display</span>
          </div>
        )}
      </div>
    </div>
  );
}
