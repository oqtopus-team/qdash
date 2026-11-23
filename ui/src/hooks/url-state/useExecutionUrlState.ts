import { useCallback, useState, useEffect } from "react";

import { parseAsString, useQueryStates } from "nuqs";

import { cleanPage, executionViewParsers } from "@/lib/executionArea";

interface UseExecutionUrlStateResult {
  selectedChip: string | null;
  /** Sets the chip without a history entry, as when the latest chip is picked by default. */
  setSelectedChip: (chip: string | null) => void;
  /** A day written `YYYYMMDD`, or `"latest"` when none is picked or the URL's is invalid. */
  selectedDate: string;
  /** Whether sessions are grouped; `flat=true` shows every execution on its own. */
  groupSessions: boolean;
  /** One-based page, at least 1. A missing, non-numeric or non-positive `page` reads as 1. */
  page: number;
  /** Picks another chip: its own days apply, so the day and page are reset. */
  changeChip: (chip: string | null) => void;
  /** Picks a day, or `"latest"`, and returns to the first page. */
  changeDate: (date: string) => void;
  /** Groups sessions or shows the flat list, and returns to the first page. */
  changeGrouping: (grouped: boolean) => void;
  /** Goes to a page; `replace` corrects the URL without adding a history entry. */
  setPage: (page: number, options?: { replace?: boolean }) => void;
  /**
   * Sets the default chip of a newly switched project and drops the previous chip's day and
   * page, in one URL update without a history entry.
   */
  resetForProject: (chip: string) => void;
  isInitialized: boolean;
}

const parsers = {
  chip: parseAsString,
  ...executionViewParsers,
};

/**
 * Chip, day, grouping and page of the Executions list, kept in the URL so reload, Back and a
 * link back from a session or execution page restore them. A filter change adds a history
 * entry and returns to the first page.
 */
export function useExecutionUrlState(): UseExecutionUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);
  const [state, setState] = useQueryStates(parsers);

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  const setSelectedChip = useCallback(
    (chip: string | null) => {
      void setState({ chip: chip || null }); // null removes the parameter from URL
    },
    [setState],
  );

  const changeChip = useCallback(
    (chip: string | null) => {
      void setState({ chip: chip || null, date: null, page: null }, { history: "push" });
    },
    [setState],
  );

  const changeDate = useCallback(
    (date: string) => {
      void setState(
        { date: date && date !== "latest" ? date : null, page: null },
        { history: "push" },
      );
    },
    [setState],
  );

  const changeGrouping = useCallback(
    (grouped: boolean) => {
      void setState({ flat: grouped ? null : true, page: null }, { history: "push" });
    },
    [setState],
  );

  const setPage = useCallback(
    (page: number, options: { replace?: boolean } = {}) => {
      void setState(
        { page: page > 1 ? Math.floor(page) : null },
        { history: options.replace ? "replace" : "push" },
      );
    },
    [setState],
  );

  const resetForProject = useCallback(
    (chip: string) => {
      void setState({ chip: chip || null, date: null, page: null });
    },
    [setState],
  );

  return {
    selectedChip: state.chip,
    setSelectedChip,
    selectedDate: state.date ?? "latest",
    groupSessions: !state.flat,
    page: cleanPage(state.page),
    changeChip,
    changeDate,
    changeGrouping,
    setPage,
    resetForProject,
    isInitialized,
  };
}
