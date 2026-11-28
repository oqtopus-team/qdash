/**
 * Reviewed QDash writes are approved by the host, never by an argument the
 * model sets: the pi CLI write gate's dialog, a host's own approval UI passed
 * in the extension context, or the tool's own dialog. A `confirmWrite` value
 * in the call, of any type, approves nothing, in the hook and when a handler
 * is invoked directly.
 */

import assert from "node:assert/strict";
import { after, before, test } from "node:test";

import { REVIEWED_WRITE_TOOL_NAMES, SESSION_GRANTED_WRITE_TOOL_NAMES } from "../.test-dist/lib/tool-policy.js";
import {
  cancelledApprovalMessage,
  canonicalArgs,
  changedArgsMessage,
  hasGateApproval,
  HOST_WRITE_APPROVAL_KEY,
  noApprovalMessage,
  requireWriteApproval,
  recordGateApproval,
  unserializableArgsMessage,
} from "../.test-dist/lib/write-approval.js";
import qdashExtension from "../.test-dist/qdash.js";
import { gateDialogMessage } from "../.test-dist/lib/write-gate.js";
import { startFakeAgentQDash } from "./helpers/fake-agent-qdash.mjs";

const FORGED = [true, "true", "yes", 1, { approved: true }];

test("cancellation refuses gate and host approval and consumes the gate record", async () => {
  const controller = new AbortController();
  const name = "qdash_execute_flow";
  const params = { name: "flow" };
  recordGateApproval("cancelled-gate", name, canonicalArgs(params));
  controller.abort();
  await assert.rejects(requireWriteApproval(name, "cancelled-gate", params, { signal: controller.signal }, { title: "t", message: "m" }), /turn was cancelled/);
  assert.equal(hasGateApproval("cancelled-gate"), false);
  await assert.rejects(requireWriteApproval(name, "cancelled-host", params, { signal: controller.signal, [HOST_WRITE_APPROVAL_KEY]: { toolCallId: "cancelled-host", toolName: name } }, { title: "t", message: "m" }), /turn was cancelled/);
});

test("approval dialog discloses arguments after a long parameter", () => {
  const args = { parameters: { a: "x".repeat(7000), z_target: "important-target" } };
  const message = gateDialogMessage("qdash_execute_flow", canonicalArgs(args));
  assert.ok(message.includes(JSON.stringify(args, null, 2)));
  assert.ok(message.includes("important-target"));
});

let fake;
const saved = {};
before(async () => {
  fake = await startFakeAgentQDash();
  for (const name of ["QDASH_BASE_URL", "QDASH_API_TOKEN"]) saved[name] = process.env[name];
  process.env.QDASH_BASE_URL = fake.baseUrl;
  process.env.QDASH_API_TOKEN = "fixture-token";
});
after(async () => {
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  await fake.close();
});

/** pi with the parts pi-qdash uses at load, recording tools and handlers. */
function loadPi() {
  const tools = new Map();
  const handlers = new Map();
  const pi = {
    registerTool: (definition) => tools.set(definition.name, definition),
    registerCommand() {},
    registerShortcut() {},
    registerFlag() {},
    getFlag() {},
    appendEntry() {},
    sendMessage() {},
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    getAllTools: () => [...tools.values()].map((definition) => ({ ...definition, sourceInfo: { path: "x", source: "local", scope: "temporary", origin: "top-level" } })),
    getActiveTools: () => [...tools.keys()],
    setActiveTools() {},
    getSettings: () => ({}),
  };
  qdashExtension(pi);
  const toolCall = async (event, ctx) => {
    let last;
    for (const handler of handlers.get("tool_call") ?? []) {
      const result = await handler({ type: "tool_call", ...event }, ctx);
      if (result !== undefined) last = result;
    }
    return last;
  };
  const emit = async (event, payload) => {
    for (const handler of handlers.get(event) ?? []) await handler({ type: event, ...payload }, noUi());
  };
  return { tools, toolCall, emit };
}

const noUi = () => ({ hasUI: false, sessionManager: { getBranch: () => [], getSessionFile: () => undefined } });
const withUi = (answer, asked = []) => ({
  ...noUi(),
  hasUI: true,
  ui: { async confirm(title) { asked.push(title); return answer; }, notify() {}, setStatus() {}, setWidget() {} },
});

