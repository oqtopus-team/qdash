/**
 * Custom hook to get qubit task results based on date selection.
 * This hook properly handles the "latest" vs historical date selection
 * without violating React's rules of hooks.
 */
import { keepPreviousData } from "@tanstack/react-query";

import {
  useGetLatestQubitTaskResults,
  useGetHistoricalQubitTaskResults,
} from "@/client/task-result/task-result";

interface UseQubitTaskResultsOptions {
  chipId: string;
  task: string;
  selectedDate: string;
  staleTime?: number;
  keepPrevious?: boolean;
}

export function useQubitTaskResults({
  chipId,
  task,
  selectedDate,
  staleTime = 30000,
  keepPrevious = false,
}: UseQubitTaskResultsOptions) {
  const isLatest = selectedDate === "latest";
  const dateForHistorical = isLatest
    ? new Date().toISOString().split("T")[0]
    : selectedDate;

  // Always call both hooks, but only enable one based on condition
  const latestResult = useGetLatestQubitTaskResults(
    { chip_id: chipId, task },
    {
      query: {
        staleTime,
        enabled: isLatest,
        ...(keepPrevious && { placeholderData: keepPreviousData }),
      },
    },
  );

  const historicalResult = useGetHistoricalQubitTaskResults(
    {
      chip_id: chipId,
      task,
      date: dateForHistorical,
    },
    {
      query: {
        staleTime,
        enabled: !isLatest,
        ...(keepPrevious && { placeholderData: keepPreviousData }),
      },
    },
  );

  // Return the appropriate result based on the date selection
  return isLatest ? latestResult : historicalResult;
}
