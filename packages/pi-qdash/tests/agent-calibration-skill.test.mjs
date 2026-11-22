import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// The agent calibration skill's model-visible contracts. These check that the guidance says
// what the session policy and the tools enforce; they do not show that a model follows it,
// and nothing here judges a scientific choice.
const SKILL = readFileSync(new URL("../skills/qdash-agent-calibration/SKILL.md", import.meta.url), "utf8").replace(/\s+/g, " ");

test("planning separates which parameters may update from numeric bounds", () => {
  assert.match(SKILL, /The grant says which parameters may change; it needs no numeric bounds\./);
  assert.match(SKILL, /A granted output from a granted task is accepted when its task completed, so the task's own checks \(such as its fit R² threshold\) passed/);
  assert.match(SKILL, /Without `parameter_updates`, a session you create accepts no output, because it holds no bounds \(step 4\), so nothing in it can be committed\./);
  assert.match(SKILL, /an output you leave out is staged for reference without affecting the granted one/);
  assert.match(SKILL, /declared input and output parameters with units from `qdash_get_pipeline_catalog` with `taskNames`/);
});

test("the model never authors thresholds, update authority is part of the session approval, and doubtful results are never committed", () => {
  // The tool refuses numeric criteria; the skill must not invite the model to write any.
  assert.match(SKILL, /`qdash_create_agent_session` refuses `allowed_overrides`, `task_quality_gates`, and `quality_gates`, even when the user stated the values and even when empty/);
  assert.doesNotMatch(SKILL, /Put numbers in `allowed_overrides`|any `allowed_overrides` and `task_quality_gates` the user stated|ask them for the accepted window/);
  assert.match(SKILL, /a frequency outside it was not measured, so do not call it checked/);
  assert.doesNotMatch(SKILL, /put a proposed window in the session proposal/);
  assert.match(SKILL, /propose `parameter_updates`: `parameters` \(exactly the outputs the goal commits, under the output names the catalog lists\), `tasks` \(only the tasks that measure them\)/);
  assert.match(SKILL, /commit it with `qdash_commit_agent_session_update`/);
  assert.match(SKILL, /Never commit a failed, uncertain, or unexplained result or a rejected granted output, and never record a pass you do not hold/);
  assert.match(SKILL, /Without a grant for the value, in a session a person created whose approved bounds accepted it, show the accepted candidate and propose `qdash_commit_agent_candidate`/);
  assert.match(SKILL, /it does not make a failed or uncertain result committable/);
  assert.match(SKILL, /Never create a new session to get around a paused one/);
});

test("an unexplained failure is recorded as an intervention before wider research", () => {
  assert.match(SKILL, /Call `qdash_request_agent_human` next, citing the failed action in `attemptActionIds`, before reading source code, older sessions, or other history\./);
  assert.match(SKILL, /A decision with `nextAction: request_human`, or a question in your answer, opens nothing and reaches nobody\./);
  // No retry on the agent's own: QDash refuses a repeat until an expert answers about that action.
  assert.match(SKILL, /a repeat of the same task included, until an expert answers an intervention that cites that action/);
  assert.doesNotMatch(SKILL, /as often as the evidence supports/);
  assert.match(SKILL, /do not supply a cause it did not report/);
});

test("a new session is proposed without reading older ones when the user asks for one", () => {
  assert.match(SKILL, /When the user asks for a new session, propose one without reading the older ones\./);
  assert.match(SKILL, /Reuse one only when you created it and its qubits, tasks, and bounds already cover the goal/);
});

test("an out-of-scope output is reference only, never a rejection of the result or a reason to widen the grant", () => {
  assert.match(SKILL, /A `not_in_scope` candidate is not a rejection of the result: it says nothing about the measurement, does not block the granted output, and needs no expert\./);
  assert.match(SKILL, /A `not_in_scope` output of the same result never makes it unresolved\./);
  assert.match(SKILL, /cannot be committed from this session, and the grant never widens to it\. When no later step of the goal reads it, report it and carry on\./);
  assert.doesNotMatch(SKILL, /a failed, uncertain, rejected, or unexplained result/);
});
