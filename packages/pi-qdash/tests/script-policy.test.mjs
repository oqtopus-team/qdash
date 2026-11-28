import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  applyToolPolicy,
  CODEMODE_ENV,
  installQDashToolPolicy,
  nestedCallBlock,
  SCRIPT_DATA_SCHEMA,
} from "../.test-dist/lib/script-policy.js";
import {
  DEFAULT_SCRIPT_TIMEOUT_MS,
  DEFERRED_TOOL_NAMES,
  MAX_NESTED_DATA_BYTES,
  MAX_SCRIPT_TIMEOUT_MS,
  NESTED_PROPOSAL_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  QDASH_TOOL_NAMESPACE,
  REVIEWED_WRITE_TOOL_NAMES,
  SCRIPT_DATA_DESCRIPTION,
  boundScriptData,
  jsonByteLength,
  scriptDataOf,
  withScriptDeadline,
} from "../.test-dist/lib/tool-policy.js";
import { createOwnershipCheck, sourceFileKey } from "../.test-dist/lib/extension-identity.js";
import {
  SELECTION_ENTRY,
  branchSelection,
  clearHandoffs,
  leaveHandoff,
  settingsSelection,
  takeHandoff,
} from "../.test-dist/lib/tool-selection.js";
import qdashExtension from "../.test-dist/qdash.js";

// A real entry file, so identity compares real paths as it does under pi.
const ENTRY_DIR = mkdtempSync(join(tmpdir(), "pi-qdash-entry-"));
mkdirSync(join(ENTRY_DIR, "extensions"));
const ENTRY = join(ENTRY_DIR, "extensions", "qdash.ts");
writeFileSync(ENTRY, "");
const FOREIGN = join(ENTRY_DIR, "foreign.ts");
writeFileSync(FOREIGN, "");
const OWN_SOURCE = { path: ENTRY, source: "local", scope: "temporary", origin: "top-level" };
const FOREIGN_SOURCE = { path: FOREIGN, source: "local", scope: "temporary", origin: "top-level" };
const policy = (env = {}) => ({ entry: pathToFileURL(ENTRY).href, env });
/** A tool definition with its own parameter schema object, as pi requires. */
const tool = (name, extra = {}) => ({ name, parameters: { type: "object", properties: {} }, ...extra });

/**
 * A pi double with the parts the policy uses, recording registrations and
 * handlers. Its registry reports tools the way pi's does: per name, the first
 * extension to register it wins (`foreign` tools come from an extension loaded
 * before pi-qdash), with the registering extension's source info and the
 * registered parameters object. `allTools` replaces the registry outright.
 */
function fakePi({ allTools, active = [], foreign = [], own = OWN_SOURCE, settings } = {}) {
  const registered = [];
  const handlers = new Map();
  const branch = [];
  const state = { active: [...active], all: allTools, foreign, branch, settings };
  const registry = () => {
    const byName = new Map();
    for (const definition of state.foreign) if (!byName.has(definition.name)) byName.set(definition.name, { ...definition, sourceInfo: definition.sourceInfo ?? FOREIGN_SOURCE });
    const ownByName = new Map(registered.map((definition) => [definition.name, definition]));
    for (const [name, definition] of ownByName) {
      if (!byName.has(name)) byName.set(name, { ...definition, exposure: definition.exposure ?? "direct", sourceInfo: own });
    }
    return [...byName.values()];
  };
  const pi = {
    registered,
    handlers,
    state,
    registerTool: (definition) => registered.push(definition),
    registerCommand() {},
    appendEntry: (customType, data) => branch.push({ type: "custom", customType, data }),
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    getAllTools: () => state.all ?? registry(),
    getActiveTools: () => [...state.active],
    setActiveTools: (names) => { state.active = [...names]; },
    getSettings: () => state.settings ?? {},
  };
  pi.ctx = { sessionManager: { getBranch: () => [...branch], getSessionFile: () => undefined } };
  return pi;
}

async function emit(pi, event, payload, ctx = pi.ctx ?? {}) {
  let last;
  for (const handler of pi.handlers.get(event) ?? []) {
    const result = await handler(payload, ctx);
    if (result !== undefined) last = result;
  }
  return last;
}

