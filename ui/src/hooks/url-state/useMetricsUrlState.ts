import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { type SelectionMode, type MetricType } from "./types";
import { useRangeModeUrlState } from "./useRangeModeUrlState";

interface UseMetricsUrlStateResult {
  selectedChip: string;
  selectionMode: SelectionMode;
  metricType: MetricType;
  selectedMetric: string;
  startDate: string;
  endDate: string;
  setSelectedChip: (chip: string) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setMetricType: (type: MetricType) => void;
  setSelectedMetric: (metric: string) => void;
  setStartDate: (date: string) => void;
  setEndDate: (date: string) => void;
  setQuickRange: (days: number) => void;
  isInitialized: boolean;
}

export function useMetricsUrlState(): UseMetricsUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  const [selectedChip, setSelectedChipState] = useQueryState("chip", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState("mode", parseAsString);

  const [metricType, setMetricTypeState] = useQueryState("type", parseAsString);

  const [selectedMetric, setSelectedMetricState] = useQueryState("metric", parseAsString);

  const { startDate, endDate, setStartDate, setEndDate, setQuickRange } = useRangeModeUrlState();

  useEffect(() => {
    setIsInitialized(true);
  }, []);

  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null);
    },
    [setSelectedChipState],
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

  return {
    selectedChip: selectedChip ?? "",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    metricType: (metricType as MetricType) ?? "qubit",
    selectedMetric: selectedMetric ?? "t1",
    startDate,
    endDate,
    setSelectedChip,
    setSelectionMode,
    setMetricType,
    setSelectedMetric,
    setStartDate,
    setEndDate,
    setQuickRange,
    isInitialized,
  };
}
