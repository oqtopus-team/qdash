/**
 * Status counts of the task results that match one set of filters, read page
 * by page from `GET /task-results`: `qdash.taskResults.summarize(options)`.
 *
 * QDash answers the totals (`total`, `status_counts`) for every matching row,
 * but rows only one page of at most 100 at a time. This operation pages
 * through the rows within an explicit bound, counts the rows it read, and says
 * how far those counts can be trusted. It never reads a malformed page as an
 * empty one, never counts a row twice, and never calls a partial read
 * complete.
 *
 * The pages are separate offset reads, not a snapshot: rows added or removed
 * while the pages are read can shift later pages. Changes that show in the
 * totals, repeated rows, and short or empty pages are reported, but a read
 * without them is still not proof that nothing changed.
 */
import { isRecord, read, type Context } from "./_http.js";
import { QDashApiError, QDashValidationError } from "./errors.js";
import type { TaskResultListItem } from "./types.js";

/** Rows one `GET /task-results` request returns at most, and the page size `summarize` uses by default. */
export const SUMMARIZE_PAGE_SIZE = 100;
/** Rows `summarize` reads when `maxRows` is omitted. */
export const SUMMARIZE_DEFAULT_ROWS = 1000;
/** Most rows one `summarize` call reads. */
export const SUMMARIZE_MAX_ROWS = 5000;
/** Most `GET /task-results` requests one `summarize` call sends. */
export const SUMMARIZE_MAX_PAGES = 50;

const FILTERS = [
  "chipId",
  "taskName",
  "qid",
  "executionId",
  "username",
  "status",
  "startFrom",
  "startTo",
  "messageContains",
] as const;
const SUMMARIZE_OPTIONS = new Set<string>([...FILTERS, "maxRows", "pageSize", "timezone"]);

export interface TaskResultSummaryOptions {
  chipId?: string;
  taskName?: string;
  /** Exact qubit (`"6"`) or coupling (`"6-7"`) ID as QDash stores it. */
  qid?: string;
  executionId?: string;
  username?: string;
  /** Exact stored status. QDash counts `status_counts` without this filter. */
  status?: string;
  /**
   * Inclusive lower bound on the task start time: an ISO 8601 date-time
   * `YYYY-MM-DDTHH:MM[:SS[.ffffff]]` with an optional `Z` or `±HH:MM` offset.
   * Without an offset it is UTC, as QDash stores times. It is sent with an
   * explicit offset.
   */
  startFrom?: string;
  /** Inclusive upper bound on the task start time, in the same form as `startFrom`; not before it. */
  startTo?: string;
  /** Text the row's `message` contains, compared case-insensitively, as `GET /task-results` filters it. */
  messageContains?: string;
  /** Most rows to read, an integer from 1 to 5000. Defaults to 1000. */
  maxRows?: number;
  /** Rows per request, an integer from 1 to 100. Defaults to 100. At most 50 requests are sent. */
  pageSize?: number;
  /** IANA time zone that defines the days of `byDay`. Defaults to `"UTC"`. */
  timezone?: string;
}

/** The filters sent with every page, as `GET /task-results` names them. */
export interface TaskResultSummaryFilters {
  chip_id?: string;
  task_name?: string;
  qid?: string;
  execution_id?: string;
  username?: string;
  status?: string;
  start_from?: string;
  start_to?: string;
  message_contains?: string;
}

/**
 * Something that limits what the counts of the rows read can say.
 *
 * - `max_rows_reached`: `maxRows` rows were read before `total`.
 * - `empty_page` / `short_page`: a page had no rows, or fewer than asked,
 *   before `total` rows were read; reading stopped there.
 * - `duplicate_task_id`: a row was returned again on a later page; it is
 *   counted once. Rows were probably added while reading, so some may be missed.
 * - `total_changed` / `status_counts_changed`: a later page reported other
 *   totals than the first.
 * - `row_count_mismatch`: reading ended with a different number of distinct
 *   rows than `total`.
 * - `status_counts_mismatch`: without a status filter, the counts of the rows
 *   read disagree with `statusCounts`, or `statusCounts` does not add up to
 *   `total`; with one, `statusCounts[status]` is not `total`.
 * - `row_outside_filters`: a row does not match a filter sent: an exact
 *   filter (chip, task, qid, execution, username or status), the start-time
 *   bounds, or `messageContains`.
 * - `row_start_unreadable`: with a start-time bound sent, a row has no
 *   readable `start_at`, so it cannot be shown to be within the bounds.
 */
