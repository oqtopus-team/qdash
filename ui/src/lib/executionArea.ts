import {
  createParser,
  parseAsBoolean,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
} from "nuqs";

/**
 * Links and URL state of the Execution area: the Executions list at `/execution` and the
 * calibration session list and pages at `/calibration-sessions`. The two lists keep their own
 * query parameters; only the chip and the project travel between them.
 */

/** Whether `value` is a calendar day written `YYYYMMDD`, the form the date selector uses. */
export function isExecutionDay(value: string): boolean {
  if (!/^\d{8}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    year >= 1970 &&
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

/** A picked day of the Executions list; any other value reads as no day (the latest runs). */
const parseAsExecutionDay = createParser({
  parse: (value: string) => (isExecutionDay(value) ? value : null),
  serialize: (value: string) => value,
});

/**
 * The Executions list's own view, as its URL holds it: a picked day (`date`, absent for the
 * latest runs), the flat list instead of grouped sessions (`flat=true`), and the page. An
 * absent or invalid value reads as the default, so an old link opens the grouped latest runs.
 */
export const executionViewParsers = {
  date: parseAsExecutionDay,
  flat: parseAsBoolean.withDefault(false),
  page: parseAsInteger.withDefault(1),
};

/** The Executions list's filters: its chip, and the view `executionViewParsers` reads. */
export interface ExecutionListContext {
  chip?: string | null;
  /** A day written `YYYYMMDD`; absent or `null` for the latest runs. */
  date?: string | null;
  flat?: boolean;
  page?: number;
}

/** A page number read from a URL: a whole number of at least 1, otherwise the first page. */
export function cleanPage(page: number | null | undefined): number {
  return page != null && Number.isSafeInteger(page) && page >= 1 ? page : 1;
}

export const SESSION_STATUS_FILTERS = ["all", "open", "closed"] as const;
export const SESSION_ORIGIN_FILTERS = ["all", "manual", "automatic"] as const;
type SessionStatusFilter = (typeof SESSION_STATUS_FILTERS)[number];
type SessionOriginFilter = (typeof SESSION_ORIGIN_FILTERS)[number];

/** The calibration session list's filters, as its URL holds them. */
export const sessionListParsers = {
  status: parseAsStringLiteral(SESSION_STATUS_FILTERS).withDefault("all"),
  origin: parseAsStringLiteral(SESSION_ORIGIN_FILTERS).withDefault("all"),
  mine: parseAsBoolean.withDefault(false),
  chip: parseAsString,
  page: parseAsInteger.withDefault(1),
};

/** The list a calibration session page was opened from. */
const SESSION_RETURN_VIEWS = ["sessions", "executions"] as const;

/**
 * What a calibration session page reads to link back: the list it came from and that list's
 * filters. A page opened without them (a bookmark, a chat or SDK link) links to the plain
 * session list. `page` is the page of whichever list `from` names; `date` and `flat` belong to
 * the Executions list only.
 */
export const sessionReturnParsers = {
  ...sessionListParsers,
  date: executionViewParsers.date,
  flat: executionViewParsers.flat,
  from: parseAsStringLiteral(SESSION_RETURN_VIEWS).withDefault("sessions"),
};

/** The query state `sessionReturnParsers` reads. */
export interface SessionReturnQuery {
  from: (typeof SESSION_RETURN_VIEWS)[number];
  status: SessionStatusFilter;
  origin: SessionOriginFilter;
  mine: boolean;
  chip: string | null;
  page: number;
  date: string | null;
  flat: boolean;
}

/** The list to return to, from a session page's query; each list keeps only its own filters. */
export function sessionReturnFromQuery(query: SessionReturnQuery): SessionReturnContext {
  const page = cleanPage(query.page);
  if (query.from === "executions") {
    return {
      from: "executions",
      list: { chip: query.chip, date: query.date, flat: query.flat, page },
    };
  }
  return {
    from: "sessions",
    list: {
      status: query.status,
      origin: query.origin,
      mine: query.mine,
      chip: query.chip,
      page,
    },
  };
}

export interface SessionListContext {
  status?: SessionStatusFilter;
  origin?: SessionOriginFilter;
  mine?: boolean;
  chip?: string | null;
  page?: number;
}

export type SessionReturnContext =
  | { from: "sessions"; list: SessionListContext }
  | { from: "executions"; list: ExecutionListContext };

/** Longest chip ID carried in a link; anything longer is not a chip and is dropped. */
const MAX_CHIP_LENGTH = 128;

function cleanChip(chip: string | null | undefined): string | null {
  const value = chip?.trim();
  return value && value.length <= MAX_CHIP_LENGTH ? value : null;
}

/** Query parameters in order, each encoded with `encodeURIComponent` (a space is `%20`). */
type QueryPairs = Array<[string, string]>;

function withQuery(path: string, params: QueryPairs): string {
  const query = params
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join("&");
  return query ? `${path}?${query}` : path;
}

/** Writes the list filters that differ from their defaults, so a plain list keeps a plain URL. */
function setListParams(params: QueryPairs, list: SessionListContext) {
  const chip = cleanChip(list.chip);
  if (chip) params.push(["chip", chip]);
  if (list.status && list.status !== "all") params.push(["status", list.status]);
  if (list.origin && list.origin !== "all") params.push(["origin", list.origin]);
  if (list.mine) params.push(["mine", "true"]);
  const page = cleanPage(list.page);
  if (page > 1) params.push(["page", String(page)]);
}

/** Writes the Executions view (day, flat list, page) that differs from its defaults. */
function setExecutionViewParams(params: QueryPairs, list: ExecutionListContext) {
  if (list.date && isExecutionDay(list.date)) params.push(["date", list.date]);
  if (list.flat) params.push(["flat", "true"]);
  const page = cleanPage(list.page);
  if (page > 1) params.push(["page", String(page)]);
}

/**
 * The Executions list, optionally on one chip and with its day, flat list and page, pinned to
 * a project when known. Defaults are left out, so the plain list keeps the plain URL.
 */
export function executionListHref({
  chipId,
  projectId,
  date,
  flat,
  page,
}: {
  chipId?: string | null;
  projectId?: string | null;
  date?: string | null;
  flat?: boolean;
  page?: number;
} = {}): string {
  const params: QueryPairs = [];
  const chip = cleanChip(chipId);
  if (chip) params.push(["chip", chip]);
  setExecutionViewParams(params, { date, flat, page });
  if (projectId) params.push(["project", projectId]);
  return withQuery("/execution", params);
}

/** The Executions list a context names, pinned to a project when known. */
function executionListContextHref(list: ExecutionListContext, projectId?: string | null) {
  return executionListHref({ chipId: list.chip, projectId, ...list });
}

/**
 * An execution's page, pinned to a project when known. Opened from the Executions list, it
 * carries that list's day, flat list and page so its crumb returns to the same view; the chip
 * is the one in the path.
 */
export function executionDetailHref(
  chipId: string,
  executionId: string,
  projectId?: string | null,
  back?: ExecutionListContext,
): string {
  const params: QueryPairs = [];
  if (projectId) params.push(["project", projectId]);
  if (back) setExecutionViewParams(params, back);
  return withQuery(
    `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`,
    params,
  );
}

/** The calibration session list with the given filters, pinned to a project when known. */
export function calibrationSessionListHref(
  list: SessionListContext = {},
  projectId?: string | null,
): string {
  const params: QueryPairs = [];
  setListParams(params, list);
  if (projectId) params.push(["project", projectId]);
  return withQuery("/calibration-sessions", params);
}

/**
 * A calibration session page, pinned to a project when known, carrying the list to return to.
 * Without `back`, or coming from an unfiltered session list, the URL is the plain page URL that
 * bookmarks and chat links use.
 */
export function calibrationSessionDetailHref(
  calibrationSessionId: string,
  projectId?: string | null,
  back?: SessionReturnContext,
): string {
  const params: QueryPairs = [];
  if (projectId) params.push(["project", projectId]);
  if (back?.from === "executions") {
    params.push(["from", "executions"]);
    const chip = cleanChip(back.list.chip);
    if (chip) params.push(["chip", chip]);
    setExecutionViewParams(params, back.list);
  } else if (back) {
    setListParams(params, back.list);
  }
  return withQuery(`/calibration-sessions/${encodeURIComponent(calibrationSessionId)}`, params);
}

/** The anchor of a run on its calibration session page. */
export function runAnchorId(runId: string): string {
  return `run-${runId}`;
}

/** Longest run ID read from a page's `#run-…` fragment; anything longer names no run. */
const MAX_RUN_ID_LENGTH = 128;

/** The run a `#run-…` fragment names, or `null` when it names none. */
export function runIdFromHash(hash: string): string | null {
  const prefix = "#run-";
  if (!hash.startsWith(prefix)) return null;
  let runId: string;
  try {
    runId = decodeURIComponent(hash.slice(prefix.length));
  } catch {
    return null;
  }
  return runId && runId.length <= MAX_RUN_ID_LENGTH ? runId : null;
}

/** A crumb of the Execution area: a link, or the current place when it has no `href`. */
export interface ExecutionCrumb {
  label: string;
  href?: string;
  /** Hover text, such as the full ID or objective a cut label shows. */
  title?: string;
}

/**
 * The crumbs above a calibration session page: the Execution area, then the session list when
 * the page was not opened from the Executions list. Every link stays in `projectId`.
 */
export function calibrationSessionCrumbs(
  back: SessionReturnContext,
  projectId: string | null,
): ExecutionCrumb[] {
  if (back.from === "executions") {
    return [{ label: "Execution", href: executionListContextHref(back.list, projectId) }];
  }
  return [
    { label: "Execution", href: executionListHref({ chipId: back.list.chip, projectId }) },
    { label: "Calibration sessions", href: calibrationSessionListHref(back.list, projectId) },
  ];
}
