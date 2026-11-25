// The pi-qdash connection on one @oqtopus-team/qdash-sdk session: auth and project on every
// request, read retries and single writes, downloads, list queries, the guarded agent-session
// creation, cancellation, and the config sources the SDK reads for it.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { QDash, QDashNotFoundError, QDashPreflightError, QDashResultUnknownError, QDashTimeoutError, QDashTransportError } from "@oqtopus-team/qdash-sdk";

import { connectClient } from "../.test-dist/lib/connection.js";
import { QDashConnection } from "../.test-dist/lib/qdash-connection.js";

const BASE = "https://qdash.example/api";
const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

/** A connection whose fetch answers from `answer(request, url)` and records every request. */
function connectionWith(answer, config = {}) {
  const requests = [];
  const fetch = async (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const body = request.method === "GET" ? undefined : await request.text();
    requests.push({ method: request.method, path: url.pathname.replace(/^\/api/, ""), url, headers: request.headers, body });
    return answer(requests.at(-1));
  };
  const qdash = new QDash({ baseUrl: BASE, apiToken: "user-token", projectId: "p-1", readAttempts: 3, ...config }, { fetch, sleep: async () => {} });
  return { client: new QDashConnection(qdash), requests };
}

test("every request carries the session's token and project, generated and passthrough alike", async () => {
  const { client, requests } = connectionWith(({ path }) => {
    if (path === "/chips") return json({ chips: [], total: 0 });
    if (path === "/executions/figure") return new Response(new Uint8Array([1, 2, 3]), { headers: { "Content-Type": "image/png" } });
    return json({ ok: true });
  });
  await client.listChips();
  await client.rawGet("/some/route", { a: "1", skip: undefined, b: null });
  const figure = await client.getExecutionFigure("/data/fig/q0.png");
  assert.deepEqual([...new Uint8Array(figure.data)], [1, 2, 3]);
  assert.equal(figure.mediaType, "image/png");
  assert.equal(figure.filename, "q0.png");
  assert.equal(requests.length, 3);
  for (const request of requests) {
    assert.equal(request.headers.get("authorization"), "Bearer user-token");
    assert.equal(request.headers.get("x-project-id"), "p-1");
  }
  assert.equal(requests[1].url.search, "?a=1");
  assert.equal(requests[2].url.searchParams.get("path"), "/data/fig/q0.png");
});

test("a project-scoped connection keeps the sign-in and changes only the project", async () => {
  const { client, requests } = connectionWith(() => json({ chips: [] }));
  const other = client.withProject("p-2");
  await other.listChips();
  await client.listChips();
  assert.deepEqual(requests.map((request) => request.headers.get("x-project-id")), ["p-2", "p-1"]);
});

test("raw GETs refuse absolute URLs, so credentials never leave the API", async () => {
  const { client, requests } = connectionWith(() => json({}));
  await assert.rejects(client.rawGet("https://elsewhere.example/steal"), /not an absolute URL/);
  await assert.rejects(client.rawGet("//elsewhere.example/steal"), /not an absolute URL/);
  assert.equal(requests.length, 0);
});

test("reads are sent again after a transient failure; writes are sent once", async () => {
  let reads = 0;
  const { client, requests } = connectionWith(({ method }) => {
    if (method === "GET") return ++reads < 3 ? json({ detail: "busy" }, 503) : json({ chips: [] });
    return json({ detail: "busy" }, 503);
  });
  assert.deepEqual(await client.listChips(), { chips: [] });
  assert.equal(reads, 3);
  await assert.rejects(client.createForumPost({ title: "t", content: "c" }), (error) => error.statusCode === 503);
  assert.equal(requests.filter((request) => request.method === "POST").length, 1);
});

test("errors are the SDK's, with status and payload", async () => {
  const { client } = connectionWith(() => json({ detail: "Task result not found" }, 404));
  await assert.rejects(client.getTaskResult("t-1"), (error) => {
    assert.ok(error instanceof QDashNotFoundError);
    assert.equal(error.statusCode, 404);
    assert.deepEqual(error.payload, { detail: "Task result not found" });
    // A test Response has no URL, so the message has no path here; a real one names it.
    assert.match(error.message, /^404\b.*: Task result not found$/);
    return true;
  });
});

