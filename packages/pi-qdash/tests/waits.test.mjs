import assert from "node:assert/strict";
import test from "node:test";

import { QDashTimeoutError } from "@oqtopus-team/qdash-sdk";

import { QDashConnection } from "../.test-dist/lib/qdash-connection.js";

import {
  EXECUTION_TERMINAL_STATUSES,
  MIN_CHECK_MS,
  WAIT_AGENT_ACTION,
  WAIT_AGENT_INTERVENTION,
  WAIT_EXECUTION,
  WAIT_SPECS,
  boundedCheck,
  isWaitToolName,
  pollUntilSettled,
} from "../.test-dist/lib/waits.js";

/** A client whose reads return `responses` in order (the last repeats), with the client's own polling loops. */
function fakeClient(method, responses) {
  const client = Object.create(QDashConnection.prototype);
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
  assert.deepEqual(Object.keys(WAIT_SPECS).sort(), ["qdash_wait_agent_action", "qdash_wait_agent_intervention", "qdash_wait_execution"]);
  assert.ok(isWaitToolName("qdash_wait_execution"));
  assert.ok(!isWaitToolName("qdash_wait_agent_candidate_apply"));
  assert.ok(!isWaitToolName("toString"));
});

/** A promise settled from outside, for a read that hangs until the test lets it answer. */
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** A wait spec whose polls are the given functions, one per call (the last repeats). */
function scriptedSpec(polls, timing = { timeoutSeconds: 60, pollIntervalSeconds: 0 }) {
  const queue = [...polls];
  const spec = {
    calls: 0,
    signals: [],
    timing: () => timing,
    check: (_client, _params, signal) => {
      spec.calls += 1;
      spec.signals.push(signal);
      return (queue.length > 1 ? queue.shift() : queue[0])();
    },
    result: (_client, _params, value) => ({ value }),
    timeoutError: () => new QDashTimeoutError("timed out"),
  };
  return spec;
}

/** Collect unhandled rejections while `run` and a grace period after it go by. */
async function withoutUnhandledRejections(run) {
  const unhandled = [];
  const listener = (reason) => unhandled.push(reason);
  process.on("unhandledRejection", listener);
  try {
    await run();
    await new Promise((resolve) => setTimeout(resolve, 30));
  } finally {
    process.off("unhandledRejection", listener);
  }
  assert.deepEqual(unhandled, []);
}

const tick = (ms = 10) => new Promise((resolve) => setTimeout(resolve, ms));

test("a bounded poll returns the value and leaves no timer or listener behind", async () => {
  const controller = new AbortController();
  const spec = scriptedSpec([async () => undefined, async () => "done"]);
  const result = await pollUntilSettled(spec, {}, {}, controller.signal, async () => {});
  assert.deepEqual(result, { value: "done" });
  assert.equal(spec.calls, 2);
  // The signal reaches the check, so a check with several reads can stop between them.
  assert.equal(spec.signals[0], controller.signal);
  const outcome = await boundedCheck(spec, {}, {}, { timeoutMs: 60_000, signal: controller.signal });
  assert.deepEqual(outcome, { kind: "value", value: "done" });
  // A pending 60 s timer would keep the test process alive; none is left.
});

test("cancelling during a hung read ends the wait at once and drops the late answer", async () => {
  await withoutUnhandledRejections(async () => {
    for (const late of ["value", "failure"]) {
      const hung = deferred();
      const spec = scriptedSpec([() => hung.promise]);
      const controller = new AbortController();
      const started = Date.now();
      const waiting = pollUntilSettled(spec, {}, {}, controller.signal);
      await tick();
      controller.abort();
      await assert.rejects(waiting, (error) => error.name === "AbortError" && /cancelled/.test(error.message));
      assert.ok(Date.now() - started < 500);
      if (late === "value") hung.resolve("late");
      else hung.reject(new Error("late failure"));
      await tick(20);
      assert.equal(spec.calls, 1, late);
    }
  });
});

test("a read still running at the deadline ends the wait with the timeout error, once", async () => {
  await withoutUnhandledRejections(async () => {
    for (const late of ["value", "failure"]) {
      const hung = deferred();
      const spec = scriptedSpec([() => hung.promise], { timeoutSeconds: 0.05, pollIntervalSeconds: 0 });
      const started = Date.now();
      await assert.rejects(pollUntilSettled(spec, {}, {}), /timed out/);
      const took = Date.now() - started;
      // The deadline is near, so the read gets the minimum time and no more.
      assert.ok(took >= MIN_CHECK_MS - 50 && took < MIN_CHECK_MS + 500, `took ${took} ms`);
      if (late === "value") hung.resolve("late");
      else hung.reject(new Error("late failure"));
      await tick(20);
      assert.equal(spec.calls, 1, late);
    }
  });
});

test("a read failure ends the wait with that failure", async () => {
  const spec = scriptedSpec([async () => { throw new Error("HTTP 500"); }]);
  await assert.rejects(pollUntilSettled(spec, {}, {}), /HTTP 500/);
  assert.equal(spec.calls, 1);
});

test("an intervention poll stops before its next request once cancelled", async () => {
  const controller = new AbortController();
  const reads = [];
  const client = {
    async getAgentSession() {
      reads.push("session");
      controller.abort();
      return { session_id: "s1", status: "waiting_for_human", active_intervention_id: "int-1" };
    },
    async getAgentIntervention() { reads.push("intervention"); return { status: "open" }; },
    async listAgentActions() { reads.push("actions"); return []; },
    async listAgentInterventions() { reads.push("interventions"); return []; },
  };
  await assert.rejects(WAIT_AGENT_INTERVENTION.check(client, { sessionId: "s1" }, controller.signal), (error) => error.name === "AbortError");
  assert.deepEqual(reads, ["session"]);
});

test("a failed run's wait result adds the mechanical next step after the unchanged record", () => {
  const { client } = fakeClient("getAgentAction", []);
  const failed = { action_id: "a9", action_type: "run_task", execution_status: "failed", execution_id: "e9" };
  const result = WAIT_AGENT_ACTION.result(client, {}, failed);
  assert.deepEqual(JSON.parse(result.content[0].text), result.details.data);
  assert.equal(result.content.length, 2);
  assert.match(result.content[1].text, /^Next: Action a9 did not complete\. .*call qdash_request_agent_human now, citing it in attemptActionIds, before any wider research\./);
  for (const action of [
    { action_id: "a1", action_type: "run_task", execution_status: "running", execution_id: "e1" },
    { action_id: "a2", action_type: "run_task", execution_status: "completed", execution_id: "e2" },
    { action_id: "a3", action_type: "request_human", execution_status: "failed" },
  ]) {
    assert.equal(WAIT_AGENT_ACTION.result(client, {}, action).content.length, 1, action.action_id);
  }
});
