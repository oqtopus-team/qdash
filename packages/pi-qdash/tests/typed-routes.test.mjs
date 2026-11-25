// The registered tools reach list-filtered, Markdown and task-result routes through the SDK's
// generated client: these tests read the query string on the wire, and fail when a normal tool
// falls back to the raw GET or the session's passthrough fetch.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";

import { QDash } from "@oqtopus-team/qdash-sdk";

import qdashExtension from "../.test-dist/qdash.js";
import { QDashConnection } from "../.test-dist/lib/qdash-connection.js";

const MARKDOWN = '{"looks": "like JSON"}\n\n# CheckT1\n';

/** A QDash API on a local port that records each request's path, raw query and project. */
async function fakeQDash(t) {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    requests.push({ path: url.pathname, search: url.search, query: url.searchParams, project: request.headers["x-project-id"] });
    const send = (status, body, type = "application/json") => {
      response.writeHead(status, { "content-type": type });
      response.end(type === "application/json" ? JSON.stringify(body) : body);
    };
    if (url.pathname === "/task-results") return send(200, { items: [], total: 0, skip: 0, limit: 50, status_counts: {} });
    if (url.pathname === "/tasks/Check%20T1/knowledge/markdown") return send(200, MARKDOWN, "text/markdown; charset=utf-8");
    if (url.pathname === "/agent-sessions") return send(200, { items: [] });
    if (url.pathname === "/calibration-sessions") return send(200, { items: [], total: 0, skip: 0, limit: 20, has_more: false });
    if (url.pathname === "/provenance/changes") return send(200, { changes: [], total_count: 0 });
    return send(404, { detail: `no ${url.pathname}` });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const previous = {
    QDASH_BASE_URL: process.env.QDASH_BASE_URL,
    QDASH_API_TOKEN: process.env.QDASH_API_TOKEN,
    QDASH_PROJECT_ID: process.env.QDASH_PROJECT_ID,
  };
  process.env.QDASH_BASE_URL = `http://127.0.0.1:${server.address().port}`;
  process.env.QDASH_API_TOKEN = "test-token";
  process.env.QDASH_PROJECT_ID = "p-1";
  t.after(() => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  // A normal tool never takes the raw path: these throw if one does.
  const rawGet = QDashConnection.prototype.rawGet;
  const passthrough = QDash.prototype.fetch;
  QDashConnection.prototype.rawGet = () => Promise.reject(new Error("a normal tool called rawGet"));
  QDash.prototype.fetch = () => Promise.reject(new Error("a normal tool called the passthrough fetch"));
  t.after(() => {
    QDashConnection.prototype.rawGet = rawGet;
    QDash.prototype.fetch = passthrough;
  });
  const tools = new Map();
  qdashExtension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on() {}, appendEntry() {} });
  const run = (name, params) => tools.get(name).execute("t", { useEnv: true, ...params });
  return { requests, run };
}

test("qdash_query task_results sends every filter through the generated task-results call", async (t) => {
  const { run, requests } = await fakeQDash(t);
  await run("qdash_query", {
    action: "task_results",
    chipId: "C",
    taskName: "CheckT1",
    couplingId: "6-7",
    executionId: "e-1",
    username: "alice",
    status: "failed",
    startAt: "2026-11-01T00:00:00Z",
    endAt: "2026-11-02T00:00:00Z",
    messageContains: "fit",
    limit: 100,
    skip: 200,
  });
  const sent = requests.at(-1);
  assert.equal(sent.path, "/task-results");
  assert.equal(sent.project, "p-1");
  assert.deepEqual(Object.fromEntries(sent.query), {
    chip_id: "C",
    task_name: "CheckT1",
    qid: "6-7",
    execution_id: "e-1",
    username: "alice",
    status: "failed",
    start_from: "2026-11-01T00:00:00Z",
    start_to: "2026-11-02T00:00:00Z",
    message_contains: "fit",
    limit: "100",
    skip: "200",
  });
  // startFrom and startTo win over the startAt and endAt aliases, as before.
  await run("qdash_query", { action: "task_results", startFrom: "a", startAt: "b", startTo: "c", endAt: "d" });
  assert.deepEqual(Object.fromEntries(requests.at(-1).query), { start_from: "a", start_to: "c" });
  await assert.rejects(run("qdash_query", { action: "task_results", qid: "6", couplingId: "6-7" }), /give qid or couplingId, not both/);
  assert.equal(requests.length, 2);
});

test("qdash_query task_knowledge_markdown returns the Markdown text unchanged, even when it parses as JSON", async (t) => {
  const { run, requests } = await fakeQDash(t);
  const result = await run("qdash_query", { action: "task_knowledge_markdown", taskName: "Check T1" });
  assert.equal(result.details.data, MARKDOWN);
  assert.equal(requests.at(-1).path, "/tasks/Check%20T1/knowledge/markdown");
});

test("list filters of the registered tools repeat on the wire instead of sending JSON text", async (t) => {
  const { run, requests } = await fakeQDash(t);
  await run("qdash_list_agent_sessions", { chipId: "C", statuses: ["active", "waiting_for_human"], limit: 5 });
  await run("qdash_list_calibration_sessions", { chipId: "C", mine: true, openOnly: true });
  await run("qdash_query", { action: "provenance_changes", parameterName: "t1", withinHours: 12 });
  assert.deepEqual(
    requests.map((request) => `${request.path}${request.search}`),
    [
      "/agent-sessions?chip_id=C&status=active&status=waiting_for_human&mine=true&limit=5",
      "/calibration-sessions?chip_id=C&status=open&mine=true",
      "/provenance/changes?within_hours=12&parameter_names=t1",
    ],
  );
  for (const request of requests) {
    assert.equal(request.project, "p-1");
    assert.doesNotMatch(request.search, /%5B|%22/);
  }
});
