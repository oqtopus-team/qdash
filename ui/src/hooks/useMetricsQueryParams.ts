import { useMemo } from "react";

import type { SelectionMode } from "./url-state/types";

interface UseMetricsQueryParamsOptions {
  selectionMode: SelectionMode;
  startDate: string;
  endDate: string;
  selectedChip: string;
}

function toIsoSeconds(dt: string): string {
  if (dt.length === 16) return `${dt}:00`;
  return dt;
}

export function useMetricsQueryParams({
  selectionMode,
  startDate,
  endDate,
  selectedChip,
}: UseMetricsQueryParamsOptions) {
  const startIso = toIsoSeconds(startDate);
  const endIso = toIsoSeconds(endDate);

  const queryParams = useMemo(
    () => ({
      start_at: startIso,
      end_at: endIso,
      selection_mode: selectionMode,
    }),
    [startIso, endIso, selectionMode],
  );

  const canFetch = !!selectedChip;

  return { queryParams, canFetch };
}
