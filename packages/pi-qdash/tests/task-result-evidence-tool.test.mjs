import assert from "node:assert/strict";
import test from "node:test";
import { QDashClient, QDashConfig } from "@oqtopus-team/qdash-client";

import { EVIDENCE_BOUNDS, evidenceText, presentEvidence, registerTaskResultEvidenceTool, TASK_RESULT_EVIDENCE_TOOL } from "../.test-dist/tools/task-result-evidence.js";
import { applyToolPolicy } from "../.test-dist/lib/script-policy.js";
import {
  DEFERRED_TOOL_NAMES,
  isDeferredTool,
  isNestedReadTool,
  isReviewedWriteTool,
  isSessionGrantedWriteTool,
} from "../.test-dist/lib/tool-policy.js";
import { sdkOver } from "./helpers/sdk-session.mjs";

const RESULT = {
  task_id: "t-1",
  task_name: "CheckT1",
  qid: "6",
  chip_id: "C",
  status: "failed",
  execution_id: "e-1",
  flow_name: "one_qubit",
  username: "alice",
  figure_path: ["/data/t1.png"],
  json_figure_path: [],
  raw_data_path: [],
  input_parameters: {},
  output_parameters: { t1: { value: 31.5, unit: "us" } },
  output_parameter_names: ["t1"],
  run_parameters: { api_token: "leak-me" },
  message: "fit did not converge",
  stack_trace: "Traceback ...",
  start_at: "2026-11-22T10:00:00Z",
  end_at: "2026-11-22T10:01:00Z",
  re_executions: [],
};

