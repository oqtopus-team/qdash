/**
 * Paging of the evaluation runs list.
 *
 * `GET /evaluations/runs` returns the newest runs up to `limit` (at most 200) and has no offset,
 * so a page is a slice of the newest `page * RUNS_PAGE_SIZE` runs. One extra run is requested to
 * tell whether a next page exists. Runs older than the newest 200 of the current filters cannot
 * be listed; narrowing the chip or task filter reaches them.
 */

export const RUNS_PAGE_SIZE = 25;
/** Upper bound of `limit` accepted by the API. */
export const RUNS_LIST_MAX = 200;
export const RUNS_MAX_PAGE = Math.ceil(RUNS_LIST_MAX / RUNS_PAGE_SIZE);

/** The `limit` to request for a page: its runs, every newer run, and one more when allowed. */
export function runsRequestLimit(page: number): number {
  return Math.min(clampRunsPage(page) * RUNS_PAGE_SIZE + 1, RUNS_LIST_MAX);
}

export function clampRunsPage(page: number): number {
  return Math.min(Math.max(1, Math.floor(page)), RUNS_MAX_PAGE);
}

export interface RunsPage<T> {
  /** The page shown, after moving past-the-end pages back to the last page with runs. */
  page: number;
  items: T[];
  /** One-based position of the first and last run shown, or 0 when the page is empty. */
  first: number;
  last: number;
  hasPrevious: boolean;
  hasNext: boolean;
  /** The list stopped at the API maximum, so older runs exist that no page can show. */
  truncated: boolean;
}

/** Slices one page out of the newest runs returned for `runsRequestLimit(page)`. */
export function runsPage<T>(runs: T[], requestedPage: number): RunsPage<T> {
  const lastPageWithRuns = Math.max(1, Math.ceil(runs.length / RUNS_PAGE_SIZE));
  const page = Math.min(clampRunsPage(requestedPage), lastPageWithRuns);
  const start = (page - 1) * RUNS_PAGE_SIZE;
  const items = runs.slice(start, start + RUNS_PAGE_SIZE);
  return {
    page,
    items,
    first: items.length > 0 ? start + 1 : 0,
    last: start + items.length,
    hasPrevious: page > 1,
    hasNext: runs.length > start + RUNS_PAGE_SIZE,
    truncated: page === RUNS_MAX_PAGE && runs.length >= RUNS_LIST_MAX,
  };
}
