/**
 * Paging of the evaluation runs list.
 *
 * `GET /evaluations/runs` returns one page of runs, newest first, for `skip` and `limit`, with
 * `has_more` when older runs follow and `total` for every run matching the filters. Each page
 * requests only its own runs, so every run of the filters can be reached however old it is.
 */

export const RUNS_PAGE_SIZE = 25;

/** One-based page, at least 1, as a whole number. */
export function clampRunsPage(page: number): number {
  return Number.isFinite(page) ? Math.max(1, Math.floor(page)) : 1;
}

/** The `skip` and `limit` that request one page. */
export function runsPageParams(page: number): { skip: number; limit: number } {
  return { skip: (clampRunsPage(page) - 1) * RUNS_PAGE_SIZE, limit: RUNS_PAGE_SIZE };
}

/** The last page with runs, or 1 when there are none. */
export function lastRunsPage(total: number): number {
  return Math.max(1, Math.ceil(total / RUNS_PAGE_SIZE));
}

export interface RunsPageResponse<T> {
  runs: T[];
  skip: number;
  has_more: boolean;
  total: number;
}

export interface RunsPage<T> {
  /** The page the response holds. */
  page: number;
  items: T[];
  /** One-based position of the first and last run shown, or 0 when the page is empty. */
  first: number;
  last: number;
  total: number;
  hasPrevious: boolean;
  hasNext: boolean;
  /**
   * The page to show instead, when the requested page lies past the end (an old link, or runs
   * removed since); null when the requested page is the right one.
   */
  correctedPage: number | null;
}

/** Reads one page of the API response for the requested page. */
export function runsPage<T>(response: RunsPageResponse<T>, requestedPage: number): RunsPage<T> {
  const page = clampRunsPage(requestedPage);
  const items = response.runs;
  const lastPage = lastRunsPage(response.total);
  return {
    page,
    items,
    first: items.length > 0 ? response.skip + 1 : 0,
    last: response.skip + items.length,
    total: response.total,
    hasPrevious: page > 1,
    hasNext: response.has_more,
    // An empty page after the first lies past the end. `total` names the last page with runs;
    // stepping back at least one page also settles a count taken as runs were removed.
    correctedPage: items.length === 0 && page > 1 ? Math.min(page - 1, lastPage) : null,
  };
}
