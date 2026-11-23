import assert from "node:assert/strict";
import test from "node:test";

import { QDashClient, QDashTimeoutError } from "@oqtopus-team/qdash-client";

import {
  EXECUTION_TERMINAL_STATUSES,
  WAIT_AGENT_ACTION,
  WAIT_EXECUTION,
  WAIT_SPECS,
  isWaitToolName,
} from "../.test-dist/lib/waits.js";

/** A client whose reads return `responses` in order (the last repeats), with the client's own polling loops. */
function fakeClient(method, responses) {
  const client = Object.create(QDashClient.prototype);
  const queue = [...responses];
  let calls = 0;
  client[method] = async () => {
    calls += 1;
    return queue.length > 1 ? queue.shift() : queue[0];
  };
  Object.defineProperty(client, "config", { value: { baseUrl: "https://qdash.example/api" } });
  return { client, calls: () => calls };
}

/** Run a spec the way the runtime does, one check per wake, without sleeping. */
async function runSpec(spec, client, params) {
  const timing = spec.timing(params);
  for (let polls = 1; polls < 100; polls++) {
    const value = await spec.check(client, params);
    if (value !== undefined) return { value, polls };
  }
  throw spec.timeoutError(params, timing);
}

const execution = (status, pipeline) => ({ execution_id: "e1", status, ...(pipeline ? { pipeline: { status: pipeline } } : {}) });

const SEQUENCES = [
  [execution("running"), execution("completed")],
  [execution("pending"), execution("FAILED")],
  [execution("running"), execution("cancelled")],
  [execution("canceled")],
  [execution("crashed")],
  [execution("completed", "running"), execution("completed", "running"), execution("completed", "completed")],
  [execution("running", "failed")],
];

test("an execution wait stops on the value the client's loop stops on", async () => {
  for (const sequence of SEQUENCES) {
    const sdk = fakeClient("getExecution", sequence);
    const expected = await sdk.client.waitForExecution("e1", { pollIntervalSeconds: 0 });
    const step = fakeClient("getExecution", sequence);
    const { value, polls } = await runSpec(WAIT_EXECUTION, step.client, { executionId: "e1" });
    assert.deepEqual(value, expected, JSON.stringify(sequence));
    assert.equal(polls, sdk.calls(), JSON.stringify(sequence));
  }
  assert.deepEqual([...EXECUTION_TERMINAL_STATUSES].sort(), ["canceled", "cancelled", "completed", "crashed", "failed"]);
});

test("an agent action wait stops on the value the client's loop stops on", async () => {
  const action = (fields) => ({ action_id: "a1", execution_status: "pending", operation_id: null, execution_id: null, ...fields });
  const cases = [
    { waitForExecution: false, method: "waitForAgentAction", sequence: [action({}), action({ operation_id: "op" })] },
    { waitForExecution: true, method: "waitForAgentActionExecution", sequence: [action({ operation_id: "op" }), action({ operation_id: "op", execution_id: "e1" })] },
    { waitForExecution: true, method: "waitForAgentActionExecution", sequence: [action({}), action({ execution_status: "failed" })] },
  ];
  for (const { waitForExecution, method, sequence } of cases) {
    const sdk = fakeClient("getAgentAction", sequence);
    const expected = await sdk.client[method]("s1", "a1", { pollIntervalSeconds: 0 });
    const step = fakeClient("getAgentAction", sequence);
    const { value, polls } = await runSpec(WAIT_AGENT_ACTION, step.client, { sessionId: "s1", actionId: "a1", waitForExecution });
    assert.deepEqual(value, expected);
    assert.equal(polls, sdk.calls());
  }
});

test("timing, validation and timeout errors match the client's", async () => {
  assert.deepEqual(WAIT_EXECUTION.timing({ executionId: "e1" }), { timeoutSeconds: 600, pollIntervalSeconds: 0.5 });
  assert.deepEqual(WAIT_AGENT_ACTION.timing({ sessionId: "s", actionId: "a" }), { timeoutSeconds: 120, pollIntervalSeconds: 0.5 });
  assert.deepEqual(WAIT_AGENT_ACTION.timing({ sessionId: "s", actionId: "a", waitForExecution: true }), { timeoutSeconds: 600, pollIntervalSeconds: 0.5 });
  assert.throws(() => WAIT_EXECUTION.timing({ executionId: "e1", timeoutSeconds: -1 }), /must be non-negative/);

  const running = fakeClient("getExecution", [execution("running")]);
  const sdkError = await running.client.waitForExecution("e1", { timeoutSeconds: 0, pollIntervalSeconds: 0 }).catch((error) => error);
  const ours = WAIT_EXECUTION.timeoutError({ executionId: "e1" }, { timeoutSeconds: 0, pollIntervalSeconds: 0 });
  assert.ok(ours instanceof QDashTimeoutError);
  assert.equal(ours.message, sdkError.message);

  const pending = fakeClient("getAgentAction", [{ execution_status: "pending", operation_id: null, execution_id: null }]);
  for (const [method, waitForExecution] of [["waitForAgentAction", false], ["waitForAgentActionExecution", true]]) {
    const error = await pending.client[method]("s1", "a1", { timeoutSeconds: 0, pollIntervalSeconds: 0 }).catch((e) => e);
    const params = { sessionId: "s1", actionId: "a1", waitForExecution };
    assert.equal(WAIT_AGENT_ACTION.timeoutError(params, { timeoutSeconds: 0 }).message, error.message);
  }
});

test("results are pi-qdash's tool results with links and redaction", () => {
  const { client } = fakeClient("getExecution", []);
  const result = WAIT_EXECUTION.result(client, { executionId: "e1" }, { execution_id: "e1", chip_id: "A", status: "completed", api_token: "secret" });
  assert.equal(result.details.tool, "qdash_wait_execution");
  assert.equal(result.details.executionId, "e1");
  assert.equal(result.details.webBaseUrl, "https://qdash.example");
  assert.equal(result.details.data.api_token, "[redacted]");
  assert.ok(result.details.data._links);
  assert.deepEqual(JSON.parse(result.content[0].text), result.details.data);
  assert.equal(WAIT_AGENT_ACTION.result(client, {}, { action_id: "a1" }).details.tool, "qdash_wait_agent_action");
  assert.deepEqual(Object.keys(WAIT_SPECS).sort(), ["qdash_wait_agent_action", "qdash_wait_execution"]);
  assert.ok(isWaitToolName("qdash_wait_execution"));
  assert.ok(!isWaitToolName("qdash_wait_agent_candidate_apply"));
  assert.ok(!isWaitToolName("toString"));
});
