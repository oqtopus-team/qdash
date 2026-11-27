// The spectroscopy reanalysis tools as pi-qdash registers them: real HTTP requests to a local
// QDash that answers the reanalyze routes, so the wire body, the policy, and the image content
// are checked together.
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import qdashExtension from "../.test-dist/qdash.js";
import { selectEvaluationFigures } from "../.test-dist/lib/qcal-hydration.js";
import {
  DEFERRED_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
  SESSION_GRANTED_WRITE_TOOL_NAMES,
  scriptDataOf,
} from "../.test-dist/lib/tool-policy.js";
import { toolIntents } from "../.test-dist/lib/tool-intents.js";
import { missingImageNote, REANALYZE_QUBIT_TOOL, REANALYZE_RESONATOR_TOOL } from "../.test-dist/tools/reanalysis.js";

// A real 1x1 PNG, so the image passes the evaluation hosts' signature check.
const PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

function qubitResponse(body) {
  return {
    source_task_id: body.figure ? null : "task-q1",
    source_task_name: "CheckQubitSpectroscopy",
    qid: "1",
    figure: { data: [{ type: "heatmap", z: [[1]] }], layout: {} },
    output_parameters: [
      { name: "qubit_frequency", value: 7.123, unit: "GHz" },
      { name: "coarse_qubit_frequency", value: 7.123, unit: "GHz" },
      { name: "coarse_control_amplitude", value: 0.1, unit: "a.u." },
      { name: "f01_repr_db", value: -30, unit: "dB" },
      { name: "f01_quality_level", value: 4, unit: "a.u." },
    ],
    image_base64: body.include_image ? PNG_BASE64 : null,
    image_media_type: body.include_image ? "image/png" : null,
    image_error: null,
    committed: false,
  };
}

function resonatorResponse(body) {
  return {
    source_task_id: "task-r1",
    source_task_name: "CheckResonatorSpectroscopy",
    qid: "1",
    figure: { data: [], layout: {} },
    output_parameters: [
      { name: "readout_frequency", value: 6.3, unit: "GHz" },
      { name: "optimal_power", value: -35, unit: "dB" },
      { name: "readout_amplitude", value: 10 ** (-35 / 20), unit: "a.u." },
    ],
    image_base64: null,
    image_media_type: null,
    image_error: body.include_image ? "Preview image rendering failed." : null,
    committed: false,
  };
}

