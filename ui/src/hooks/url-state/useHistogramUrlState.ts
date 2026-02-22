import { useCallback, useState, useEffect } from "react";

import {
  useQueryState,
  parseAsString,
  parseAsBoolean,
  parseAsFloat,
} from "nuqs";

import { URL_DEFAULTS, type TimeRange, type SelectionMode } from "./types";

export interface UseHistogramUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  selectedParameter: string;
  showAsErrorRate: boolean;
  customThreshold: number | null;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setSelectedParameter: (parameter: string) => void;
  setShowAsErrorRate: (show: boolean) => void;
  setCustomThreshold: (threshold: number | null) => void;
  isInitialized: boolean;
}

export function useHistogramUrlState(): UseHistogramUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [selectedParameter, setSelectedParameterState] = useQueryState(
    "param",
    parseAsString,
  );

  const [showAsErrorRate, setShowAsErrorRateState] = useQueryState(
    "errorRate",
    parseAsBoolean,
  );

  const [customThreshold, setCustomThresholdState] = useQueryState(
    "threshold",
    parseAsFloat,
  );

  // Initialize state on mount
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
      setTimeRangeState(range === "7d" ? null : range); // 7d as default
    },
    [setTimeRangeState],
  );

  const setSelectionMode = useCallback(
    (mode: SelectionMode) => {
      setSelectionModeState(mode === "latest" ? null : mode); // latest as default
    },
    [setSelectionModeState],
  );

  const setSelectedParameter = useCallback(
    (parameter: string) => {
      setSelectedParameterState(parameter === "t1" ? null : parameter); // t1 as default
      // Clear custom threshold when parameter changes
      setCustomThresholdState(null);
    },
    [setSelectedParameterState, setCustomThresholdState],
  );

  const setShowAsErrorRate = useCallback(
    (show: boolean) => {
      setShowAsErrorRateState(
        show === URL_DEFAULTS.SHOW_ERROR_RATE ? null : show,
      );
    },
    [setShowAsErrorRateState],
  );

  const setCustomThreshold = useCallback(
    (threshold: number | null) => {
      setCustomThresholdState(threshold);
    },
    [setCustomThresholdState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    selectedParameter: selectedParameter ?? "t1",
    showAsErrorRate: showAsErrorRate ?? URL_DEFAULTS.SHOW_ERROR_RATE,
    customThreshold: customThreshold ?? null,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setSelectedParameter,
    setShowAsErrorRate,
    setCustomThreshold,
    isInitialized,
  };
}
