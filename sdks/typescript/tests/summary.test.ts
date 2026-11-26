import { describe, expect, it } from "vitest";

import { QDash, QDashApiError, QDashValidationError, SUMMARIZE_MAX_PAGES, type TaskResultListItem } from "../src/index.js";

/** A GET /task-results row; `i` orders rows newest first. */
const row = (i: number, overrides: Partial<TaskResultListItem> = {}): TaskResultListItem => ({
  task_id: `t-${i}`,
  task_name: i % 3 === 0 ? "CheckRabi" : "CheckT1",
  qid: String(i % 16),
  chip_id: "16Qv1",
  status: i % 5 === 0 ? "failed" : "completed",
  execution_id: `e-${Math.floor(i / 40)}`,
  // 30 rows per UTC hour, newest first, from 2026-11-25T23:00:00Z down.
  start_at: new Date(Date.UTC(2026, 10, 25, 23) - Math.floor(i / 30) * 3_600_000).toISOString().replace(".000Z", ""),
  ...overrides,
});

const countStatuses = (rows: TaskResultListItem[]) => {
  const counts: Record<string, number> = {};
  for (const item of rows) counts[item.status] = (counts[item.status] ?? 0) + 1;
  return counts;
};

type PageAnswer = (query: { skip: number; limit: number; params: URLSearchParams; call: number }) => unknown;

