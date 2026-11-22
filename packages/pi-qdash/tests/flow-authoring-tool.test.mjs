import assert from "node:assert/strict";
import test from "node:test";

import { flowCodeProblems, formatFlowExecution, registerFlowAuthoringTools } from "../.test-dist/tools/flow-authoring.js";

const CODE = [
  "from prefect import flow",
  "",
  "@flow",
  "def my_check(qids: list[str]):",
  "    return qids",
  "",
].join("\n");

function registeredTools(saveFlow, chipId = "64Qv3", executeFlow = async () => { throw new Error("must not be called"); }, projectId = "project-1", pausedSessions = []) {
  const tools = new Map();
  const calls = [];
  const sessionQueries = [];
  registerFlowAuthoringTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() {
      return {
        // null stands for a profile without a project.
        config: { projectId: projectId ?? undefined },
        async saveFlow(request) { calls.push(request); return saveFlow(request); },
        async executeFlow(name, parameters) { calls.push({ execute: name, parameters }); return executeFlow(name, parameters); },
        // The pause guard: the user's agent sessions waiting for an expert.
        async listAgentSessions(options) { sessionQueries.push(options); return typeof pausedSessions === "function" ? pausedSessions() : pausedSessions; },
        // A tool that starts a run must not follow it.
        async getExecution() { calls.push("getExecution"); throw new Error("must not wait"); },
        async waitForExecution() { calls.push("waitForExecution"); throw new Error("must not wait"); },
      };
    },
    async resolveChipId(_client, explicit) { return explicit ?? chipId; },
    flowPageUrl: (_client, name) => `https://qdash.example/workflow/${name}`,
  });
  return { tools, tool: tools.get("qdash_save_flow"), run: tools.get("qdash_execute_flow"), calls, sessionQueries };
}

// A host that collected the user's approval of call `toolCallId` in its own UI (write-approval.ts).
const approved = (toolCallId, toolName = "qdash_execute_flow") => ({ hasUI: false, qdashWriteApproval: { toolCallId, toolName } });
const uiContext = (answer) => ({ hasUI: true, ui: { async confirm() { return answer; } } });

test("code that QDash would reject is reported before anyone is asked to approve it", () => {
  assert.deepEqual(flowCodeProblems("my_check", CODE, "my_check"), []);
  assert.deepEqual(flowCodeProblems("my_check", CODE, "other"), ["the code defines no function named 'other'"]);
  const problems = flowCodeProblems("1bad", "def x():\n    pass\n", "x");
  assert.equal(problems.length, 3);
  assert.match(problems[0], /name '1bad'/);
  assert.match(problems[1], /@flow/);
  assert.match(problems[2], /import prefect/);
});

test("a save sends QDash's request shape and reports the registered flow", async () => {
  const { tool, calls } = registeredTools(async (request) => ({
    name: request.name,
    file_path: `/app/qdash/workflow/user_flows/p1/${request.name}.py`,
    message: `Flow '${request.name}' created successfully`,
  }));
  const result = await tool.execute("t", { name: "my_check", code: CODE, description: "T1 sweep", tags: ["check"] }, undefined, undefined, uiContext(true));

  assert.deepEqual(calls, [{
    name: "my_check",
    description: "T1 sweep",
    code: CODE,
    flow_function_name: "my_check",
    chip_id: "64Qv3",
    default_parameters: {},
    default_run_parameters: {},
    tags: ["check"],
  }]);
  assert.equal(result.details.saved, true);
  assert.equal(result.details.flowName, "my_check");
  const text = result.content[0].text;
  assert.match(text, /created successfully \(chip 64Qv3\)/);
  assert.match(text, /Page: https:\/\/qdash.example\/workflow\/my_check/);
  assert.match(text, /Saving did not run it/);
});

test("running a saved flow is confirmation-gated and reports the execution", async () => {
  const started = { execution_id: "20261022-001", flow_run_id: "fr-1", flow_run_url: "http://prefect/fr-1", qdash_ui_url: "http://qdash/execution/20261022-001", message: "Flow 'my_check' started" };
  const { run, calls } = registeredTools(async () => ({}), "64Qv3", async () => started);
  await assert.rejects(run.execute("t", { name: "my_check" }, undefined, undefined, uiContext(false)), /requires explicit confirmation/);
  assert.equal(calls.length, 0);
  const result = await run.execute("t", { name: "my_check", parameters: { qids: ["0"] } }, undefined, undefined, approved("t"));
  assert.deepEqual(calls, [{ execute: "my_check", parameters: { qids: ["0"] } }]);
  assert.equal(result.details.executionId, "20261022-001");
  assert.equal(result.details.started, true);
  assert.equal(result.content[0].text, formatFlowExecution(started, "my_check"));
  assert.match(result.content[0].text, /Execution: 20261022-001[\s\S]*qdash_wait_execution/);

  // Without parameters the saved defaults run: an empty object is sent, as before.
  await run.execute("t", { name: "my_check" }, undefined, undefined, approved("t"));
  assert.deepEqual(calls.at(-1), { execute: "my_check", parameters: {} });
});

