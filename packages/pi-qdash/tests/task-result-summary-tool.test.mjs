// qdash_summarize_task_results as pi-qdash registers it: the extension's makeClient reads a
// profile file and the production sdkSession sends real HTTP requests to a local QDash.
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import qdashExtension from "../.test-dist/qdash.js";
import { DEFERRED_TOOL_NAMES, NESTED_READ_TOOL_NAMES } from "../.test-dist/lib/tool-policy.js";
import { toolIntents } from "../.test-dist/lib/tool-intents.js";
import { QDASH_SCRIPT_GUIDELINE } from "../.test-dist/lib/qdash-guidance.js";
import { summaryOptions, TASK_RESULT_SUMMARY_SCHEMA, TASK_RESULT_SUMMARY_TOOL } from "../.test-dist/tools/task-result-summary.js";

const row = (i, overrides = {}) => ({
  task_id: `t-${i}`,
  task_name: i % 2 === 0 ? "CheckT1" : "CheckRabi",
  qid: String(i % 16),
  chip_id: "16Qv1",
  status: i % 10 === 0 ? "failed" : "completed",
  execution_id: `e-${Math.floor(i / 50)}`,
  start_at: `2026-11-25T${String(23 - Math.floor(i / 20)).padStart(2, "0")}:00:00`,
  ...overrides,
});
const ROWS = Array.from({ length: 230 }, (_, i) => row(i));
const counts = (rows) => {
  const out = {};
  for (const item of rows) out[item.status] = (out[item.status] ?? 0) + 1;
  return out;
};

