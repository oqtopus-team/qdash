import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";

import qdashExtension from "../.test-dist/qdash.js";
import {
  CHIP_METRICS_SCHEMA,
  checkQueryResponse,
  TASK_RESULT_PAGE_SCHEMA,
  TIMESERIES_SCHEMA,
} from "../.test-dist/lib/query-contracts.js";

const page = (items, total = items.length) => ({ items, total, skip: 0, limit: 50, status_counts: {} });
const row = (taskId, qid) => ({ task_id: taskId, task_name: "CheckT1", qid, chip_id: "C", status: "completed", execution_id: "e" });

/** A QDash API that records every request and answers the routes these tests use. */
async function fakeQDash(t) {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    requests.push({ path: url.pathname, query: Object.fromEntries(url.searchParams) });
    const send = (status, body) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    };
    if (url.pathname === "/task-results") return send(200, page([row("t-1", url.searchParams.get("qid") ?? "6")]));
    if (url.pathname === "/executions") return send(200, { executions: [], total: 0 });
    if (url.pathname === "/chips/C/couplings/6-7") return send(200, { coupling_id: "6-7", chip_id: "C" });
    if (url.pathname === "/forum/posts") return send(200, { posts: [], total: 0 });
    return send(404, { detail: `no ${url.pathname}` });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const previous = { QDASH_BASE_URL: process.env.QDASH_BASE_URL, QDASH_API_TOKEN: process.env.QDASH_API_TOKEN };
  process.env.QDASH_BASE_URL = `http://127.0.0.1:${server.address().port}`;
  process.env.QDASH_API_TOKEN = "test-token";
  t.after(() => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  const tools = new Map();
  qdashExtension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on() {}, appendEntry() {} });
  const run = (name, params) => tools.get(name).execute("t", { useEnv: true, ...params });
  return { tools, requests, run };
}

test("the dedicated query tools declare their paging bounds and response shapes", async (t) => {
  const { tools } = await fakeQDash(t);
  const list = tools.get("qdash_list_task_results");
  assert.deepEqual(
    { type: list.parameters.properties.limit.type, minimum: list.parameters.properties.limit.minimum, maximum: list.parameters.properties.limit.maximum },
    { type: "integer", minimum: 1, maximum: 100 },
  );
  assert.deepEqual({ type: list.parameters.properties.skip.type, minimum: list.parameters.properties.skip.minimum }, { type: "integer", minimum: 0 });
  assert.equal(list.outputSchema, TASK_RESULT_PAGE_SCHEMA);
  assert.equal(tools.get("qdash_get_chip_metrics").outputSchema, CHIP_METRICS_SCHEMA);
  assert.equal(tools.get("qdash_get_timeseries").outputSchema, TIMESERIES_SCHEMA);
  // The descriptions name the real fields, not the ones scripts guessed.
  assert.match(list.description, /\{ items, total, skip, limit, status_counts \}/);
  assert.match(list.description, /skip increased by the rows already read/);
  assert.match(tools.get("qdash_get_chip_metrics").description, /qubit_metrics\[metricKey\]\[qid\]/);
  assert.match(tools.get("qdash_get_timeseries").description, /data\[qid\] is an array/);
  assert.match(tools.get("qdash_get_timeseries").description, /no aliases/);
  for (const name of ["qdash_list_task_results", "qdash_get_chip_metrics", "qdash_get_timeseries"]) {
    const description = tools.get(name).description;
    assert.doesNotMatch(description, /\.results\b|\bresults:|updated_at|Q6:/, name);
  }
  // qdash_query covers many actions, so it keeps the generic script data schema.
  assert.doesNotMatch(JSON.stringify(tools.get("qdash_query").outputSchema ?? {}), /status_counts/);
});

