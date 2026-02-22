import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { type TimeRange, type SelectionMode } from "./types";

interface UseCorrelationUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  xParameter: string;
  yParameter: string;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setXParameter: (parameter: string) => void;
  setYParameter: (parameter: string) => void;
  isInitialized: boolean;
}

export function useCorrelationUrlState(): UseCorrelationUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for correlation view
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [xParameter, setXParameterState] = useQueryState(
    "xParam",
    parseAsString,
  );

  const [yParameter, setYParameterState] = useQueryState(
    "yParam",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

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

  const setXParameter = useCallback(
    (parameter: string) => {
      setXParameterState(parameter === "t1" ? null : parameter); // t1 as default
    },
    [setXParameterState],
  );

  const setYParameter = useCallback(
    (parameter: string) => {
      setYParameterState(parameter === "t2_echo" ? null : parameter); // t2_echo as default
    },
    [setYParameterState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    xParameter: xParameter ?? "t1",
    yParameter: yParameter ?? "t2_echo",
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setXParameter,
    setYParameter,
    isInitialized,
  };
}
