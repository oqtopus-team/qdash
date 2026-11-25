// pi-qdash reads the TOML config file shared with the QDash SDKs (written by `qdash config init`)
// as well as the legacy INI config.ini, through the extension's own tools and commands,
// against a local HTTP server.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import qdashExtension from "../.test-dist/qdash.js";
import { configProfiles, connectClient, connectionSource } from "../.test-dist/lib/connection.js";
import { connectionClient } from "../.test-dist/lib/waits.js";

const pi = fileURLToPath(new URL("..", import.meta.url));
const sdkCli = join(realpathSync(join(pi, "node_modules", "@oqtopus-team/qdash-sdk")), "dist", "cli.js");

const SECRET = "sekrit-token-value";
const ENV_KEYS = ["XDG_CONFIG_HOME", "QDASH_BASE_URL", "QDASH_API_TOKEN", "QDASH_PROJECT_ID", "QDASH_LAB_TOKEN", "PI_CODING_AGENT_DIR"];

/** Isolate the variables pi-qdash reads, restoring them after the test. */
function isolateEnv(t, values = {}) {
  const saved = Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
  for (const key of ENV_KEYS) delete process.env[key];
  const home = mkdtempSync(join(tmpdir(), "pi-qdash-config-"));
  process.env.XDG_CONFIG_HOME = join(home, "xdg");
  process.env.PI_CODING_AGENT_DIR = join(home, "agent");
  Object.assign(process.env, values);
  t.after(() => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    rmSync(home, { recursive: true, force: true });
  });
  const qdashDir = join(process.env.XDG_CONFIG_HOME, "qdash");
  mkdirSync(qdashDir, { recursive: true });
  return { home, qdashDir, toml: join(qdashDir, "config.toml"), ini: join(qdashDir, "config.ini") };
}

