import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";

import qdashExtension from "../.test-dist/qdash.js";

// A GET /task-results row as TaskResultListItem serializes it: no output_parameters.
const row = (taskId, taskName, qid, startAt, status = "completed") => ({
  task_id: taskId,
  task_name: taskName,
  qid,
  chip_id: "C",
  status,
  execution_id: `exec-${taskId}`,
  user_id: "u-1",
  username: "alice",
  message: "",
  has_stack_trace: false,
  source_task_id: null,
  invocation: null,
  start_at: startAt,
  end_at: startAt,
  elapsed_time: "0:00:12",
});

// An output parameter as TaskResultOutputParameterModel serializes it.
const output = (value, unit, error = 0.1) => ({
  parameter_name: "",
  qid_role: "",
  source: null,
  required: false,
  value,
  value_type: "float",
  error,
  unit,
  description: "",
  calibrated_at: "2026-11-20T00:00:00Z",
  execution_id: "",
  task_id: "",
  previous_database_value: null,
  database_updated: false,
  database_updates: [],
});

// A GET /tasks/{task_id}/result body as TaskResultResponse serializes it.
const detail = (listRow, outputParameters) => ({
  task_id: listRow.task_id,
  task_name: listRow.task_name,
  qid: listRow.qid,
  chip_id: listRow.chip_id,
  status: listRow.status,
  execution_id: listRow.execution_id,
  flow_name: "one_qubit",
  user_id: "u-1",
  username: "alice",
  figure_path: [],
  json_figure_path: [],
  raw_data_path: [],
  input_parameters: {},
  output_parameters: outputParameters,
  output_parameter_names: Object.keys(outputParameters),
  run_parameters: {},
  start_at: listRow.start_at,
  end_at: listRow.end_at,
  elapsed_time: listRow.elapsed_time,
  source_task_id: null,
  re_executions: [],
});

const t1New = row("t1-new", "CheckT1", "6", "2026-11-22T10:00:00Z");
const rabiNew = row("rabi-new", "CheckRabi", "6", "2026-11-22T09:00:00Z");
const t1Old = row("t1-old", "CheckT1", "6", "2026-11-21T10:00:00Z");
const rabiOld = row("rabi-old", "CheckRabi", "6", "2026-11-21T09:00:00Z");
const t1Oldest = row("t1-oldest", "CheckT1", "6", "2026-11-20T10:00:00Z");
const echoOnly = row("echo-1", "CheckT2Echo", "6", "2026-11-22T08:00:00Z");

/** A QDash API that answers GET /task-results with `rows` (newest first) and GET /tasks/{id}/result from `details`. */
async function fakeQDash(t, { rows, details = {}, total = rows.length }) {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    requests.push({ path: url.pathname, query: Object.fromEntries(url.searchParams) });
    const send = (status, body) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    };
    if (url.pathname === "/task-results") return send(200, { items: rows, total, skip: 0, limit: Number(url.searchParams.get("limit")), status_counts: {} });
    const match = url.pathname.match(/^\/tasks\/([^/]+)\/result$/);
    if (match) {
      const body = details[decodeURIComponent(match[1])];
      if (body === undefined) return send(404, { detail: "Task result not found" });
      if (body instanceof Error) return send(500, { detail: body.message });
      return send(200, body);
    }
    const history = url.pathname.match(/^\/task-results\/(qubits|couplings)\/([^/]+)\/history$/);
    if (history) return send(200, { name: url.searchParams.get("task"), data: { "t1-new": { task_id: "t1-new", name: "CheckT1", qid: decodeURIComponent(history[2]), status: "completed" } } });
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
  const run = (name, params) => tools.get(name).execute("t", { useEnv: true, chipId: "C", ...params });
  const detailReads = () => requests.filter((request) => request.path.startsWith("/tasks/")).map((request) => request.path).sort();
  return { run, requests, detailReads };
}

const textOf = (result) => result.content.map((part) => part.text).join("\n");

test("qdash_compare_calibration reads the two newest results' details and reports their output changes", async (t) => {
  const { run, requests, detailReads } = await fakeQDash(t, {
    rows: [t1New, rabiNew, t1Old, rabiOld, t1Oldest],
    details: {
      "t1-new": detail(t1New, { t1: output(31.5, "us"), t1_fit_r2: output(0.98, "") }),
      "t1-old": detail(t1Old, { t1: output(24.0, "us"), t1_fit_r2: output(0.98, "") }),
      "t1-oldest": detail(t1Oldest, { t1: output(1, "us") }),
      "rabi-new": detail(rabiNew, { rabi_amplitude: output(0.42, "a.u."), rabi_frequency: output(12.1, "MHz") }),
      "rabi-old": detail(rabiOld, { rabi_amplitude: output(0.40, "a.u.") }),
    },
  });
  const result = await run("qdash_compare_calibration", { qid: "6", limit: 5 });
  const data = result.details.data;
  assert.deepEqual(requests[0], { path: "/task-results", query: { chip_id: "C", qid: "6", limit: "5" } });
  // Only the newest two of each task are read; the third CheckT1 result is not.
  assert.deepEqual(detailReads(), ["/tasks/rabi-new/result", "/tasks/rabi-old/result", "/tasks/t1-new/result", "/tasks/t1-old/result"]);
  const byTask = Object.fromEntries(data.compared.map((item) => [item.task, item]));
  assert.equal(byTask.CheckT1.before.task_id, "t1-old");
  assert.equal(byTask.CheckT1.after.task_id, "t1-new");
  assert.equal(byTask.CheckT1.status, "compared");
  assert.deepEqual(byTask.CheckT1.changes, { t1: { before: 24.0, after: 31.5 } });
  assert.deepEqual(byTask.CheckRabi.changes, {
    rabi_amplitude: { before: 0.40, after: 0.42 },
    rabi_frequency: { before: undefined, after: 12.1 },
  });
  assert.deepEqual(data.insufficient, []);
  assert.deepEqual(data.rows, { read: 5, total: 5 });
  assert.match(textOf(result), /t1: 24 → 31\.5/);
  assert.doesNotMatch(textOf(result), /no output-parameter changes/);
});