test("no reviewed write offers confirmWrite or tells the model to set it", () => {
  const { tools } = loadPi();
  for (const name of [...REVIEWED_WRITE_TOOL_NAMES, ...SESSION_GRANTED_WRITE_TOOL_NAMES]) {
    const tool = tools.get(name);
    assert.ok(tool, name);
    assert.equal("confirmWrite" in (tool.parameters.properties ?? {}), false, name);
    const text = [tool.description, tool.promptSnippet, ...(tool.promptGuidelines ?? [])].join("\n");
    assert.doesNotMatch(text, /set confirmWrite|confirmWrite: true/i, name);
  }
});

test("the write gate ignores a model's confirmWrite: without a UI it refuses, with one it always asks", async () => {
  const { toolCall } = loadPi();
  for (const name of REVIEWED_WRITE_TOOL_NAMES) {
    // A pipeline run names exactly one source; a spec keeps the call well formed.
    const base = name === "qdash_run_pipeline" ? { spec: {} } : {};
    for (const confirmWrite of FORGED) {
      const refused = await toolCall({ toolName: name, toolCallId: `m-${name}`, input: { ...base, confirmWrite } }, noUi());
      assert.deepEqual(refused, { block: true, reason: noApprovalMessage(name) }, name);
    }
    const asked = [];
    const declined = await toolCall({ toolName: name, toolCallId: `d-${name}`, input: { ...base, confirmWrite: true } }, withUi(false, asked));
    assert.deepEqual(declined, { block: true, reason: "QDash write operation rejected by user" }, name);
    assert.equal(asked.length, 1, name);
  }
  // A script's call is refused before any dialog.
  const asked = [];
  const nested = await toolCall({ toolName: "qdash_commit_agent_candidate", toolCallId: "c1/1", parentToolCallId: "c1", input: { confirmWrite: true } }, withUi(true, asked));
  assert.equal(nested.block, true);
  assert.equal(asked.length, 0);
  // Session-granted tools ask nothing.
  for (const name of SESSION_GRANTED_WRITE_TOOL_NAMES) {
    assert.equal(await toolCall({ toolName: name, toolCallId: `s-${name}`, input: {} }, noUi()), undefined, name);
  }
});

const COMMIT = { sessionId: "missing", actionId: "a-1", parameterName: "qubit_frequency", taskId: "t-1", expectedStateVersion: 1 };
const APPLY = { sessionId: "missing", commitId: "c-1", expectedStateVersion: 1 };

test("reviewed commit and apply handlers called directly refuse a forged confirmWrite and send nothing", async () => {
  const { tools } = loadPi();
  const before = fake.state.requests.length;
  for (const [name, params] of [["qdash_commit_agent_candidate", COMMIT], ["qdash_apply_agent_candidate_commit", APPLY]]) {
    for (const confirmWrite of FORGED) {
      await assert.rejects(
        tools.get(name).execute("call-1", { ...params, confirmWrite }, undefined, undefined, noUi()),
        /requires explicit confirmation/,
        `${name} ${JSON.stringify(confirmWrite)}`,
      );
    }
    // The tool's own dialog still decides when the host has a UI.
    const asked = [];
    await assert.rejects(tools.get(name).execute("call-2", { ...params, confirmWrite: true }, undefined, undefined, withUi(false, asked)), /requires explicit confirmation/);
    assert.equal(asked.length, 1, name);
    // A host approval names one call; another call is not approved by it.
    const other = { ...noUi(), [HOST_WRITE_APPROVAL_KEY]: { toolCallId: "call-approved", toolName: name } };
    await assert.rejects(tools.get(name).execute("call-3", { ...params }, undefined, undefined, other), /requires explicit confirmation/);
  }
  assert.equal(fake.state.requests.length, before);
});

