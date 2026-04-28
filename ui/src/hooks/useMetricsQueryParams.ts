import { useMemo } from "react";

import type { RangeMode, TimeRange, SelectionMode } from "./url-state/types";

interface UseMetricsQueryParamsOptions {
  rangeMode: RangeMode;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  startDate: string | null;
  endDate: string | null;
  selectedChip: string;
}

export function useMetricsQueryParams({
  rangeMode,
  timeRange,
  selectionMode,
  startDate,
  endDate,
  selectedChip,
}: UseMetricsQueryParamsOptions) {
  const isAbsolute = rangeMode === "absolute";

  const relativeWithinHours = useMemo(() => {
    switch (timeRange) {
      case "1d":
        return 24;
      case "7d":
        return 24 * 7;
      case "30d":
        return 24 * 30;
      default:
        return 24 * 7;
    }
  }, [timeRange]);

  const absoluteStartIso = startDate ? `${startDate}T00:00:00` : null;
  const absoluteEndIso = endDate ? `${endDate}T23:59:59` : null;

  const queryParams = useMemo(
    () =>
      isAbsolute
        ? {
            start_at: absoluteStartIso,
            end_at: absoluteEndIso,
            selection_mode: selectionMode,
          }
        : {
            within_hours: relativeWithinHours,
            selection_mode: selectionMode,
          },
    [
      isAbsolute,
      absoluteStartIso,
      absoluteEndIso,
      selectionMode,
      relativeWithinHours,
    ],
  );

  const hasAbsoluteBound = Boolean(startDate || endDate);
  const canFetch = !!selectedChip && (!isAbsolute || hasAbsoluteBound);

  return { queryParams, isAbsolute, canFetch };
}