test("the shared lists name real pi-qdash tools and agree with each other", () => {
  const pi = fakePi();
  qdashExtension(pi);
  const byName = new Map(pi.registered.map((definition) => [definition.name, definition]));
  for (const name of [...NESTED_READ_TOOL_NAMES, ...DEFERRED_TOOL_NAMES]) assert.ok(byName.has(name), name);
  for (const name of REVIEWED_WRITE_TOOL_NAMES.filter((n) => byName.has(n))) {
    assert.ok(!NESTED_READ_TOOL_NAMES.includes(name), name);
  }
  for (const [name, definition] of byName) {
    if (!name.startsWith("qdash_")) continue;
    const read = NESTED_READ_TOOL_NAMES.includes(name);
    const proposal = NESTED_PROPOSAL_TOOL_NAMES.includes(name);
    const deferred = DEFERRED_TOOL_NAMES.includes(name);
    assert.equal(definition.exposure, deferred ? "deferred" : read || proposal ? undefined : "model-only", name);
    // A read with a checked response contract or its own output shape declares that shape; the others the generic data schema.
    const contracted = ["qdash_list_task_results", "qdash_get_chip_metrics", "qdash_get_timeseries", "qdash_summarize_task_results"].includes(name);
    assert.equal(definition.outputSchema !== undefined && (definition.outputSchema === SCRIPT_DATA_SCHEMA) !== contracted, read || proposal, name);
    if (read) assert.equal(definition.annotations?.readOnlyHint, true, name);
    // A proposal tool persists a record: never labelled a read, never destructive.
    if (proposal) {
      assert.equal(definition.annotations?.readOnlyHint, false, name);
      assert.equal(definition.annotations?.destructiveHint, false, name);
      assert.equal(definition.annotations?.idempotentHint, true, name);
      assert.ok(!REVIEWED_WRITE_TOOL_NAMES.includes(name) && !NESTED_READ_TOOL_NAMES.includes(name), name);
    }
    if (REVIEWED_WRITE_TOOL_NAMES.includes(name)) assert.equal(definition.annotations?.destructiveHint, true, name);
    // The same code mode namespace QDash chat declares on its qdash extension.
    assert.equal(definition.namespace, QDASH_TOOL_NAMESPACE, name);
  }
});

test("the generic script data schema says the value is already parsed", () => {
  assert.equal(SCRIPT_DATA_SCHEMA.description, SCRIPT_DATA_DESCRIPTION);
  assert.match(SCRIPT_DATA_DESCRIPTION, /already parsed into a JavaScript value \(not a JSON string; do not JSON\.parse it\)/);
});

test("applyToolPolicy keeps other extensions' tools and an exposure or namespace a tool states", () => {
  const bash = { name: "bash" };
  assert.equal(applyToolPolicy(bash), bash);
  assert.equal(applyToolPolicy({ name: "qdash_raw_get" }).exposure, "model-only");
  assert.equal(applyToolPolicy({ name: "qdash_list_chips", exposure: "hidden" }).exposure, "hidden");
  const own = { name: "qdash", description: "stated" };
  assert.equal(applyToolPolicy({ name: "qdash_list_chips", namespace: own }).namespace, own);
  assert.equal(applyToolPolicy(bash).namespace, undefined);
});

test("scripts reach only pi-qdash's audited reads and declared read-only tools", () => {
  const block = (name, options = {}) => nestedCallBlock(name, { parent: "codemode", ownTool: true, ...options });
  assert.equal(block("qdash_list_chips"), undefined);
  // Another extension's tool that took an audited name is not audited.
  assert.match(block("qdash_list_chips", { ownTool: false }), /read-only tools/);
  for (const name of ["qdash_create_forum_post", "qdash_save_flow", "qdash_raw_get", "qdash_get_figure", "qdash_build_qcal_evidence", "qdash_run_pipeline", "qdash_wait_execution", "qdash_run_agent_session_step", "qdash_record_calibration_decision"]) {
    assert.match(block(name), /cannot be called from a code mode script/, name);
  }
  // The pinned plan store is the one proposal tool a script may call; a replacement is not.
  assert.equal(block("qdash_create_pipeline_plan"), undefined);
  assert.match(block("qdash_create_pipeline_plan", { ownTool: false }), /cannot be called from a code mode script/);
  for (const name of ["bash", "write", "edit", "powershell"]) {
    assert.match(block(name, { annotations: { readOnlyHint: true } }), /Call .* directly/, name);
  }
  assert.match(block("qcal_evaluate"), /directly/);
  assert.match(block("mcp__docs__search"), /directly/);
  assert.equal(block("mcp__docs__search", { annotations: { readOnlyHint: true } }), undefined);
  assert.match(block("mcp__docs__search", { annotations: { readOnlyHint: true, destructiveHint: true } }), /directly/);
  // An unknown parent is treated as a script; another orchestrator keeps its own rules, except for QDash tools.
  assert.match(block("bash", { parent: undefined }), /directly/);
  assert.equal(block("bash", { parent: "subagent" }), undefined);
  assert.match(block("qdash_create_forum_post", { parent: "subagent" }), /cannot be called/);
});

