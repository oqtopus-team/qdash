/**
 * `qdash_summarize_task_results`: the pi adapter of the SDK's
 * `qdash.taskResults.summarize(options)`, which pages through
 * `GET /task-results` within a bound and counts the rows read by exact status,
 * task name, and day, saying whether the read was complete.
 *
 * The SDK owns the reads, the checks, and the counts. This adapter maps the
 * same filters `qdash_list_task_results` takes, writes a short summary that
 * keeps QDash's totals apart from the counts of the rows read, and returns the
 * SDK's summary as its data.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashConnection } from "../lib/qdash-connection.js";
import type { TaskResultCounts, TaskResultSummary, TaskResultSummaryOptions } from "@oqtopus-team/qdash-sdk";
import { Type, type TSchema } from "typebox";

import { qdashWebBaseUrl } from "../lib/links.js";
import { toTextToolResult } from "../lib/results.js";
import { sdkSession, type SdkSessionFactory } from "../lib/sdk-session.js";
import { CONFIG_PATH_DESCRIPTION, PROFILE_DESCRIPTION } from "../lib/connection.js";

export const TASK_RESULT_SUMMARY_TOOL = "qdash_summarize_task_results";

/** Rows the tool reads when maxRows is omitted, and the most it reads. */
export const SUMMARY_DEFAULT_ROWS = 1000;
export const SUMMARY_MAX_ROWS = 5000;
/** Task names and days listed in the text answer; the data keeps them all. */
const TEXT_ROWS = 15;

export type TaskResultSummaryParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  chipId?: string;
  taskName?: string;
  qid?: string;
  couplingId?: string;
  executionId?: string;
  username?: string;
  status?: string;
  startAt?: string;
  endAt?: string;
  startFrom?: string;
  startTo?: string;
  messageContains?: string;
  timezone?: string;
  maxRows?: number;
};

export type TaskResultSummaryDependencies = {
  makeClient(params: TaskResultSummaryParams): Promise<QDashConnection>;
  /** The chip of the active QDash context, as qdash_list_task_results uses it; none filters no chip. */
  contextChipId?(): string | undefined;
  /** The SDK session for a resolved client; defaults to one with the client's settings. */
  sdk?: SdkSessionFactory;
};

/** The SDK options for the tool's arguments: the filters qdash_list_task_results sends, at most maxRows rows. */
export function summaryOptions(params: TaskResultSummaryParams, contextChipId?: string): TaskResultSummaryOptions {
  if (params.qid !== undefined && params.couplingId !== undefined && params.qid !== params.couplingId) {
    throw new Error(`${TASK_RESULT_SUMMARY_TOOL}: give qid or couplingId, not both; QDash filters task results by one exact target ID. No request was sent.`);
  }
  for (const [alias, name] of [["startAt", "startFrom"], ["endAt", "startTo"]] as const) {
    if (params[alias] !== undefined && params[name] !== undefined && params[alias] !== params[name]) {
      throw new Error(`${TASK_RESULT_SUMMARY_TOOL}: ${alias} and ${name} are the same bound and differ; give one. No request was sent.`);
    }
  }
  const options: TaskResultSummaryOptions = {
    chipId: params.chipId ?? contextChipId,
    taskName: params.taskName,
    qid: params.qid ?? params.couplingId,
    executionId: params.executionId,
    username: params.username,
    status: params.status,
    startFrom: params.startFrom ?? params.startAt,
    startTo: params.startTo ?? params.endAt,
    messageContains: params.messageContains,
    timezone: params.timezone,
    maxRows: params.maxRows ?? SUMMARY_DEFAULT_ROWS,
  };
  return Object.fromEntries(Object.entries(options).filter(([, value]) => value !== undefined)) as TaskResultSummaryOptions;
}

const counts = (description: string) => Type.Record(Type.String(), Type.Integer(), { description });
const groupCounts = {
  rows: Type.Integer(),
  statuses: counts("Rows by exact stored status."),
};