/** A QDash answering the two reanalyze routes and recording each request. */
async function fakeQDash(t, { defaultChip = "64Qv3" } = {}) {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    let raw = "";
    request.on("data", (chunk) => (raw += chunk));
    request.on("end", () => {
      const body = raw ? JSON.parse(raw) : {};
      requests.push({ method: request.method, path: url.pathname, body });
      const send = (status, payload) => {
        response.writeHead(status, { "content-type": "application/json" });
        response.end(JSON.stringify(payload));
      };
      if (url.pathname === "/chips") return send(200, { chips: [{ chip_id: defaultChip, size: 64, activity_status: "active" }] });
      if (url.pathname.endsWith("/reanalyze/qubit-spectroscopy")) return send(200, qubitResponse(body));
      if (url.pathname.endsWith("/reanalyze/resonator-spectroscopy")) return send(200, resonatorResponse(body));
      return send(404, { detail: `no ${url.pathname}` });
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const directory = await mkdtemp(join(tmpdir(), "pi-qdash-reanalysis-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const configPath = join(directory, "config.ini");
  await writeFile(configPath, `[runtime]\nbase_url = "http://127.0.0.1:${server.address().port}"\napi_token = "user-token"\n`, { mode: 0o600 });
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  return { requests, baseUrl, connection: { profile: "runtime", configPath, useEnv: false } };
}

function extensionTools(handlers = new Map()) {
  const tools = new Map();
  qdashExtension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on: (event, handler) => handlers.set(event, handler), appendEntry() {} });
  return tools;
}

const ENV_KEYS = ["XDG_CONFIG_HOME", "QDASH_BASE_URL", "QDASH_API_TOKEN", "QDASH_PROJECT_ID", "PI_CODING_AGENT_DIR"];

/** Isolate the variables pi-qdash reads, with a config.toml of the given contents; restored after the test. */
async function isolateEnv(t, toml) {
  const saved = Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
  for (const key of ENV_KEYS) delete process.env[key];
  const home = await mkdtemp(join(tmpdir(), "pi-qdash-reanalysis-env-"));
  process.env.XDG_CONFIG_HOME = join(home, "xdg");
  process.env.PI_CODING_AGENT_DIR = join(home, "agent");
  t.after(async () => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    await rm(home, { recursive: true, force: true });
  });
  await mkdir(join(home, "xdg", "qdash"), { recursive: true });
  await writeFile(join(home, "xdg", "qdash", "config.toml"), toml, { mode: 0o600 });
}

test("the reanalysis tools are deferred, script-callable reads for diagnosis", () => {
  const tools = extensionTools();
  for (const name of [REANALYZE_QUBIT_TOOL, REANALYZE_RESONATOR_TOOL]) {
    assert.ok(tools.has(name), name);
    assert.ok(NESTED_READ_TOOL_NAMES.includes(name), name);
    assert.ok(DEFERRED_TOOL_NAMES.includes(name), name);
    assert.ok(!REVIEWED_WRITE_TOOL_NAMES.includes(name), name);
    assert.ok(!SESSION_GRANTED_WRITE_TOOL_NAMES.includes(name), name);
    assert.deepEqual(toolIntents(name), ["diagnosis"]);
    const tool = tools.get(name);
    assert.equal(tool.annotations?.readOnlyHint, true, name);
    assert.equal(tool.exposure, "deferred", name);
  }
});

test("qubit reanalysis sends the overrides, returns the seeds, and attaches the PNG by default", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tool = extensionTools().get(REANALYZE_QUBIT_TOOL);

  const result = await tool.execute("call-1", {
    ...connection,
    chipId: "64Qv3",
    qid: "1",
    sourceTaskId: "task-q1",
    parameters: { f01_height_min: 10, retry_with_trim: true, top_power: undefined },
  });

  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, "POST");
  assert.equal(requests[0].path, "/chips/64Qv3/qubits/1/reanalyze/qubit-spectroscopy");
  assert.deepEqual(requests[0].body, {
    source_task_id: "task-q1",
    parameters: { f01_height_min: 10, retry_with_trim: true },
    include_image: true,
  });

  const [text, image] = result.content;
  assert.equal(text.type, "text");
  assert.match(text.text, /coarse_qubit_frequency=7\.123 GHz/);
  assert.match(text.text, /coarse_control_amplitude=0\.1 a\.u\./);
  assert.match(text.text, /Preview only/);
  assert.doesNotMatch(text.text, /Preview rendering failed/);
  assert.deepEqual(image, { type: "image", data: PNG_BASE64, mimeType: "image/png" });

  const data = result.details.data;
  assert.equal(data.committed, false);
  assert.deepEqual(data.outputs.coarse_control_amplitude, { value: 0.1, unit: "a.u." });
  assert.deepEqual(data.image, { requested: true, included: true, media_type: "image/png" });
  assert.equal(data.links.task_result.endsWith("/task-results/task-q1"), true);
  // The script data carries no Plotly figure and no image bytes.
  const scriptData = scriptDataOf(result);
  assert.equal(JSON.stringify(scriptData).includes(PNG_BASE64), false);
  assert.equal("figure" in scriptData, false);

  // qcal_evaluate for the same task takes this reanalyzed figure.
  assert.equal(result.details.taskName, "CheckQubitSpectroscopy");
  assert.equal(result.details.taskId, "task-q1");
  const selected = selectEvaluationFigures([result], { taskName: "CheckQubitSpectroscopy" });
  assert.equal(selected.images.length, 1);
  assert.equal(selected.taskId, "task-q1");
});