export type TaskResultSummaryDiagnosticCode =
  | "max_rows_reached"
  | "empty_page"
  | "short_page"
  | "duplicate_task_id"
  | "total_changed"
  | "status_counts_changed"
  | "row_count_mismatch"
  | "status_counts_mismatch"
  | "row_outside_filters"
  | "row_start_unreadable";

export interface TaskResultSummaryDiagnostic {
  code: TaskResultSummaryDiagnosticCode;
  message: string;
}

/** Counts of the rows of one task name or day, by exact stored status. */
export interface TaskResultCounts {
  rows: number;
  statuses: Record<string, number>;
}

export interface TaskResultSummary {
  filters: TaskResultSummaryFilters;
  /** Rows matching every filter sent, `status` included, as the first page reported. */
  total: number;
  /**
   * Rows per stored status as the first page reported, for every row matching
   * the filters other than `status`: QDash counts them without the status
   * filter, so with `status` they do not add up to `total`. QDash counts rows
   * with an empty or missing status under `"unknown"`, together with rows
   * whose status is `"unknown"`.
   */
  statusCounts: Record<string, number>;
  /** How the rows were read. */
  read: {
    /** Distinct rows read and counted in `aggregates`. */
    rows: number;
    /** Rows returned, including repeated ones. */
    returned: number;
    pages: number;
    pageSize: number;
    maxRows: number;
    /** Why reading stopped. */
    stoppedBy: "all_rows" | "max_rows" | "empty_page" | "short_page";
  };
  /**
   * True only when every row `total` counts was read once, the totals stayed
   * the same on every page, and the counts agree. Offset pages are not a
   * snapshot, so even then concurrent changes cannot be ruled out.
   */
  complete: boolean;
  /** Empty when `complete` is true. */
  diagnostics: TaskResultSummaryDiagnostic[];
  /**
   * Counts of the rows read only (`read.rows`). When `complete` is false these
   * are partial and are not counts of all matching rows; use `total` and
   * `statusCounts` for those.
   */
  aggregates: {
    /** Rows by exact stored status; an empty status stays `""`. */
    byStatus: Record<string, number>;
    /** By task name, most rows first. */
    byTask: Array<{ taskName: string } & TaskResultCounts>;
    /** By the day of `start_at` in `timezone` (`YYYY-MM-DD`), oldest first; rows without a readable `start_at` are in `undated`. */
    byDay: Array<{ day: string } & TaskResultCounts>;
    undated: number;
    timezone: string;
    /** Distinct `execution_id` values. */
    executions: number;
  };
}

interface Page {
  items: TaskResultListItem[];
  total: number;
  skip: number;
  limit: number;
  status_counts: Record<string, number>;
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function dayFormatter(timezone: string): Intl.DateTimeFormat | null {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" });
  } catch {
    return null;
  }
}

