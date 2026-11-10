import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { isCompactActivityDate } from "@/lib/utils/datetime";

import { URL_DEFAULTS } from "./types";

interface UseExecutionUrlStateResult {
  selectedChip: string | null;
  setSelectedChip: (chip: string | null) => void;
  /** Day filter of the execution list: YYYYMMDD, or `latest` when no day is picked. */
  selectedDate: string;
  setSelectedDate: (date: string) => void;
  isInitialized: boolean;
}

export function useExecutionUrlState(): UseExecutionUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for execution page
  const [selectedChip, setSelectedChipState] = useQueryState("chip", parseAsString);
  const [dateParam, setDateState] = useQueryState("date", parseAsString);

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

  const setSelectedDate = useCallback(
    (date: string) => {
      setDateState(isCompactActivityDate(date) ? date : null); // `latest` removes the parameter
    },
    [setDateState],
  );

  return {
    selectedChip, // Return null as-is instead of converting to empty string
    setSelectedChip,
    selectedDate: isCompactActivityDate(dateParam) ? dateParam : URL_DEFAULTS.DATE,
    setSelectedDate,
    isInitialized,
  };
}