test("the tool_call hook blocks nested writes, bounds script deadlines, and leaves the model's calls alone", async () => {
  const pi = fakePi();
  const api = installQDashToolPolicy(pi, policy());
  api.registerTool(tool("qdash_list_chips"));
  api.registerTool(tool("qdash_create_forum_post"));
  const script = { type: "tool_call", toolName: "codemode", toolCallId: "c1", input: { code: "text(1)" } };
  assert.equal(await emit(pi, "tool_call", script), undefined);
  assert.equal(script.input.code, `// @options: {"timeout_ms":${DEFAULT_SCRIPT_TIMEOUT_MS}}\ntext(1)`);
  const nested = (toolName, input = {}) => emit(pi, "tool_call", { type: "tool_call", toolName, toolCallId: "c1/1", parentToolCallId: "c1", input });
  assert.equal(await nested("qdash_list_chips"), undefined);
  const write = await nested("qdash_create_forum_post", { confirmWrite: true });
  assert.equal(write.block, true);
  assert.match(write.reason, /write tools then ask the user for approval/);
  assert.equal((await nested("bash", { command: "rm -rf /" })).block, true);
  assert.equal(await emit(pi, "tool_call", { type: "tool_call", toolName: "qdash_create_forum_post", toolCallId: "m1", input: {} }), undefined);
});

test("a script gets an audited read's redacted data, bounded per call", async () => {
  const pi = fakePi();
  const api = installQDashToolPolicy(pi, policy());
  api.registerTool(tool("qdash_list_chips"));
  const result = (details, extra = {}) => emit(pi, "tool_result", {
    type: "tool_result", toolName: "qdash_list_chips", toolCallId: "c1/1", parentToolCallId: "c1",
    input: {}, content: [{ type: "text", text: "boxed summary" }], details, isError: false, ...extra,
  });
  assert.deepEqual(await result({ data: { chips: [{ chip_id: "A", api_token: "[redacted]" }] } }), {
    structuredContent: { chips: [{ chip_id: "A", api_token: "[redacted]" }] },
  });
  const huge = await result({ data: { rows: "x".repeat(MAX_NESTED_DATA_BYTES) } });
  assert.equal(huge.isError, true);
  assert.equal(huge.structuredContent, undefined);
  assert.match(huge.content[0].text, /Narrow the request/);
  // The model's own call, and a failed call, are left as they are.
  assert.equal(await emit(pi, "tool_result", { type: "tool_result", toolName: "qdash_list_chips", toolCallId: "m1", input: {}, content: [], details: { data: 1 }, isError: false }), undefined);
  assert.equal(await result({ data: 1 }, { isError: true }), undefined);
});

