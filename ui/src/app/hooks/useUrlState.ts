import { useQueryState, parseAsString } from "nuqs";
import { useCallback, useState, useEffect } from "react";

// Default values for URL parameters - used to determine when to remove params from URL
const URL_DEFAULTS = {
  DATE: "latest",
  TASK: "CheckRabi", 
  VIEW: "1q"
} as const;

interface UseChipUrlStateResult {
  selectedChip: string;
  selectedDate: string;
  selectedTask: string;
  viewMode: string;
  setSelectedChip: (chip: string) => void;
  setSelectedDate: (date: string) => void;
  setSelectedTask: (task: string) => void;
  setViewMode: (mode: string) => void;
  isInitialized: boolean; // Track if URL state has been initialized
}

export function useChipUrlState(): UseChipUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);
  
  // URL state management - don't use withDefault to preserve URL params
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString
  );
  
  const [selectedDate, setSelectedDateState] = useQueryState(
    "date", 
    parseAsString
  );
  
  const [selectedTask, setSelectedTaskState] = useQueryState(
    "task",
    parseAsString
  );
  
  const [viewMode, setViewModeState] = useQueryState(
    "view",
    parseAsString
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates smoothly
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState]
  );

  const setSelectedDate = useCallback(
    (date: string) => {
      setSelectedDateState(date === URL_DEFAULTS.DATE ? null : date); // Remove default from URL
    },
    [setSelectedDateState]
  );

  const setSelectedTask = useCallback(
    (task: string) => {
      setSelectedTaskState(task === URL_DEFAULTS.TASK ? null : task); // Remove default from URL
    },
    [setSelectedTaskState]
  );
  
  const setViewMode = useCallback(
    (mode: string) => {
      setViewModeState(mode === URL_DEFAULTS.VIEW ? null : mode); // Remove default from URL
    },
    [setViewModeState]
  );

  return {
    selectedChip: selectedChip ?? "",
    selectedDate: selectedDate ?? URL_DEFAULTS.DATE, 
    selectedTask: selectedTask ?? URL_DEFAULTS.TASK,
    viewMode: viewMode ?? URL_DEFAULTS.VIEW,
    setSelectedChip,
    setSelectedDate,
    setSelectedTask,
    setViewMode,
    isInitialized,
  };
}