test("list filters are sent as repeated query parameters, as the API reads them", async () => {
  const { client, requests } = connectionWith(({ path }) =>
    path === "/agent-sessions" ? json({ items: [] }) : path === "/calibration-sessions" ? json({ items: [], has_more: false }) : json({ changes: [] }),
  );
  await client.listAgentSessions({ chipId: "C", statuses: ["active", "waiting_for_human"], mine: true, limit: 5 });
  await client.listCalibrationSessions({ chip_id: "C", status: ["open"], origin: ["manual", "automatic"] });
  await client.getRecentChanges({ parameterNames: ["t1", "t2"] });
  await client.getDegradationTrends({ parameterNames: ["t1"] });
  assert.deepEqual(requests[0].url.searchParams.getAll("status"), ["active", "waiting_for_human"]);
  assert.equal(requests[0].url.searchParams.get("mine"), "true");
  assert.deepEqual(requests[1].url.searchParams.getAll("origin"), ["manual", "automatic"]);
  assert.deepEqual(requests[2].url.searchParams.getAll("parameter_names"), ["t1", "t2"]);
  assert.deepEqual(requests[3].url.searchParams.getAll("parameter_names"), ["t1"]);
  // Repeated keys, never one JSON text such as status=%5B%22active%22%5D.
  assert.equal(requests[0].url.search, "?chip_id=C&status=active&status=waiting_for_human&mine=true&limit=5");
  assert.equal(requests[1].url.search, "?chip_id=C&status=open&origin=manual&origin=automatic");
  for (const request of requests) assert.equal(request.headers.get("x-project-id"), "p-1");
});

test("list filters go through the generated client with its read retries", async () => {
  let calls = 0;
  const { client, requests } = connectionWith(() => (++calls < 2 ? json({ detail: "busy" }, 503) : json({ items: [] })));
  assert.deepEqual(await client.listAgentSessions({ statuses: ["active"] }), []);
  assert.equal(requests.length, 2);
  assert.equal(requests[1].url.search, "?status=active");
});

test("task knowledge Markdown comes back as text, exactly as served", async () => {
  const markdown = '{"a": 1}\n\n# CheckT1\n';
  const { client, requests } = connectionWith(() => new Response(markdown, { headers: { "Content-Type": "text/markdown" } }));
  assert.equal(await client.getTaskKnowledgeMarkdown("CheckT1"), markdown);
  const empty = connectionWith(() => new Response("", { headers: { "Content-Type": "text/markdown" } }));
  assert.equal(await empty.client.getTaskKnowledgeMarkdown("Check T1/x"), "");
  assert.equal(empty.requests[0].path, "/tasks/Check%20T1%2Fx/knowledge/markdown");
  assert.equal(requests[0].headers.get("x-project-id"), "p-1");
});

test("listing task results checks its page size before sending and the page it gets back", async () => {
  const { client, requests } = connectionWith(() => json({ items: [{}], total: 1 }));
  await assert.rejects(client.listTaskResults({ limit: 101 }), /limit must be an integer from 1 to 100/);
  assert.equal(requests.length, 0);
  await assert.rejects(client.listTaskResults({ limit: 1 }), /Unexpected GET \/task-results response: an item has no task_id/);
});

test("an agent session in a calibration session is preflighted and its admission checked", async () => {
  const session = { session_id: "s-1", chip_id: "C", calibration_session_id: "cs-1", calibration_admission: "admitted" };
  const make = (created, listed = [{ calibration_session_id: "cs-1", chip_id: "C" }]) =>
    connectionWith(({ method, path }) => {
      if (method === "GET" && path === "/calibration-sessions") return json({ items: listed, has_more: false });
      if (method === "POST" && path === "/agent-sessions") return json(created);
      return json({ detail: "unexpected" }, 500);
    });
  const ok = make(session);
  assert.deepEqual(await ok.client.createAgentSession({ chipId: "C", policy: {}, calibrationSessionId: "cs-1" }), session);
  // The preflight lists sessions; it never reads the detail, which would close an automatic one.
  assert.deepEqual(ok.requests.map((request) => `${request.method} ${request.path}`), ["GET /calibration-sessions", "POST /agent-sessions"]);
  assert.equal(JSON.parse(ok.requests[1].body).calibration_session_id, "cs-1");

  const missing = make(session, []);
  await assert.rejects(missing.client.createAgentSession({ chipId: "C", policy: {}, calibrationSessionId: "cs-1" }), QDashPreflightError);
  assert.equal(missing.requests.filter((request) => request.method === "POST").length, 0);

  const dropped = make({ ...session, calibration_admission: null });
  await assert.rejects(
    dropped.client.createAgentSession({ chipId: "C", policy: {}, calibrationSessionId: "cs-1" }),
    (error) => error instanceof QDashResultUnknownError && /Do not retry automatically/.test(error.message),
  );
  assert.equal(dropped.requests.filter((request) => request.method === "POST").length, 1);

  const plain = make({ session_id: "s-2" });
  assert.equal((await plain.client.createAgentSession({ chipId: "C", policy: {} })).session_id, "s-2");
  assert.deepEqual(plain.requests.map((request) => request.method), ["POST"]);
});

test("waits stop polling and abort the read in flight when the signal aborts", async () => {
  const controller = new AbortController();
  let polls = 0;
  const { client } = connectionWith(() => {
    polls += 1;
    if (polls === 2) controller.abort(new Error("stopped by the user"));
    return json({ execution_id: "e-1", status: "running" });
  });
  await assert.rejects(client.waitForExecution("e-1", { pollIntervalSeconds: 0, signal: controller.signal }), /stopped by the user/);
  assert.equal(polls, 2);
});

