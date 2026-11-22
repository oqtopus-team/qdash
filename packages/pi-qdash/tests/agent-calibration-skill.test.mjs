import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// The agent calibration skill's model-visible contracts. These check that the guidance says
// what the session policy and the tools enforce; they do not show that a model follows it,
// and nothing here judges a scientific choice.
const SKILL = readFileSync(new URL("../skills/qdash-agent-calibration/SKILL.md", import.meta.url), "utf8").replace(/\s+/g, " ");

test("planning explains allowed_overrides as the candidate gate and where output names come from", () => {
  assert.match(SKILL, /QDash uses `allowed_overrides` for two things: a step may override a task input of that name within the bounds, and a task output of that name becomes an accepted candidate only inside them\./);
  assert.match(SKILL, /An output that is not a key is staged as rejected and can never be committed from this session/);
  assert.match(SKILL, /under the output name and in the unit the catalog lists, and nothing the goal does not need: a key is also scope the user grants\./);
  assert.match(SKILL, /declared input and output parameters with units from `qdash_get_pipeline_catalog` with `taskNames`/);
});

test("bounds come from evidence, update authority is part of the session approval, and doubtful results are never committed", () => {
  assert.match(SKILL, /Take every bound from evidence, never from a habit or a round number/);
  assert.match(SKILL, /When neither documents a range, do not invent one and do not widen a bound to be safe/);
  assert.match(SKILL, /ask them for the accepted window, or put a proposed window in the session proposal and say plainly that it is your suggestion with no documented basis/);
  assert.match(SKILL, /propose `parameter_updates` in the same policy: `parameters` \(exactly the outputs the goal commits\), `tasks` \(only the tasks that measure them\)/);
  assert.match(SKILL, /Do not ask the user to invent extra thresholds/);
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