test("includeImage false asks for no image and returns text only", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tool = extensionTools().get(REANALYZE_QUBIT_TOOL);

  const result = await tool.execute("call-2", { ...connection, chipId: "64Qv3", qid: "1", includeImage: false });

  assert.deepEqual(requests[0].body, { include_image: false });
  assert.deepEqual(result.content.map((block) => block.type), ["text"]);
  assert.deepEqual(result.details.data.image, { requested: false, included: false });
  assert.match(result.content[0].text, /overrides: none/);
  // Not asking for an image is not a rendering failure.
  assert.doesNotMatch(result.content[0].text, /Preview rendering failed/);
});

test("resonator reanalysis uses the default chip and reports a missing image", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tool = extensionTools().get(REANALYZE_RESONATOR_TOOL);

  const result = await tool.execute("call-3", {
    ...connection,
    qid: "1",
    parameters: { bare_shift_estimator_type: "config", resonator_assignment_order: [0, 3, 1, 2] },
  });

  const call = requests.find((request) => request.path.endsWith("/reanalyze/resonator-spectroscopy"));
  assert.equal(call.path, "/chips/64Qv3/qubits/1/reanalyze/resonator-spectroscopy");
  assert.deepEqual(call.body, {
    parameters: { bare_shift_estimator_type: "config", resonator_assignment_order: [0, 3, 1, 2] },
    include_image: true,
  });
  assert.deepEqual(result.content.map((block) => block.type), ["text"]);
  assert.match(result.content[0].text, /optimal_power=-35 dB/);
  assert.match(result.content[0].text, /image: unavailable: Preview image rendering failed\./);
  // Without the reanalyzed figure, qcal_evaluate would hydrate an older stored figure of the task.
  assert.ok(result.content[0].text.includes(missingImageNote("CheckResonatorSpectroscopy")));
  assert.match(result.content[0].text, /Do not call qcal_evaluate for CheckResonatorSpectroscopy now/);
  assert.equal(result.details.data.image.included, false);
  assert.equal(result.details.data.image.error, "Preview image rendering failed.");
  assert.equal(result.details.data.outputs.readout_amplitude.unit, "a.u.");
});

test("an inline figure is forwarded and its result is still routed to qcal_evaluate", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tool = extensionTools().get(REANALYZE_QUBIT_TOOL);
  const figure = { data: [{ type: "heatmap", x: [7.0, 7.1], y: [-60, -55], z: [[0, 1], [1, 0]] }], layout: {} };

  const result = await tool.execute("call-4", { ...connection, chipId: "64Qv3", qid: "1", figure });

  assert.deepEqual(requests[0].body, { figure, include_image: true });
  assert.match(result.content[0].text, /^Reanalyzed an inline CheckQubitSpectroscopy figure \(no stored task result\) for qubit 1/);
  assert.equal(result.details.data.source_task_id, null);
  assert.deepEqual(result.details.data.links, {});
  // No task result to name, but the task name keeps qcal_evaluate on this figure.
  assert.equal("taskId" in result.details, false);
  assert.equal(result.details.taskName, "CheckQubitSpectroscopy");
  const selected = selectEvaluationFigures([result], { taskName: "CheckQubitSpectroscopy" });
  assert.equal(selected.images.length, 1);
  assert.equal(selected.taskId, undefined);
});

test("sourceTaskId and figure together are refused before any request", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tool = extensionTools().get(REANALYZE_RESONATOR_TOOL);

  await assert.rejects(
    tool.execute("call-5", { ...connection, chipId: "64Qv3", qid: "1", sourceTaskId: "task-r1", figure: { data: [] } }),
    /either sourceTaskId or figure, not both/,
  );
  assert.equal(requests.length, 0);
});

