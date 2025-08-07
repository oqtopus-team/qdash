import { useQueryState, parseAsString } from "nuqs";
import { useCallback, useState, useEffect } from "react";

interface UseChipUrlStateResult {
  selectedChip: string;
  selectedDate: string;
  selectedTask: string;
  setSelectedChip: (chip: string) => void;
  setSelectedDate: (date: string) => void;
  setSelectedTask: (task: string) => void;
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
      setSelectedDateState(date === "latest" ? null : date); // Remove "latest" from URL as it's default
    },
    [setSelectedDateState]
  );

  const setSelectedTask = useCallback(
    (task: string) => {
      setSelectedTaskState(task === "CheckRabi" ? null : task); // Remove default from URL
    },
    [setSelectedTaskState]
  );

  return {
    selectedChip: selectedChip ?? "",
    selectedDate: selectedDate ?? "latest", 
    selectedTask: selectedTask ?? "CheckRabi",
    setSelectedChip,
    setSelectedDate,
    setSelectedTask,
    isInitialized,
  };
}