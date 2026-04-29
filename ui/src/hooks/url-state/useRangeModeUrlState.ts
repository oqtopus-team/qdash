import { useCallback, useMemo } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { dateToDateTimeLocal } from "@/lib/utils/datetime";

interface UseRangeModeUrlStateResult {
  startDate: string;
  endDate: string;
  setStartDate: (date: string) => void;
  setEndDate: (date: string) => void;
  setQuickRange: (days: number) => void;
}

export function useRangeModeUrlState(): UseRangeModeUrlStateResult {
  const [startDate, setStartDateState] = useQueryState("start", parseAsString);
  const [endDate, setEndDateState] = useQueryState("end", parseAsString);

  const defaults = useMemo(() => {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return {
      start: dateToDateTimeLocal(sevenDaysAgo),
      end: dateToDateTimeLocal(now),
    };
  }, []);

  const setStartDate = useCallback(
    (date: string) => {
      setStartDateState(date && date.length > 0 ? date : null);
    },
    [setStartDateState],
  );

  const setEndDate = useCallback(
    (date: string) => {
      setEndDateState(date && date.length > 0 ? date : null);
    },
    [setEndDateState],
  );

  const setQuickRange = useCallback(
    (days: number) => {
      const now = new Date();
      const past = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
      setStartDateState(dateToDateTimeLocal(past));
      setEndDateState(dateToDateTimeLocal(now));
    },
    [setStartDateState, setEndDateState],
  );

  return {
    startDate: startDate ?? defaults.start,
    endDate: endDate ?? defaults.end,
    setStartDate,
    setEndDate,
    setQuickRange,
  };
}
