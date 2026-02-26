import { useCallback, useState, useEffect } from "react";

import {
  useQueryState,
  parseAsString,
  parseAsArrayOf,
  parseAsBoolean,
} from "nuqs";

import { URL_DEFAULTS, type TimeRange, type SelectionMode } from "./types";

interface UseCDFUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  selectedParameters: string[];
  showAsErrorRate: boolean;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setSelectedParameters: (parameters: string[]) => void;
  setShowAsErrorRate: (show: boolean) => void;
  isInitialized: boolean;
}

export function useCDFUrlState(): UseCDFUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for CDF view
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [selectedParameters, setSelectedParametersState] = useQueryState(
    "params",
    parseAsArrayOf(parseAsString),
  );

  const [showAsErrorRate, setShowAsErrorRateState] = useQueryState(
    "errorRate",
    parseAsBoolean,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Helper function to check if arrays are equal
  const arraysEqual = (a: string[], b: string[]) => {
    if (a.length !== b.length) return false;
    return a.every((val, i) => val === b[i]);
  };

  // Wrapped setters to handle URL updates
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
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

  const setSelectedParameters = useCallback(
    (parameters: string[]) => {
      // Remove default parameters from URL to keep it clean
      if (arraysEqual(parameters, [...URL_DEFAULTS.CDF_PARAMETERS])) {
        setSelectedParametersState(null);
      } else {
        setSelectedParametersState(parameters);
      }
    },
    [setSelectedParametersState],
  );

  const setShowAsErrorRate = useCallback(
    (show: boolean) => {
      setShowAsErrorRateState(
        show === URL_DEFAULTS.SHOW_ERROR_RATE ? null : show,
      ); // Remove default from URL
    },
    [setShowAsErrorRateState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    selectedParameters: selectedParameters ?? [...URL_DEFAULTS.CDF_PARAMETERS],
    showAsErrorRate: showAsErrorRate ?? URL_DEFAULTS.SHOW_ERROR_RATE,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setSelectedParameters,
    setShowAsErrorRate,
    isInitialized,
  };
}
