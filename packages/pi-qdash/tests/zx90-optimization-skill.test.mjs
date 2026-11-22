import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

import { QDashClient, QDashTimeoutError } from "@oqtopus-team/qdash-client";

import { REVIEWED_WRITE_TOOL_NAMES, SESSION_GRANTED_WRITE_TOOL_NAMES } from "../.test-dist/lib/tool-policy.js";
import { WAIT_EXECUTION } from "../.test-dist/lib/waits.js";

// The ZX90 search skill's model-visible contracts for a long, active-session loop. The first
// tests pin the skill's statements about the tools to the code; the last ones pin how the skill
// handles realistic situations (a long wait, a stop while hardware runs, an exhausted budget, a
// bound it cannot verify, an approval it already holds). None of this shows that a model follows
// the skill, and nothing here judges a scientific choice. The qubex facts are pinned in
// tests/qdash/workflow/test_zx90_skill_example.py.
const RAW = readFileSync(new URL("../skills/qdash-zx90-optimization/SKILL.md", import.meta.url), "utf8");
const SKILL = RAW.replace(/\s+/g, " ");

function registeredToolNames() {
  const dir = new URL("../extensions/", import.meta.url);
  const files = ["qdash.ts", ...readdirSync(new URL("tools/", dir)).map((name) => `tools/${name}`)];
  const names = new Set();
  for (const file of files) {
    const source = readFileSync(new URL(file, dir), "utf8");
    for (const [, name] of source.matchAll(/name: "(qdash_[a-z0-9_]+)"/g)) names.add(name);
  }
  return names;
}

/** A client whose getExecution returns `responses` in order (the last repeats) and has no write method. */
function readOnlyClient(responses) {
  const client = Object.create(QDashClient.prototype);
  const queue = [...responses];
  const calls = [];
  client.getExecution = async (id) => {
    calls.push(id);
    return queue.length > 1 ? queue.shift() : queue[0];
  };
  for (const write of ["cancelExecution", "runPipeline", "executeFlow"]) {
    client[write] = () => assert.fail(`waiting called ${write}`);
  }
  Object.defineProperty(client, "config", { value: { baseUrl: "https://qdash.example/api" } });
  return { client, calls };
}

test("each experiment needs the host's approval, and the skill does not offer approval in prose", () => {
  assert.ok(REVIEWED_WRITE_TOOL_NAMES.includes("qdash_run_pipeline"));
  assert.ok(!SESSION_GRANTED_WRITE_TOOL_NAMES.includes("qdash_run_pipeline"));
  assert.match(SKILL, /Each `qdash_run_pipeline` is a reviewed write\./);
  assert.match(SKILL, /The approved scope does not replace that approval; it means you call the tool directly with the exact spec instead of asking again in prose\. A declined approval is a stop\./);
});

test("no tool cancels an execution, so the skill separates stopping the agent from cancelling hardware", () => {
  const names = registeredToolNames();
  assert.ok(names.has("qdash_run_pipeline") && names.has("qdash_wait_execution"), "the scan found the registrations");
  for (const name of [...names, ...REVIEWED_WRITE_TOOL_NAMES, ...SESSION_GRANTED_WRITE_TOOL_NAMES]) {
    assert.doesNotMatch(name, /cancel|abort|stop/, name);
  }
  assert.match(SKILL, /You have no cancel tool\./);
  assert.match(SKILL, /a running execution keeps measuring and writing on the hardware/);
  assert.match(SKILL, /Never claim it was cancelled until `qdash_get_execution` shows `cancelled`/);
});

test("the status cadence matches the wait tool: a bounded, read-only slice over the whole pipeline", async () => {
  // The skill's default cadence is the tool's default timeout.
  assert.match(SKILL, /the status cadence for long waits \(default 10 minutes\)/);
  assert.equal(WAIT_EXECUTION.timing({ executionId: "e" }).timeoutSeconds, 600);
  assert.deepEqual(WAIT_EXECUTION.timing({ executionId: "e", timeoutSeconds: 600, pollIntervalSeconds: 15 }), {
    timeoutSeconds: 600,
    pollIntervalSeconds: 15,
  });
  // A step's own execution completes long before its pipeline: the wait keeps going.
  const running = { execution_id: "e", status: "completed", pipeline: { status: "running" } };
  const done = { execution_id: "e", status: "completed", pipeline: { status: "completed" } };
  const { client, calls } = readOnlyClient([running, done]);
  assert.equal(await WAIT_EXECUTION.check(client, { executionId: "e" }), undefined);
  assert.equal(await WAIT_EXECUTION.check(client, { executionId: "e" }), done);
  assert.deepEqual(calls, ["e", "e"]);
  // A slice that runs out is a timeout error about the wait, not a failed execution.
  const timeout = WAIT_EXECUTION.timeoutError({ executionId: "e" }, { timeoutSeconds: 600, pollIntervalSeconds: 15 });
  assert.ok(timeout instanceof QDashTimeoutError);
  assert.match(timeout.message, /did not reach a terminal state within 600 seconds/);
  assert.match(SKILL, /A waiting tool blocks the chat until it returns, so wait in slices/);
  assert.match(SKILL, /A timeout means "not finished yet", not a failure: read `qdash_get_execution`, post a short status/);
});

test("the skill describes only ordinary pipelines and no background optimizer", () => {
  assert.doesNotMatch(RAW, /zx90_optimization|zx90-simulate|calibration guard/i);
  assert.match(SKILL, /A QDash optimizer, flow, or scheduler that runs this search; anything that acts after your turn ends or the runtime stops/);
  assert.match(SKILL, /Nothing runs between turns or after the runtime or CLI stops\./);
});

test("a continued loop ends only for a stated reason, never for an arbitrary count or a self-extended scope", () => {
  assert.match(SKILL, /Do not end the search after an arbitrary number of experiments or ask whether to go on while the scope allows another run\./);
  assert.match(SKILL, /never extend the bounds or the budget yourself/);
  assert.match(SKILL, /running out of budget and stopping is the intended end, not a failure/);
  assert.match(SKILL, /the budget minus the reserve cannot pay for the next experiment/);
  assert.match(SKILL, /Before each run, post: the experiment number, the key and its change \(from, to\), the evidence that motivates it/);
  assert.match(SKILL, /Post the measured evidence, the decision, the incumbent's values, and the pair's actual current stored state/);
});

test("a stop while hardware runs, and a resume, never re-dispatch an uncertain experiment", () => {
  assert.match(SKILL, /dispatch nothing new\. Stopping a turn ends its wait at once and changes nothing in QDash/);
  assert.match(SKILL, /never re-dispatch an experiment whose completion is uncertain/);
  assert.match(SKILL, /failed and cancelled runs included/);
});

test("an unverifiable amplitude bound stops the run before dispatch, not after", () => {
  assert.match(SKILL, /CreateZX90 does not inherit the CheckCR cap/);
  assert.match(SKILL, /QDash enforces no user bound on any of this\./);
  assert.match(SKILL, /If neither holds, do not dispatch: say which bound is missing and what evidence would establish it\./);
  assert.match(SKILL, /A post-run check alone is not enough\./);
});

test("the final state is the last run's recalibration, reported truthfully", () => {
  assert.match(SKILL, /do not rerun it afterwards to "restore" it, since rerunning recalibrates/);
  assert.match(SKILL, /the actual last stored pair state with the execution that wrote it/);
  assert.match(SKILL, /If that run failed or its evidence is incomplete, report the state as unverified\./);
  assert.match(SKILL, /Repeated, uncorrected comparisons carry no significance claim\./);
});