function checkOptions(options: TaskResultSummaryOptions): {
  filters: TaskResultSummaryFilters;
  /** Epoch milliseconds of the start-time bounds sent. */
  bounds: { from?: number; to?: number };
  maxRows: number;
  pageSize: number;
  timezone: string;
} {
  const raw = (options ?? {}) as unknown as Record<string, unknown>;
  const problems: string[] = [];
  if (!isRecord(options)) problems.push("options must be an object");
  for (const field of FILTERS) {
    const value = raw[field];
    // A message search may be blank text; QDash matches it as a substring.
    const ok = field === "messageContains" ? typeof value === "string" && value !== "" : nonEmptyString(value);
    if (value !== undefined && !ok) problems.push(`${field} must be a non-empty string`);
  }
  const bounds: Partial<Record<"startFrom" | "startTo", IsoTime>> = {};
  for (const field of ["startFrom", "startTo"] as const) {
    const value = raw[field];
    if (!nonEmptyString(value)) continue;
    const time = parseIsoTime(value);
    if (time === null) {
      problems.push(
        `${field} is not an ISO 8601 date-time YYYY-MM-DDTHH:MM[:SS[.ffffff]] with an optional Z or ±HH:MM offset (got ${JSON.stringify(value)})`,
      );
    } else bounds[field] = time;
  }
  if (bounds.startFrom && bounds.startTo && bounds.startFrom.at > bounds.startTo.at) {
    problems.push(`startFrom ${JSON.stringify(raw.startFrom)} is after startTo ${JSON.stringify(raw.startTo)}`);
  }
  const maxRows = raw.maxRows ?? SUMMARIZE_DEFAULT_ROWS;
  if (!(Number.isInteger(maxRows) && (maxRows as number) >= 1 && (maxRows as number) <= SUMMARIZE_MAX_ROWS)) {
    problems.push(`maxRows must be an integer from 1 to ${SUMMARIZE_MAX_ROWS} (got ${JSON.stringify(raw.maxRows)})`);
  }
  const pageSize = raw.pageSize ?? SUMMARIZE_PAGE_SIZE;
  if (!(Number.isInteger(pageSize) && (pageSize as number) >= 1 && (pageSize as number) <= SUMMARIZE_PAGE_SIZE)) {
    problems.push(`pageSize must be an integer from 1 to ${SUMMARIZE_PAGE_SIZE} (got ${JSON.stringify(raw.pageSize)})`);
  } else if (Number.isInteger(maxRows) && Math.ceil((maxRows as number) / (pageSize as number)) > SUMMARIZE_MAX_PAGES) {
    problems.push(`maxRows ${maxRows} at pageSize ${pageSize} needs more than ${SUMMARIZE_MAX_PAGES} requests; raise pageSize or lower maxRows`);
  }
  const timezone = raw.timezone ?? "UTC";
  if (!nonEmptyString(timezone) || dayFormatter(timezone) === null) {
    problems.push(`timezone must be an IANA time zone such as "UTC" or "Asia/Tokyo" (got ${JSON.stringify(raw.timezone)})`);
  }
  const unknown = Object.keys(raw).filter((key) => raw[key] !== undefined && !SUMMARIZE_OPTIONS.has(key));
  if (unknown.length > 0) {
    problems.push(`${unknown.join(", ")} ${unknown.length === 1 ? "is not an option" : "are not options"} of summarize`);
  }
  if (problems.length > 0) throw new QDashValidationError(`${problems.join("; ")}.`, { body: { problems } });
  const filters: TaskResultSummaryFilters = {};
  const names: Record<(typeof FILTERS)[number], keyof TaskResultSummaryFilters> = {
    chipId: "chip_id",
    taskName: "task_name",
    qid: "qid",
    executionId: "execution_id",
    username: "username",
    status: "status",
    startFrom: "start_from",
    startTo: "start_to",
    messageContains: "message_contains",
  };
  for (const field of FILTERS) {
    const value = raw[field];
    if (typeof value === "string") filters[names[field]] = value;
  }
  // Send the bounds with an explicit offset, so QDash reads the instant checked here.
  if (bounds.startFrom) filters.start_from = bounds.startFrom.text;
  if (bounds.startTo) filters.start_to = bounds.startTo.text;
  return {
    filters,
    bounds: { from: bounds.startFrom?.at, to: bounds.startTo?.at },
    maxRows: maxRows as number,
    pageSize: pageSize as number,
    timezone: timezone as string,
  };
}