/** What a script receives: the SDK's TaskResultSummary. */
export const TASK_RESULT_SUMMARY_SCHEMA: TSchema = Type.Object({
  filters: Type.Record(Type.String(), Type.String(), { description: "Filters sent with every page, as GET /task-results names them." }),
  total: Type.Integer({ description: "Rows matching every filter sent, status included, as QDash reported on the first page." }),
  statusCounts: counts(
    "QDash's rows per stored status for the rows matching every filter except status: QDash counts them without the status filter, so with a status filter they do not add up to total. Rows with an empty status are counted under \"unknown\" together with rows whose status is \"unknown\".",
  ),
  read: Type.Object({
    rows: Type.Integer({ description: "Distinct rows read and counted in aggregates." }),
    returned: Type.Integer({ description: "Rows returned, including repeated ones." }),
    pages: Type.Integer(),
    pageSize: Type.Integer(),
    maxRows: Type.Integer(),
    stoppedBy: Type.Union([Type.Literal("all_rows"), Type.Literal("max_rows"), Type.Literal("empty_page"), Type.Literal("short_page")]),
  }),
  complete: Type.Boolean({
    description: "True only when every matching row was read once and the totals stayed the same and agree. Offset pages are not a snapshot: even then concurrent changes are not ruled out.",
  }),
  diagnostics: Type.Array(Type.Object({ code: Type.String(), message: Type.String() }), { description: "Why complete is false; empty when it is true." }),
  aggregates: Type.Object(
    {
      byStatus: counts("Rows read by exact stored status; an empty status stays \"\"."),
      byTask: Type.Array(Type.Object({ taskName: Type.String(), ...groupCounts }), { description: "By task name, most rows first." }),
      byDay: Type.Array(Type.Object({ day: Type.String({ description: "YYYY-MM-DD in timezone." }), ...groupCounts }), { description: "By start day, oldest first." }),
      undated: Type.Integer({ description: "Rows read without a readable ISO 8601 start_at." }),
      timezone: Type.String(),
      executions: Type.Integer({ description: "Distinct execution_id values among the rows read." }),
    },
    { description: "Counts of the rows read only. When complete is false they are partial, not counts of all matching rows." },
  ),
});

function statusText(statuses: Record<string, number>): string {
  const entries = Object.entries(statuses);
  return entries.length === 0 ? "none" : entries.map(([status, count]) => `${status === "" ? '""' : status} ${count}`).join(", ");
}

function groupLines(entries: Array<{ label: string } & TaskResultCounts>): string[] {
  const lines = entries.slice(0, TEXT_ROWS).map((entry) => `  ${entry.label}: ${entry.rows} (${statusText(entry.statuses)})`);
  if (entries.length > TEXT_ROWS) lines.push(`  ... ${entries.length - TEXT_ROWS} more in the data`);
  return lines;
}

export function summaryText(summary: TaskResultSummary): string {
  const filters = Object.entries(summary.filters).map(([name, value]) => `${name}=${value}`).join(", ") || "none";
  const { read, aggregates } = summary;
  const scope = summary.complete ? "all matching rows" : `PARTIAL: only the ${read.rows} rows read, not all ${summary.total}`;
  return [
    `Task results matching ${filters}`,
    `QDash totals: total ${summary.total} (rows matching every filter); status_counts ${statusText(summary.statusCounts)} (${summary.filters.status ? "rows matching every filter except status, which QDash leaves out of status_counts" : "rows matching every filter"})`,
    `Read ${read.rows} distinct of ${summary.total} rows in ${read.pages} page${read.pages === 1 ? "" : "s"}; stopped by ${read.stoppedBy}. ${summary.complete ? "Complete" : "Incomplete"}.`,
    ...(summary.diagnostics.length > 0 ? ["Diagnostics:", ...summary.diagnostics.map((d) => `  - ${d.code}: ${d.message}`)] : []),
    "",
    `Counts of ${scope}:`,
    `  by status: ${statusText(aggregates.byStatus)}`,
    `  distinct executions: ${aggregates.executions}`,
    "By task:",
    ...groupLines(aggregates.byTask.map((entry) => ({ label: entry.taskName, ...entry }))),
    `By start day (${aggregates.timezone}):`,
    ...groupLines(aggregates.byDay.map((entry) => ({ label: entry.day, ...entry }))),
    ...(aggregates.undated > 0 ? [`  without start_at: ${aggregates.undated}`] : []),
    "",
    "Statuses are counted exactly as stored. Pages are separate offset reads, not a snapshot of the results.",
  ].join("\n");
}

