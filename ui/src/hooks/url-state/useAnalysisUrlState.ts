import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString, parseAsArrayOf } from "nuqs";

export interface UseAnalysisUrlStateResult {
  selectedChip: string;
  selectedParameter: string;
  selectedParameters: string[];
  selectedTag: string;
  analysisViewType: string;
  setSelectedChip: (chip: string) => void;
  setSelectedParameter: (parameter: string) => void;
  setSelectedParameters: (parameters: string[]) => void;
  setSelectedTag: (tag: string) => void;
  setAnalysisViewType: (type: string) => void;
  isInitialized: boolean;
}

export function useAnalysisUrlState(): UseAnalysisUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for analysis pages
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [selectedParameter, setSelectedParameterState] = useQueryState(
    "parameter",
    parseAsString,
  );

  // Multiple parameters for dual-axis timeseries
  const [selectedParameters, setSelectedParametersState] = useQueryState(
    "params",
    parseAsArrayOf(parseAsString),
  );

  const [selectedTag, setSelectedTagState] = useQueryState(
    "tag",
    parseAsString,
  );

  const [analysisViewType, setAnalysisViewTypeState] = useQueryState(
    "aview",
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

  const setSelectedParameter = useCallback(
    (parameter: string) => {
      // Always include parameter in URL for complete state management
      setSelectedParameterState(parameter);
    },
    [setSelectedParameterState],
  );

  const setSelectedParameters = useCallback(
    (parameters: string[]) => {
      // Store multiple parameters for dual-axis view
      if (parameters.length === 0) {
        setSelectedParametersState(null);
      } else {
        setSelectedParametersState(parameters);
      }
    },
    [setSelectedParametersState],
  );

  const setSelectedTag = useCallback(
    (tag: string) => {
      // Always include tag in URL for complete state management
      setSelectedTagState(tag);
    },
    [setSelectedTagState],
  );

  const setAnalysisViewType = useCallback(
    (type: string) => {
      // Always include view type in URL for complete state management
      setAnalysisViewTypeState(type);
    },
    [setAnalysisViewTypeState],
  );

  return {
    selectedChip: selectedChip ?? "",
    selectedParameter: selectedParameter ?? "t1",
    selectedParameters: selectedParameters ?? [],
    selectedTag: selectedTag ?? "daily",
    analysisViewType: analysisViewType ?? "timeseries",
    setSelectedChip,
    setSelectedParameter,
    setSelectedParameters,
    setSelectedTag,
    setAnalysisViewType,
    isInitialized,
  };
}
