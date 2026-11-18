import { describe, expect, it } from "vitest";

import {
  RUNS_LIST_MAX,
  RUNS_MAX_PAGE,
  RUNS_PAGE_SIZE,
  clampRunsPage,
  runsPage,
  runsRequestLimit,
} from "../evaluationRunsPaging";

const ids = (count: number) => Array.from({ length: count }, (_, index) => index + 1);

describe("evaluation runs paging", () => {
  it("requests every newer run plus one to detect a next page, within the API maximum", () => {
    expect(runsRequestLimit(1)).toBe(RUNS_PAGE_SIZE + 1);
    expect(runsRequestLimit(2)).toBe(2 * RUNS_PAGE_SIZE + 1);
    expect(runsRequestLimit(RUNS_MAX_PAGE)).toBe(RUNS_LIST_MAX);
    expect(runsRequestLimit(99)).toBe(RUNS_LIST_MAX);
  });

  it("clamps pages into the reachable range", () => {
    expect(clampRunsPage(0)).toBe(1);
    expect(clampRunsPage(-3)).toBe(1);
    expect(clampRunsPage(2.7)).toBe(2);
    expect(clampRunsPage(99)).toBe(RUNS_MAX_PAGE);
  });

  it("slices one page and reports neighbours from the extra run", () => {
    const first = runsPage(ids(RUNS_PAGE_SIZE + 1), 1);
    expect(first.items).toEqual(ids(RUNS_PAGE_SIZE));
    expect(first).toMatchObject({ page: 1, first: 1, last: 25, hasPrevious: false });
    expect(first.hasNext).toBe(true);

    const second = runsPage(ids(40), 2);
    expect(second.items).toEqual(ids(40).slice(25));
    expect(second).toMatchObject({ page: 2, first: 26, last: 40, hasPrevious: true });
    expect(second.hasNext).toBe(false);
  });

  it("moves a page past the end back to the last page with runs", () => {
    expect(runsPage(ids(30), 4)).toMatchObject({ page: 2, first: 26, last: 30 });
    expect(runsPage([], 3)).toMatchObject({ page: 1, items: [], first: 0, last: 0 });
  });

  it("flags the last reachable page when the API maximum cut the list", () => {
    const last = runsPage(ids(RUNS_LIST_MAX), RUNS_MAX_PAGE);
    expect(last).toMatchObject({ page: RUNS_MAX_PAGE, hasNext: false, truncated: true });
    expect(runsPage(ids(RUNS_LIST_MAX - 1), RUNS_MAX_PAGE).truncated).toBe(false);
  });
});
