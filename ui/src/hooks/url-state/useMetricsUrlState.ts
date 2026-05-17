import { useCallback, useMemo, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { dateToDateTimeLocal } from "@/lib/utils/datetime";

import { type SelectionMode, type MetricType } from "./types";

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

  const [startDate, setStartDateState] = useQueryState("start", parseAsString);
  const [endDate, setEndDateState] = useQueryState("end", parseAsString);

  const defaults = useMemo(() => {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return {
      start: dateToDateTimeLocal(sevenDaysAgo),
      end: dateToDateTimeLocal(now),
    };
  }, []);

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

  const setStartDate = useCallback(
    (date: string) => {
      setStartDateState(date && date.length > 0 ? date : null);
    },
    [setStartDateState],
  );

  const setEndDate = useCallback(
    (date: string) => {
      setEndDateState(date && date.length > 0 ? date : null);
    },
    [setEndDateState],
  );

  const setQuickRange = useCallback(
    (days: number) => {
      const now = new Date();
      const past = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
      setStartDateState(dateToDateTimeLocal(past));
      setEndDateState(dateToDateTimeLocal(now));
    },
    [setStartDateState, setEndDateState],
  );

  return {
    selectedChip: selectedChip ?? "",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    metricType: (metricType as MetricType) ?? "qubit",
    selectedMetric: selectedMetric ?? "t1",
    startDate: startDate ?? defaults.start,
    endDate: endDate ?? defaults.end,
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