/** The page, or `QDashApiError` naming what is wrong with it; never an empty page in place of a malformed one. */
function checkPage(payload: unknown, skip: number, limit: number): Page {
  const problems: string[] = [];
  if (!isRecord(payload)) problems.push("the body is not an object");
  else {
    if (!Array.isArray(payload.items)) problems.push("items is not an array");
    else {
      if (payload.items.length > limit) problems.push(`items has ${payload.items.length} rows, more than the limit ${limit} requested`);
      const bad = payload.items.findIndex(
        (item) =>
          !isRecord(item) ||
          !nonEmptyString(item.task_id) ||
          typeof item.task_name !== "string" ||
          typeof item.status !== "string" ||
          typeof item.execution_id !== "string",
      );
      if (bad !== -1) problems.push(`item ${bad} lacks a string task_id, task_name, status or execution_id`);
    }
    if (!(Number.isInteger(payload.total) && (payload.total as number) >= 0)) problems.push("total is not a non-negative integer");
    if (payload.skip !== skip) problems.push(`skip is ${JSON.stringify(payload.skip)}, not the ${skip} requested`);
    if (payload.limit !== limit) problems.push(`limit is ${JSON.stringify(payload.limit)}, not the ${limit} requested`);
    const counts = payload.status_counts;
    if (!isRecord(counts) || Object.values(counts).some((count) => !(Number.isInteger(count) && (count as number) >= 0))) {
      problems.push("status_counts is not an object of non-negative integers");
    }
  }
  if (problems.length > 0) {
    throw new QDashApiError(`Unexpected GET /task-results response: ${problems.join("; ")}`, { body: payload });
  }
  return payload as unknown as Page;
}

function sameCounts(a: Record<string, number>, b: Record<string, number>): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) if ((a[key] ?? 0) !== (b[key] ?? 0)) return false;
  return true;
}

function sortedCounts(counts: Map<string, number>): Record<string, number> {
  return Object.fromEntries([...counts].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

function bump(counts: Map<string, number>, key: string): void {
  counts.set(key, (counts.get(key) ?? 0) + 1);
}

interface IsoTime {
  /** Epoch milliseconds; sub-millisecond digits are dropped, as QDash's database keeps milliseconds. */
  at: number;
  /** The same time with an explicit `Z` or `±HH:MM` offset. */
  text: string;
}

const ISO_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|([+-])(\d{2}):?(\d{2}))?$/;

/**
 * An ISO 8601 date-time `YYYY-MM-DDTHH:MM[:SS[.ffffff]]` with an optional
 * `Z` or `±HH:MM` (`±HHMM`) offset, or null. A time without an offset is UTC,
 * as QDash stores and returns times. Impossible dates and times, such as
 * February 30 or hour 24, are null rather than rolled over as `Date.parse`
 * would.
 */
function parseIsoTime(value: unknown): IsoTime | null {
  if (typeof value !== "string") return null;
  const match = ISO_TIME.exec(value);
  if (!match) return null;
  const [, y, mo, d, h, mi, sec = "00", fraction = "", zone, sign, oh, om] = match;
  const year = Number(y);
  const month = Number(mo);
  const day = Number(d);
  const hour = Number(h);
  const minute = Number(mi);
  const second = Number(sec);
  const daysInMonth = month >= 1 && month <= 12 ? new Date(Date.UTC(2000, month, 0)).getUTCDate() : 0;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const lastDay = month === 2 && !leap ? 28 : daysInMonth;
  if (year < 1 || day < 1 || day > lastDay || hour > 23 || minute > 59 || second > 59) return null;
  if (zone && zone !== "Z" && (Number(oh) > 23 || Number(om) > 59)) return null;
  const local = new Date(0);
  local.setUTCFullYear(year, month - 1, day);
  local.setUTCHours(hour, minute, second, Number(fraction.padEnd(3, "0").slice(0, 3)));
  const offset = !zone || zone === "Z" ? 0 : (sign === "-" ? -1 : 1) * (Number(oh) * 60 + Number(om));
  const clock = `${y}-${mo}-${d}T${h}:${mi}:${sec}${fraction ? `.${fraction}` : ""}`;
  return {
    at: local.getTime() - offset * 60_000,
    text: `${clock}${!zone || zone === "Z" ? "Z" : `${sign}${oh}:${om}`}`,
  };
}

/** `status_counts` names an empty stored status `"unknown"`, as QDash groups it. */
function apiStatusKey(status: string): string {
  return status === "" ? "unknown" : status;
}

/** Whether `message` contains `needle` case-insensitively, as QDash's escaped case-insensitive regex matches it. */
function messageContains(message: unknown, needle: string): boolean {
  if (typeof message !== "string") return false;
  return new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "iu").test(message);
}

