import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

interface UseQubitTimeSeriesUrlStateResult {
  selectedParameter: string;
  selectedTag: string;
  setSelectedParameter: (parameter: string) => void;
  setSelectedTag: (tag: string) => void;
  isInitialized: boolean;
}

export function useQubitTimeSeriesUrlState(): UseQubitTimeSeriesUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for qubit time series view
  const [selectedParameter, setSelectedParameterState] = useQueryState(
    "param",
    parseAsString,
  );

  const [selectedTag, setSelectedTagState] = useQueryState(
    "tag",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates
  const setSelectedParameter = useCallback(
    (parameter: string) => {
      // Remove default parameter from URL (e.g., if "t1" is default)
      setSelectedParameterState(parameter === "t1" ? null : parameter);
    },
    [setSelectedParameterState],
  );

  const setSelectedTag = useCallback(
    (tag: string) => {
      // Remove default tag from URL (e.g., if "daily" is default)
      setSelectedTagState(tag === "daily" ? null : tag);
    },
    [setSelectedTagState],
  );

  return {
    selectedParameter: selectedParameter ?? "t1",
    selectedTag: selectedTag ?? "daily",
    setSelectedParameter,
    setSelectedTag,
    isInitialized,
  };
}
