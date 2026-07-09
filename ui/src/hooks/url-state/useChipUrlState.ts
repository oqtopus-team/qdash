import { useCallback, useMemo, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { dateToDateTimeLocal } from "@/lib/utils/datetime";

import { URL_DEFAULTS } from "./types";

interface UseChipUrlStateResult {
  selectedChip: string;
  selectedDate: string;
  selectedTask: string;
  selectedCooldownId: string | null;
  startDate: string;
  endDate: string;
  hasTimeRangeParams: boolean;
  viewMode: string;
  qubitViewMode: string;
  setSelectedChip: (chip: string) => void;
  setSelectedDate: (date: string) => void;
  setSelectedTask: (task: string) => void;
  setSelectedCooldownId: (cooldownId: string | null) => void;
  setStartDate: (date: string) => void;
  setEndDate: (date: string) => void;
  setQuickRange: (days: number) => void;
  setViewMode: (mode: string) => void;
  setQubitViewMode: (mode: string) => void;
  isInitialized: boolean;
}

export function useChipUrlState(): UseChipUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management - don't use withDefault to preserve URL params
  const [selectedChip, setSelectedChipState] = useQueryState("chip", parseAsString);

  const [selectedDate, setSelectedDateState] = useQueryState("date", parseAsString);

  const [selectedTask, setSelectedTaskState] = useQueryState("task", parseAsString);

  const [selectedCooldownId, setSelectedCooldownIdState] = useQueryState("cooldown", parseAsString);

  const [startDate, setStartDateState] = useQueryState("start", parseAsString);
  const [endDate, setEndDateState] = useQueryState("end", parseAsString);

  const [viewMode, setViewModeState] = useQueryState("view", parseAsString);

  const [qubitViewMode, setQubitViewModeState] = useQueryState("qview", parseAsString);

  const rangeDefaults = useMemo(() => {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return {
      start: dateToDateTimeLocal(sevenDaysAgo),
      end: dateToDateTimeLocal(now),
    };
  }, []);

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates smoothly
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  const setSelectedDate = useCallback(
    (date: string) => {
      setSelectedDateState(date === URL_DEFAULTS.DATE ? null : date); // Remove default from URL
    },
    [setSelectedDateState],
  );

  const setSelectedTask = useCallback(
    (task: string) => {
      setSelectedTaskState(task === URL_DEFAULTS.TASK ? null : task); // Remove default from URL
    },
    [setSelectedTaskState],
  );

  const setSelectedCooldownId = useCallback(
    (cooldownId: string | null) => {
      setSelectedCooldownIdState(cooldownId || null);
    },
    [setSelectedCooldownIdState],
  );

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

  const setViewMode = useCallback(
    (mode: string) => {
      setViewModeState(mode === URL_DEFAULTS.VIEW ? null : mode); // Remove default from URL
    },
    [setViewModeState],
  );

  const setQubitViewMode = useCallback(
    (mode: string) => {
      // Remove default qubit view mode from URL (e.g., if "dashboard" is default)
      setQubitViewModeState(mode === "dashboard" ? null : mode);
    },
    [setQubitViewModeState],
  );

  return {
    selectedChip: selectedChip ?? "",
    selectedDate: selectedDate ?? URL_DEFAULTS.DATE,
    selectedTask: selectedTask ?? URL_DEFAULTS.TASK,
    selectedCooldownId: selectedCooldownId ?? null,
    startDate: startDate ?? rangeDefaults.start,
    endDate: endDate ?? rangeDefaults.end,
    hasTimeRangeParams: Boolean(startDate || endDate),
    viewMode: viewMode ?? URL_DEFAULTS.VIEW,
    qubitViewMode: qubitViewMode ?? "dashboard",
    setSelectedChip,
    setSelectedDate,
    setSelectedTask,
    setSelectedCooldownId,
    setStartDate,
    setEndDate,
    setQuickRange,
    setViewMode,
    setQubitViewMode,
    isInitialized,
  };
}