test("a task with a single result is listed as not compared, and no detail is read", async (t) => {
  const { run, detailReads } = await fakeQDash(t, { rows: [echoOnly, t1New], total: 40 });
  const result = await run("qdash_compare_calibration", { qid: "6" });
  assert.deepEqual(result.details.data.compared, []);
  assert.deepEqual(result.details.data.insufficient, [{ task: "CheckT2Echo", results: 1 }, { task: "CheckT1", results: 1 }]);
  assert.deepEqual(detailReads(), []);
  assert.match(textOf(result), /Not enough repeated task results to compare among the 2 newest of 40/);
  assert.match(textOf(result), /single result, not compared: CheckT2Echo, CheckT1/);
  assert.doesNotMatch(textOf(result), /no output-parameter changes/);
});

test("an unreadable detail is presented as unavailable, not unchanged", async (t) => {
  const { run } = await fakeQDash(t, { rows: [t1New, t1Old], details: { "t1-new": detail(t1New, { t1: output(31.5, "us") }) } });
  const result = await run("qdash_compare_calibration", { qid: "6" });
  const [item] = result.details.data.compared;
  assert.equal(item.status, "unavailable");
  assert.equal(item.changes, null);
  assert.match(item.error, /reading the result of t1-old failed/);
  assert.match(textOf(result), /comparison unavailable: reading the result of t1-old failed/);
  assert.doesNotMatch(textOf(result), /no output-parameter changes/);
});

test("the limit is clamped to the SDK's 2 to 100 rows instead of failing", async (t) => {
  const { run, requests } = await fakeQDash(t, { rows: [] });
  await run("qdash_compare_calibration", { qid: "6", limit: 1 });
  await run("qdash_compare_calibration", { qid: "6", limit: 500 });
  assert.deepEqual(requests.map((request) => request.query.limit), ["2", "100"]);
});

test("a coupling target is compared through the list's qid filter", async (t) => {
  const cNew = row("c-new", "CheckCrossResonance", "6-7", "2026-11-22T10:00:00Z");
  const cOld = row("c-old", "CheckCrossResonance", "6-7", "2026-11-21T10:00:00Z");
  const { run, requests } = await fakeQDash(t, {
    rows: [cNew, cOld],
    details: { "c-new": detail(cNew, { cr_amplitude: output(0.8, "") }), "c-old": detail(cOld, { cr_amplitude: output(0.7, "") }) },
  });
  const result = await run("qdash_compare_calibration", { couplingId: "6-7" });
  assert.equal(requests[0].query.qid, "6-7");
  assert.equal(result.details.data.target.label, "c6-7");
  assert.deepEqual(result.details.data.compared[0].changes, { cr_amplitude: { before: 0.7, after: 0.8 } });
});

test("qubit_history and coupling_history send chip_id and task only", async (t) => {
  const { run, requests } = await fakeQDash(t, { rows: [] });
  const qubit = await run("qdash_query", { action: "qubit_history", qid: "6", task: "CheckT1" });
  const coupling = await run("qdash_query", { action: "coupling_history", couplingId: "6-7", taskName: "CheckCrossResonance" });
  assert.deepEqual(requests.map((request) => [request.path, request.query]), [
    ["/task-results/qubits/6/history", { chip_id: "C", task: "CheckT1" }],
    ["/task-results/couplings/6-7/history", { chip_id: "C", task: "CheckCrossResonance" }],
  ]);
  assert.equal(qubit.details.data.name, "CheckT1");
  assert.equal(coupling.details.data.data["t1-new"].qid, "6-7");
});

test("qubit_history and coupling_history refuse a date before any request", async (t) => {
  const { run, requests } = await fakeQDash(t, { rows: [] });
  for (const [params, target] of [
    [{ action: "qubit_history", qid: "6", task: "CheckT1", date: "20261120" }, "qid"],
    [{ action: "coupling_history", couplingId: "6-7", task: "CheckCrossResonance", date: "20261120" }, "couplingId"],
  ]) {
    await assert.rejects(run("qdash_query", params), (error) =>
      new RegExp(`^${params.action}: date cannot filter ${params.action}`).test(error.message)
      && /Omit date to read the whole history/.test(error.message)
      && new RegExp(`task_results action \\(or qdash_list_task_results\\) with ${target}, taskName, startFrom and startTo`).test(error.message)
      && /No request was sent/.test(error.message));
  }
  assert.deepEqual(requests, []);
});