/** The tool over a QDash client whose fetch answers from `routes` by path; anything else is a 404. */
function toolWith(routes) {
  const requests = [];
  const client = new QDashClient(new QDashConfig({ baseUrl: "http://qdash.test/api", apiToken: "token", retry: { maxAttempts: 1 } }), {
    fetch: async (input, init) => {
      const request = new Request(input, init);
      const path = new URL(request.url).pathname;
      requests.push(`${request.method} ${path}`);
      const body = routes[path];
      const status = body === undefined ? 404 : body.__status ?? 200;
      return new Response(JSON.stringify(status === 200 ? body : { detail: "unavailable" }), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  const tools = new Map();
  registerTaskResultEvidenceTool({ registerTool: (tool) => tools.set(tool.name, tool) }, { sdk: sdkOver, makeClient: async () => client });
  return { tool: tools.get(TASK_RESULT_EVIDENCE_TOOL), requests };
}

test("the tool adapts the SDK evidence with links, bounds, and redaction, reading only", async () => {
  const { tool, requests } = toolWith({
    "/api/tasks/t-1/result": RESULT,
    "/api/executions/e-1": { name: "run", status: "failed", chip_id: "C", task: [{ task_id: "t-1", status: "failed", task_type: "qubit" }] },
    "/api/chips/C/qubits/6": { qid: "6", chip_id: "C", status: "active", data: { t1: { value: 24, task_id: "t-1" } } },
  });
  const result = await tool.execute("call", { taskId: "t-1" });
  const data = result.details.data;
  assert.ok(requests.every((line) => line.startsWith("GET ")));
  assert.equal(data.result.status, "failed");
  assert.equal(data.result.run_parameters.api_token, "[redacted]");
  // The section's status is not replaced by the execution's own status.
  assert.equal(data.execution.status, "ok");
  assert.equal(data.execution.execution_status, "failed");
  assert.equal(data.execution.this_task.task_type, "qubit");
  assert.deepEqual(data.target.stored_values_for_outputs.t1, { stored: { value: 24, task_id: "t-1" }, from_this_result: true });
  assert.equal(data.cooldown.status, "not_associated");
  assert.equal(data.links.task_result, "http://qdash.test/task-results/t-1");
  assert.equal(data.links.execution, "http://qdash.test/execution/C/e-1");
  const text = result.content[0].text;
  assert.match(text, /status failed/);
  assert.match(text, /cooldown: not associated/);
  assert.doesNotMatch(text, /leak-me/);
});

test("failed and inapplicable parts are reported, never substituted", async () => {
  const { tool } = toolWith({
    "/api/tasks/t-1/result": { ...RESULT, qid: "" },
    "/api/executions/e-1": { __status: 503 },
  });
  const result = await tool.execute("call", { taskId: "t-1", cooldownId: "2026-001" });
  const { execution, target, cooldown } = result.details.data;
  assert.equal(execution.status, "failed");
  assert.equal(execution.statusCode, 503);
  assert.equal(target.status, "not_applicable");
  assert.equal(cooldown.status, "failed");
  assert.equal(cooldown.statusCode, 404);
  assert.equal(result.details.data.identifiers.cooldown_id, null);
  assert.match(result.content[0].text, /execution: read failed .*no other data is substituted/);
});

test("a failed result read fails the tool, as qdash_get_task_result does", async () => {
  const { tool } = toolWith({ "/api/tasks/t-1/result": { __status: 500 } });
  await assert.rejects(tool.execute("call", { taskId: "t-1" }), /500|Internal|unavailable/i);
});

test("large values are bounded", async () => {
  const outputs = Object.fromEntries(Array.from({ length: 200 }, (_, i) => [`p${i}`, { value: "x".repeat(2000) }]));
  const { tool } = toolWith({
    "/api/tasks/t-1/result": { ...RESULT, output_parameters: outputs, output_parameter_names: Object.keys(outputs), execution_id: "" },
    "/api/chips/C/qubits/6": { qid: "6", chip_id: "C", status: "active", data: outputs },
  });
  const result = await tool.execute("call", { taskId: "t-1" });
  assert.ok(Buffer.byteLength(JSON.stringify(result.details.data)) <= EVIDENCE_BOUNDS.maxBytes);
  assert.ok(result.details.data.result.omitted_for_size.length > 0);
});

test("the evidence tool is a deferred, script-callable read and never a write", () => {
  assert.ok(DEFERRED_TOOL_NAMES.includes(TASK_RESULT_EVIDENCE_TOOL));
  assert.ok(isDeferredTool(TASK_RESULT_EVIDENCE_TOOL));
  assert.ok(isNestedReadTool(TASK_RESULT_EVIDENCE_TOOL));
  assert.ok(!isReviewedWriteTool(TASK_RESULT_EVIDENCE_TOOL));
  assert.ok(!isSessionGrantedWriteTool(TASK_RESULT_EVIDENCE_TOOL));
  const tools = new Map();
  registerTaskResultEvidenceTool({ registerTool: (tool) => tools.set(tool.name, applyToolPolicy(tool)) }, { sdk: sdkOver, makeClient: async () => { throw new Error("unused"); } });
  const applied = tools.get(TASK_RESULT_EVIDENCE_TOOL);
  assert.equal(applied.exposure, "deferred");
  assert.equal(applied.annotations.readOnlyHint, true);
  assert.match(applied.description, /\nRequest type: diagnosis:/);
});

test("the final byte budget covers context errors, metadata, keys, and Unicode", () => {
  const largeBlock = Object.fromEntries(Array.from({ length: 40 }, (_, i) => [`p${i}`, "x".repeat(500)]));
  const missing = { status: "not_applicable", reason: "No target" };
  const base = { taskId: "t-1", result: RESULT, execution: missing, target: missing, cooldown: missing };
  const cases = [
    { ...base, execution: { status: "failed", error: "x".repeat(30000), statusCode: 503 } },
    { ...base, execution: { status: "ok", value: { execution: { pipeline: largeBlock, agent_session: largeBlock }, task: null, chipMatches: true } } },
    { ...base, result: { ...RESULT, tags: { ["巨大🔬".repeat(10000)]: "value" } } },
    { ...base, execution: { status: "failed", error: "🔬".repeat(10000) } },
    { ...base, taskId: "🔬".repeat(10000) },
  ];
  for (const input of cases) {
    const data = presentEvidence(input, { task_result: "https://qdash.test/task-results/t-1" });
    assert.ok(Buffer.byteLength(JSON.stringify(data)) <= EVIDENCE_BOUNDS.maxBytes);
    assert.match(data.omitted_for_size, /Detailed evidence omitted/);
    assert.equal(data.execution.status, input.execution.status);
    assert.equal(data.links.task_result, "https://qdash.test/task-results/t-1");
    assert.equal(data.links.execution, undefined);
    assert.doesNotMatch(evidenceText(data), /undefined|NaN/);
    assert.match(evidenceText(data), /details omitted for size/);
  }
  const longLinks = presentEvidence(base, { execution: "https://qdash.test/" + "🔬".repeat(10000) });
  assert.ok(Buffer.byteLength(JSON.stringify(longLinks)) <= EVIDENCE_BOUNDS.maxBytes);
  assert.equal(longLinks.links.execution, undefined);
  assert.match(longLinks.omitted_for_size, /Detailed evidence omitted/);
});

test("compact evidence retains whole result identifiers or omits them", () => {
  const keys = ["task_id", "execution_id", "chip_id", "qid"];
  for (const length of [600, 3000]) {
    const id = "x".repeat(length);
    const data = presentEvidence({
      taskId: id,
      result: { ...RESULT, ...Object.fromEntries(keys.map((key) => [key, id])) },
      execution: { status: "failed", error: "failure".repeat(10000) },
      target: { status: "not_applicable", reason: "No target" },
      cooldown: { status: "not_associated", reason: "No association" },
    }, {});
    assert.ok(Buffer.byteLength(JSON.stringify(data)) <= EVIDENCE_BOUNDS.maxBytes);
    for (const key of keys) assert.equal(data.result[key], length <= 2048 ? id : undefined);
    assert.doesNotMatch(JSON.stringify(data.result), /…|chars/);
  }
});