test("an approval the gate or the host collected lets exactly that call reach QDash", async () => {
  const { tools, toolCall } = loadPi();
  for (const [name, params] of [["qdash_commit_agent_candidate", COMMIT], ["qdash_apply_agent_candidate_commit", APPLY]]) {
    // The pi CLI gate approves the call id, tool, and the arguments its dialog showed.
    const input = { ...params };
    const asked = [];
    assert.equal(await toolCall({ toolName: name, toolCallId: `gate-${name}`, input }, withUi(true, asked)), undefined);
    const before = fake.state.requests.length;
    // The fake has no such session: reaching QDash is what shows the call was approved.
    // The tool asks nothing itself: exactly one dialog for the call.
    await assert.rejects(tools.get(name).execute(`gate-${name}`, input, undefined, undefined, withUi(true, asked)), (error) => !/requires explicit confirmation|not run/.test(String(error)));
    assert.ok(fake.state.requests.length > before, name);
    assert.equal(asked.length, 1, name);
    // The approval is spent: the same call id again needs a new approval.
    await assert.rejects(tools.get(name).execute(`gate-${name}`, input, undefined, undefined, noUi()), /requires explicit confirmation/);
    // A different value under the same call id is not what the user approved.
    assert.equal(await toolCall({ toolName: name, toolCallId: `swap-${name}`, input: { ...params } }, withUi(true)), undefined);
    const sent = fake.state.requests.length;
    await assert.rejects(tools.get(name).execute(`swap-${name}`, { ...params, expectedStateVersion: 2 }, undefined, undefined, noUi()), /arguments changed after the user saw them/);
    assert.equal(hasGateApproval(`swap-${name}`), false);

    // A host's own approval UI (the QDash Agent's approval card) names the call and tool in the context.
    const host = { ...noUi(), [HOST_WRITE_APPROVAL_KEY]: { toolCallId: `host-${name}`, toolName: name } };
    await assert.rejects(tools.get(name).execute(`host-${name}`, { ...params }, undefined, undefined, host), (error) => !/requires explicit confirmation/.test(String(error)));
    assert.ok(fake.state.requests.length > sent, name);
    // The same host approval does not cover another tool.
    const otherTool = { ...noUi(), [HOST_WRITE_APPROVAL_KEY]: { toolCallId: `host-${name}`, toolName: "qdash_save_flow" } };
    const stillSent = fake.state.requests.length;
    await assert.rejects(tools.get(name).execute(`host-${name}`, { ...params }, undefined, undefined, otherTool), /requires explicit confirmation/);
    assert.equal(fake.state.requests.length, stillSent, name);
  }
});

const COMMIT_NESTED = { ...COMMIT, candidate: { value: 7.45, unit: "GHz", tags: ["a"] } };

test("a gate approval covers the arguments' value, not their key order, and refuses any nested change", async () => {
  const name = "qdash_commit_agent_candidate";
  const { tools, toolCall } = loadPi();
  // Rebuilt with the same value in another key order: still the approved call.
  const input = structuredClone(COMMIT_NESTED);
  assert.equal(await toolCall({ toolName: name, toolCallId: "order", input }, withUi(true)), undefined);
  const reordered = Object.fromEntries(Object.entries(structuredClone(COMMIT_NESTED)).reverse());
  reordered.candidate = { tags: ["a"], unit: "GHz", value: 7.45 };
  const before = fake.state.requests.length;
  await assert.rejects(tools.get(name).execute("order", reordered, undefined, undefined, noUi()), (error) => !/not run|requires explicit confirmation/.test(String(error)));
  assert.ok(fake.state.requests.length > before);

  // A nested change after the approval, in place, as a later tool_call hook may make.
  for (const mutate of [(args) => args.candidate.tags.push("b"), (args) => { args.candidate.value = 8; }, (args) => { args.extra = { x: 1 }; }]) {
    const changed = structuredClone(COMMIT_NESTED);
    assert.equal(await toolCall({ toolName: name, toolCallId: "nested", input: changed }, withUi(true)), undefined);
    mutate(changed);
    const sent = fake.state.requests.length;
    await assert.rejects(tools.get(name).execute("nested", changed, undefined, undefined, withUi(true)), /arguments changed after the user saw them/);
    assert.equal(fake.state.requests.length, sent);
    assert.equal(hasGateApproval("nested"), false);
  }
});

test("the gate approves the arguments its dialog showed, never ones changed while it was open", async () => {
  const name = "qdash_create_agent_session";
  const { toolCall } = loadPi();
  const input = { chipId: "chip-001", policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto" } };
  const shown = [];
  const ctx = {
    ...noUi(),
    hasUI: true,
    ui: {
      async confirm(_title, message) {
        shown.push(message);
        input.policy.qids.push("Q01");
        return true;
      },
    },
  };
  const result = await toolCall({ toolName: name, toolCallId: "during", input }, ctx);
  assert.deepEqual(result, { block: true, reason: changedArgsMessage(name) });
  assert.equal(hasGateApproval("during"), false);
  // The dialog showed the session grant and the exact arguments of the snapshot.
  assert.match(shown[0], /Create an agent session on chip chip-001:/);
  assert.match(shown[0], /- steps: run without asking/);
  assert.match(shown[0], /"qids": \[\n\s+"Q00"\n\s+\]/);
  assert.doesNotMatch(shown[0], /Q01/);
});

const GRANT_POLICY = {
  qids: ["Q00"],
  allowed_tasks: ["CheckChevron", "CheckRabi"],
  autonomy: "auto",
  max_actions: 4,
  parameter_updates: { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], apply_backend: false },
};