/** A QDash answering GET /task-results by skip and limit from `rows`, recording each query. */
async function fakeTaskResults(t, rows) {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    response.writeHead(url.pathname === "/task-results" ? 200 : 404, { "content-type": "application/json" });
    if (url.pathname !== "/task-results") return response.end(JSON.stringify({ detail: "not found" }));
    const query = Object.fromEntries(url.searchParams);
    requests.push(query);
    const skip = Number(query.skip ?? 0);
    const limit = Number(query.limit ?? 50);
    response.end(JSON.stringify({ items: rows.slice(skip, skip + limit), total: rows.length, skip, limit, status_counts: counts(rows) }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const directory = await mkdtemp(join(tmpdir(), "pi-qdash-summary-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, "config.ini");
  await writeFile(configPath, `[runtime]\nbase_url = "http://127.0.0.1:${server.address().port}"\napi_token = "user-token"\n`, { mode: 0o600 });
  return { requests, connection: { profile: "runtime", configPath, useEnv: false } };
}

function extensionTools() {
  const tools = new Map();
  qdashExtension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on() {}, appendEntry() {} });
  return tools;
}

const FILTERS = {
  chipId: "16Qv1",
  taskName: "CheckT1",
  qid: "6",
  status: "completed",
  startFrom: "2026-11-25T00:00:00Z",
  startTo: "2026-11-26T00:00:00Z",
  messageContains: "fit failed",
};
const withoutPaging = ({ skip, limit, ...rest }) => rest;

test("the summary sends the filters qdash_list_task_results and qdash_query task_results send", async (t) => {
  const { requests, connection } = await fakeTaskResults(t, []);
  const tools = extensionTools();
  await tools.get("qdash_list_task_results").execute("a", { ...connection, ...FILTERS });
  await tools.get("qdash_query").execute("b", { ...connection, ...FILTERS, action: "task_results" });
  await tools.get(TASK_RESULT_SUMMARY_TOOL).execute("c", { ...connection, ...FILTERS });
  assert.equal(requests.length, 3);
  const [list, query, summary] = requests.map(withoutPaging);
  // The dedicated list and the query action take the same path; the summary sends the same filters.
  assert.deepEqual(list, query);
  assert.deepEqual(summary, list);
  assert.deepEqual(summary, {
    chip_id: "16Qv1",
    task_name: "CheckT1",
    qid: "6",
    status: "completed",
    start_from: "2026-11-25T00:00:00Z",
    start_to: "2026-11-26T00:00:00Z",
    message_contains: "fit failed",
  });
  // startAt and couplingId are the list's aliases here too.
  assert.deepEqual(summaryOptions({ startAt: "2026-11-25T00:00:00Z", couplingId: "6-7" }), { startFrom: "2026-11-25T00:00:00Z", qid: "6-7", maxRows: 1000 });
});

test("the summary reads every page past 100 rows and reports QDash's totals with the counts of the rows read", async (t) => {
  const { requests, connection } = await fakeTaskResults(t, ROWS);
  const result = await extensionTools().get(TASK_RESULT_SUMMARY_TOOL).execute("s", { ...connection, chipId: "16Qv1", startFrom: "2026-11-25T00:00:00Z" });
  assert.deepEqual(requests.map((query) => [query.skip, query.limit]), [["0", "100"], ["100", "100"], ["200", "100"]]);
  const data = result.details.data;
  assert.equal(result.details.tool, TASK_RESULT_SUMMARY_TOOL);
  assert.equal(data.complete, true);
  assert.equal(data.total, 230);
  assert.deepEqual(data.statusCounts, { completed: 207, failed: 23 });
  assert.deepEqual(data.aggregates.byStatus, { completed: 207, failed: 23 });
  assert.deepEqual(data.aggregates.byTask.map((entry) => [entry.taskName, entry.rows]), [["CheckRabi", 115], ["CheckT1", 115]]);
  assert.equal(data.aggregates.executions, 5);
  const text = result.content[0].text;
  assert.match(text, /QDash totals: total 230 \(rows matching every filter\); status_counts completed 207, failed 23 \(rows matching every filter\)/);
  assert.match(text, /Read 230 distinct of 230 rows in 3 pages; stopped by all_rows\. Complete\./);
  assert.match(text, /Counts of all matching rows:/);
  assert.doesNotMatch(text, /PARTIAL/);
});

test("a summary cut off by maxRows says its counts are partial and why", async (t) => {
  const { requests, connection } = await fakeTaskResults(t, ROWS);
  const result = await extensionTools().get(TASK_RESULT_SUMMARY_TOOL).execute("s", { ...connection, maxRows: 120 });
  assert.deepEqual(requests.map((query) => query.limit), ["100", "20"]);
  assert.equal(result.details.data.complete, false);
  assert.deepEqual(result.details.data.diagnostics.map((d) => d.code), ["max_rows_reached"]);
  const text = result.content[0].text;
  assert.match(text, /Incomplete\./);
  assert.match(text, /max_rows_reached: read 120 of 230 rows/);
  assert.match(text, /Counts of PARTIAL: only the 120 rows read, not all 230:/);
  // QDash's totals still describe every matching row.
  assert.match(text, /total 230 \(rows matching every filter\); status_counts completed 207, failed 23/);
});

test("with a status filter the text keeps total apart from status_counts, which QDash counts without it", async (t) => {
  const failed = ROWS.filter((item) => item.status === "failed");
  const { connection } = await fakeTaskResults(t, failed);
  const result = await extensionTools().get(TASK_RESULT_SUMMARY_TOOL).execute("s", { ...connection, status: "failed" });
  const text = result.content[0].text;
  assert.match(text, /QDash totals: total 23 \(rows matching every filter\); status_counts failed 23 \(rows matching every filter except status, which QDash leaves out of status_counts\)/);
});

test("refused start times never reach QDash", async (t) => {
  const { requests, connection } = await fakeTaskResults(t, ROWS);
  const tool = extensionTools().get(TASK_RESULT_SUMMARY_TOOL);
  await assert.rejects(tool.execute("s", { ...connection, startFrom: "2026-02-30T00:00:00Z" }), /startFrom is not an ISO 8601 date-time/);
  await assert.rejects(tool.execute("s", { ...connection, startAt: "2026-11-26" }), /startFrom is not an ISO 8601 date-time/);
  await assert.rejects(tool.execute("s", { ...connection, startFrom: "2026-11-26T00:00:00Z", endAt: "2026-11-25T00:00:00Z" }), /is after startTo/);
  assert.deepEqual(requests, []);
});

test("conflicting target or time arguments are refused before any request", async (t) => {
  const { requests, connection } = await fakeTaskResults(t, ROWS);
  const tool = extensionTools().get(TASK_RESULT_SUMMARY_TOOL);
  await assert.rejects(tool.execute("s", { ...connection, qid: "6", couplingId: "6-7" }), /give qid or couplingId, not both/);
  await assert.rejects(tool.execute("s", { ...connection, startAt: "2026-11-25T00:00:00Z", startFrom: "2026-11-24T00:00:00Z" }), /startAt and startFrom are the same bound/);
  // The SDK refuses an unusable bound before sending.
  await assert.rejects(tool.execute("s", { ...connection, maxRows: 6000 }), /maxRows must be an integer from 1 to 5000/);
  assert.deepEqual(requests, []);
});

test("the summary is an offered read tool scripts may call, and the guides route multi-page counts to", () => {
  const tool = extensionTools().get(TASK_RESULT_SUMMARY_TOOL);
  assert.ok(NESTED_READ_TOOL_NAMES.includes(TASK_RESULT_SUMMARY_TOOL));
  assert.ok(!DEFERRED_TOOL_NAMES.includes(TASK_RESULT_SUMMARY_TOOL));
  assert.deepEqual(toolIntents(TASK_RESULT_SUMMARY_TOOL), ["stored_values"]);
  // A script's declaration shows the summary's shape, not the generic data schema.
  assert.equal(tool.outputSchema, TASK_RESULT_SUMMARY_SCHEMA);
  assert.equal(tool.annotations?.readOnlyHint, true);
  assert.match(tool.promptGuidelines.join("\n"), /instead of paging qdash_list_task_results in a script/);
  assert.match(tool.promptGuidelines.join("\n"), /do not merge them into success or failure/);
  assert.match(tool.promptGuidelines.join("\n"), /status_counts counts the rows matching every filter except status, so with a status filter it is not a breakdown of total/);
  // Single pages stay with the list; its description and the script rule point multi-page counts here.
  assert.match(extensionTools().get("qdash_list_task_results").description, /To count results across pages by status, task, or day, use qdash_summarize_task_results instead/);
  assert.match(QDASH_SCRIPT_GUIDELINE, /call `qdash_summarize_task_results` instead of paging `qdash_list_task_results`/);
});