export function registerTaskResultSummaryTool(pi: Pick<ExtensionAPI, "registerTool">, deps: TaskResultSummaryDependencies): void {
  pi.registerTool({
    name: TASK_RESULT_SUMMARY_TOOL,
    label: "QDash Summarize Task Results",
    description: `Count the task results matching filters (chip, task, qubit or coupling, execution, user, status, start-time range, message text) across all pages: QDash's total and status_counts for every matching row, and counts of the rows read by exact status, by task name, by start day, and distinct executions. Reads up to maxRows rows (default ${SUMMARY_DEFAULT_ROWS}, at most ${SUMMARY_MAX_ROWS}) itself, 100 per request. complete is true only when every matching row was read once and the totals agree; otherwise diagnostics say why and the counts of rows read are partial. Read-only. Takes the same filters as qdash_list_task_results.`,
    promptSnippet: "Count QDash task results by status, task, and day across all pages for a chip and time range",
    promptGuidelines: [
      `Use ${TASK_RESULT_SUMMARY_TOOL} to count or summarize task results over more than one page (for example all results of a chip since a time, by status, task or day) instead of paging qdash_list_task_results in a script. Use qdash_list_task_results to read individual rows.`,
      "Report total as the number of rows matching every filter. status_counts counts the rows matching every filter except status, so with a status filter it is not a breakdown of total: report total for the filtered status and status_counts only as the counts of the other statuses under the remaining filters. When complete is false, say the per-task and per-day counts cover only the rows read and give the diagnostics; never present them as complete.",
      "Report statuses as QDash stores them; do not merge them into success or failure unless the user defines how.",
    ],
    parameters: Type.Object({
      profile: Type.Optional(Type.String({ description: PROFILE_DESCRIPTION })),
      configPath: Type.Optional(Type.String({ description: CONFIG_PATH_DESCRIPTION })),
      useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
      chipId: Type.Optional(Type.String({ description: "Chip ID. Defaults to the active chip when one is selected; otherwise every chip." })),
      taskName: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String({ description: "Exact qubit ID as QDash stores it, such as \"6\"." })),
      couplingId: Type.Optional(Type.String({ description: "Exact coupling ID as QDash stores it, such as \"6-7\"." })),
      executionId: Type.Optional(Type.String()),
      username: Type.Optional(Type.String()),
      status: Type.Optional(Type.String({ description: "Exact stored status. status_counts is counted without it." })),
      startAt: Type.Optional(Type.String({ description: "Same as startFrom." })),
      endAt: Type.Optional(Type.String({ description: "Same as startTo." })),
      startFrom: Type.Optional(
        Type.String({ description: "Inclusive lower bound on the task start time: ISO 8601 YYYY-MM-DDTHH:MM[:SS[.ffffff]] with an optional Z or ±HH:MM offset; without an offset it is UTC." }),
      ),
      startTo: Type.Optional(Type.String({ description: "Inclusive upper bound on the task start time, in the same form as startFrom and not before it." })),
      messageContains: Type.Optional(Type.String({ description: "Text the result message contains, compared case-insensitively." })),
      timezone: Type.Optional(Type.String({ description: "IANA time zone for the start days, such as \"Asia/Tokyo\". Defaults to UTC." })),
      maxRows: Type.Optional(Type.Integer({ minimum: 1, maximum: SUMMARY_MAX_ROWS, description: `Most rows to read, from 1 to ${SUMMARY_MAX_ROWS}. Defaults to ${SUMMARY_DEFAULT_ROWS}.` })),
    }),
    outputSchema: TASK_RESULT_SUMMARY_SCHEMA,
    async execute(_toolCallId, params: TaskResultSummaryParams) {
      const options = summaryOptions(params, deps.contextChipId?.());
      const client = await deps.makeClient(params);
      const summary = await (deps.sdk ?? sdkSession)(client).taskResults.summarize(options);
      return toTextToolResult(summaryText(summary), summary, { tool: TASK_RESULT_SUMMARY_TOOL, webBaseUrl: qdashWebBaseUrl(client) });
    },
  });
}
