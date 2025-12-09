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
  staleTime?: number;
}

export function useCouplingTaskResults({
  chipId,
  task,
  selectedDate,
  staleTime = 30000,
}: UseCouplingTaskResultsOptions) {
  const isLatest = selectedDate === "latest";

  // Always call both hooks, but only enable one based on condition
  const latestResult = useGetLatestCouplingTaskResults(
    { chip_id: chipId, task },
    {
      query: {
        placeholderData: keepPreviousData,
        staleTime,
        enabled: isLatest,
      },
    },
  );

  const historicalResult = useGetHistoricalCouplingTaskResults(
    {
      chip_id: chipId,
      task,
      date: selectedDate === "latest" ? "" : selectedDate,
    },
    {
      query: {
        placeholderData: keepPreviousData,
        staleTime,
        enabled: !isLatest,
      },
    },
  );

  // Return the appropriate result based on the date selection
  return isLatest ? latestResult : historicalResult;
}