test("session start activates tool_search and codemode for a new user, or offers deferred tools directly", async () => {
  const reaching = [{ name: "tool_search", reachesTools: () => "all" }, { name: "codemode", reachesTools: () => "all" }];
  let pi = fakePi({ allTools: reaching, active: ["read"] });
  let api = installQDashToolPolicy(pi, policy());
  api.registerTool(tool("qdash_list_cryostats"));
  await emit(pi, "session_start", { type: "session_start", reason: "startup" });
  assert.deepEqual(pi.state.active, ["read", "tool_search", "codemode"]);

  pi = fakePi({ allTools: reaching, active: ["read"] });
  api = installQDashToolPolicy(pi, policy({ [CODEMODE_ENV]: "off" }));
  api.registerTool(tool("qdash_list_cryostats"));
  await emit(pi, "session_start", { type: "session_start", reason: "startup" });
  assert.deepEqual(pi.state.active, ["read", "tool_search"]);

  // A tool named tool_search that cannot reach tools is not a loader.
  pi = fakePi({ allTools: [{ name: "tool_search" }, { name: "read" }], active: ["read"] });
  api = installQDashToolPolicy(pi, policy());
  api.registerTool(tool("qdash_list_cryostats"));
  await emit(pi, "session_start", { type: "session_start", reason: "startup" });
  assert.deepEqual(pi.registered.map(({ name, exposure }) => [name, exposure]), [
    ["qdash_list_cryostats", "deferred"],
    ["qdash_list_cryostats", "direct"],
  ]);

  // A hidden loader is not activated.
  pi = fakePi({ allTools: reaching.map((t) => ({ ...t, exposure: "hidden" })), active: ["read"] });
  api = installQDashToolPolicy(pi, policy());
  api.registerTool(tool("qdash_list_cryostats"));
  await emit(pi, "session_start", { type: "session_start", reason: "startup" });
  assert.deepEqual(pi.state.active, ["read"]);
});

test("session start keeps a selection the user made: reload, branch records, settings, and a replaced session's handoff", async () => {
  clearHandoffs();
  const reaching = [{ name: "tool_search", reachesTools: () => "all" }, { name: "codemode", reachesTools: () => "all" }];
  const start = async ({ reason = "startup", active = ["read"], settings, branch = [], env, ctx } = {}) => {
    const pi = fakePi({ allTools: reaching, active, settings });
    pi.state.branch.push(...branch);
    const api = installQDashToolPolicy(pi, policy(env));
    api.registerTool(tool("qdash_list_cryostats"));
    await emit(pi, "session_start", { type: "session_start", reason }, ctx ?? pi.ctx);
    return pi;
  };
  // A reload keeps what is active, and offers deferred tools directly when tool_search is off.
  let pi = await start({ reason: "reload" });
  assert.deepEqual(pi.state.active, ["read"]);
  assert.deepEqual(pi.registered.map(({ exposure }) => exposure), ["deferred", "direct"]);

  // pi's own loadout record was restored by pi and is left alone.
  pi = await start({ reason: "fork", branch: [{ type: "message", message: { role: "system", toolsAdded: [{ name: "read" }] } }, { type: "message", message: { role: "system", toolsRemoved: [{ name: "codemode" }], toolsAdded: [{ name: "tool_search" }] } }], active: ["read", "tool_search"] });
  assert.deepEqual(pi.state.active, ["read", "tool_search"]);
  // pi-qdash's later record wins over pi's earlier one.
  pi = await start({ reason: "resume", branch: [{ type: "message", message: { role: "system", toolsAdded: [{ name: "codemode" }] } }, { type: "custom", customType: SELECTION_ENTRY, data: { codemode: false, tool_search: false } }], active: ["read", "codemode"] });
  assert.deepEqual(pi.state.active, ["read"]);

  // defaultTools: "-codemode" opts out; "+codemode" keeps it on even with PI_QDASH_CODEMODE=off.
  pi = await start({ settings: { defaultTools: ["-codemode"] } });
  assert.deepEqual(pi.state.active, ["read", "tool_search"]);
  pi = await start({ settings: { defaultTools: ["+codemode"] }, env: { [CODEMODE_ENV]: "off" } });
  assert.deepEqual(pi.state.active, ["read", "tool_search", "codemode"]);

  // A session the user turned both off in hands its selection to the session that replaces it.
  pi = await start();
  pi.state.active = ["read"];
  await emit(pi, "session_shutdown", { type: "session_shutdown", reason: "new" });
  assert.deepEqual(pi.state.branch.at(-1), { type: "custom", customType: SELECTION_ENTRY, data: { tool_search: false, codemode: false } });
  const next = await start({ reason: "new", ctx: { sessionManager: pi.ctx.sessionManager } });
  assert.deepEqual(next.state.active, ["read"]);
  assert.deepEqual(next.registered.map(({ exposure }) => exposure), ["deferred", "direct"]);
  // The handoff is used once: the session after that is a new user's again.
  assert.deepEqual((await start({ reason: "new" })).state.active, ["read", "tool_search", "codemode"]);
  // A startup or resume never takes a handoff.
  pi.state.active = ["read"];
  await emit(pi, "session_shutdown", { type: "session_shutdown", reason: "new" });
  assert.deepEqual((await start({ reason: "startup" })).state.active, ["read", "tool_search", "codemode"]);
  clearHandoffs();
});

