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

function registeredTools(saveFlow, chipId = "64Qv3", executeFlow = async () => { throw new Error("must not be called"); }) {
  const tools = new Map();
  const calls = [];
  registerFlowAuthoringTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() {
      return {
        async saveFlow(request) { calls.push(request); return saveFlow(request); },
        async executeFlow(name, parameters) { calls.push({ execute: name, parameters }); return executeFlow(name, parameters); },
      };
    },
    async resolveChipId(_client, explicit) { return explicit ?? chipId; },
    flowPageUrl: (_client, name) => `https://qdash.example/workflow/${name}`,
  });
  return { tool: tools.get("qdash_save_flow"), run: tools.get("qdash_execute_flow"), calls };
}

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
  const result = await run.execute("t", { name: "my_check", parameters: { qids: ["0"] }, confirmWrite: true }, undefined, undefined, { hasUI: false });
  assert.deepEqual(calls, [{ execute: "my_check", parameters: { qids: ["0"] } }]);
  assert.equal(result.details.executionId, "20261022-001");
  assert.equal(result.details.started, true);
  assert.equal(result.content[0].text, formatFlowExecution(started, "my_check"));
  assert.match(result.content[0].text, /Execution: 20261022-001[\s\S]*qdash_wait_execution/);
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
  const result = await tool.execute("t", { name: "my_check", code: CODE, confirmWrite: true }, undefined, undefined, { hasUI: false });
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
