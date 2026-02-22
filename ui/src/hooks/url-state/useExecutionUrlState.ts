import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

export interface UseExecutionUrlStateResult {
  selectedChip: string | null;
  setSelectedChip: (chip: string | null) => void;
  isInitialized: boolean;
}

export function useExecutionUrlState(): UseExecutionUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for execution page
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setter to handle URL updates - now accepts null explicitly
  const setSelectedChip = useCallback(
    (chip: string | null) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  return {
    selectedChip, // Return null as-is instead of converting to empty string
    setSelectedChip,
    isInitialized,
  };
}