async function fakeQDash(t, routes = {}) {
  const requests = [];
  const server = createServer(async (request, response) => {
    for await (const _chunk of request);
    const url = new URL(request.url, "http://localhost");
    const key = `${request.method} ${url.pathname}`;
    requests.push({ key, headers: request.headers });
    const body = routes[key];
    response.writeHead(body === undefined ? 404 : 200, { "content-type": "application/json" });
    response.end(JSON.stringify(body ?? { detail: `no ${key}` }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  return { baseUrl: `http://127.0.0.1:${server.address().port}`, requests };
}

/**
 * The extension's tools and commands, after a session start that resets its module-level
 * context from the isolated agent directory. Requests made by that start are dropped.
 */
async function extension(...servers) {
  const tools = new Map();
  const commands = new Map();
  const handlers = new Map();
  qdashExtension({
    registerTool: (tool) => tools.set(tool.name, tool),
    registerCommand: (name, command) => commands.set(name, command),
    on: (event, handler) => handlers.set(event, handler),
    appendEntry() {},
  });
  await handlers.get("session_start")({}, { sessionManager: { getEntries: () => [] }, ui: { setStatus() {} } });
  for (const server of servers) server.requests.length = 0;
  return { tools, commands };
}

const CHIPS = { chips: [{ chip_id: "64Qv3", activity_status: "active" }] };
const SPEC = { spec_version: 2, targets: { qids: ["0"] }, steps: [{ type: "CustomOneQubit", tasks: [{ name: "CheckT1" }] }] };
const VALID = { valid: true, problems: [], warnings: [], backend_name: "qubex", spec: SPEC, targets: { qids: ["0"] }, steps: [], task_run_count: 1 };

const iniProfile = (name, values) => `[${name}]\n${Object.entries(values).map(([key, value]) => `${key} = ${JSON.stringify(value)}`).join("\n")}\n`;
const authOf = (requests) => [...new Set(requests.map((request) => request.headers.authorization))];

test("a config.toml written by `qdash config init` drives client tools, SDK tools, waits and config info", async (t) => {
  const paths = isolateEnv(t, { QDASH_LAB_TOKEN: SECRET });
  const { baseUrl, requests } = await fakeQDash(t, {
    "GET /chips": CHIPS,
    "POST /calibration-pipelines/validate": VALID,
    "GET /executions/exec-1": { execution_id: "exec-1", status: "completed", chip_id: "64Qv3" },
  });
  execFileSync(process.execPath, [sdkCli, "config", "init", "--profile", "lab", "--base-url", `${baseUrl}/`, "--api-token-env", "QDASH_LAB_TOKEN", "--project-id", "p-1"], { env: process.env, stdio: "pipe" });
  const { tools } = await extension({ requests });

  await tools.get("qdash_list_chips").execute("t", {});
  const plan = await tools.get("qdash_plan_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC });
  assert.equal(plan.details.valid, true);
  await tools.get("qdash_wait_execution").execute("t", { executionId: "exec-1", timeoutSeconds: 5, pollIntervalSeconds: 0.1 });

  assert.deepEqual(requests.map((request) => request.key), ["GET /chips", "POST /calibration-pipelines/validate", "GET /executions/exec-1"]);
  assert.deepEqual(authOf(requests), [`Bearer ${SECRET}`]);
  assert.ok(requests.every((request) => request.headers["x-project-id"] === "p-1"));

  const info = await tools.get("qdash_config_info").execute("t", {});
  const text = JSON.stringify(info);
  assert.doesNotMatch(text, new RegExp(SECRET));
  assert.deepEqual(info.details.data.profiles, { path: paths.toml, format: "toml", defaultProfile: "lab", exists: true, profiles: ["lab"] });
  assert.equal(info.details.data.active.source, "profile:lab");
  assert.equal(info.details.data.active.baseUrl, baseUrl);
  assert.equal(info.details.data.active.projectId, "p-1");
});

test("/qdash-setup without a profile selects the config.toml default_profile", async (t) => {
  const paths = isolateEnv(t);
  const { baseUrl, requests } = await fakeQDash(t, { "GET /chips": CHIPS });
  writeFileSync(paths.toml, `default_profile = "lab"\n\n[lab]\nbase_url = "${baseUrl}"\napi_token = "${SECRET}"\n`);
  const { commands } = await extension({ requests });
  const notes = [];
  const ui = { notify: (message, level) => notes.push({ message, level }), setStatus() {}, setWidget() {} };
  await commands.get("qdash-setup").handler("", { ui });
  assert.deepEqual(notes.at(-1), { message: "QDash setup complete: profile lab, chip 64Qv3", level: "info" });
  assert.ok(requests.length > 0 && authOf(requests).every((value) => value === `Bearer ${SECRET}`));
});

test("an explicit .toml configPath and profile select that profile; the default path is not read", async (t) => {
  const paths = isolateEnv(t);
  const { baseUrl, requests } = await fakeQDash(t, { "GET /chips": CHIPS });
  writeFileSync(paths.toml, "not = [valid toml");
  const configPath = join(paths.home, "other.TOML");
  writeFileSync(configPath, `[a]\nbase_url = "http://127.0.0.1:1"\n\n[b]\nbase_url = "${baseUrl}"\napi_token = "tok-b"\ntimeout_sec = 7\nread_attempts = 2\n`);
  const client = await connectClient({ profile: "b", configPath });
  assert.equal(client.config.timeoutSec, 7);
  assert.equal(client.config.readAttempts, 2);
  await (await extension({ requests })).tools.get("qdash_list_chips").execute("t", { profile: "b", configPath });
  assert.deepEqual(authOf(requests), ["Bearer tok-b"]);
  assert.equal(connectionSource({ configPath }), "profile:default");
});

test("QDASH_BASE_URL still wins without profile or configPath, and an explicit profile reads config.toml", async (t) => {
  const paths = isolateEnv(t);
  const envServer = await fakeQDash(t, { "GET /chips": CHIPS });
  const fileServer = await fakeQDash(t, { "GET /chips": CHIPS });
  process.env.QDASH_BASE_URL = envServer.baseUrl;
  process.env.QDASH_API_TOKEN = "env-token";
  writeFileSync(paths.toml, `default_profile = "lab"\n[lab]\nbase_url = "${fileServer.baseUrl}"\napi_token = "file-token"\n`);
  const { tools } = await extension(envServer, fileServer);
  await tools.get("qdash_list_chips").execute("t", {});
  assert.deepEqual(authOf(envServer.requests), ["Bearer env-token"]);
  assert.equal(connectionSource({}), "env");
  await tools.get("qdash_list_chips").execute("t", { profile: "lab" });
  assert.deepEqual(authOf(fileServer.requests), ["Bearer file-token"]);
  await tools.get("qdash_list_chips").execute("t", { useEnv: true, profile: "lab" });
  assert.equal(envServer.requests.length, 2);
});

test("a hosted connection reads only its explicit INI profile, never the environment or config.toml", async (t) => {
  const paths = isolateEnv(t);
  const { baseUrl, requests } = await fakeQDash(t, { "GET /chips": CHIPS, "POST /calibration-pipelines/validate": VALID });
  process.env.QDASH_BASE_URL = "http://127.0.0.1:1";
  process.env.QDASH_API_TOKEN = "ambient-token";
  writeFileSync(paths.toml, "this is = = not toml");
  const configPath = join(paths.home, "hosted", "config.ini");
  mkdirSync(join(paths.home, "hosted"));
  writeFileSync(configPath, iniProfile("runtime", { base_url: baseUrl, api_token: "user-token", project_id: "p-9" }));
  const connection = { profile: "runtime", configPath, useEnv: false };
  const { tools } = await extension({ requests });
  await tools.get("qdash_list_chips").execute("t", connection);
  await tools.get("qdash_plan_pipeline").execute("t", { ...connection, chipId: "64Qv3", spec: SPEC });
  const client = await connectionClient(connection);
  assert.equal(client.config.baseUrl, baseUrl);
  assert.deepEqual(authOf(requests), ["Bearer user-token"]);
  assert.ok(requests.every((request) => request.headers["x-project-id"] === "p-9"));
  await assert.rejects(connectionClient({ profile: "runtime", configPath: "" }), /must name its config file/);
});

test("without config.toml the legacy config.ini default profile is used as before", async (t) => {
  const paths = isolateEnv(t);
  const { baseUrl, requests } = await fakeQDash(t, { "GET /chips": CHIPS });
  writeFileSync(paths.ini, iniProfile("default", { base_url: baseUrl, api_token: "ini-token", timeout_seconds: "9", retry_max_attempts: "4" }) + iniProfile("other", { base_url: "http://127.0.0.1:1" }));
  const client = await connectClient({});
  assert.equal(client.config.timeoutSec, 9);
  assert.equal(client.config.readAttempts, 4);
  await (await extension({ requests })).tools.get("qdash_list_chips").execute("t", {});
  assert.deepEqual(authOf(requests), ["Bearer ini-token"]);
  assert.deepEqual(configProfiles(), { path: paths.ini, format: "ini", defaultProfile: "default", exists: true, profiles: ["default", "other"] });
  assert.equal(connectionSource({}), "profile:default");
});

test("an invalid config.toml fails without falling back to config.ini or leaking its contents", async (t) => {
  const paths = isolateEnv(t);
  const { baseUrl, requests } = await fakeQDash(t, { "GET /chips": CHIPS });
  writeFileSync(paths.ini, iniProfile("default", { base_url: baseUrl, api_token: "ini-token" }));
  writeFileSync(paths.toml, `[default]\nbase_url = "${baseUrl}"\napi_token = "${SECRET}\n`);
  const { tools } = await extension({ requests });
  await assert.rejects(tools.get("qdash_list_chips").execute("t", {}), (error) => {
    assert.match(error.message, /^Invalid TOML in config file .*config\.toml: .*\(at line \d+, column \d+\)$/);
    assert.doesNotMatch(error.message, new RegExp(SECRET));
    return true;
  });
  assert.equal(requests.length, 0);
  const info = await tools.get("qdash_config_info").execute("t", {});
  assert.doesNotMatch(JSON.stringify(info), new RegExp(SECRET));
  assert.equal(info.details.data.profiles.format, "toml");
  assert.match(info.details.data.profiles.error, /^Invalid TOML in config file/);
  assert.match(info.details.data.error, /^Invalid TOML in config file/);
});

test("a profile only in the ignored config.ini is reported against config.toml", async (t) => {
  const paths = isolateEnv(t);
  writeFileSync(paths.ini, iniProfile("legacy", { base_url: "http://127.0.0.1:1", api_token: "ini-token" }));
  writeFileSync(paths.toml, `[lab]\nbase_url = "http://127.0.0.1:1"\n`);
  await assert.rejects(connectClient({ profile: "legacy" }), /Config profile not found: legacy in .*config\.toml\. The legacy .*config\.ini is not read while .*config\.toml exists/);
  assert.equal((await connectClient({ profile: "legacy", configPath: paths.ini })).config.apiToken, "ini-token");
});

test("TOML settings pi-qdash cannot apply fail with the profile and field, never a value", async (t) => {
  const paths = isolateEnv(t);
  writeFileSync(paths.toml, [
    `[insecure]\nbase_url = "https://qdash.example/api"\napi_token = "${SECRET}"\nverify_tls = false`,
    `[proxied]\nbase_url = "https://qdash.example/api"\nproxy = "http://user:${SECRET}@proxy:8080"`,
    `[relative]\nbase_url = "qdash/api"\napi_token = "${SECRET}"`,
    `[tokenenv]\nbase_url = "https://qdash.example/api"\napi_token_env = "QDASH_LAB_TOKEN"`,
    `[typo]\nbase_url = "https://qdash.example/api"\napi_tokn = "${SECRET}"`,
  ].join("\n\n"));
  const failure = (pattern) => (error) => {
    assert.match(error.message, pattern);
    assert.doesNotMatch(error.message, new RegExp(SECRET));
    return true;
  };
  await assert.rejects(connectClient({ profile: "insecure" }), failure(/^Profile 'insecure' in config file .*config\.toml cannot be used by pi-qdash: proxy and verifyTls=false need a custom fetch/));
  await assert.rejects(connectClient({ profile: "proxied" }), failure(/^Profile 'proxied' .* cannot be used by pi-qdash: proxy and verifyTls=false need a custom fetch/));
  await assert.rejects(connectClient({ profile: "relative" }), failure(/^Profile 'relative' .* cannot be used by pi-qdash: baseUrl must be a valid URL/));
  await assert.rejects(connectClient({ profile: "tokenenv" }), failure(/Environment variable QDASH_LAB_TOKEN named by 'api_token_env' in profile 'tokenenv' is not set or empty/));
  await assert.rejects(connectClient({ profile: "typo" }), failure(/Unknown keys in profile 'typo': api_tokn/));
  await assert.rejects(connectClient({}), /Config profile not found: default/);
});