test("task_results paging is checked before any request, with advice to page", async (t) => {
  const { run, requests } = await fakeQDash(t);
  for (const [params, message] of [
    [{ limit: 200 }, /limit must be an integer from 1 to 100 \(got 200\)/],
    [{ limit: 0 }, /limit must be an integer from 1 to 100/],
    [{ limit: 2.5 }, /limit must be an integer from 1 to 100 \(got 2\.5\)/],
    [{ skip: -1 }, /skip must be an integer of 0 or more \(got -1\)/],
    [{ skip: 0.5 }, /skip must be an integer of 0 or more/],
  ]) {
    for (const call of [() => run("qdash_query", { action: "task_results", chipId: "C", ...params }), () => run("qdash_list_task_results", { chipId: "C", ...params })]) {
      await assert.rejects(call(), (error) => message.test(error.message) && /No request was sent/.test(error.message) && /skip 0, then 100/.test(error.message));
    }
  }
  assert.deepEqual(requests, []);
  // Other actions keep their own limits: executions is not held to the task-result maximum.
  await run("qdash_query", { action: "executions", chipId: "C", limit: 200 });
  assert.deepEqual(requests.map((request) => [request.path, request.query.limit]), [["/executions", "200"]]);
});

test("couplingId filters task results through the API's exact qid filter", async (t) => {
  const { run, requests } = await fakeQDash(t);
  const result = await run("qdash_list_task_results", { chipId: "C", couplingId: "6-7", limit: 100, skip: 100 });
  assert.deepEqual(requests.at(-1).query, { chip_id: "C", qid: "6-7", limit: "100", skip: "100" });
  assert.deepEqual(Object.keys(result.details.data).sort(), ["items", "limit", "skip", "status_counts", "total"]);
  await run("qdash_list_task_results", { chipId: "C", qid: "6" });
  assert.equal(requests.at(-1).query.qid, "6");
  await assert.rejects(run("qdash_list_task_results", { chipId: "C", qid: "6", couplingId: "6-7" }), /give qid or couplingId, not both/);
});

test("the target report sends its time window and coupling with the API's filter names", async (t) => {
  const { run, requests } = await fakeQDash(t);
  await run("qdash_target_report", { chipId: "C", couplingId: "6-7", withinHours: 24 });
  const list = requests.find((request) => request.path === "/task-results");
  assert.equal(list.query.qid, "6-7");
  assert.equal(list.query.coupling_id, undefined);
  assert.equal(list.query.start_at, undefined);
  assert.ok(list.query.start_from && list.query.start_to, JSON.stringify(list.query));
  const hours = (Date.parse(list.query.start_to) - Date.parse(list.query.start_from)) / 3_600_000;
  assert.ok(Math.abs(hours - 24) < 0.01, `window ${hours}h`);
});

test("a response of another shape fails with its path instead of reading as empty", () => {
  assert.throws(() => checkQueryResponse("task_results", { results: [] }), /task_results response that does not match its documented shape \(\/: must have required properties items/);
  assert.throws(() => checkQueryResponse("chip_metrics", []), /chip_metrics response/);
  assert.throws(
    () => checkQueryResponse("chip_metrics", { chip_id: "C", qubit_count: 1, qubit_metrics: { t1: { 6: { value: "x", task_id: null, execution_id: null, stddev: null } } }, coupling_metrics: {} }),
    /\/qubit_metrics\/t1\/6\/value/,
  );
  assert.throws(() => checkQueryResponse("timeseries", { data: [] }), /\/data/);
  // The documented shapes pass unchanged, null values and extra fields included.
  const metrics = { chip_id: "C", username: "u", qubit_count: 1, within_hours: null, start_at: null, end_at: null, qubit_metrics: { t1: { 6: { value: null, task_id: "t", execution_id: "e", stddev: null } } }, coupling_metrics: {}, _links: { chip: "x" } };
  assert.equal(checkQueryResponse("chip_metrics", metrics), metrics);
  const series = { data: {} };
  assert.equal(checkQueryResponse("timeseries", series), series);
  const empty = page([]);
  assert.equal(checkQueryResponse("task_results", empty), empty);
});