/** A fetch answering GET /task-results from `rows` (newest first) by skip and limit, or from `answer`. */
function qdashWith(rows: TaskResultListItem[], answer?: PageAnswer) {
  const requests: URLSearchParams[] = [];
  const fetch = async (input: RequestInfo | URL): Promise<Response> => {
    const url = new URL(new Request(input).url);
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (url.pathname !== "/api/task-results") return json({ detail: "not found" }, 404);
    requests.push(url.searchParams);
    const skip = Number(url.searchParams.get("skip") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    if (answer) {
      const body = answer({ skip, limit, params: url.searchParams, call: requests.length });
      if (body instanceof Response) return body;
      return json(body);
    }
    return json({ items: rows.slice(skip, skip + limit), total: rows.length, skip, limit, status_counts: countStatuses(rows) });
  };
  const qdash = new QDash({ baseUrl: "https://qdash.example/api", apiToken: "token", readAttempts: 1 }, { fetch });
  return { qdash, requests };
}

const rows250 = Array.from({ length: 250 }, (_, i) => row(i));

describe("qdash.taskResults.summarize", () => {
  it("pages past 100 rows with the filters on every request and counts exact statuses, tasks, days and executions", async () => {
    const { qdash, requests } = qdashWith(rows250);
    const summary = await qdash.taskResults.summarize({ chipId: "16Qv1", startFrom: "2026-11-25T00:00:00Z", startTo: "2026-11-26T00:00:00Z" });

    expect(requests.map((params) => [params.get("skip"), params.get("limit")])).toEqual([
      ["0", "100"],
      ["100", "100"],
      ["200", "100"],
    ]);
    for (const params of requests) {
      expect(params.get("chip_id")).toBe("16Qv1");
      expect(params.get("start_from")).toBe("2026-11-25T00:00:00Z");
      expect(params.get("start_to")).toBe("2026-11-26T00:00:00Z");
    }
    expect(summary.filters).toEqual({ chip_id: "16Qv1", start_from: "2026-11-25T00:00:00Z", start_to: "2026-11-26T00:00:00Z" });
    expect(summary.complete).toBe(true);
    expect(summary.diagnostics).toEqual([]);
    expect(summary.total).toBe(250);
    expect(summary.statusCounts).toEqual({ completed: 200, failed: 50 });
    expect(summary.read).toEqual({ rows: 250, returned: 250, pages: 3, pageSize: 100, maxRows: 1000, stoppedBy: "all_rows" });
    expect(summary.aggregates.byStatus).toEqual({ completed: 200, failed: 50 });
    const rabi = rows250.filter((item) => item.task_name === "CheckRabi");
    expect(summary.aggregates.byTask).toEqual([
      { taskName: "CheckT1", rows: 250 - rabi.length, statuses: countStatuses(rows250.filter((item) => item.task_name === "CheckT1")) },
      { taskName: "CheckRabi", rows: rabi.length, statuses: countStatuses(rabi) },
    ]);
    // Times without a zone are UTC: 250 rows from 23:00 back 9 hours stay on 2026-11-25.
    expect(summary.aggregates.byDay).toEqual([{ day: "2026-11-25", rows: 250, statuses: { completed: 200, failed: 50 } }]);
    expect(summary.aggregates.undated).toBe(0);
    expect(summary.aggregates.executions).toBe(7);
  });

  it("counts days in the requested time zone", async () => {
    const { qdash } = qdashWith(rows250);
    const summary = await qdash.taskResults.summarize({ chipId: "16Qv1", timezone: "Asia/Tokyo" });
    // 23:00Z..15:00Z is 08:00..00:00 JST the next day; the 15:xx hour stays on 26 as 00:xx JST.
    expect(summary.aggregates.byDay.map((day) => [day.day, day.rows])).toEqual([["2026-11-26", 250]]);
    expect(summary.aggregates.timezone).toBe("Asia/Tokyo");
  });

  it("reads no further than an empty result", async () => {
    const { qdash, requests } = qdashWith([]);
    const summary = await qdash.taskResults.summarize({ chipId: "16Qv1" });
    expect(requests).toHaveLength(1);
    expect(summary.complete).toBe(true);
    expect(summary.total).toBe(0);
    expect(summary.statusCounts).toEqual({});
    expect(summary.read).toMatchObject({ rows: 0, pages: 1, stoppedBy: "all_rows" });
    expect(summary.aggregates).toMatchObject({ byStatus: {}, byTask: [], byDay: [], executions: 0 });
  });

  it("stops at maxRows and reports partial aggregates beside QDash's full totals", async () => {
    const { qdash, requests } = qdashWith(rows250);
    const summary = await qdash.taskResults.summarize({ chipId: "16Qv1", maxRows: 150 });
    expect(requests.map((params) => params.get("limit"))).toEqual(["100", "50"]);
    expect(summary.complete).toBe(false);
    expect(summary.read).toMatchObject({ rows: 150, stoppedBy: "max_rows" });
    expect(summary.diagnostics.map((d) => d.code)).toEqual(["max_rows_reached"]);
    expect(summary.diagnostics[0]!.message).toMatch(/read 150 of 250 rows/);
    // The full totals come from QDash; the aggregates only from the rows read.
    expect(summary.statusCounts).toEqual({ completed: 200, failed: 50 });
    expect(summary.aggregates.byStatus).toEqual(countStatuses(rows250.slice(0, 150)));
  });

  it.each([
    [undefined, { completed: 200 }, true],
    [undefined, { completed: 200, failed: 50 }, false],
    ["completed", { completed: 200, failed: 50 }, true],
    ["completed", { completed: 250, failed: 50 }, false],
    ["unknown", { unknown: 200 }, true],
    ["unknown", { unknown: 260 }, false],
  ] as const)("checks partial metadata for status %s and counts %j", async (status, status_counts, mismatch) => {
    const rows = rows250.map((item) => ({ ...item, status: status ?? item.status }));
    const { qdash } = qdashWith(rows, ({ skip, limit }) => ({
      items: rows.slice(skip, skip + limit), total: 250, skip, limit, status_counts,
    }));
    const summary = await qdash.taskResults.summarize({ maxRows: 100, status });
    expect(summary.complete).toBe(false);
    const codes = summary.diagnostics.map((d) => d.code);
    expect(codes).toContain("max_rows_reached");
    expect(codes.includes("status_counts_mismatch")).toBe(mismatch);
  });

  it("is complete when maxRows equals total", async () => {
    const { qdash } = qdashWith(rows250);
    const summary = await qdash.taskResults.summarize({ maxRows: 250 });
    expect(summary.complete).toBe(true);
    expect(summary.read.stoppedBy).toBe("all_rows");
  });

  it("counts a row repeated on a later page once and reports it", async () => {
    // A row added at the head between pages shifts the next page by one.
    const shifted = [row(-1), ...rows250];
    const { qdash } = qdashWith(rows250, ({ skip, limit, call }) => {
      const source = call === 1 ? rows250 : shifted;
      return { items: source.slice(skip, skip + limit), total: source.length, skip, limit, status_counts: countStatuses(source) };
    });
    const summary = await qdash.taskResults.summarize({});
    expect(summary.complete).toBe(false);
    expect(summary.read.rows).toBe(250);
    expect(summary.diagnostics.map((d) => d.code)).toEqual(
      expect.arrayContaining(["total_changed", "status_counts_changed", "duplicate_task_id"]),
    );
    expect(summary.aggregates.byStatus).toEqual(countStatuses(rows250));
    // total stays the first page's.
    expect(summary.total).toBe(250);
  });

  it.each([
    ["an empty page", 0, "empty_page"],
    ["a short page", 10, "short_page"],
  ])("stops at %s before total and does not call the read complete", async (_name, rowsOnSecondPage, code) => {
    const { qdash, requests } = qdashWith(rows250, ({ skip, limit }) => ({
      items: skip === 0 ? rows250.slice(0, limit) : rows250.slice(skip, skip + rowsOnSecondPage),
      total: 250,
      skip,
      limit,
      status_counts: countStatuses(rows250),
    }));
    const summary = await qdash.taskResults.summarize({});
    expect(requests).toHaveLength(2);
    expect(summary.complete).toBe(false);
    expect(summary.read.stoppedBy).toBe(code);
    expect(summary.diagnostics.map((d) => d.code)).toEqual([code]);
  });

  it("reports status_counts that disagree with the rows read or with total", async () => {
    const rows = rows250.slice(0, 20);
    const { qdash } = qdashWith(rows, ({ skip, limit }) => ({
      items: rows.slice(skip, skip + limit),
      total: rows.length,
      skip,
      limit,
      status_counts: { completed: 20 },
    }));
    const summary = await qdash.taskResults.summarize({});
    expect(summary.complete).toBe(false);
    expect(summary.diagnostics.map((d) => d.code)).toEqual(["status_counts_mismatch"]);
  });

  it("compares status_counts of the filtered status with total, since QDash counts it without the status filter", async () => {
    const failed = rows250.filter((item) => item.status === "failed");
    const answer = (counts: Record<string, number>) =>
      qdashWith(failed, ({ skip, limit }) => ({ items: failed.slice(skip, skip + limit), total: failed.length, skip, limit, status_counts: counts }));
    const ok = await answer({ completed: 200, failed: 50 }).qdash.taskResults.summarize({ status: "failed" });
    expect(ok.complete).toBe(true);
    expect(ok.aggregates.byStatus).toEqual({ failed: 50 });
    const off = await answer({ completed: 200, failed: 49 }).qdash.taskResults.summarize({ status: "failed" });
    expect(off.diagnostics.map((d) => d.code)).toEqual(["status_counts_mismatch"]);
  });

  it("keeps statuses as stored and reports rows outside the filters", async () => {
    const rows = [row(1, { status: "skipped" }), row(2, { status: "running", chip_id: "other" }), row(3, { start_at: null })];
    const { qdash } = qdashWith(rows);
    const summary = await qdash.taskResults.summarize({ chipId: "16Qv1" });
    expect(summary.aggregates.byStatus).toEqual({ completed: 1, running: 1, skipped: 1 });
    expect(summary.aggregates.undated).toBe(1);
    expect(summary.diagnostics.map((d) => d.code)).toEqual(["row_outside_filters"]);
  });

  it.each<[string, unknown, RegExp]>([
    ["a body that is not an object", [], /the body is not an object/],
    ["items that are not an array", { items: null, total: 1, skip: 0, limit: 100, status_counts: {} }, /items is not an array/],
    ["a row without task_id", { items: [{ status: "completed" }], total: 1, skip: 0, limit: 100, status_counts: {} }, /item 0 lacks/],
    ["no status_counts", { items: [], total: 0, skip: 0, limit: 100 }, /status_counts/],
    ["another skip", { items: [], total: 0, skip: 5, limit: 100, status_counts: {} }, /skip is 5, not the 0 requested/],
    ["another limit", { items: [], total: 0, skip: 0, limit: 50, status_counts: {} }, /limit is 50, not the 100 requested/],
    [
      "more rows than the limit",
      { items: Array.from({ length: 101 }, (_, i) => row(i)), total: 300, skip: 0, limit: 100, status_counts: {} },
      /items has 101 rows, more than the limit 100 requested/,
    ],
  ])("rejects %s instead of reading it as empty", async (_name, body, message) => {
    const { qdash } = qdashWith([], () => body);
    const error = await qdash.taskResults.summarize({}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(QDashApiError);
    expect((error as Error).message).toMatch(message);
  });

  it("never reads past maxRows when a page returns more rows than it asked for", async () => {
    const { qdash, requests } = qdashWith(rows250, ({ skip, limit }) => ({
      // The second request asks for 50 rows; answering 100 would overrun maxRows 150.
      items: rows250.slice(skip, skip + 100),
      total: 250,
      skip,
      limit,
      status_counts: countStatuses(rows250),
    }));
    const error = await qdash.taskResults.summarize({ maxRows: 150 }).catch((e: unknown) => e);
    expect(requests.map((params) => params.get("limit"))).toEqual(["100", "50"]);
    expect(error).toBeInstanceOf(QDashApiError);
    expect((error as Error).message).toMatch(/items has 100 rows, more than the limit 50 requested/);
  });

  it("accepts a February 29 of a leap year and the earliest and latest clock times", async () => {
    const { qdash } = qdashWith([]);
    await expect(qdash.taskResults.summarize({ startFrom: "2028-02-29T00:00", startTo: "2028-02-29T23:59:59.999999" })).resolves.toMatchObject({
      complete: true,
    });
  });

  it("sends the bounds with an explicit offset, reading a time without one as UTC", async () => {
    const { qdash, requests } = qdashWith([]);
    const summary = await qdash.taskResults.summarize({ startFrom: "2026-11-25T09:00:00+0900", startTo: "2026-11-25T12:00" });
    expect(requests[0]!.get("start_from")).toBe("2026-11-25T09:00:00+09:00");
    expect(requests[0]!.get("start_to")).toBe("2026-11-25T12:00:00Z");
    expect(summary.filters).toMatchObject({ start_from: "2026-11-25T09:00:00+09:00", start_to: "2026-11-25T12:00:00Z" });
  });

  it("checks returned start times against the inclusive bounds", async () => {
    const at = (time: string, i: number, extra: Partial<TaskResultListItem> = {}) => row(i, { start_at: time, ...extra });
    const options = { startFrom: "2026-11-25T00:00:00Z", startTo: "2026-11-25T09:00:00+09:00" };
    // Both bounds are 2026-11-25T00:00:00Z; a row exactly at them is inside.
    const inside = await qdashWith([at("2026-11-25T00:00:00", 1), at("2026-11-25T09:00:00+09:00", 2)]).qdash.taskResults.summarize(options);
    expect(inside.complete).toBe(true);

    const outside = await qdashWith([at("2026-11-25T00:00:00.001000", 1), at("2026-11-24T23:59:59.999", 2)]).qdash.taskResults.summarize(options);
    expect(outside.complete).toBe(false);
    expect(outside.diagnostics.map((d) => d.code)).toEqual(["row_outside_filters"]);
    expect(outside.diagnostics[0]!.message).toMatch(/^2 rows do not match/);

    const unreadable = await qdashWith([at("2026-11-25T00:00:00Z", 1), row(2, { start_at: null }), at("2026-11-25", 3)]).qdash.taskResults.summarize(
      options,
    );
    expect(unreadable.complete).toBe(false);
    expect(unreadable.diagnostics.map((d) => d.code)).toEqual(["row_start_unreadable"]);
    expect(unreadable.diagnostics[0]!.message).toMatch(/^2 rows have no readable start_at/);
    expect(unreadable.aggregates.undated).toBe(2);
  });

  it("filters by message as GET /task-results does and checks the rows returned", async () => {
    const rows = [row(1, { message: "Fit FAILED (r2 < 0.5)" }), row(2, { message: "fit failed (R2 < 0.5) twice" })];
    const { qdash, requests } = qdashWith(rows);
    const summary = await qdash.taskResults.summarize({ messageContains: "failed (r2" });
    expect(requests[0]!.get("message_contains")).toBe("failed (r2");
    expect(summary.filters).toEqual({ message_contains: "failed (r2" });
    expect(summary.complete).toBe(true);

    const off = await qdashWith([...rows, row(3, { message: "ok" }), row(4, { message: undefined })]).qdash.taskResults.summarize({
      messageContains: "failed (r2",
    });
    expect(off.diagnostics.map((d) => d.code)).toEqual(["row_outside_filters"]);
    expect(off.diagnostics[0]!.message).toMatch(/^2 rows do not match/);
  });

  it("keeps an empty stored status as is and compares it with QDash's \"unknown\" count", async () => {
    const rows = [row(1, { status: "" }), row(2, { status: "" }), row(3, { status: "unknown" }), row(4, { status: "completed" })];
    const { qdash } = qdashWith(rows, ({ skip, limit }) => ({
      items: rows.slice(skip, skip + limit),
      total: rows.length,
      skip,
      limit,
      status_counts: { completed: 1, unknown: 3 },
    }));
    const summary = await qdash.taskResults.summarize({});
    expect(summary.complete).toBe(true);
    expect(summary.aggregates.byStatus).toEqual({ "": 2, completed: 1, unknown: 1 });
    expect(summary.aggregates.byTask.flatMap((task) => Object.keys(task.statuses))).toContain("");

    const wrong = await qdashWith(rows, ({ skip, limit }) => ({
      items: rows.slice(skip, skip + limit),
      total: rows.length,
      skip,
      limit,
      status_counts: { "": 2, completed: 1, unknown: 1 },
    })).qdash.taskResults.summarize({});
    expect(wrong.diagnostics.map((d) => d.code)).toEqual(["status_counts_mismatch"]);
  });

  it("accepts status_counts.unknown above total for status \"unknown\", since it also counts empty statuses", async () => {
    const rows = [row(1, { status: "unknown" })];
    const answer = (unknown: number) =>
      qdashWith(rows, ({ skip, limit }) => ({ items: rows.slice(skip, skip + limit), total: 1, skip, limit, status_counts: { unknown } }));
    expect((await answer(3).qdash.taskResults.summarize({ status: "unknown" })).complete).toBe(true);
    const short = await answer(0).qdash.taskResults.summarize({ status: "unknown" });
    expect(short.diagnostics.map((d) => d.code)).toEqual(["status_counts_mismatch"]);
  });

  it("rejects when a later page fails, as other reads do", async () => {
    const { qdash } = qdashWith(rows250, ({ skip, limit, call }) =>
      call === 1
        ? { items: rows250.slice(skip, skip + limit), total: 250, skip, limit, status_counts: countStatuses(rows250) }
        : new Response(JSON.stringify({ detail: "database unavailable" }), { status: 500, headers: { "Content-Type": "application/json" } }),
    );
    await expect(qdash.taskResults.summarize({})).rejects.toBeInstanceOf(QDashApiError);
  });

  it.each<[string, Record<string, unknown>, RegExp]>([
    ["maxRows above the bound", { maxRows: 5001 }, /maxRows must be an integer from 1 to 5000/],
    ["a fractional maxRows", { maxRows: 1.5 }, /maxRows must be/],
    ["pageSize above 100", { pageSize: 101 }, /pageSize must be an integer from 1 to 100/],
    ["too many pages", { maxRows: 1000, pageSize: 10 }, new RegExp(`more than ${SUMMARIZE_MAX_PAGES} requests`)],
    ["an empty filter", { chipId: "" }, /chipId must be a non-empty string/],
    ["a bad time", { startFrom: "yesterday" }, /startFrom is not an ISO 8601 date-time/],
    ["a date without a time", { startFrom: "2026-11-26" }, /startFrom is not an ISO 8601 date-time/],
    ["a free-form date", { startTo: "Nov 26 2026" }, /startTo is not an ISO 8601 date-time/],
    ["an impossible date", { startFrom: "2026-02-30T00:00:00Z" }, /startFrom is not an ISO 8601 date-time/],
    ["February 29 outside a leap year", { startFrom: "2026-02-29T00:00:00Z" }, /startFrom is not/],
    ["hour 24", { startTo: "2026-11-26T24:00:00Z" }, /startTo is not/],
    ["an impossible offset", { startTo: "2026-11-26T00:00:00+09:60" }, /startTo is not/],
    ["reversed bounds", { startFrom: "2026-11-26T00:00:00Z", startTo: "2026-11-26T08:59:59+09:00" }, /startFrom .* is after startTo/],
    ["an empty message search", { messageContains: "" }, /messageContains must be a non-empty string/],
    ["a bad time zone", { timezone: "Mars/Olympus" }, /timezone must be an IANA time zone/],
    ["an unknown option", { limit: 10 }, /limit is not an option of summarize/],
  ])("refuses %s before any request", async (_name, options, message) => {
    const { qdash, requests } = qdashWith(rows250);
    const error = await qdash.taskResults.summarize(options).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(QDashValidationError);
    expect((error as Error).message).toMatch(message);
    expect(requests).toEqual([]);
  });
});
