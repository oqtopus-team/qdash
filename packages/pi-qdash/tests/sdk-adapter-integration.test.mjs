// The SDK-backed tools as pi-qdash registers them: the extension's own makeClient reads a
// profile file, the production sdkSession maps the client's settings to an SDK session, and both
// send real HTTP requests to a local server. Nothing replaces sdkSession here.
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { QDashClient, QDashConfig } from "@oqtopus-team/qdash-client";

import qdashExtension from "../.test-dist/qdash.js";
import { registerTaskResultEvidenceTool } from "../.test-dist/tools/task-result-evidence.js";
import { sdkSessionFactory } from "../.test-dist/lib/sdk-session.js";

const json = (response, status, body) => {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
};

const STATUS = Symbol("status");
/** An answer with a status other than 200. */
const answered = (status, body) => ({ [STATUS]: status, body });
const RAW = Symbol("raw");
/** An answer whose body is sent as these exact bytes, such as a truncated JSON document. */
const rawAnswer = (status, text, contentType = "application/json") => ({ [RAW]: { status, text, contentType } });

/**
 * A QDash API on 127.0.0.1 answering from `routes` ("METHOD /path" to a list of answers, the
 * last one repeating; an answer is a body, `answered(status, body)`, or a function of the request).
 */
async function fakeQDash(t, routes) {
  const requests = [];
  const server = createServer(async (request, response) => {
    let text = "";
    for await (const chunk of request) text += chunk;
    const url = new URL(request.url, "http://localhost");
    const key = `${request.method} ${url.pathname}`;
    requests.push({ key, query: Object.fromEntries(url.searchParams), headers: request.headers, body: text });
    const queue = routes[key];
    if (!queue?.length) return json(response, 404, { detail: `no ${key}` });
    const answer = queue.length > 1 ? queue.shift() : queue[0];
    const reply = typeof answer === "function" ? answer({ text, headers: request.headers }) : answer;
    if (reply && typeof reply === "object" && RAW in reply) {
      response.writeHead(reply[RAW].status, { "content-type": reply[RAW].contentType });
      return response.end(reply[RAW].text);
    }
    if (reply && typeof reply === "object" && STATUS in reply) return json(response, reply[STATUS], reply.body);
    return json(response, 200, reply);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  return { baseUrl: `http://127.0.0.1:${server.address().port}`, requests };
}

/** A private INI profile like the one the QDash web Agent writes for each harness (agent-runtime auth.ts). */
async function profileFile(t, values) {
  const directory = await mkdtemp(join(tmpdir(), "pi-qdash-sdk-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, "config.ini");
  await writeFile(configPath, `[runtime]\n${Object.entries(values).map(([key, value]) => `${key} = ${JSON.stringify(value)}`).join("\n")}\n`, { mode: 0o600 });
  return { profile: "runtime", configPath, useEnv: false };
}

function extensionTools() {
  const tools = new Map();
  qdashExtension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on() {}, appendEntry() {} });
  return tools;
}

const approved = (toolCallId, toolName) => ({ hasUI: false, qdashWriteApproval: { toolCallId, toolName } });
const sdkRequests = (requests) => requests.filter((request) => !request.key.startsWith("GET /agent-sessions"));
const posts = (requests, path) => requests.filter((request) => request.key === `POST ${path}`);

const SPEC = { spec_version: 2, targets: { qids: ["0"] }, steps: [{ type: "CustomOneQubit", tasks: [{ name: "CheckT1" }] }] };
const DISPATCHED = { execution_id: "exec-1", flow_run_id: "run-1", flow_run_url: "", qdash_ui_url: "", message: "started", steps: [] };
const NO_PAUSE = { items: [], total: 0 };

test("the hosted profile's token, project, gateway headers and user agent reach the SDK's requests", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {
    "POST /calibration-pipelines/validate": [{ valid: true, problems: [], warnings: [], backend_name: "qubex", spec: SPEC, targets: { qids: ["0"] }, steps: [], task_run_count: 1 }],
  });
  const connection = await profileFile(t, {
    base_url: baseUrl,
    api_token: "user-token",
    project_id: "p-1",
    cf_access_client_id: "cf-id",
    cf_access_client_secret: "cf-secret",
    user_agent: "qdash-agent-runtime/1",
  });
  const result = await extensionTools().get("qdash_plan_pipeline").execute("t", { ...connection, chipId: "64Qv3", spec: SPEC });
  assert.equal(result.details.valid, true);
  assert.deepEqual(requests.map((request) => request.key), ["POST /calibration-pipelines/validate"]);
  const [validate] = requests;
  assert.equal(validate.headers.authorization, "Bearer user-token");
  assert.equal(validate.headers["x-project-id"], "p-1");
  assert.equal(validate.headers["cf-access-client-id"], "cf-id");
  assert.equal(validate.headers["cf-access-client-secret"], "cf-secret");
  assert.equal(validate.headers["user-agent"], "qdash-agent-runtime/1");
  assert.deepEqual(JSON.parse(validate.body), { chip_id: "64Qv3", spec: SPEC });
});