test("the session's chip is used only for the session's connection; another one resolves its own default", async (t) => {
  const lab = await fakeQDash(t, { defaultChip: "LAB_DEFAULT" });
  const other = await fakeQDash(t, { defaultChip: "OTHER_DEFAULT" });
  await isolateEnv(
    t,
    `default_profile = "lab"\n[lab]\nbase_url = "${lab.baseUrl}"\napi_token = "lab-token"\n[other]\nbase_url = "${other.baseUrl}"\napi_token = "other-token"\n`,
  );
  const handlers = new Map();
  const tool = extensionTools(handlers).get(REANALYZE_RESONATOR_TOOL);
  // The session's context: profile lab with its chip SESSION_CHIP.
  const session = (data) => ({ sessionManager: { getEntries: () => [{ type: "custom", customType: "qdash-context", data }] }, ui: { setStatus() {} } });
  await handlers.get("session_start")({}, session({ profile: "lab", chipId: "SESSION_CHIP" }));
  t.after(() => handlers.get("session_start")({}, session({})));
  const reanalyzedChip = async (server, params) => {
    server.requests.length = 0;
    await tool.execute("call-ctx", { qid: "1", includeImage: false, ...params });
    const call = server.requests.find((request) => request.path.endsWith("/reanalyze/resonator-spectroscopy"));
    assert.ok(call, JSON.stringify(params));
    return call.path.split("/")[2];
  };

  // The session's profile, implied or named, keeps the session's chip.
  assert.equal(await reanalyzedChip(lab, {}), "SESSION_CHIP");
  assert.equal(await reanalyzedChip(lab, { profile: "lab" }), "SESSION_CHIP");
  // Another profile does not inherit it: that server's default chip is used.
  assert.equal(await reanalyzedChip(other, { profile: "other" }), "OTHER_DEFAULT");
  // An explicit chip always wins.
  assert.equal(await reanalyzedChip(other, { profile: "other", chipId: "EXPLICIT" }), "EXPLICIT");
  // Neither the environment nor another config file is the session's connection.
  process.env.QDASH_BASE_URL = other.baseUrl;
  process.env.QDASH_API_TOKEN = "env-token";
  assert.equal(await reanalyzedChip(other, { useEnv: true }), "OTHER_DEFAULT");
  delete process.env.QDASH_BASE_URL;
  delete process.env.QDASH_API_TOKEN;
  const altConfig = join(process.env.XDG_CONFIG_HOME, "alt.ini");
  await writeFile(altConfig, `[lab]\nbase_url = "${lab.baseUrl}"\napi_token = "alt-token"\n`, { mode: 0o600 });
  assert.equal(await reanalyzedChip(lab, { profile: "lab", configPath: altConfig }), "LAB_DEFAULT");
});

test("frequencyMin and frequencyMax are sent as the frequency window of either tool", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tools = extensionTools();

  const qubit = await tools.get(REANALYZE_QUBIT_TOOL).execute("call-6", {
    ...connection,
    chipId: "64Qv3",
    qid: "1",
    sourceTaskId: "task-q1",
    frequencyMin: 7.3,
    frequencyMax: 7.9,
    parameters: { top_power: -5, f01_height_min: 8, retry_with_trim: true },
    includeImage: false,
  });
  await tools.get(REANALYZE_RESONATOR_TOOL).execute("call-7", {
    ...connection,
    chipId: "64Qv3",
    qid: "1",
    frequencyMax: 10.4,
    includeImage: false,
  });

  assert.deepEqual(requests[0].body, {
    source_task_id: "task-q1",
    parameters: { top_power: -5, f01_height_min: 8, retry_with_trim: true, frequency_min: 7.3, frequency_max: 7.9 },
    include_image: false,
  });
  assert.deepEqual(requests[1].body, { parameters: { frequency_max: 10.4 }, include_image: false });
  assert.match(qubit.content[0].text, /overrides: .*frequency_min=7\.3, frequency_max=7\.9/);
  assert.deepEqual(qubit.details.data.parameters.frequency_min, 7.3);
});

