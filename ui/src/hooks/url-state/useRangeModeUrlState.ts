import { useCallback } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { type RangeMode } from "./types";

interface UseRangeModeUrlStateResult {
  rangeMode: RangeMode;
  startDate: string | null;
  endDate: string | null;
  setRangeMode: (mode: RangeMode) => void;
  setStartDate: (date: string | null) => void;
  setEndDate: (date: string | null) => void;
}

export function useRangeModeUrlState(): UseRangeModeUrlStateResult {
  const [rangeMode, setRangeModeState] = useQueryState(
    "rangeMode",
    parseAsString,
  );
  const [startDate, setStartDateState] = useQueryState("start", parseAsString);
  const [endDate, setEndDateState] = useQueryState("end", parseAsString);

  const setRangeMode = useCallback(
    (mode: RangeMode) => {
      setRangeModeState(mode === "relative" ? null : mode);
      if (mode === "relative") {
        setStartDateState(null);
        setEndDateState(null);
      } else {
        if (!startDate && !endDate) {
          const today = new Date();
          const sixDaysAgo = new Date();
          sixDaysAgo.setDate(today.getDate() - 6);
          const toIso = (d: Date) => {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            return `${y}-${m}-${day}`;
          };
          setStartDateState(toIso(sixDaysAgo));
          setEndDateState(toIso(today));
        }
      }
    },
    [setRangeModeState, setStartDateState, setEndDateState, startDate, endDate],
  );

  const setStartDate = useCallback(
    (date: string | null) => {
      setStartDateState(date && date.length > 0 ? date : null);
    },
    [setStartDateState],
  );

  const setEndDate = useCallback(
    (date: string | null) => {
      setEndDateState(date && date.length > 0 ? date : null);
    },
    [setEndDateState],
  );

  return {
    rangeMode: (rangeMode as RangeMode) ?? "relative",
    startDate: startDate ?? null,
    endDate: endDate ?? null,
    setRangeMode,
    setStartDate,
    setEndDate,
  };
}