test("qdash_run_pipeline checks pauses with the client, lists the session, and dispatches once with the SDK", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /agent-sessions": [NO_PAUSE],
    "GET /calibration-sessions": [{ items: [{ calibration_session_id: "cs-1", chip_id: "64Qv3", status: "open" }], has_more: false }],
    "POST /calibration-pipelines/execute": [answered(201, { ...DISPATCHED, calibration_session_id: "cs-1", pipeline_run_id: "cpr-1", replayed: false })],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token", project_id: "p-1" });
  const params = { ...connection, chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1" };
  const result = await extensionTools().get("qdash_run_pipeline").execute("call-1", params, undefined, undefined, approved("call-1", "qdash_run_pipeline"));
  assert.equal(result.details.started, true);
  assert.equal(result.details.pipelineRunId, "cpr-1");
  assert.deepEqual(requests.map((request) => request.key), ["GET /agent-sessions", "GET /calibration-sessions", "POST /calibration-pipelines/execute"]);
  assert.deepEqual(requests[1].query, { chip_id: "64Qv3", mine: "true", limit: "100", skip: "0" });
  assert.ok(requests.every((request) => request.headers["x-project-id"] === "p-1" && request.headers.authorization === "Bearer user-token"));
  const body = JSON.parse(requests[2].body);
  assert.equal(body.calibration_session_id, "cs-1");
  assert.match(body.idempotency_key, /call-1/);
  assert.deepEqual(body.reported_origin, { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" });
});

test("qdash_run_pipeline launches into an open automatic session without reading its closing detail", async (t) => {
  // The detail route closes an open automatic session whose work ended; the launch must not read it.
  const automatic = { calibration_session_id: "cs-auto", chip_id: "64Qv3", status: "open", origin: "automatic" };
  const others = Array.from({ length: 100 }, (_, index) => ({ calibration_session_id: `cs-${index}`, chip_id: "64Qv3", status: "closed" }));
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /agent-sessions": [NO_PAUSE],
    "GET /calibration-sessions": [{ items: others, has_more: true }, { items: [automatic], has_more: false }],
    "GET /calibration-sessions/cs-auto": [() => {
      automatic.status = "closed";
      return automatic;
    }],
    "POST /calibration-pipelines/execute": [() =>
      automatic.status === "closed"
        ? answered(409, { detail: "Calibration session cs-auto is closed; start a new one" })
        : answered(201, { ...DISPATCHED, calibration_session_id: "cs-auto", pipeline_run_id: "cpr-1", replayed: false })],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token" });
  const params = { ...connection, chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-auto" };
  const result = await extensionTools().get("qdash_run_pipeline").execute("call-a", params, undefined, undefined, approved("call-a", "qdash_run_pipeline"));
  assert.equal(result.details.started, true);
  assert.equal(automatic.status, "open");
  assert.deepEqual(sdkRequests(requests).map((request) => `${request.key} ${request.query.skip ?? ""}`.trim()), [
    "GET /calibration-sessions 0",
    "GET /calibration-sessions 100",
    "POST /calibration-pipelines/execute",
  ]);
});

test("qdash_run_pipeline dispatches nothing when the session is not the user's on that chip", async (t) => {
  for (const items of [[], [{ calibration_session_id: "cs-1", chip_id: "other", status: "open" }]]) {
    const { baseUrl, requests } = await fakeQDash(t, {
      "GET /agent-sessions": [NO_PAUSE],
      "GET /calibration-sessions": [{ items, has_more: false }],
    });
    const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token" });
    const params = { ...connection, chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1" };
    await assert.rejects(
      extensionTools().get("qdash_run_pipeline").execute("call-m", params, undefined, undefined, approved("call-m", "qdash_run_pipeline")),
      /Calibration session preflight failed: cs-1 .*nothing dispatched/,
    );
    assert.equal(posts(requests, "/calibration-pipelines/execute").length, 0);
    assert.ok(requests.every((request) => request.key !== "GET /calibration-sessions/cs-1"));
  }
});

test("a preflight 503 reports no dispatch instead of advising a worker restart", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /agent-sessions": [NO_PAUSE],
    "GET /calibration-sessions": [answered(503, { detail: "API unavailable" })],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token", retry_max_attempts: 1 });
  const params = { ...connection, chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1" };
  await assert.rejects(
    extensionTools().get("qdash_run_pipeline").execute("call-p", params, undefined, undefined, approved("call-p", "qdash_run_pipeline")),
    (error) => {
      assert.equal(error.name, "QDashPreflightError");
      assert.match(error.message, /nothing dispatched/);
      assert.doesNotMatch(error.message, /restart|worker/);
      assert.equal(error.cause.statusCode, 503);
      return true;
    },
  );
  assert.equal(posts(requests, "/calibration-pipelines/execute").length, 0);
});

test("a pipeline answer without its recording is a result-unknown tool error, dispatched once", async (t) => {
  for (const [name, answer, extra] of [
    ["an old server", { ...DISPATCHED }, {}],
    ["another session", { ...DISPATCHED, calibration_session_id: "cs-2", pipeline_run_id: "cpr-1" }, { calibrationSessionId: "cs-1" }],
    ["a dropped decision", { ...DISPATCHED, calibration_session_id: "cs-1", pipeline_run_id: "cpr-1" }, { calibrationSessionId: "cs-1", decisionId: "d-1" }],
  ]) {
    const { baseUrl, requests } = await fakeQDash(t, {
      "GET /agent-sessions": [NO_PAUSE],
      "GET /calibration-sessions": [{ items: [{ calibration_session_id: "cs-1", chip_id: "64Qv3", status: "open" }], has_more: false }],
      "POST /calibration-pipelines/execute": [answered(201, answer)],
    });
    const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token" });
    const params = { ...connection, chipId: "64Qv3", spec: SPEC, ...extra };
    await assert.rejects(
      extensionTools().get("qdash_run_pipeline").execute("call-2", params, undefined, undefined, approved("call-2", "qdash_run_pipeline")),
      (error) => {
        assert.match(error.message, /^Pipeline result unknown: .*Do not retry automatically/, name);
        assert.match(error.message, /Do not start this run again; check execution exec-1 with qdash_get_execution, and tell the user\.$/, name);
        assert.equal(error.cause?.name, "QDashResultUnknownError", name);
        return true;
      },
    );
    assert.equal(posts(requests, "/calibration-pipelines/execute").length, 1, name);
  }
});

test("a pipeline the server rejects with 422 reports its problems and is not started", async (t) => {
  const problems = [{ path: "steps[0].tasks[0]", message: "unknown task" }];
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /agent-sessions": [NO_PAUSE],
    "POST /calibration-pipelines/execute": [answered(422, { detail: { message: "invalid", problems } })],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token" });
  const result = await extensionTools().get("qdash_run_pipeline").execute("call-3", { ...connection, chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("call-3", "qdash_run_pipeline"));
  assert.equal(result.details.started, false);
  assert.equal(result.details.problemCount, 1);
  assert.equal(posts(requests, "/calibration-pipelines/execute").length, 1);
});

test("qdash_execute_flow dispatches a saved workflow once; an unrecorded answer is a result-unknown tool error", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /agent-sessions": [NO_PAUSE],
    "POST /flows/coherence_check/execute": [{ ...DISPATCHED, calibration_session_id: "auto-1", calibration_run_id: "cr-1" }, { ...DISPATCHED }],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token", project_id: "p-1" });
  const tool = extensionTools().get("qdash_execute_flow");
  const started = await tool.execute("call-4", { ...connection, name: "coherence_check", parameters: { qids: ["0"] } }, undefined, undefined, approved("call-4", "qdash_execute_flow"));
  assert.equal(started.details.started, true);
  assert.equal(started.details.calibrationRunId, "cr-1");
  const first = JSON.parse(posts(requests, "/flows/coherence_check/execute")[0].body);
  assert.deepEqual(first.parameters, { qids: ["0"] });
  assert.match(first.idempotency_key, /call-4/);

  await assert.rejects(
    tool.execute("call-5", { ...connection, name: "coherence_check" }, undefined, undefined, approved("call-5", "qdash_execute_flow")),
    /^Error: Workflow result unknown: .*reconcile the execution first\. Do not start this run again; check execution exec-1 with qdash_get_execution, and tell the user\.$/,
  );
  assert.equal(posts(requests, "/flows/coherence_check/execute").length, 2);
});

test("a dispatch acknowledged with truncated JSON is a result-unknown tool error, never started or sent again", async (t) => {
  const truncated = JSON.stringify({ ...DISPATCHED, calibration_session_id: "cs-1" }).slice(0, 40);
  const listFallback = (chip) =>
    new RegExp(
      `Do not start this run again; no execution ID was returned, so look for the run with qdash_list_executions, passing ${chip}, ` +
        "and page with skip until the rows are older than this launch, and tell the user\\.$",
    );
  const cases = [
    ["qdash_run_pipeline", "/calibration-pipelines/execute", { chipId: "64Qv3", spec: SPEC }, /^Pipeline result unknown: .*may have started/, "chipId 64Qv3"],
    ["qdash_execute_flow", "/flows/coherence_check/execute", { name: "coherence_check", parameters: { chip_id: "64Qv3" } }, /^Workflow result unknown: .*may have started/, "chipId 64Qv3"],
    [
      "qdash_execute_flow",
      "/flows/coherence_check/execute",
      { name: "coherence_check" },
      /^Workflow result unknown: .*may have started/,
      "chipId set to the chip_id that qdash_get_flow shows for flow coherence_check",
    ],
  ];
  for (const [toolName, path, params, message, chip] of cases) {
    for (const contentType of ["application/json", "text/plain"]) {
      const { baseUrl, requests } = await fakeQDash(t, {
        "GET /agent-sessions": [NO_PAUSE],
        [`POST ${path}`]: [rawAnswer(200, truncated, contentType)],
      });
      const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token" });
      let started = false;
      await assert.rejects(
        extensionTools()
          .get(toolName)
          .execute("call-t", { ...connection, ...params }, undefined, undefined, approved("call-t", toolName))
          .then((result) => {
            started = result?.details?.started === true;
            return result;
          }),
        (error) => {
          assert.match(error.message, message, `${toolName} ${contentType}`);
          assert.match(error.message, listFallback(chip), `${toolName} ${contentType}`);
          assert.equal(error.cause?.name, "QDashResultUnknownError");
          assert.equal(error.cause?.statusCode, 200);
          assert.equal(error.cause?.body, truncated);
          return true;
        },
      );
      assert.equal(started, false);
      assert.equal(posts(requests, path).length, 1, `${toolName} ${contentType}`);
    }
  }
});

test("qdash_save_metric_script validates with the client and creates the script once with the SDK", async (t) => {
  const saved = {
    script_id: "ms_1",
    name: "T1",
    description: "",
    visibility: "private",
    owner: "alice",
    project_id: "p-1",
    revision: 1,
    active_revision: 1,
    status: "valid",
    source: "src",
    diagnostics: [],
    metrics: [],
    created_at: "2026-11-24T00:00:00Z",
    updated_at: "2026-11-24T00:00:00Z",
  };
  const { baseUrl, requests } = await fakeQDash(t, {
    "POST /metric-scripts/validate": [{ ok: true, metrics: [], diagnostics: [] }],
    "POST /metric-scripts": [answered(201, saved)],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token", project_id: "p-1" });
  const result = await extensionTools().get("qdash_save_metric_script").execute("call-6", { ...connection, name: "T1", source: "src" }, undefined, undefined, approved("call-6", "qdash_save_metric_script"));
  assert.equal(result.details.saved, true);
  assert.equal(result.details.scriptId, "ms_1");
  assert.deepEqual(requests.map((request) => request.key), ["POST /metric-scripts/validate", "POST /metric-scripts"]);
  assert.deepEqual(JSON.parse(requests[1].body), { name: "T1", source: "src" });
  assert.equal(requests[1].headers["x-project-id"], "p-1");
});

test("a username/password profile signs in for the client and the SDK, with the password from password_env", async (t) => {
  const logins = [];
  const { baseUrl, requests } = await fakeQDash(t, {
    "POST /auth/login": [({ text }) => {
      logins.push(Object.fromEntries(new URLSearchParams(text)));
      return { access_token: `jwt-${logins.length}`, token_type: "bearer" };
    }],
    "GET /agent-sessions": [NO_PAUSE],
    "POST /flows/coherence_check/execute": [{ ...DISPATCHED, calibration_session_id: "auto-1", calibration_run_id: "cr-1" }],
  });
  const previous = process.env.PI_QDASH_TEST_PASSWORD;
  process.env.PI_QDASH_TEST_PASSWORD = "s3cret";
  t.after(() => {
    if (previous === undefined) delete process.env.PI_QDASH_TEST_PASSWORD;
    else process.env.PI_QDASH_TEST_PASSWORD = previous;
  });
  const connection = await profileFile(t, { base_url: baseUrl, username: "alice", password_env: "PI_QDASH_TEST_PASSWORD" });
  const result = await extensionTools().get("qdash_execute_flow").execute("call-7", { ...connection, name: "coherence_check" }, undefined, undefined, approved("call-7", "qdash_execute_flow"));
  assert.equal(result.details.started, true);
  // The client and the SDK session each sign in once; the dispatch is sent once.
  assert.deepEqual(logins, [{ username: "alice", password: "s3cret" }, { username: "alice", password: "s3cret" }]);
  assert.equal(posts(requests, "/flows/coherence_check/execute").length, 1);
  assert.equal(posts(requests, "/flows/coherence_check/execute")[0].headers.authorization, "Bearer jwt-2");
  assert.doesNotMatch(JSON.stringify(result), /s3cret/);
});

test("a 401 to the SDK's dispatch is reported once, not sent again", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /agent-sessions": [NO_PAUSE],
    "POST /flows/coherence_check/execute": [answered(401, { detail: "Could not validate credentials" })],
  });
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "expired" });
  await assert.rejects(
    extensionTools().get("qdash_execute_flow").execute("call-8", { ...connection, name: "coherence_check" }, undefined, undefined, approved("call-8", "qdash_execute_flow")),
    (error) => error.name === "QDashAuthError" && error.statusCode === 401 && /Could not validate credentials/.test(error.message),
  );
  assert.equal(sdkRequests(requests).length, 1);
});

test("a proxy profile is refused before anything is sent, by the client as before", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {});
  const connection = await profileFile(t, { base_url: baseUrl, api_token: "user-token", proxy: "http://proxy.example:3128" });
  await assert.rejects(extensionTools().get("qdash_plan_pipeline").execute("t", { ...connection, chipId: "64Qv3", spec: SPEC }), /custom fetch/);
  assert.deepEqual(requests, []);
});

