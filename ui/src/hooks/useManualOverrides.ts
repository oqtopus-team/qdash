"use client";

import { useMemo } from "react";
import { useGetManualEdits } from "@/client/calibration/calibration";
import type { ParameterOverride } from "@/components/features/metrics/ParametersTable";
import { formatDateTimeCompact } from "@/lib/utils/datetime";

/**
 * Fetch manual parameter edits for a qid and return an overrides map
 * suitable for passing to ParametersTable.
 */
export function useManualOverrides(qid: string) {
  const { data } = useGetManualEdits(qid, {
    query: { staleTime: 30000, gcTime: 60000 },
  });

  const overrides = useMemo(() => {
    const edits = data?.data?.edits;
    if (!edits || edits.length === 0) return undefined;
    const map: Record<string, ParameterOverride> = {};
    for (const edit of edits) {
      map[edit.parameter_name] = {
        currentValue: edit.value as number | string,
        editedAt: edit.edited_at ? formatDateTimeCompact(String(edit.edited_at)) : undefined,
      };
    }
    return map;
  }, [data]);

  return overrides;
}
