import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString, parseAsInteger } from "nuqs";

import {
  type TimeRange,
  type RangeMode,
  type SelectionMode,
  type MetricType,
} from "./types";

interface UseMetricsUrlStateResult {
  selectedChip: string;
  rangeMode: RangeMode;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  metricType: MetricType;
  selectedMetric: string;
  customDays: number | null;
  startDate: string | null;
  endDate: string | null;
  setSelectedChip: (chip: string) => void;
  setRangeMode: (mode: RangeMode) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setMetricType: (type: MetricType) => void;
  setSelectedMetric: (metric: string) => void;
  setCustomDays: (days: number) => void;
  setStartDate: (date: string | null) => void;
  setEndDate: (date: string | null) => void;
  isInitialized: boolean;
}

export function useMetricsUrlState(): UseMetricsUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [rangeMode, setRangeModeState] = useQueryState(
    "rangeMode",
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

  const [startDate, setStartDateState] = useQueryState("start", parseAsString);
  const [endDate, setEndDateState] = useQueryState("end", parseAsString);

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

  const setRangeMode = useCallback(
    (mode: RangeMode) => {
      setRangeModeState(mode === "relative" ? null : mode);
      // Clear the inactive mode's params to keep URLs clean.
      if (mode === "relative") {
        setStartDateState(null);
        setEndDateState(null);
      } else {
        setTimeRangeState(null);
        setCustomDaysState(null);
        // Seed a 7-day range (from = 6 days ago, to = today) on the first
        // switch to absolute mode, unless the user already has dates set.
        if (!startDate && !endDate) {
          const today = new Date();
          const sixDaysAgo = new Date();
          sixDaysAgo.setDate(today.getDate() - 6);
          const toIso = (d: Date) => {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            return `${y}-${m}-${day}`;
          };
          setStartDateState(toIso(sixDaysAgo));
          setEndDateState(toIso(today));
        }
      }
    },
    [
      setRangeModeState,
      setStartDateState,
      setEndDateState,
      setTimeRangeState,
      setCustomDaysState,
      startDate,
      endDate,
    ],
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

  const setStartDate = useCallback(
    (date: string | null) => {
      setStartDateState(date && date.length > 0 ? date : null);
    },
    [setStartDateState],
  );

  const setEndDate = useCallback(
    (date: string | null) => {
      setEndDateState(date && date.length > 0 ? date : null);
    },
    [setEndDateState],
  );

  return {
    selectedChip: selectedChip ?? "",
    rangeMode: (rangeMode as RangeMode) ?? "relative",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    metricType: (metricType as MetricType) ?? "qubit",
    selectedMetric: selectedMetric ?? "t1",
    customDays: customDays ?? null,
    startDate: startDate ?? null,
    endDate: endDate ?? null,
    setSelectedChip,
    setRangeMode,
    setTimeRange,
    setSelectionMode,
    setMetricType,
    setSelectedMetric,
    setCustomDays,
    setStartDate,
    setEndDate,
    isInitialized,
  };
}