test("frequencyMin and frequencyMax override the same fields in parameters", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tool = extensionTools().get(REANALYZE_QUBIT_TOOL);

  await tool.execute("call-8", {
    ...connection,
    chipId: "64Qv3",
    qid: "1",
    frequencyMin: 7.4,
    parameters: { frequency_min: 7.0, frequency_max: 8.0 },
    includeImage: false,
  });

  assert.deepEqual(requests[0].body.parameters, { frequency_min: 7.4, frequency_max: 8.0 });
});

test("an unusable frequency window is refused before any request", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tools = extensionTools();
  const base = { ...connection, chipId: "64Qv3", qid: "1" };

  for (const name of [REANALYZE_QUBIT_TOOL, REANALYZE_RESONATOR_TOOL]) {
    const tool = tools.get(name);
    await assert.rejects(tool.execute("call-9", { ...base, frequencyMin: 7.9, frequencyMax: 7.3 }), /minimum \(7\.9 GHz\) must be less than its maximum \(7\.3 GHz\)/);
    await assert.rejects(tool.execute("call-10", { ...base, frequencyMin: 7.3, frequencyMax: 7.3 }), /must be less than its maximum/);
    await assert.rejects(tool.execute("call-11", { ...base, frequencyMax: Number.NaN }), /frequencyMax must be a finite frequency in GHz/);
    await assert.rejects(tool.execute("call-12", { ...base, frequencyMin: Number.POSITIVE_INFINITY }), /frequencyMin must be a finite frequency in GHz/);
  }
  assert.equal(requests.length, 0);
});

test("both tools describe the frequency window", () => {
  const tools = extensionTools();
  for (const name of [REANALYZE_QUBIT_TOOL, REANALYZE_RESONATOR_TOOL]) {
    const { properties } = tools.get(name).parameters;
    assert.equal(properties.frequencyMin.type, "number", name);
    assert.equal(properties.frequencyMax.type, "number", name);
    assert.match(properties.frequencyMin.description, /GHz/);
    assert.ok(tools.get(name).promptGuidelines.some((line) => line.includes("frequencyMin")), name);
  }
});

test("the merged frequency window is checked, whichever field each edge came from", async (t) => {
  const { requests, connection } = await fakeQDash(t);
  const tools = extensionTools();
  const base = { ...connection, chipId: "64Qv3", qid: "1", includeImage: false };

  for (const name of [REANALYZE_QUBIT_TOOL, REANALYZE_RESONATOR_TOOL]) {
    const tool = tools.get(name);
    await assert.rejects(
      tool.execute("call-13", { ...base, frequencyMin: 7.4, parameters: { frequency_max: 7.0 } }),
      /minimum \(7\.4 GHz\) must be less than its maximum \(7 GHz\)/,
    );
    await assert.rejects(
      tool.execute("call-14", { ...base, frequencyMax: 7.0, parameters: { frequency_min: 7.4 } }),
      /minimum \(7\.4 GHz\) must be less than its maximum/,
    );
    await assert.rejects(
      tool.execute("call-15", { ...base, parameters: { frequency_min: 7.9, frequency_max: 7.3 } }),
      /must be less than its maximum/,
    );
    await assert.rejects(
      tool.execute("call-16", { ...base, parameters: { frequency_min: "7.3" } }),
      /parameters\.frequency_min must be a finite frequency in GHz/,
    );
  }
  assert.equal(requests.length, 0);

  // An override that repairs the window is accepted.
  await tools.get(REANALYZE_QUBIT_TOOL).execute("call-17", { ...base, frequencyMin: 6.9, parameters: { frequency_min: 7.4, frequency_max: 7.0 } });
  assert.deepEqual(requests[0].body.parameters, { frequency_min: 6.9, frequency_max: 7.0 });
});
