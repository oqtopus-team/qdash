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
  startAt?: string | null;
  endAt?: string | null;
  staleTime?: number;
  keepPrevious?: boolean;
}

export function useQubitTaskResults({
  chipId,
  task,
  selectedDate,
  startAt,
  endAt,
  staleTime = 30000,
  keepPrevious = false,
}: UseQubitTaskResultsOptions) {
  const isLatest = selectedDate === "latest";
  const canFetch = Boolean(chipId && task);
  // Always call both hooks, but only enable one based on condition
  const latestResult = useGetLatestQubitTaskResults(
    { chip_id: chipId, task },
    {
      query: {
        staleTime,
        enabled: canFetch && isLatest,
        retry: false,
        ...(keepPrevious && { placeholderData: keepPreviousData }),
      },
    },
  );

  const historicalResult = useGetHistoricalQubitTaskResults(
    {
      chip_id: chipId,
      task,
      date: selectedDate === "latest" ? "" : selectedDate,
      start_at: startAt || undefined,
      end_at: endAt || undefined,
    },
    {
      query: {
        staleTime,
        enabled: canFetch && !isLatest,
        retry: false,
        ...(keepPrevious && { placeholderData: keepPreviousData }),
      },
    },
  );

  // Return the appropriate result based on the date selection
  return isLatest ? latestResult : historicalResult;
}
