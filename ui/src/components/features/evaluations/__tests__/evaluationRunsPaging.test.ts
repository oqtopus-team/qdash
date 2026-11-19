import { describe, expect, it } from "vitest";

import {
  RUNS_PAGE_SIZE,
  clampRunsPage,
  lastRunsPage,
  runsPage,
  runsPageParams,
} from "../evaluationRunsPaging";

const ids = (from: number, count: number) => Array.from({ length: count }, (_, i) => from + i);

/** The response for one page of `total` runs numbered 1 (newest) to `total`. */
function response(page: number, total: number) {
  const { skip, limit } = runsPageParams(page);
  const count = Math.max(0, Math.min(limit, total - skip));
  return { runs: ids(skip + 1, count), skip, has_more: skip + count < total, total };
}

describe("evaluation runs paging", () => {
  it("requests only the runs of the page, with no cap on how far back", () => {
    expect(runsPageParams(1)).toEqual({ skip: 0, limit: RUNS_PAGE_SIZE });
    expect(runsPageParams(2)).toEqual({ skip: RUNS_PAGE_SIZE, limit: RUNS_PAGE_SIZE });
    expect(runsPageParams(41)).toEqual({ skip: 40 * RUNS_PAGE_SIZE, limit: RUNS_PAGE_SIZE });
  });

  it("clamps invalid pages to the first page", () => {
    expect(clampRunsPage(0)).toBe(1);
    expect(clampRunsPage(-3)).toBe(1);
    expect(clampRunsPage(Number.NaN)).toBe(1);
    expect(clampRunsPage(2.7)).toBe(2);
    expect(clampRunsPage(99)).toBe(99);
  });

  it("counts the last page with runs", () => {
    expect(lastRunsPage(0)).toBe(1);
    expect(lastRunsPage(25)).toBe(1);
    expect(lastRunsPage(26)).toBe(2);
    expect(lastRunsPage(230)).toBe(10);
  });

  it("reports positions and neighbours from the response", () => {
    const first = runsPage(response(1, 230), 1);
    expect(first).toMatchObject({ page: 1, first: 1, last: 25, total: 230 });
    expect(first).toMatchObject({ hasPrevious: false, hasNext: true, correctedPage: null });

    // Past the newest 200: page 9 holds runs 201-225, and page 10 is the end.
    expect(runsPage(response(9, 230), 9)).toMatchObject({ first: 201, last: 225, hasNext: true });
    const end = runsPage(response(10, 230), 10);
    expect(end.items).toEqual(ids(226, 5));
    expect(end).toMatchObject({ first: 226, last: 230, hasPrevious: true, hasNext: false });
  });

  it("moves a page past the end back to the last page with runs", () => {
    expect(runsPage(response(14, 230), 14).correctedPage).toBe(10);
    expect(runsPage(response(3, 0), 3)).toMatchObject({ items: [], first: 0, correctedPage: 1 });
    // A count taken while runs were removed still steps back.
    expect(runsPage({ runs: [], skip: 50, has_more: false, total: 60 }, 3).correctedPage).toBe(2);
    expect(runsPage(response(1, 0), 1).correctedPage).toBeNull();
  });
});
