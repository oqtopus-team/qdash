import { useCallback } from "react";

import { parseAsInteger, parseAsStringLiteral, useQueryStates } from "nuqs";

export const INBOX_FILTERS = ["all", "unread"] as const;
export type InboxFilter = (typeof INBOX_FILTERS)[number];

interface UseInboxUrlStateResult {
  /** `?filter=unread` shows unread items; a missing or unknown value shows everything. */
  filter: InboxFilter;
  /** One-based page, at least 1. A missing, non-numeric or non-positive `page` reads as 1. */
  page: number;
  /** Switches the filter and returns to the first page. */
  setFilter: (filter: InboxFilter) => void;
  /** Goes to a page; `replace` corrects the URL without adding a history entry. */
  setPage: (page: number, options?: { replace?: boolean }) => void;
}

const parsers = {
  filter: parseAsStringLiteral(INBOX_FILTERS),
  page: parseAsInteger,
};

/**
 * Filter and page of the Inbox, kept in the URL so reload, Back and a shared link restore them.
 * Each change adds a history entry, and changing the filter returns to the first page.
 */
export function useInboxUrlState(): UseInboxUrlStateResult {
  const [state, setState] = useQueryStates(parsers, { history: "push" });

  const setFilter = useCallback(
    (filter: InboxFilter) => {
      void setState({ filter: filter === "all" ? null : filter, page: null });
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
    filter: state.filter ?? "all",
    page: rawPage !== null && Number.isFinite(rawPage) && rawPage >= 1 ? rawPage : 1,
    setFilter,
    setPage,
  };
}
