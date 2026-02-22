import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString, parseAsInteger } from "nuqs";

import { type TimeRange, type SelectionMode, type MetricType } from "./types";

interface UseMetricsUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  metricType: MetricType;
  selectedMetric: string;
  customDays: number | null;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setMetricType: (type: MetricType) => void;
  setSelectedMetric: (metric: string) => void;
  setCustomDays: (days: number) => void;
  isInitialized: boolean;
}

export function useMetricsUrlState(): UseMetricsUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [metricType, setMetricTypeState] = useQueryState("type", parseAsString);

  const [selectedMetric, setSelectedMetricState] = useQueryState(
    "metric",
    parseAsString,
  );

  const [customDays, setCustomDaysState] = useQueryState(
    "days",
    parseAsInteger,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null);
    },
    [setSelectedChipState],
  );

  const setTimeRange = useCallback(
    (range: TimeRange) => {
      setTimeRangeState(range === "7d" ? null : range);
      // Clear days param when switching away from custom
      if (range !== "custom") {
        setCustomDaysState(null);
      } else if (!customDays) {
        // Set default of 90 days when entering custom mode
        setCustomDaysState(90);
      }
    },
    [setTimeRangeState, setCustomDaysState, customDays],
  );

  const setSelectionMode = useCallback(
    (mode: SelectionMode) => {
      setSelectionModeState(mode === "latest" ? null : mode);
    },
    [setSelectionModeState],
  );

  const setMetricType = useCallback(
    (type: MetricType) => {
      setMetricTypeState(type === "qubit" ? null : type);
    },
    [setMetricTypeState],
  );

  const setSelectedMetric = useCallback(
    (metric: string) => {
      setSelectedMetricState(metric === "t1" ? null : metric);
    },
    [setSelectedMetricState],
  );

  const setCustomDays = useCallback(
    (days: number) => {
      setCustomDaysState(days);
    },
    [setCustomDaysState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    metricType: (metricType as MetricType) ?? "qubit",
    selectedMetric: selectedMetric ?? "t1",
    customDays: customDays ?? null,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setMetricType,
    setSelectedMetric,
    setCustomDays,
    isInitialized,
  };
}
