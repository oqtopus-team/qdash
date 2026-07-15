/**
 * Custom hook to get coupling task results based on date selection.
 * This hook properly handles the "latest" vs historical date selection
 * without violating React's rules of hooks.
 */
import { keepPreviousData } from "@tanstack/react-query";

import {
  useGetLatestCouplingTaskResults,
  useGetHistoricalCouplingTaskResults,
} from "@/client/task-result/task-result";

interface UseCouplingTaskResultsOptions {
  chipId: string;
  task: string;
  selectedDate: string;
  startAt?: string | null;
  endAt?: string | null;
  staleTime?: number;
  keepPrevious?: boolean;
}

export function useCouplingTaskResults({
  chipId,
  task,
  selectedDate,
  startAt,
  endAt,
  staleTime = 30000,
  keepPrevious = false,
}: UseCouplingTaskResultsOptions) {
  const isLatest = selectedDate === "latest";
  const canFetch = Boolean(chipId && task);

  // Always call both hooks, but only enable one based on condition
  const latestResult = useGetLatestCouplingTaskResults(
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

  const historicalResult = useGetHistoricalCouplingTaskResults(
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