test("a host whose client has a custom fetch passes it to the SDK sessions through sdkSessionFactory", async (t) => {
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /tasks/t-1/result": [{ task_id: "t-1", task_name: "CheckT1", qid: "6", chip_id: "C", status: "completed", execution_id: "e-1", output_parameters: {}, output_parameter_names: [], input_parameters: {}, run_parameters: {}, figure_path: [], json_figure_path: [], raw_data_path: [], re_executions: [] }],
    "GET /executions/e-1": [{ name: "e", status: "completed", task: [{ task_id: "t-1", name: "CheckT1", qid: "6", status: "completed" }], note: {} }],
    "GET /chips/C/qubits/6": [{ qid: "6", chip_id: "C", status: "ok", data: {} }],
  });
  const routed = [];
  // The host's fetch reaches QDash at a name only it can resolve.
  const fetch = (input, init) => {
    const request = new Request(input, init);
    routed.push(request.url);
    return globalThis.fetch(request.url.replace("http://qdash.internal", baseUrl), { method: request.method, headers: request.headers });
  };
  const client = new QDashClient(new QDashConfig({ baseUrl: "http://qdash.internal", apiToken: "user-token" }), { fetch });
  const tools = new Map();
  registerTaskResultEvidenceTool({ registerTool: (tool) => tools.set(tool.name, tool) }, { makeClient: async () => client, sdk: sdkSessionFactory({ fetch }) });
  const result = await tools.get("qdash_get_task_result_evidence").execute("t", { taskId: "t-1" });
  assert.equal(result.details.tool, "qdash_get_task_result_evidence");
  assert.deepEqual(requests.map((request) => request.key), ["GET /tasks/t-1/result", "GET /executions/e-1", "GET /chips/C/qubits/6"]);
  assert.ok(routed.every((url) => url.startsWith("http://qdash.internal/")));
  assert.ok(requests.every((request) => request.headers.authorization === "Bearer user-token"));
});
