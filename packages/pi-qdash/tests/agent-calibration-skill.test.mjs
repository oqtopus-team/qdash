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
  assert.match(SKILL, /Without `parameter_updates` an output is a candidate only inside bounds in `allowed_overrides`, and every commit and apply is a separate approval\./);
  assert.match(SKILL, /declared input and output parameters with units from `qdash_get_pipeline_catalog` with `taskNames`/);
});

test("the model never authors thresholds, update authority is part of the session approval, and doubtful results are never committed", () => {
  assert.match(SKILL, /Never author a scientific threshold\. Do not derive bounds from the current value, a percent window, a round number, or your own reading of the task knowledge, and do not add bounds only to make a grant or a commit possible\./);
  assert.match(SKILL, /Put numbers in `allowed_overrides` or `task_quality_gates` only when the user stated them in this conversation/);
  assert.match(SKILL, /a gate never applies to another task, and an output such as `average_gate_fidelity` is not a quality metric/);
  assert.match(SKILL, /measurement can proceed in the approved scope without it, but nothing can be committed/);
  assert.doesNotMatch(SKILL, /put a proposed window in the session proposal/);
  assert.match(SKILL, /propose `parameter_updates`: `parameters` \(exactly the outputs the goal commits, under the output names the catalog lists\), `tasks` \(only the tasks that measure them\)/);
  assert.match(SKILL, /commit it with `qdash_commit_agent_session_update`/);
  assert.match(SKILL, /Never commit a failed, uncertain, rejected, or unexplained result, and never record a pass you do not hold/);
  assert.match(SKILL, /Without a grant for the value, show the accepted candidate and propose `qdash_commit_agent_candidate`/);
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