test("an execution wait times out with the SDK's timeout error and leaves the run going", async () => {
  const { client } = connectionWith(() => json({ execution_id: "e-1", status: "completed", pipeline: { status: "running" } }));
  await assert.rejects(client.waitForExecution("e-1", { timeoutSeconds: 0, pollIntervalSeconds: 0 }), QDashTimeoutError);
  const step = await client.waitForExecution("e-1", { wholePipeline: false });
  assert.equal(step.status, "completed");
});

test("waiting for an action's execution keeps its 600 s default when the timeout is passed as undefined", async () => {
  const { client } = connectionWith(() => json({ action_id: "a-1", execution_status: "failed" }));
  const action = await client.waitForAgentActionExecution("s-1", "a-1", { timeoutSeconds: undefined });
  assert.equal(action.execution_status, "failed");
  await assert.rejects(client.waitForAgentActionExecution("s-1", "a-1", { timeoutSeconds: -1 }), RangeError);
});

test("a timeout or failed connection is a transport error", async () => {
  const qdash = new QDash({ baseUrl: BASE, apiToken: "t", readAttempts: 1 }, { fetch: async () => { throw new TypeError("fetch failed"); } });
  await assert.rejects(new QDashConnection(qdash).rawGet("/x"), (error) => error instanceof QDashTransportError && error.statusCode === undefined);
});

function configDir(t) {
  const dir = mkdtempSync(join(tmpdir(), "pi-qdash-connection-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test("the hosted private INI profile connects without a deprecation warning", async (t) => {
  const dir = configDir(t);
  const configPath = join(dir, "config.ini");
  // As agent-runtime/src/auth.ts writes it: JSON-quoted values in one [runtime] section.
  writeFileSync(configPath, `[runtime]\nbase_url = "${BASE}"\napi_token = "user-token"\nproject_id = "p-9"\n`, { mode: 0o600 });
  const warnings = [];
  const onWarning = (warning) => warnings.push(warning);
  process.on("warning", onWarning);
  t.after(() => process.off("warning", onWarning));
  const client = await connectClient({ profile: "runtime", configPath, useEnv: false }, {});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(client.config.baseUrl, BASE);
  assert.equal(client.config.apiToken, "user-token");
  assert.equal(client.projectId ?? client.qdash.projectId, "p-9");
  assert.deepEqual(warnings.filter((warning) => warning.code === "QDASH_SDK_INI_CONFIG"), []);
});

test("an explicit INI file without the .ini extension is still read as INI", async (t) => {
  const dir = configDir(t);
  const configPath = join(dir, "qdash.cfg");
  writeFileSync(configPath, `[lab]\nbase_url = ${BASE}\napi_token = tok\ntimeout_seconds = 9\nretry_max_attempts = 4\n`);
  const client = await connectClient({ profile: "lab", configPath }, {});
  assert.equal(client.config.timeoutSec, 9);
  assert.equal(client.config.readAttempts, 4);
});

test("the environment connects as before, with the password read from the given environment", async () => {
  const env = { QDASH_BASE_URL: `${BASE}/`, QDASH_USERNAME: "alice", QDASH_PASSWORD: "pw", QDASH_PROJECT_ID: "p-3", QDASH_TIMEOUT_SECONDS: "5", QDASH_RETRY_MAX_ATTEMPTS: "2" };
  const logins = [];
  const client = await connectClient({}, env, {
    fetch: async (input, init) => {
      const request = new Request(input, init);
      if (new URL(request.url).pathname.endsWith("/auth/login")) {
        logins.push(await request.text());
        return json({ access_token: "jwt" });
      }
      assert.equal(request.headers.get("authorization"), "Bearer jwt");
      assert.equal(request.headers.get("x-project-id"), "p-3");
      return json({ chips: [] });
    },
  });
  assert.equal(client.config.baseUrl, BASE);
  assert.equal(client.config.timeoutSec, 5);
  assert.equal(client.config.readAttempts, 2);
  await client.listChips();
  await client.getMetricsConfig().catch(() => {});
  assert.equal(logins.length, 1);
  assert.match(logins[0], /username=alice/);
});

test("a base URL that is not a URL is refused before any request", async () => {
  await assert.rejects(connectClient({}, { QDASH_BASE_URL: "qdash/api", QDASH_API_TOKEN: "t" }), /baseUrl must be a valid URL/);
});

test("the hosted INI directory may be missing its profile file only with a clear error", async (t) => {
  const dir = configDir(t);
  mkdirSync(join(dir, "hosted"));
  await assert.rejects(connectClient({ profile: "runtime", configPath: join(dir, "hosted", "config.ini"), useEnv: false }, {}), /Config file not found/);
});