test("a handoff pairs with the session that replaced its own, never with an unrelated one", () => {
  clearHandoffs();
  const off = { codemode: false, tool_search: false };
  const managerA = {};
  const managerB = {};
  // Persisted sessions pair by pi's session file.
  leaveHandoff({ selection: off, reason: "new", targetSessionFile: "/s/new.jsonl", sessionManager: managerA });
  assert.equal(takeHandoff({ reason: "new", sessionFile: "/s/other.jsonl", sessionManager: {} }), undefined);
  assert.deepEqual(takeHandoff({ reason: "new", sessionFile: "/s/new.jsonl", sessionManager: {} }), off);
  // An in-memory fork keeps its session manager.
  leaveHandoff({ selection: off, reason: "fork", targetSessionFile: undefined, sessionManager: managerA });
  assert.equal(takeHandoff({ reason: "fork", sessionFile: undefined, sessionManager: managerB }), undefined);
  assert.deepEqual(takeHandoff({ reason: "fork", sessionFile: undefined, sessionManager: managerA }), off);
  // A sole abandoned handoff cannot override an unrelated runtime's settings.
  leaveHandoff({ selection: { codemode: true, tool_search: true }, reason: "new", targetSessionFile: undefined, sessionManager: managerA });
  assert.equal(takeHandoff({ reason: "new", sessionFile: undefined, sessionManager: managerB }), undefined);
  assert.equal(takeHandoff({ reason: "new", sessionFile: undefined, sessionManager: {} }), undefined);
  // Multiple pending handoffs also require an exact relationship.
  leaveHandoff({ selection: off, reason: "new", targetSessionFile: undefined, sessionManager: managerA });
  leaveHandoff({ selection: off, reason: "new", targetSessionFile: undefined, sessionManager: managerB });
  assert.equal(takeHandoff({ reason: "new", sessionFile: undefined, sessionManager: {} }), undefined);
  assert.equal(takeHandoff({ reason: "new", sessionFile: undefined, sessionManager: {} }), undefined);
  clearHandoffs();
});

test("branch and settings selections read pi's records and modifiers", () => {
  const managed = ["tool_search", "codemode"];
  const { selection, fromPi } = branchSelection([
    { type: "message", message: { role: "system", toolsAdded: [{ name: "codemode" }, { name: "tool_search" }] } },
    { type: "custom", customType: SELECTION_ENTRY, data: { codemode: false, other: true } },
    { type: "custom", customType: "other", data: { tool_search: false } },
  ], managed);
  assert.deepEqual(selection, { codemode: false, tool_search: true });
  assert.deepEqual([...fromPi], ["tool_search"]);
  assert.deepEqual(settingsSelection(["read", "-codemode", "+tool_search", "+codemode"], managed), { codemode: true, tool_search: true });
  assert.deepEqual(settingsSelection(["read", "bash"], managed), {});
  assert.deepEqual(settingsSelection(undefined, managed), {});
});

test("script deadlines and data bounds are shared values", () => {
  assert.equal(withScriptDeadline(`// @options: {"timeout_ms": ${MAX_SCRIPT_TIMEOUT_MS * 2}}\nx`), `// @options: {"timeout_ms":${MAX_SCRIPT_TIMEOUT_MS}}\nx`);
  assert.equal(withScriptDeadline("// @options: {broken\nx"), "// @options: {broken\nx");
  assert.equal(jsonByteLength({ a: "é😀" }), Buffer.byteLength(JSON.stringify({ a: "é😀" })));
  assert.equal(boundScriptData("t", [1, 2]).ok, true);
  assert.deepEqual(scriptDataOf({ content: [{ type: "text", text: "{\"a\":1}" }] }), { a: 1 });
  assert.equal(scriptDataOf({ content: [{ type: "text", text: "plain" }] }), "plain");
});