test("the session dialog shows the update grant, and the approved policy reaches QDash unchanged", async () => {
  const name = "qdash_create_agent_session";
  const { tools, toolCall } = loadPi();
  const input = { chipId: "chip-001", policy: structuredClone(GRANT_POLICY) };
  const shown = [];
  const ctx = { ...noUi(), hasUI: true, ui: { async confirm(_title, message) { shown.push(message); return true; } } };
  assert.equal(await toolCall({ toolName: name, toolCallId: "grant", input }, ctx), undefined);
  assert.match(shown[0], /- Parameter updates: granted for qubit_frequency from CheckChevron after a pass assessment and QDash's gates; backend apply not granted/);
  assert.match(shown[0], /- numeric bounds and quality gates: none; no task input is overridden/);
  assert.doesNotMatch(shown[0], /- bounds \(overrides and candidate gate\)|- quality gates/);
  // A grant without bounds says the task's own checks decide; no number is shown for it.
  assert.match(shown[0], /- Update criteria: qubit_frequency no numeric bounds \(its task's own checks decide\)/);
  const before = fake.state.requests.length;
  await tools.get(name).execute("grant", input, undefined, undefined, ctx);
  const posted = fake.state.requests.slice(before).find((request) => request.method === "POST" && request.path.endsWith("/agent-sessions"));
  assert.ok(posted, "the session was created");
  assert.deepEqual(posted.body.policy, { ...GRANT_POLICY, evaluation: "off" });
  assert.equal(shown.length, 1);
});

test("a malformed session policy fails before any dialog or QDash call", async () => {
  const name = "qdash_create_agent_session";
  const { tools } = loadPi();
  for (const parameterUpdates of [
    [{ parameter: "qubit_frequency", task: "CheckChevron" }],
    ["qubit_frequency"],
    { parameters: ["qubit_frequency"] },
    { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], apply_backend: "yes" },
  ]) {
    const input = { chipId: "chip-001", policy: { ...structuredClone(GRANT_POLICY), parameter_updates: parameterUpdates } };
    const asked = [];
    const before = fake.state.requests.length;
    await assert.rejects(
      tools.get(name).execute("malformed", input, undefined, undefined, withUi(true, asked)),
      /Invalid agent session policy; no session was created:\n- policy\.parameter_updates/,
    );
    assert.deepEqual(asked, [], JSON.stringify(parameterUpdates));
    assert.equal(fake.state.requests.length, before, JSON.stringify(parameterUpdates));
  }
});

test("numeric bounds and quality gates the model sends are refused before the dialog or any QDash call, whatever source they claim", async () => {
  const name = "qdash_create_agent_session";
  const { tools, toolCall } = loadPi();
  const forged = [
    // What the reported session needed to commit the incidental amplitude: a model-written window.
    [{ allowed_overrides: { control_amplitude: { minimum: 0.005, maximum: 0.01 } } }, /- policy\.allowed_overrides: not accepted from this tool/],
    [{ allowed_overrides: { qubit_frequency: { minimum: 8.22, maximum: 8.32 } } }, /- policy\.allowed_overrides: not accepted from this tool/],
    // An empty field and a claimed source are refused too: no argument proves who wrote a number.
    [{ allowed_overrides: {} }, /- policy\.allowed_overrides: not accepted from this tool/],
    [{ allowed_overrides: { control_amplitude: { minimum: 0.005, source: "user" } } }, /- policy\.allowed_overrides: not accepted from this tool/],
    [{ bounds_source: "user_stated", allowed_overrides: { qubit_frequency: { maximum: 8.3 } } }, /- policy\.allowed_overrides: not accepted from this tool/],
    [{ bounds_source: "user_stated" }, /- policy: must not have additional properties/],
    [{ task_quality_gates: { CheckChevron: { r2: { minimum: 0.9 } } } }, /- policy\.task_quality_gates: not accepted from this tool/],
    [{ quality_gates: { r2: { minimum: 0.9 } } }, /- policy\.quality_gates: not accepted from this tool/],
    [{ parameter_updates: { parameters: ["qubit_frequency"], tasks: ["CheckRamsey"] } }, /- policy\.parameter_updates\.tasks: CheckRamsey must also be in allowed_tasks/],
  ];
  for (const [fields, problem] of forged) {
    const input = { chipId: "chip-001", policy: { ...structuredClone(GRANT_POLICY), ...fields } };
    const asked = [];
    const before = fake.state.requests.length;
    const blocked = await toolCall({ toolName: name, toolCallId: "forged", input }, withUi(true, asked));
    assert.equal(blocked?.block, true, JSON.stringify(fields));
    assert.match(blocked.reason, /Invalid agent session policy; no session was created/);
    assert.match(blocked.reason, problem);
    await assert.rejects(tools.get(name).execute("forged", input, undefined, undefined, withUi(true, asked)), problem);
    assert.deepEqual(asked, [], JSON.stringify(fields));
    assert.equal(fake.state.requests.length, before, JSON.stringify(fields));
  }
  const offered = tools.get(name).parameters.properties.policy.properties;
  for (const field of ["allowed_overrides", "task_quality_gates", "quality_gates"]) assert.equal(offered[field], undefined, field);
});

test("session creation refuses missing or changed evaluation authority from the server", async () => {
  const originalFetch = globalThis.fetch;
  const { tools } = loadPi();
  try {
    for (const [requested, returned] of [["required", undefined], ["required", "off"], [undefined, undefined], ["off", "required"], ["required", "required"], [undefined, "off"]]) {
      globalThis.fetch = async (...args) => {
        const response = await originalFetch(...args);
        const init = args[1];
        const method = args[0] instanceof Request ? args[0].method : init?.method;
        const url = args[0] instanceof Request ? args[0].url : String(args[0]);
        if (method?.toUpperCase() === "POST" && url.endsWith("/agent-sessions")) {
          const body = await response.json();
          if (returned === undefined) delete body.policy.evaluation;
          else body.policy.evaluation = returned;
          return new Response(JSON.stringify(body), { status: response.status, headers: response.headers });
        }
        return response;
      };
      const policy = structuredClone(GRANT_POLICY);
      if (requested !== undefined) policy.evaluation = requested;
      const call = tools.get("qdash_create_agent_session").execute("evaluation-contract", { chipId: "chip-001", policy }, undefined, undefined, withUi(true));
      if (returned !== (requested ?? "off")) await assert.rejects(call, /without the approved evaluation mode/);
      else await call;
      const posted = fake.state.requests.filter((r) => r.method === "POST" && r.path.endsWith("/agent-sessions")).at(-1);
      assert.equal(posted.body.policy.evaluation, requested ?? "off");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("arguments that are not plain JSON data are refused without a dialog", async () => {
  const { toolCall } = loadPi();
  const cyclic = { sessionId: "s" };
  cyclic.self = cyclic;
  const accessor = Object.defineProperty({}, "sessionId", { get: () => "s", enumerable: true });
  for (const input of [cyclic, accessor, { when: new Date(0) }, { n: Number.NaN }, { f() {} }, { big: 1n }]) {
    const asked = [];
    const result = await toolCall({ toolName: "qdash_commit_agent_candidate", toolCallId: "bad", input }, withUi(true, asked));
    assert.deepEqual(result, { block: true, reason: unserializableArgsMessage("qdash_commit_agent_candidate") });
    assert.equal(asked.length, 0);
  }
  await assert.rejects(requireWriteApproval("qdash_save_flow", "x", { when: new Date(0) }, withUi(true), { title: "t", message: "m" }), /not plain JSON data/);
  assert.equal(canonicalArgs({ b: 1, a: { d: [1, { f: null, e: "x" }], c: undefined } }), '{"a":{"d":[1,{"e":"x","f":null}]},"b":1}');
  assert.equal(canonicalArgs([1, , 3]), undefined);
  assert.equal(canonicalArgs({ [Symbol("s")]: 1 }), undefined);
});

test("an abort before, during, or after the gate's dialog leaves no approval", async () => {
  const name = "qdash_commit_agent_candidate";
  const { tools, toolCall, emit } = loadPi();
  // Before the hook: no dialog at all.
  const aborted = new AbortController();
  aborted.abort();
  const asked = [];
  assert.deepEqual(await toolCall({ toolName: name, toolCallId: "pre", input: { ...COMMIT } }, { ...withUi(true, asked), signal: aborted.signal }), { block: true, reason: cancelledApprovalMessage(name) });
  assert.equal(asked.length, 0);
  // During the dialog: the dialog gets pi's signal; an accept after the abort approves nothing.
  const during = new AbortController();
  const seen = [];
  const ctx = { ...noUi(), hasUI: true, signal: during.signal, ui: { async confirm(_t, _m, opts) { seen.push(opts?.signal); during.abort(); return true; } } };
  assert.deepEqual(await toolCall({ toolName: name, toolCallId: "mid", input: { ...COMMIT } }, ctx), { block: true, reason: cancelledApprovalMessage(name) });
  assert.equal(seen[0], during.signal);
  assert.equal(hasGateApproval("mid"), false);
  // After the gate approved, before the tool ran: pi ends the skipped call with tool_execution_end.
  assert.equal(await toolCall({ toolName: name, toolCallId: "post", input: { ...COMMIT } }, withUi(true)), undefined);
  assert.equal(hasGateApproval("post"), true);
  await emit("tool_execution_end", { toolCallId: "post", toolName: name, result: {}, isError: true });
  assert.equal(hasGateApproval("post"), false);
  const before = fake.state.requests.length;
  await assert.rejects(tools.get(name).execute("post", { ...COMMIT }, undefined, undefined, noUi()), /requires explicit confirmation/);
  assert.equal(fake.state.requests.length, before);
});

test("no gate approval outlives its turn, agent run, or session", async () => {
  const { toolCall, emit } = loadPi();
  for (const event of ["turn_end", "agent_end", "session_shutdown"]) {
    assert.equal(await toolCall({ toolName: "qdash_commit_agent_candidate", toolCallId: `life-${event}`, input: { ...COMMIT } }, withUi(true)), undefined);
    assert.equal(hasGateApproval(`life-${event}`), true);
    await emit(event, {});
    assert.equal(hasGateApproval(`life-${event}`), false, event);
  }
  // A new tool_call with an approved id first voids the earlier approval, even when it is then refused.
  assert.equal(await toolCall({ toolName: "qdash_commit_agent_candidate", toolCallId: "again", input: { ...COMMIT } }, withUi(true)), undefined);
  await toolCall({ toolName: "qdash_commit_agent_candidate", toolCallId: "again", input: { ...COMMIT } }, withUi(false));
  assert.equal(hasGateApproval("again"), false);
});

test("another tool cannot use an approval granted for one tool's call id and arguments", async () => {
  const { tools, toolCall } = loadPi();
  const args = { ...APPLY };
  assert.equal(await toolCall({ toolName: "qdash_commit_agent_candidate", toolCallId: "shared", input: args }, withUi(true)), undefined);
  const before = fake.state.requests.length;
  await assert.rejects(tools.get("qdash_apply_agent_candidate_commit").execute("shared", args, undefined, undefined, noUi()), /arguments changed after the user saw them|not run/);
  assert.equal(fake.state.requests.length, before);
  assert.equal(hasGateApproval("shared"), false);
});

test("the tool's own dialog never approves arguments changed or a turn aborted while it was open", async () => {
  const params = { name: "flow", parameters: { qids: ["Q00"] } };
  const mutating = { hasUI: true, ui: { async confirm() { params.parameters.qids.push("Q01"); return true; } } };
  await assert.rejects(requireWriteApproval("qdash_execute_flow", "own-1", params, mutating, { title: "t", message: "m" }), /arguments changed after the user saw them/);
  const controller = new AbortController();
  const aborting = { hasUI: true, signal: controller.signal, ui: { async confirm(_t, _m, opts) { assert.equal(opts.signal, controller.signal); controller.abort(); return true; } } };
  await assert.rejects(requireWriteApproval("qdash_execute_flow", "own-2", { name: "flow" }, aborting, { title: "t", message: "m" }), /turn was cancelled/);
  const asked = [];
  await assert.rejects(requireWriteApproval("qdash_execute_flow", "own-3", { name: "flow" }, { ...withUi(true, asked), signal: controller.signal }, { title: "t", message: "m" }), /turn was cancelled/);
  assert.equal(asked.length, 0);
});

test("requireWriteApproval refuses without a UI and asks with the tool's dialog otherwise", async () => {
  await assert.rejects(requireWriteApproval("qdash_save_flow", "x", {}, undefined, { title: "t", message: "m" }), /requires explicit confirmation/);
  await assert.rejects(requireWriteApproval("qdash_save_flow", "x", { confirmWrite: true }, { hasUI: false }, { title: "t", message: "m" }), /no UI to ask in/);
  const asked = [];
  await requireWriteApproval("qdash_save_flow", "x", {}, withUi(true, asked), { title: "Save?", message: "m" });
  assert.deepEqual(asked, ["Save?"]);
});