const ROW_FILTER_FIELDS: Array<[keyof TaskResultSummaryFilters, keyof TaskResultListItem]> = [
  ["chip_id", "chip_id"],
  ["task_name", "task_name"],
  ["qid", "qid"],
  ["execution_id", "execution_id"],
  ["username", "username"],
  ["status", "status"],
];

export async function summarizeTaskResults(context: Context, options: TaskResultSummaryOptions): Promise<TaskResultSummary> {
  const { filters, bounds, maxRows, pageSize, timezone } = checkOptions(options);
  const bounded = bounds.from !== undefined || bounds.to !== undefined;
  const formatter = dayFormatter(timezone)!;
  const diagnostics: TaskResultSummaryDiagnostic[] = [];
  const noted = new Set<TaskResultSummaryDiagnosticCode>();
  const note = (code: TaskResultSummaryDiagnosticCode, message: string) => {
    if (noted.has(code)) return;
    noted.add(code);
    diagnostics.push({ code, message });
  };

  const seen = new Set<string>();
  const rows: TaskResultListItem[] = [];
  let duplicates = 0;
  let outside = 0;
  let unreadableStart = 0;
  let returned = 0;
  let pages = 0;
  let skip = 0;
  let first: Page | undefined;
  let stoppedBy: TaskResultSummary["read"]["stoppedBy"] = "all_rows";

  for (;;) {
    const limit = Math.min(pageSize, maxRows - returned);
    const payload: unknown = await read(context.reads, (requestOptions) =>
      context.api.taskResult.listTaskResults({ ...filters, skip, limit }, requestOptions),
    );
    const page = checkPage(payload, skip, limit);
    pages += 1;
    if (!first) first = page;
    else {
      if (page.total !== first.total) {
        note("total_changed", `total changed from ${first.total} to ${page.total} at skip ${skip}: rows were added or removed while reading`);
      }
      if (!sameCounts(page.status_counts, first.status_counts)) {
        note("status_counts_changed", `status_counts changed at skip ${skip}: rows were added, removed or changed status while reading`);
      }
    }
    returned += page.items.length;
    for (const row of page.items) {
      if (seen.has(row.task_id)) {
        duplicates += 1;
        continue;
      }
      seen.add(row.task_id);
      rows.push(row);
      let matches = !ROW_FILTER_FIELDS.some(([filter, field]) => filters[filter] !== undefined && row[field] !== filters[filter]);
      if (filters.message_contains !== undefined && !messageContains(row.message, filters.message_contains)) matches = false;
      if (bounded) {
        const at = parseIsoTime(row.start_at)?.at;
        if (at === undefined) unreadableStart += 1;
        else if ((bounds.from !== undefined && at < bounds.from) || (bounds.to !== undefined && at > bounds.to)) matches = false;
      }
      if (!matches) outside += 1;
    }
    skip += page.items.length;
    if (skip >= page.total) break;
    if (page.items.length === 0) {
      stoppedBy = "empty_page";
      note("empty_page", `the page at skip ${skip} had no rows although total is ${page.total}`);
      break;
    }
    if (page.items.length < limit) {
      stoppedBy = "short_page";
      note("short_page", `the page at skip ${skip - page.items.length} had ${page.items.length} rows, not ${limit}, although total is ${page.total}`);
      break;
    }
    if (returned >= maxRows) {
      stoppedBy = "max_rows";
      note("max_rows_reached", `read ${returned} of ${page.total} rows: maxRows ${maxRows} was reached; aggregates count only the rows read`);
      break;
    }
  }

  const total = first!.total;
  const statusCounts = sortedCounts(new Map(Object.entries(first!.status_counts)));
  if (duplicates > 0) {
    note("duplicate_task_id", `${duplicates} row${duplicates === 1 ? " was" : "s were"} returned again on a later page and counted once; rows were probably added while reading, so others may have been skipped`);
  }
  if (outside > 0) note("row_outside_filters", `${outside} row${outside === 1 ? " does" : "s do"} not match the filters sent`);
  if (unreadableStart > 0) {
    note(
      "row_start_unreadable",
      `${unreadableStart} row${unreadableStart === 1 ? " has" : "s have"} no readable start_at, so ${unreadableStart === 1 ? "it" : "they"} cannot be shown to be within the start-time bounds`,
    );
  }
  if (stoppedBy === "all_rows" && rows.length !== total) {
    note("row_count_mismatch", `read ${rows.length} distinct rows, but total is ${total}`);
  }

  const byStatus = new Map<string, number>();
  const byTask = new Map<string, { rows: number; statuses: Map<string, number> }>();
  const byDay = new Map<string, { rows: number; statuses: Map<string, number> }>();
  const executions = new Set<string>();
  let undated = 0;
  for (const row of rows) {
    const status = row.status;
    bump(byStatus, status);
    const task = byTask.get(row.task_name) ?? { rows: 0, statuses: new Map() };
    task.rows += 1;
    bump(task.statuses, status);
    byTask.set(row.task_name, task);
    const at = parseIsoTime(row.start_at)?.at;
    if (at === undefined) undated += 1;
    else {
      const key = formatter.format(new Date(at));
      const day = byDay.get(key) ?? { rows: 0, statuses: new Map() };
      day.rows += 1;
      bump(day.statuses, status);
      byDay.set(key, day);
    }
    if (row.execution_id) executions.add(row.execution_id);
  }

  if (stoppedBy === "all_rows" && rows.length === total) {
    // Compare under the keys status_counts uses, where an empty status is "unknown".
    const apiKeyed = new Map<string, number>();
    for (const [status, count] of byStatus) apiKeyed.set(apiStatusKey(status), (apiKeyed.get(apiStatusKey(status)) ?? 0) + count);
    const counted = sortedCounts(apiKeyed);
    const reported = Object.values(statusCounts).reduce((sum, count) => sum + count, 0);
    if (filters.status !== undefined) {
      const given = statusCounts[filters.status] ?? 0;
      // QDash's "unknown" also counts empty statuses, which status=unknown does not select.
      const agrees = filters.status === "unknown" ? given >= total : given === total;
      if (!agrees) {
        note("status_counts_mismatch", `status_counts gives ${given} rows of status ${JSON.stringify(filters.status)}, but total is ${total}`);
      }
    } else if (reported !== total || !sameCounts(counted, statusCounts)) {
      note("status_counts_mismatch", `the rows read count ${JSON.stringify(counted)}, but status_counts is ${JSON.stringify(statusCounts)} for total ${total}`);
    }
  }

  const counts = (entry: { rows: number; statuses: Map<string, number> }): TaskResultCounts => ({
    rows: entry.rows,
    statuses: sortedCounts(entry.statuses),
  });
  return {
    filters,
    total,
    statusCounts,
    read: { rows: rows.length, returned, pages, pageSize, maxRows, stoppedBy },
    complete: diagnostics.length === 0,
    diagnostics,
    aggregates: {
      byStatus: sortedCounts(byStatus),
      byTask: [...byTask]
        .map(([taskName, entry]) => ({ taskName, ...counts(entry) }))
        .sort((a, b) => b.rows - a.rows || (a.taskName < b.taskName ? -1 : a.taskName > b.taskName ? 1 : 0)),
      byDay: [...byDay]
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([day, entry]) => ({ day, ...counts(entry) })),
      undated,
      timezone,
      executions: executions.size,
    },
  };
}