test("running a flow without a project keeps the server's default and the confirmation gate", async () => {
  const started = { execution_id: "20261022-002", flow_run_id: "fr-2", flow_run_url: "", qdash_ui_url: "", message: "started" };
  const { run, calls } = registeredTools(async () => ({}), "64Qv3", async () => started, null);
  await assert.rejects(run.execute("t", { name: "my_check" }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  await assert.rejects(run.execute("t", { name: "my_check" }, undefined, undefined, uiContext(false)), /requires explicit confirmation/);
  assert.equal(calls.length, 0);

  for (const confirmWrite of [true, "true"]) {
    await assert.rejects(run.execute("t", { name: "my_check", confirmWrite }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  }
  assert.equal(calls.length, 0);
  const viaHost = await run.execute("t", { name: "my_check" }, undefined, undefined, approved("t"));
  const viaUi = await run.execute("t", { name: "my_check" }, undefined, undefined, uiContext(true));
  assert.deepEqual(calls, [{ execute: "my_check", parameters: {} }, { execute: "my_check", parameters: {} }]);
  for (const result of [viaHost, viaUi]) {
    assert.equal(result.details.started, true);
    assert.equal(result.details.executionId, "20261022-002");
  }
});

test("a flow name QDash cannot have is refused by the schema and sends nothing", async () => {
  const { tools, run, calls } = registeredTools(async () => ({}));
  const pattern = new RegExp(tools.get("qdash_execute_flow").parameters.properties.name.pattern);
  assert.ok(pattern.test("my_check"));
  for (const name of ["../chips", "bad name", ""]) assert.ok(!pattern.test(name), name);
  // The SDK checks again when the tool is called directly.
  await assert.rejects(run.execute("t", { name: "../chips" }, undefined, undefined, approved("t")), /letters, digits and underscores/);
  assert.equal(calls.length, 0);
});

test("the save is confirmation-gated and never runs on refusal or without a UI", async () => {
  const { tool, calls } = registeredTools(async () => { throw new Error("must not be called"); });
  await assert.rejects(tool.execute("t", { name: "my_check", code: CODE }, undefined, undefined, uiContext(false)), /requires explicit confirmation/);
  await assert.rejects(tool.execute("t", { name: "my_check", code: CODE }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  assert.equal(calls.length, 0);
});

test("a rejected flow is reported with QDash's detail, not thrown", async () => {
  const { tool } = registeredTools(async () => {
    const error = new Error("HTTP 400");
    error.payload = { detail: "Python syntax error in code: unexpected indent (line 4)" };
    throw error;
  });
  const result = await tool.execute("t", { name: "my_check", code: CODE }, undefined, undefined, approved("t", "qdash_save_flow"));
  assert.equal(result.details.saved, false);
  assert.match(result.content[0].text, /QDash rejected the flow: Python syntax error/);
});

test("local problems return without a confirmation prompt", async () => {
  let asked = 0;
  const { tool, calls } = registeredTools(async () => ({ name: "x", file_path: "x.py", message: "ok" }));
  const result = await tool.execute("t", { name: "x", code: "print('hi')\n" }, undefined, undefined, { hasUI: true, ui: { async confirm() { asked += 1; return true; } } });
  assert.equal(asked, 0);
  assert.equal(calls.length, 0);
  assert.equal(result.details.saved, false);
  assert.match(result.content[0].text, /cannot be saved as it is \(3 problems\)/);
});

test("a flow does not run around the user's agent session paused for an expert", async () => {
  const paused = [{ session_id: "s-1", chip_id: "64Qv3", status: "waiting_for_human", active_intervention_id: "int-1", policy: { qids: ["Q00"] } }];
  const execute = async () => { throw new Error("must not run"); };
  const blocked = registeredTools(async () => ({}), "64Qv3", execute, "project-1", paused);
  const result = await blocked.run.execute("t", { name: "my_check", parameters: { chip_id: "64Qv3", qids: ["Q00", "Q01"] } }, undefined, undefined, approved("t"));
  assert.equal(result.details.started, false);
  assert.equal(result.details.blockedByPausedSession, true);
  assert.match(result.content[0].text, /s-1 .*paused for an expert on chip 64Qv3/);
  assert.deepEqual(blocked.calls, []);
  assert.deepEqual(blocked.sessionQueries, [{ chipId: "64Qv3", statuses: ["waiting_for_human"], mine: true, limit: 100 }]);

  // Unknown targets count as overlapping; other qubits on the chip do not.
  const unknown = registeredTools(async () => ({}), "64Qv3", execute, "project-1", paused);
  const any = await unknown.run.execute("t", { name: "my_check" }, undefined, undefined, approved("t"));
  assert.equal(any.details.blockedByPausedSession, true);
  assert.deepEqual(unknown.sessionQueries, [{ chipId: undefined, statuses: ["waiting_for_human"], mine: true, limit: 100 }]);
  const started = registeredTools(async () => ({}), "64Qv3", async () => ({ execution_id: "e-1", flow_run_id: "f", flow_run_url: "", qdash_ui_url: "", message: "ok" }), "project-1", paused);
  const other = await started.run.execute("t", { name: "my_check", parameters: { chip_id: "64Qv3", qids: ["Q02"] } }, undefined, undefined, approved("t"));
  assert.equal(other.details.started, true);
});

test("a flow does not run when a full page of paused sessions hides older ones", async () => {
  // QDash lists at most 100 sessions, newest first; an older paused session may cover the targets.
  const pausedOn = (count, qid) => Array.from({ length: count }, (_, index) => ({
    session_id: `s-${index}`, chip_id: "64Qv3", status: "waiting_for_human", active_intervention_id: `int-${index}`, policy: { qids: [qid] },
  }));
  const ok = async () => ({ execution_id: "e-1", flow_run_id: "f", flow_run_url: "", qdash_ui_url: "", message: "ok" });
  const params = { name: "my_check", parameters: { chip_id: "64Qv3", qids: ["Q00"] } };
  for (const count of [100, 101]) {
    const execute = async () => { throw new Error("must not run"); };
    const { run, calls } = registeredTools(async () => ({}), "64Qv3", execute, "project-1", pausedOn(count, "Q09"));
    const result = await run.execute("t", params, undefined, undefined, approved("t"));
    assert.equal(result.details.started, false, String(count));
    assert.equal(result.details.blockedByPausedSession, true, String(count));
    assert.match(result.content[0].text, /at least 100 agent sessions paused for an expert on chip 64Qv3.*no older paused session covers these targets/, String(count));
    assert.doesNotMatch(result.content[0].text, /flag|skip the guard|--force/i);
    assert.deepEqual(calls, [], String(count));
  }
  // A known overlap on a full page is reported by name.
  const overlap = [...pausedOn(99, "Q09"), ...pausedOn(1, "Q00").map((s) => ({ ...s, session_id: "s-old" }))];
  const named = registeredTools(async () => ({}), "64Qv3", async () => { throw new Error("must not run"); }, "project-1", overlap);
  const blocked = await named.run.execute("t", params, undefined, undefined, approved("t"));
  assert.match(blocked.content[0].text, /s-old \(qubits Q00/);
  assert.deepEqual(named.calls, []);
  // Unknown targets and an unknown chip still block on a full page.
  const unknown = registeredTools(async () => ({}), "64Qv3", async () => { throw new Error("must not run"); }, "project-1", pausedOn(100, "Q09"));
  assert.equal((await unknown.run.execute("t", { name: "my_check" }, undefined, undefined, approved("t"))).details.blockedByPausedSession, true);
  assert.equal((await unknown.run.execute("t", { name: "my_check", parameters: { qids: ["Q00"] } }, undefined, undefined, approved("t"))).details.blockedByPausedSession, true);
  assert.deepEqual(unknown.calls, []);
  // Fewer than a full page shows every paused session, so other qubits run.
  const clear = registeredTools(async () => ({}), "64Qv3", ok, "project-1", pausedOn(99, "Q09"));
  const started = await clear.run.execute("t", params, undefined, undefined, approved("t"));
  assert.equal(started.details.started, true);
});

test("a flow does not run when QDash cannot show that no agent session is paused", async () => {
  const cases = [
    [404, /cannot list agent sessions \(HTTP 404; it predates GET \/agent-sessions\)/],
    [405, /cannot list agent sessions \(HTTP 405/],
    [500, /could not tell whether one of your agent sessions on chip 64Qv3 is paused/],
    [undefined, /could not tell whether/],
  ];
  for (const [status, message] of cases) {
    const failing = () => {
      const error = new Error(status ? `HTTP ${status}` : "socket hang up");
      if (status) error.statusCode = status;
      throw error;
    };
    const execute = async () => { throw new Error("must not run"); };
    const { run, calls } = registeredTools(async () => ({}), "64Qv3", execute, "project-1", failing);
    const result = await run.execute("t", { name: "my_check", parameters: { chip_id: "64Qv3", qids: ["Q00"] } }, undefined, undefined, approved("t"));
    assert.equal(result.details.started, false, String(status));
    assert.equal(result.details.blockedByPausedSession, true, String(status));
    assert.match(result.content[0].text, message, String(status));
    assert.doesNotMatch(result.content[0].text, /flag|skip the guard|--force/i);
    assert.deepEqual(calls, [], String(status));
  }
});