test("nested descendants retain codemode restrictions and replacement names are not trusted", async () => {
  const pi = fakePi({ foreign: [tool("qdash_list_chips")] });
  const api = installQDashToolPolicy(pi, policy());
  for (const name of ["qdash_list_chips", "qdash_list_chip_qubits", "qdash_get_task_result"]) api.registerTool(tool(name));
  await emit(pi, "tool_call", {toolName: "codemode", toolCallId: "root", input: {code: "text(1)"}});
  for (const toolName of ["bash", "write", "qcal_evaluate", "unknown", "qdash_list_chips"]) {
    for (const parentToolCallId of ["root", "root/1", "root/1/2"]) {
      const result = await emit(pi, "tool_call", {toolName, toolCallId: `${parentToolCallId}/3`, parentToolCallId, input: {}});
      assert.equal(result?.block, true, `${toolName} under ${parentToolCallId}`);
    }
  }
  // pi-qdash's own audited read, at any depth, still runs.
  for (const parentToolCallId of ["root", "root/1", "root/1/2"]) {
    assert.equal(await emit(pi, "tool_call", {toolName: "qdash_list_chip_qubits", toolCallId: `${parentToolCallId}/4`, parentToolCallId, input: {}}), undefined);
  }
});

/** Script access of each audited read under a codemode script, as the hooks decide it. */
async function scriptAccess(pi, names) {
  await emit(pi, "tool_call", { toolName: "codemode", toolCallId: "root", input: { code: "text(1)" } });
  const access = {};
  for (const name of names) {
    const result = await emit(pi, "tool_call", { toolName: name, toolCallId: `root/${name}`, parentToolCallId: "root", input: {} });
    access[name] = result?.block ? "blocked" : "allowed";
  }
  return access;
}

test("an extension that replaces most or one of pi-qdash's audited names gets no script access to them", async () => {
  const names = ["qdash_list_chips", "qdash_list_chip_qubits", "qdash_get_task_result", "qdash_list_cryostats"];
  for (const name of names) assert.ok(NESTED_READ_TOOL_NAMES.includes(name), name);
  for (const replaced of [names.slice(0, -1), names.slice(0, 1), names]) {
    // The foreign extension even declares read-only annotations and reuses the same schema shape.
    const pi = fakePi({ foreign: replaced.map((name) => tool(name, { annotations: { readOnlyHint: true } })) });
    const api = installQDashToolPolicy(pi, policy());
    for (const name of names) api.registerTool(tool(name));
    const access = await scriptAccess(pi, names);
    for (const name of names) assert.equal(access[name], replaced.includes(name) ? "blocked" : "allowed", `${name} with ${replaced.join()} replaced`);
    // Its results are not reshaped as pi-qdash's script data either.
    const result = await emit(pi, "tool_result", { toolName: replaced[0], toolCallId: "root/x", parentToolCallId: "root", input: {}, content: [], details: { data: 1 }, isError: false });
    assert.equal(result, undefined);
  }
});

test("a foreign extension at the same name with pi-qdash's parameters object, or pi-qdash's path with another object, is not pi-qdash", async () => {
  const pi = fakePi();
  const api = installQDashToolPolicy(pi, policy());
  const own = tool("qdash_list_chips");
  api.registerTool(own);
  api.registerTool(tool("qdash_list_qubits"));
  // Reused parameters object, but registered by another file.
  pi.state.foreign = [{ ...own, sourceInfo: FOREIGN_SOURCE }, { ...tool("qdash_list_qubits"), sourceInfo: OWN_SOURCE }];
  assert.deepEqual(await scriptAccess(pi, ["qdash_list_chips", "qdash_list_qubits"]), { qdash_list_chips: "blocked", qdash_list_qubits: "blocked" });
});

