import { useCallback } from "react";

import { parseAsInteger, parseAsString, useQueryStates } from "nuqs";

interface UseEvaluationRunsUrlStateResult {
  chipId: string;
  taskName: string;
  /** One-based page, at least 1. A missing, non-numeric or non-positive `page` reads as 1. */
  page: number;
  setChipId: (chipId: string) => void;
  setTaskName: (taskName: string) => void;
  /** Goes to a page; `replace` corrects the URL without adding a history entry. */
  setPage: (page: number, options?: { replace?: boolean }) => void;
}

const parsers = {
  chip: parseAsString,
  task: parseAsString,
  page: parseAsInteger,
};

/**
 * Chip and task filters and the page of the evaluation runs list, kept in the URL so reload,
 * Back and a shared link restore them. Each change adds a history entry, and changing a filter
 * returns to the first page.
 */
export function useEvaluationRunsUrlState(): UseEvaluationRunsUrlStateResult {
  const [state, setState] = useQueryStates(parsers, { history: "push" });

  const setChipId = useCallback(
    (chipId: string) => {
      void setState({ chip: chipId || null, page: null });
    },
    [setState],
  );

  const setTaskName = useCallback(
    (taskName: string) => {
      void setState({ task: taskName || null, page: null });
    },
    [setState],
  );

  const setPage = useCallback(
    (page: number, options: { replace?: boolean } = {}) => {
      void setState(
        { page: page > 1 ? Math.floor(page) : null },
        options.replace ? { history: "replace" } : undefined,
      );
    },
    [setState],
  );

  const rawPage = state.page;
  return {
    chipId: state.chip ?? "",
    taskName: state.task ?? "",
    page: rawPage !== null && Number.isFinite(rawPage) && rawPage >= 1 ? rawPage : 1,
    setChipId,
    setTaskName,
    setPage,
  };
}