test("without pi's registry or source metadata, scripts reach no QDash tool", async () => {
  const cases = {
    "no registry": (pi) => { delete pi.getAllTools; },
    "empty registry": (pi) => { pi.state.all = []; },
    "registry throws": (pi) => { pi.getAllTools = () => { throw new Error("x"); }; },
    "no source info": (pi) => { pi.state.all = pi.registered.map((d) => ({ ...d })); },
    "synthetic source": (pi) => { pi.state.all = pi.registered.map((d) => ({ ...d, sourceInfo: { path: "<inline>" } })); },
    "relative path without baseDir": (pi) => { pi.state.all = pi.registered.map((d) => ({ ...d, sourceInfo: { path: "extensions/qdash.ts" } })); },
    "missing file": (pi) => { pi.state.all = pi.registered.map((d) => ({ ...d, sourceInfo: { path: join(ENTRY_DIR, "gone.ts") } })); },
  };
  for (const [label, mutate] of Object.entries(cases)) {
    const pi = fakePi();
    const api = installQDashToolPolicy(pi, policy());
    api.registerTool(tool("qdash_list_chips"));
    mutate(pi);
    assert.deepEqual(await scriptAccess(pi, ["qdash_list_chips"]), { qdash_list_chips: "blocked" }, label);
  }
  // No entry: nothing is pi-qdash's own, even with a complete registry.
  for (const entry of [undefined, "relative/qdash.ts", "file:///does/not/exist.ts"]) {
    const pi = fakePi();
    const api = installQDashToolPolicy(pi, { entry, env: {} });
    api.registerTool(tool("qdash_list_chips"));
    assert.deepEqual(await scriptAccess(pi, ["qdash_list_chips"]), { qdash_list_chips: "blocked" }, String(entry));
  }
});

test("pi-qdash's entry is recognized through symlinks, relative paths with baseDir, and file URLs", () => {
  const link = join(ENTRY_DIR, "linked");
  symlinkSync(join(ENTRY_DIR, "extensions"), link);
  const check = createOwnershipCheck(pathToFileURL(ENTRY));
  assert.equal(check.resolved, true);
  const parameters = {};
  const owns = (sourceInfo) => check.owns({ name: "qdash_list_chips", parameters, sourceInfo }, parameters);
  assert.equal(owns({ path: join(link, "qdash.ts") }), true);
  assert.equal(owns({ path: pathToFileURL(join(link, "qdash.ts")).href }), true);
  assert.equal(owns({ path: relative(process.cwd(), ENTRY) || "qdash.ts", baseDir: join(ENTRY_DIR, "extensions") }), true);
  assert.equal(owns({ path: join(ENTRY_DIR, "extensions", ".", "qdash.ts") }), true);
  assert.equal(owns({ path: FOREIGN }), false);
  assert.equal(owns({ path: "builtin:qdash" }), false);
  assert.equal(check.owns({ name: "qdash_list_chips", parameters: {}, sourceInfo: OWN_SOURCE }, parameters), false);
  assert.equal(check.owns(undefined, parameters), false);
  assert.equal(sourceFileKey({ path: "<sdk:qdash_list_chips>" }), undefined);
});

test("the extension itself passes its entry, so its loaded tools keep script access", async () => {
  const entry = new URL("../.test-dist/qdash.js", import.meta.url);
  const pi = fakePi({ own: { path: entry.pathname } });
  qdashExtension(pi);
  assert.deepEqual(await scriptAccess(pi, ["qdash_list_chips"]), { qdash_list_chips: "allowed" });
});

test("a top-level call id reused after its call finished, or in a new session, does not keep its old parent", async () => {
  const pi = fakePi();
  installQDashToolPolicy(pi, policy());
  const nestedBash = () => emit(pi, "tool_call", { toolName: "bash", toolCallId: "c1/1", parentToolCallId: "c1", input: {} });
  // A script c1 that never reported its result, then a new session where another orchestrator uses c1.
  await emit(pi, "tool_call", { toolName: "codemode", toolCallId: "c1", input: { code: "x" } });
  await emit(pi, "session_start", { type: "session_start", reason: "new" });
  await emit(pi, "tool_call", { toolName: "subagent", toolCallId: "c1", input: {} });
  assert.equal(await nestedBash(), undefined);
  // And the other way round within one session, after c1 finished.
  await emit(pi, "tool_result", { toolName: "subagent", toolCallId: "c1", input: {}, content: [], isError: false });
  await emit(pi, "tool_call", { toolName: "codemode", toolCallId: "c1", input: { code: "x" } });
  assert.equal((await nestedBash())?.block, true);
});
