import assert from "node:assert/strict";
import { after, before, test } from "node:test";

import { QDashClient, QDashConfig } from "@oqtopus-team/qdash-client";

import { buildAgentLoopContext, decideAgentStep, measurementKey } from "../.test-dist/lib/agent-loop.js";
import { SESSION_GRANTED_WRITE_TOOL_NAMES, REVIEWED_WRITE_TOOL_NAMES, NESTED_READ_TOOL_NAMES, DEFERRED_TOOL_NAMES } from "../.test-dist/lib/tool-policy.js";
import { registerAgentLoopTools } from "../.test-dist/tools/agent-loop.js";
import { startFakeAgentQDash } from "./helpers/fake-agent-qdash.mjs";
import { inZone, NON_UTC_ZONES } from "./helpers/time-zone.mjs";

let fake;
before(async () => {
  fake = await startFakeAgentQDash();
});
after(() => fake.close());

/** The loop tools as a host registers them, on a fresh client each call (a restarted pi). */
function tools() {
  const registered = new Map();
  registerAgentLoopTools({ registerTool(tool) { registered.set(tool.name, tool); } }, {
    async makeClient() {
      return new QDashClient(new QDashConfig({ baseUrl: fake.baseUrl, apiToken: "fixture-token" }));
    },
  });
  const call = (name) => (id, params) => registered.get(name).execute(id, params, undefined, undefined, { hasUI: false });
  return {
    context: (sessionId) => call("qdash_get_agent_session_context")("ctx", { sessionId }),
    step: (id, params) => call("qdash_run_agent_session_step")(id, params),
    human: (id, params) => call("qdash_request_agent_human")(id, params),
    wait: (params) => call("qdash_wait_agent_intervention")("wait", params),
    list: (params = {}) => call("qdash_list_agent_sessions")("list", params),
    record: (id, params) => call("qdash_record_agent_decision")(id, params),
    audit: (params) => call("qdash_get_agent_session_audit")("audit", params),
    update: (id, params) => call("qdash_commit_agent_session_update")(id, params),
    registered,
  };
}

const textOf = (result) => result.content.map((block) => block.text).join("\n");

function autoSession(policy = {}) {
  return fake.createSession({
    chip_id: "chip-001",
    policy: {
      qids: ["Q00"],
      allowed_tasks: ["CheckRabi", "CheckChevron"],
      allowed_overrides: { qubit_frequency: { minimum: 7.4, maximum: 7.6 } },
      autonomy: "auto",
      max_actions: 6,
      ...policy,
    },
  }).session_id;
}

test("the loop tools are session-granted writes or audited reads, never script-callable writes", () => {
  assert.deepEqual([...SESSION_GRANTED_WRITE_TOOL_NAMES].sort(), ["qdash_commit_agent_session_update", "qdash_record_agent_decision", "qdash_request_agent_human", "qdash_run_agent_session_step"]);
  for (const name of SESSION_GRANTED_WRITE_TOOL_NAMES) {
    assert.ok(!REVIEWED_WRITE_TOOL_NAMES.includes(name), name);
    assert.ok(!NESTED_READ_TOOL_NAMES.includes(name), `${name} must not run from a script`);
  }
  for (const name of ["qdash_get_agent_session_audit", "qdash_get_agent_session_context", "qdash_list_agent_sessions"]) assert.ok(NESTED_READ_TOOL_NAMES.includes(name), name);
  for (const name of tools().registered.keys()) assert.ok(DEFERRED_TOOL_NAMES.includes(name), name);
  // Nothing in pi answers, resumes, or reactivates an intervention.
  const names = [...tools().registered.keys()].join(" ");
  assert.doesNotMatch(names, /respond|claim|resume|reactivate/);
});

test("a successful step dispatches once, a replayed call reuses it, and the next step follows the result", async () => {
  const sessionId = autoSession();
  const t = tools();
  fake.queueOutcome("CheckRabi", { status: "completed", candidates: [{ parameter_name: "control_amplitude", value: 0.05 }] });
  const before = fake.state.dispatches.length;

  const first = await t.step("call-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first, per the one-qubit skill." });
  assert.equal(first.details.dispatched, true, textOf(first));
  assert.match(textOf(first), /Dispatched action action-\d+: CheckRabi on Q00; execution completed/);
  assert.match(textOf(first), /nothing was committed/);
  // The host replays the interrupted call: same action, no second measurement.
  const replay = await t.step("call-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first, per the one-qubit skill." });
  assert.equal(replay.details.actionId, first.details.actionId);
  assert.match(textOf(replay), /^Continued action/);
  assert.equal(fake.state.dispatches.length, before + 1);

  const read = await t.context(sessionId);
  assert.equal(read.details.state, "ready");
  assert.match(textOf(read), /candidate control_amplitude = 0\.05: accepted/);

  // The model chose the next step from the result; it is a different measurement.
  const next = await t.step("call-2", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.5 }, rationale: "Refine the frequency." });
  assert.equal(next.details.dispatched, true, textOf(next));
  assert.deepEqual(fake.state.dispatches.slice(before).map((run) => run.task_name), ["CheckRabi", "CheckChevron"]);
  // The rationale is the action's recorded diagnosis.
  assert.equal(fake.state.actions.find((action) => action.action_id === next.details.actionId).diagnosis, "Refine the frequency.");
});

test("steps outside the approved session are refused before QDash and use no budget", async () => {
  const sessionId = autoSession();
  const t = tools();
  const submitted = () => fake.state.requests.filter((request) => request.method === "POST" && request.path.endsWith("/actions")).length;
  const start = submitted();
  const cases = [
    [{ taskName: "CheckT1", qid: "Q00" }, /Task 'CheckT1' is outside the approved session/],
    [{ taskName: "CheckRabi", qid: "Q01" }, /Qubit 'Q01' is outside the approved session/],
    [{ taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 8 } }, /outside the approved bounds/],
    [{ taskName: "CheckChevron", qid: "Q00", parameterOverrides: { drag_beta: 1 } }, /Override 'drag_beta' is not allowed/],
    [{ taskName: "CheckRabi", qid: "Q00", reconfigure: true }, /does not allow hardware reconfiguration/],
  ];
  for (const [index, [request, message]] of cases.entries()) {
    const result = await t.step(`scope-${index}`, { sessionId, rationale: "test", ...request });
    assert.equal(result.details.refused, true);
    assert.match(textOf(result), message);
  }
  assert.equal(submitted(), start);
  const confirmEach = fake.createSession({ chip_id: "chip-001", policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"] } }).session_id;
  const refused = await t.step("ce", { sessionId: confirmEach, taskName: "CheckRabi", qid: "Q00", rationale: "test" });
  assert.match(textOf(refused), /confirm_each: every action needs the reviewed tools/);
  const human = await t.human("ce-h", { sessionId: confirmEach, reason: "agent_request", summary: "s", question: "q" });
  assert.match(textOf(human), /^Not recorded: .*qdash_submit_agent_action/);
});

test("an identical finished measurement repeats only on purpose, and the round budget holds", async () => {
  const sessionId = autoSession({ max_rounds_per_target: 2 });
  const t = tools();
  const first = await t.step("r-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "first" });
  const again = await t.step("r-2", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "again" });
  assert.equal(again.details.refused, true);
  assert.match(textOf(again), new RegExp(`Action ${first.details.actionId} already ran this exact measurement.*repeatOfActionId: "${first.details.actionId}"`, "s"));
  const repeat = await t.step("r-3", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "noisy fit; measure again", repeatOfActionId: first.details.actionId });
  assert.equal(repeat.details.dispatched, true, textOf(repeat));
  const third = await t.step("r-4", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "third", repeatOfActionId: repeat.details.actionId });
  assert.match(textOf(third), /already ran 2 times, the session's max_rounds_per_target/);
});

test("a running action is waited on, not started again", async () => {
  const sessionId = autoSession();
  const t = tools();
  fake.queueOutcome("CheckRabi", { status: "running" });
  const first = await t.step("f-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "first" });
  const busy = await t.step("f-2", { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "other" });
  assert.equal(busy.details.state, "in_flight");
  assert.match(textOf(busy), new RegExp(`Action ${first.details.actionId} is still running`));
  fake.setExecution(first.details.actionId, "completed");
  const read = await t.context(sessionId);
  assert.equal(read.details.state, "ready");
});

test("an unknown result pauses the session; the expert's reply is read back after a restart and the loop continues within scope", async () => {
  const sessionId = autoSession();
  fake.queueOutcome("CheckRabi", { status: "completed", candidates: [{ parameter_name: "control_amplitude", value: 0.2, accepted: false }] });
  const live = tools();
  const rabi = await live.step("u-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first." });
  const asked = await live.human("u-2", {
    sessionId,
    reason: "unknown_outcome",
    summary: "CheckRabi shows a beating pattern the task knowledge does not cover.",
    question: "Is a second transition nearby, or should Chevron be rerun first?",
    taskName: "CheckRabi",
    qids: ["Q00"],
    attemptActionIds: [rabi.details.actionId],
  });
  assert.equal(asked.details.paused, true, textOf(asked));
  assert.match(textOf(asked), /The session is paused until an expert answers in QDash/);
  assert.match(textOf(asked), /Intervention page: http:\/\/127\.0\.0\.1:\d+\/agent-sessions\/.+\/interventions\/int-/);
  // A replay of the same call returns the same record.
  const replay = await live.human("u-2", { sessionId, reason: "unknown_outcome", summary: "x", question: "y" });
  assert.equal(replay.details.interventionId, asked.details.interventionId);
  const intervention = fake.state.interventions.find((item) => item.intervention_id === asked.details.interventionId);
  assert.deepEqual(intervention.attempts.map((attempt) => [attempt.action_id, attempt.execution_id !== null]), [[rabi.details.actionId, true]]);

  // While waiting: no step, no second request, and a bounded wait times out with the rule.
  const dispatches = fake.state.dispatches.length;
  const blocked = await live.step("u-3", { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "try" });
  assert.equal(blocked.details.state, "waiting_for_expert");
  const second = await live.human("u-4", { sessionId, reason: "agent_request", summary: "s", question: "q" });
  assert.match(textOf(second), /^Not recorded: The session is paused/);
  const timeout = await live.wait({ sessionId, timeoutSeconds: 0, pollIntervalSeconds: 0 }).catch((error) => error);
  assert.match(timeout.message, /No expert answered .* within 0 seconds\. The session stays paused/);
  assert.equal(fake.state.dispatches.length, dispatches);

  // The expert answers in QDash. pi restarted: a new process reads QDash, not its memory.
  fake.respond(sessionId, { guidance: "Beating means the frequency is off; run CheckChevron first, then Rabi again." });
  const restarted = tools();
  const sessions = await restarted.list({ chipId: "chip-001" });
  assert.ok(sessions.details.data.some((session) => session.session_id === sessionId));
  const read = await restarted.context(sessionId);
  const text = textOf(read);
  assert.equal(read.details.state, "ready");
  assert.equal(read.details.data.expert_answer_pending_review, true);
  assert.match(text, /An expert answered intervention .* and the session is active again/);
  assert.match(text, /Question asked: Is a second transition nearby/);
  assert.match(text, new RegExp(`- attempt: CheckRabi on Q00, completed, action ${rabi.details.actionId}`));
  assert.match(text, /Guidance: Beating means the frequency is off; run CheckChevron first/);
  assert.match(text, /Rule: The expert's guidance is evidence .* not new permission/);
  assert.match(text, /candidate control_amplitude = 0\.2: rejected/);

  // Guidance is not permission: a task outside the session is still refused.
  const outside = await restarted.step("u-5", { sessionId, taskName: "CheckT1", qid: "Q00", rationale: "The expert mentioned coherence." });
  assert.match(textOf(outside), /Task 'CheckT1' is outside the approved session/);
  // Blindly replaying the finished Rabi is refused; the guided next step runs.
  const replayRabi = await restarted.step("u-6", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "resume" });
  assert.match(textOf(replayRabi), /already ran this exact measurement/);
  const chevron = await restarted.step("u-7", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Expert guidance: rerun Chevron first." });
  assert.equal(chevron.details.dispatched, true, textOf(chevron));
  const after = await restarted.context(sessionId);
  assert.equal(after.details.data.expert_answer_pending_review, false);
  assert.deepEqual(after.details.data.intervention.actions_since_answer, [chevron.details.actionId]);
  assert.equal(fake.state.dispatches.length, dispatches + 1);
});

test("a live bounded wait returns the expert's answer as soon as it is given", async () => {
  const sessionId = autoSession();
  const t = tools();
  await t.human("w-1", { sessionId, reason: "agent_request", summary: "s", question: "Proceed?" });
  setTimeout(() => fake.respond(sessionId, { guidance: "Yes, within the same bounds." }), 50);
  // The tool's floor is a 5 s interval; one poll after the answer is enough here.
  const started = Date.now();
  const result = await t.wait({ sessionId, timeoutSeconds: 30, pollIntervalSeconds: 5 });
  assert.ok(Date.now() - started < 9_000);
  assert.equal(result.details.state, "ready");
  assert.match(textOf(result), /Guidance: Yes, within the same bounds\./);
});

test("stopped, expired, and exhausted sessions are never continued", async () => {
  const t = tools();
  const stopped = autoSession();
  await t.human("s-1", { sessionId: stopped, reason: "agent_request", summary: "s", question: "q" });
  fake.respond(stopped, { decision: "stop", guidance: "Stop here." });
  const ended = await t.step("s-2", { sessionId: stopped, taskName: "CheckRabi", qid: "Q00", rationale: "continue" });
  assert.equal(ended.details.state, "ended");
  assert.match(textOf(ended), /cancelled and is never reactivated/);
  const endedHuman = await t.human("s-3", { sessionId: stopped, reason: "agent_request", summary: "s", question: "q" });
  assert.match(textOf(endedHuman), /^Not recorded/);

  const expiring = autoSession();
  fake.advance(7 * 3600);
  const expired = await t.step("s-4", { sessionId: expiring, taskName: "CheckRabi", qid: "Q00", rationale: "continue" });
  assert.equal(expired.details.state, "expired");
  assert.match(textOf(expired), /expired and is never reactivated/);

  const small = autoSession({ max_actions: 1 });
  await t.step("s-5", { sessionId: small, taskName: "CheckRabi", qid: "Q00", rationale: "only" });
  const exhausted = await t.step("s-6", { sessionId: small, taskName: "CheckChevron", qid: "Q00", rationale: "more" });
  assert.equal(exhausted.details.state, "budget_exhausted");
  // A person may still be asked.
  const asked = await t.human("s-7", { sessionId: small, reason: "recovery_exhausted", summary: "Budget used.", question: "Approve a new session?" });
  assert.equal(asked.details.paused, true);
});

test("an authorized action that was never dispatched is reused, and a plan's resume stays with its runner", () => {
  const now = new Date("2026-11-21T00:00:00Z");
  const session = {
    session_id: "s", project_id: "p", chip_id: "c", created_by: "alice", status: "active", state_version: 3, action_count: 1,
    created_at: "2026-11-20T23:00:00Z", expires_at: "2026-11-21T06:00:00Z", active_intervention_id: null,
    policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 5, max_rounds_per_target: 3, allowed_overrides: {} },
  };
  const action = { action_id: "a1", action_type: "run_task", decision: "authorized", task_name: "CheckRabi", qids: ["Q00"], parameter_overrides: {}, execution_status: "not_started", created_at: "2026-11-20T23:30:00Z", reason: "", diagnosis: "" };
  const context = buildAgentLoopContext({ session, actions: [action], interventions: [], now });
  assert.deepEqual(context.unstarted, ["a1"]);
  assert.deepEqual(decideAgentStep(context, [action], { taskName: "CheckRabi", qid: "Q00" }), { kind: "reuse", actionId: "a1" });
  assert.equal(measurementKey("T", "Q", { b: 1, a: 2 }), measurementKey("T", "Q", { a: 2, b: 1 }));

  const paused = { ...session, status: "waiting_for_human", active_intervention_id: "i1" };
  const plan = { intervention_id: "i1", status: "resume_authorized", checkpoint: { nodes: [] }, attempts: [], qids: [], created_at: "2026-11-20T23:40:00Z", page_path: "/x", notification: { status: "sent" }, response: { decision: "resume", guidance: "go", responded_by: "e", responded_at: "2026-11-20T23:50:00Z" }, reason: "unknown_outcome", summary: "s", question: "q" };
  const planContext = buildAgentLoopContext({ session: paused, actions: [action], interventions: [plan], now });
  assert.equal(planContext.state, "resume_needs_plan_runner");
  assert.equal(planContext.may_run_step, false);
  assert.match(planContext.next, /qdash-agent resume-plan/);
});

const posts = (sessionId) => fake.state.requests.filter((request) => request.method === "POST" && request.path.startsWith(`/agent-sessions/${sessionId}/`)).length;
const dispatchesOf = (sessionId) => fake.state.dispatches.filter((run) => fake.state.actions.find((action) => action.action_id === run.action_id)?.session_id === sessionId);

test("session-granted writes run only for the signed-in creator of the auto session", async () => {
  const t = tools();
  // Another editor of the same project created and approved this session.
  const theirs = fake.createSession({ chip_id: "chip-001", policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 4 } }, "bob").session_id;
  const step = await t.step("o-1", { sessionId: theirs, taskName: "CheckRabi", qid: "Q00", rationale: "continue" });
  assert.equal(step.details.refused, true);
  assert.match(textOf(step), /^Not run: Session .* was created by bob, not by you \(alice\)/);
  assert.match(textOf(step), /qdash_submit_agent_action, qdash_execute_agent_action/);
  const human = await t.human("o-2", { sessionId: theirs, reason: "agent_request", summary: "s", question: "q" });
  assert.match(textOf(human), /^Not recorded: Session .* was created by bob/);
  // Discovery is no grant: listing every session shows it, but the step is still refused.
  const listed = await t.list({ mine: false });
  assert.ok(listed.details.data.some((session) => session.session_id === theirs));
  assert.ok(!(await t.list({ mine: true })).details.data.some((session) => session.session_id === theirs));
  // A name the model supplies is not an identity: unknown parameters change nothing.
  const spoofed = await t.step("o-3", { sessionId: theirs, taskName: "CheckRabi", qid: "Q00", rationale: "x", createdBy: "alice", username: "bob" });
  assert.match(textOf(spoofed), /was created by bob, not by you \(alice\)/);
  assert.equal(posts(theirs), 0);
  assert.equal(fake.state.sessions.get(theirs).status, "active");

  // QDash itself refuses the same request from another user, without recording it.
  const direct = fake.submitDirect(theirs, { idempotency_key: "direct", expected_state_version: 0, action_type: "run_task", task_name: "CheckRabi", qids: ["Q00"], autonomous: true });
  assert.equal(direct.status, 403);
  assert.equal(fake.state.sessions.get(theirs).action_count, 0);

  // When QDash cannot say who is signed in, nothing is written.
  const own = autoSession();
  for (const user of [null, "error"]) {
    fake.setCurrentUser(user);
    try {
      const unknown = await t.step(`o-4-${user}`, { sessionId: own, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
      assert.match(textOf(unknown), /^Not run: QDash did not confirm who you are signed in as/);
      const unknownHuman = await t.human(`o-5-${user}`, { sessionId: own, reason: "agent_request", summary: "s", question: "q" });
      assert.match(textOf(unknownHuman), /^Not recorded: QDash did not confirm who you are signed in as/);
    } finally {
      fake.setCurrentUser("alice");
    }
  }
  assert.equal(posts(own), 0);
  // The creator's own approved session runs, and QDash recorded the step as autonomous.
  const mine = await t.step("o-6", { sessionId: own, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
  assert.equal(mine.details.dispatched, true, textOf(mine));
  assert.equal(fake.state.actions.find((action) => action.action_id === mine.details.actionId).autonomous, true);
  const body = fake.state.requests.filter((request) => request.path.endsWith(`/actions/${mine.details.actionId}/execute`)).at(-1).body;
  assert.equal(body.autonomous, true);
});

test("two steps decided from one snapshot dispatch one measurement", async () => {
  const sessionId = autoSession();
  const t = tools();
  // Hold both proposals until both arrive, so both were decided from state version 0.
  let arrived = 0;
  let release;
  const both = new Promise((resolve) => (release = resolve));
  fake.setIntercept(async ({ method, path }) => {
    if (method === "POST" && path === `/agent-sessions/${sessionId}/actions`) {
      if (++arrived === 2) release();
      await both;
    }
  });
  let results;
  try {
    results = await Promise.all([
      t.step("c-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "one" }),
      t.step("c-2", { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "other" }),
    ]);
  } finally {
    fake.setIntercept();
  }
  const [dispatched, refused] = results[0].details.dispatched ? results : [results[1], results[0]];
  assert.equal(dispatched.details.dispatched, true, textOf(dispatched));
  assert.equal(refused.details.refused, true);
  assert.match(textOf(refused), /QDash refused the step: .*state version mismatch.*Nothing was recorded and no action budget was used/s);
  assert.equal(dispatchesOf(sessionId).length, 1);
  assert.equal(fake.state.sessions.get(sessionId).action_count, 1);
});

test("history read while another client submits is read again, and the same step reuses that action", async () => {
  const sessionId = autoSession();
  const t = tools();
  let injected;
  fake.setIntercept(async ({ method, path }) => {
    if (!injected && method === "GET" && path === `/agent-sessions/${sessionId}/actions`) {
      // Another call of the same measurement is counted between the session read and the history read.
      injected = fake.submitDirect(sessionId, { idempotency_key: "other", expected_state_version: 0, action_type: "run_task", task_name: "CheckRabi", qids: ["Q00"], autonomous: true }).payload;
    }
  });
  let result;
  try {
    result = await t.step("h-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "first" });
  } finally {
    fake.setIntercept();
  }
  assert.equal(result.details.dispatched, true, textOf(result));
  assert.equal(result.details.actionId, injected.action_id);
  assert.match(textOf(result), /^Dispatched the earlier authorized action/);
  assert.equal(fake.state.actions.filter((action) => action.session_id === sessionId).length, 1);
  assert.equal(dispatchesOf(sessionId).length, 1);
});

test("a session that keeps changing while it is read allows no step", async () => {
  const sessionId = autoSession();
  const t = tools();
  fake.setIntercept(async ({ method, path }) => {
    if (method === "GET" && path === `/agent-sessions/${sessionId}/actions`) fake.state.sessions.get(sessionId).state_version += 1;
  });
  let result;
  let read;
  try {
    result = await t.step("k-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
    read = await t.context(sessionId);
  } finally {
    fake.setIntercept();
  }
  assert.equal(result.details.refused, true);
  assert.match(textOf(result), /kept changing while it was read/);
  assert.equal(read.details.data.snapshot_consistent, false);
  assert.equal(read.details.data.may_run_step, false);
  assert.equal(posts(sessionId), 0);
});

test("QDash refuses a dispatch while another measurement of the session is being dispatched", async () => {
  const sessionId = autoSession();
  const t = tools();
  // Another client proposed a different measurement through the reviewed path.
  const other = fake.submitDirect(sessionId, { idempotency_key: "reviewed", expected_state_version: 0, action_type: "run_task", task_name: "CheckChevron", qids: ["Q00"] }).payload;
  fake.queueOutcome("CheckChevron", { status: "running" });
  fake.setIntercept(async ({ method, path }) => {
    // It is dispatched after this step was proposed and before this step's dispatch.
    if (method === "POST" && path.endsWith("/execute") && !path.includes(other.action_id)) fake.executeDirect(sessionId, other.action_id);
  });
  let result;
  try {
    result = await t.step("p-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
  } finally {
    fake.setIntercept();
  }
  assert.equal(result.details.refused, true, textOf(result));
  assert.match(textOf(result), new RegExp(`QDash refused to dispatch action .*: Action ${other.action_id} of the session is being dispatched or is still running`));
  assert.deepEqual(dispatchesOf(sessionId).map((run) => run.task_name), ["CheckChevron"]);
  // The refused action stays authorized; once the other run settled, the same step reuses it.
  fake.setExecution(other.action_id, "completed");
  const retry = await t.step("p-2", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
  assert.equal(retry.details.actionId, result.details.actionId, textOf(retry));
  assert.deepEqual(dispatchesOf(sessionId).map((run) => run.task_name), ["CheckChevron", "CheckRabi"]);
});

test("concurrent repeats within the round budget measure once more, not twice", async () => {
  const sessionId = autoSession({ max_rounds_per_target: 2 });
  const t = tools();
  const first = await t.step("rr-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "first" });
  let arrived = 0;
  let release;
  const both = new Promise((resolve) => (release = resolve));
  fake.setIntercept(async ({ method, path }) => {
    if (method === "POST" && path === `/agent-sessions/${sessionId}/actions`) {
      if (++arrived === 2) release();
      await both;
    }
  });
  let results;
  try {
    results = await Promise.all(["rr-2", "rr-3"].map((id) => t.step(id, { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "noisy", repeatOfActionId: first.details.actionId })));
  } finally {
    fake.setIntercept();
  }
  assert.equal(results.filter((result) => result.details.dispatched).length, 1, results.map(textOf).join("\n"));
  assert.equal(dispatchesOf(sessionId).length, 2);
  const third = await t.step("rr-4", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "again", repeatOfActionId: first.details.actionId });
  assert.match(textOf(third), /already ran 2 times/);
  assert.equal(dispatchesOf(sessionId).length, 2);
});

test("a QDash release that does not check autonomous steps gets no dispatch", async () => {
  const sessionId = autoSession();
  const t = tools();
  fake.setLegacyServer(true);
  let result;
  let again;
  try {
    result = await t.step("l-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
    again = await t.step("l-2", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "x" });
  } finally {
    fake.setLegacyServer(false);
  }
  assert.equal(result.details.refused, true);
  assert.match(textOf(result), /did not confirm that it checks autonomous steps/);
  // The undispatched action is not reused on that server either.
  assert.match(textOf(again), /did not confirm that it checks autonomous steps/);
  assert.equal(dispatchesOf(sessionId).length, 0);
});

const decisionsOf = (sessionId) => fake.state.decisions.filter((decision) => decision.session_id === sessionId);

test("a step records the decision on the result it follows, linked to its action, and a replay records it once", async () => {
  const sessionId = autoSession();
  const t = tools();
  fake.queueOutcome("CheckChevron", { status: "completed", candidates: [{ parameter_name: "qubit_frequency", value: 7.45 }] });
  const first = await t.step("d-1", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.5 }, rationale: "Find the frequency first." });
  // Nothing preceded the first step, so it records no decision.
  assert.equal(decisionsOf(sessionId).length, 0);
  assert.doesNotMatch(textOf(first), /Audit:/);
  const read = await t.context(sessionId);
  assert.match(textOf(read), new RegExp(`results without a decision: ${first.details.actionId}`));
  assert.match(textOf(read), new RegExp(`Results without a recorded decision: ${first.details.actionId}`));

  const params = { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Chevron found 7.45 GHz; Rabi next.", assessment: "pass", interpretation: "Chevron peak at 7.45 GHz, accepted by the gate." };
  const second = await t.step("d-2", params);
  assert.equal(second.details.dispatched, true, textOf(second));
  assert.match(textOf(second), /Audit: recorded decision decision-\d+ on action-\d+ \(next next_task\)/);
  const replay = await t.step("d-2", params);
  assert.match(textOf(replay), /Audit: decision decision-\d+ was already recorded for this step/);
  const [decision] = decisionsOf(sessionId);
  assert.equal(decisionsOf(sessionId).length, 1);
  assert.deepEqual(decision.evidence_action_ids, [first.details.actionId]);
  assert.equal(decision.next_action_id, second.details.actionId);
  assert.equal(decision.assessment, "pass");
  assert.equal(decision.interpretation, "Chevron peak at 7.45 GHz, accepted by the gate.");
  assert.equal(decision.evidence_snapshot.actions[0].execution_status, "completed");
  // A retry of the same task after a result records adjust_and_retry.
  const retry = await t.step("d-3", { sessionId, taskName: "CheckRabi", qid: "Q00", parameterOverrides: { qubit_frequency: 7.46 }, rationale: "Low contrast; retry 10 MHz up." });
  assert.equal(retry.details.dispatched, true, textOf(retry));
  assert.equal(decisionsOf(sessionId).at(-1).next_action, "adjust_and_retry");
  assert.equal(decisionsOf(sessionId).at(-1).interpretation, "Low contrast; retry 10 MHz up.");
});

test("a failed run, the escalation, the expert's answer, and the step after a restart are one audit trail", async () => {
  const sessionId = autoSession();
  fake.queueOutcome("CheckRabi", { status: "failed" });
  const before = await tools().step("e-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first." });
  const failedId = before.details.actionId;
  const asked = await tools().human("e-2", {
    sessionId,
    reason: "evaluation_failed",
    summary: "CheckRabi failed with no fit; the task knowledge has no recovery for it.",
    question: "Is the drive line connected?",
    attemptActionIds: [failedId],
    assessment: "fail",
  });
  assert.match(textOf(asked), /The session is paused/);
  assert.match(textOf(asked), /Audit: recorded escalation decision decision-\d+ on action-\d+ \(next request_human\)/);
  const escalation = decisionsOf(sessionId).at(-1);
  assert.equal(escalation.intervention_id, asked.details.interventionId);
  assert.equal(escalation.session_status_at_record, "waiting_for_human");
  // A replay of the escalation records neither a second intervention nor a second decision.
  await tools().human("e-2", { sessionId, reason: "evaluation_failed", summary: "CheckRabi failed with no fit; the task knowledge has no recovery for it.", question: "Is the drive line connected?", attemptActionIds: [failedId], assessment: "fail" });
  assert.equal(decisionsOf(sessionId).length, 1);

  // While paused the agent may still note a correction; it changes no session state.
  const version = fake.state.sessions.get(sessionId).state_version;
  const note = await tools().record("e-3", { sessionId, interpretation: "Correction: the failure message names a timeout, not a fit.", nextAction: "request_human", supersedesDecisionId: escalation.decision_id });
  assert.match(textOf(note), /^Recorded decision decision-\d+: no assessment; next request_human/);
  assert.equal(fake.state.sessions.get(sessionId).state_version, version);
  assert.equal(fake.state.sessions.get(sessionId).status, "waiting_for_human");

  fake.respond(sessionId, { guidance: "The drive line was reconnected; run CheckRabi again." });
  // A restarted pi: fresh tools and client, nothing but the session id.
  const resumed = await tools().step("e-4", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Expert reconnected the drive line; repeat Rabi.", repeatOfActionId: failedId, interpretation: "Guidance says the cause was hardware; the failed run is not evidence against the frequency." });
  assert.equal(resumed.details.dispatched, true, textOf(resumed));
  assert.equal(decisionsOf(sessionId).at(-1).next_action, "repeat");
  assert.equal(decisionsOf(sessionId).at(-1).next_action_id, resumed.details.actionId);

  const audit = await tools().audit({ sessionId });
  const text = textOf(audit);
  assert.equal(audit.details.complete, true);
  for (const kind of ["session_created", "action_proposed", "measurement", "decision", "intervention_opened", "intervention_response"]) {
    assert.match(text, new RegExp(` ${kind} \\[`), kind);
  }
  assert.match(text, /intervention_response \[human_reported, expert\]: expert chose resume: The drive line was reconnected/);
  assert.match(text, /The timeline of snapshot [0-9a-f]+ is complete; records written after the snapshot was taken are not in it/);
});

test("decision records refuse another user's session and foreign references, and an older QDash runs only steps that need no decision", async () => {
  const theirs = fake.createSession({ chip_id: "chip-001", policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto" } }, "bob").session_id;
  const other = await tools().record("x-1", { sessionId: theirs, interpretation: "x", nextAction: "stop" });
  assert.match(textOf(other), /^Not recorded: Session .* was created by bob/);
  const sessionId = autoSession();
  const foreign = await tools().record("x-2", { sessionId, interpretation: "x", nextAction: "stop", evidenceActionIds: ["action-unknown"] });
  assert.match(textOf(foreign), /^Not recorded: QDash refused the decision: .*Not actions of this session: action-unknown/);
  const unknownEvidence = await tools().step("x-3", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "x", evidenceActionIds: ["action-unknown"] });
  assert.match(textOf(unknownEvidence), /^Not run: action-unknown is not an action of session/);
  assert.equal(fake.state.actions.filter((action) => action.session_id === sessionId).length, 0);
  assert.equal(decisionsOf(sessionId).length, 0);

  fake.setNoAuditServer(true);
  try {
    const first = await tools().step("x-4", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "first" });
    // The first step follows no result, so it needs no decision and runs.
    assert.equal(first.details.dispatched, true, textOf(first));
    const read = await tools().context(sessionId);
    assert.match(textOf(read), /Audit: this QDash did not list the session's decisions/);
    const used = fake.state.sessions.get(sessionId).action_count;
    const next = await tools().step("x-5", { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "next", interpretation: "Rabi looked fine." });
    assert.equal(next.details.refused, true, textOf(next));
    assert.equal(next.details.decisionRecorded, false);
    assert.match(textOf(next), /^Not run: this QDash does not record audit decisions.*Nothing was proposed or dispatched/s);
    assert.equal(fake.state.sessions.get(sessionId).action_count, used);
    assert.equal(dispatchesOf(sessionId).length, 1);
  } finally {
    fake.setNoAuditServer(false);
  }
});

test("the audit tool reads long timelines page by page and says when it is complete", async () => {
  const sessionId = autoSession({ max_actions: 10, max_rounds_per_target: 10 });
  for (let index = 0; index < 3; index++) {
    await tools().record(`p-${index}`, { sessionId, interpretation: `note ${index}`, nextAction: "stop" });
  }
  const first = await tools().audit({ sessionId, limit: 2 });
  assert.equal(first.details.complete, false);
  assert.equal(first.details.totalEvents, 4);
  assert.match(textOf(first), /More events of snapshot [0-9a-f]+ follow: call again with cursor [0-9a-f]+:2/);
  const rest = await tools().audit({ sessionId, cursor: first.details.nextCursor, limit: 2 });
  assert.equal(rest.details.complete, true);
  assert.match(textOf(rest), /#2 .* decision .*#3 .* decision/s);
  assert.equal(rest.details.snapshotId, first.details.snapshotId);

  // A decision recorded between pages invalidates the cursor; the model is told to start over.
  const again = await tools().audit({ sessionId, limit: 2 });
  await tools().record("p-late", { sessionId, interpretation: "late note", nextAction: "stop" });
  const stale = await tools().audit({ sessionId, cursor: again.details.nextCursor, limit: 2 });
  assert.equal(stale.details.restart, true);
  assert.equal(stale.details.complete, false);
  assert.match(textOf(stale), /changed after its first page was read.*Discard the pages read so far.*without a cursor/s);
  const fresh = await tools().audit({ sessionId, limit: 10 });
  assert.equal(fresh.details.complete, true);
  assert.equal(fresh.details.totalEvents, 5);
  assert.notEqual(fresh.details.snapshotId, again.details.snapshotId);
});

/** A session whose first result is finished, so the next step must record a decision first. */
async function sessionAfterResult(t) {
  const sessionId = autoSession();
  const first = await t.step(`r-${sessionId}`, { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.5 }, rationale: "Find the frequency first." });
  assert.equal(first.details.dispatched, true, textOf(first));
  return { sessionId, firstId: first.details.actionId };
}

const rabi = (sessionId, extra = {}) => ({ sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Chevron found 7.45 GHz; Rabi next.", assessment: "pass", interpretation: "Chevron peak at 7.45 GHz.", ...extra });

test("evaluation-only evidence requires a confirmed decision before dispatch, including lost responses", async () => {
  const t = tools();
  for (const fault of [
    { status: 409, detail: "Evaluation evidence refused" },
    { drop: true },
    { status: 500, detail: "Internal Server Error", afterStore: true },
  ]) {
    const sessionId = autoSession();
    const params = {
      sessionId, taskName: "CheckRabi", qid: "Q00",
      rationale: "Follow the cited evaluation.", evaluationIds: ["eval-only"],
    };
    fake.failDecisions(fault);
    const callId = `evaluation-only-${sessionId}`;
    const blocked = await t.step(callId, params);
    assert.equal(blocked.details.refused, true, textOf(blocked));
    assert.equal(blocked.details.decisionRecorded, false);
    assert.equal(dispatchesOf(sessionId).length, 0);
    const used = fake.state.sessions.get(sessionId).action_count;
    const recovered = await t.step(callId, params);
    assert.equal(recovered.details.dispatched, true, textOf(recovered));
    assert.equal(recovered.details.actionId, blocked.details.actionId);
    assert.equal(fake.state.sessions.get(sessionId).action_count, used);
    assert.equal(dispatchesOf(sessionId).length, 1);
    assert.equal(decisionsOf(sessionId).length, 1);
    assert.deepEqual(decisionsOf(sessionId)[0].evaluation_ids, ["eval-only"]);
  }
});

test("a step whose decision QDash refuses because the audit is full dispatches nothing and says no step can follow", async () => {
  const t = tools();
  const { sessionId } = await sessionAfterResult(t);
  fake.setDecisionQuota(0);
  try {
    const used = fake.state.sessions.get(sessionId).action_count;
    const step = await t.step("q-1", rabi(sessionId));
    assert.equal(step.details.refused, true, textOf(step));
    assert.equal(step.details.decisionRecorded, false);
    assert.equal(step.details.auditFull, true);
    assert.match(textOf(step), /^Not dispatched: the session's audit is full .*Action action-\d+ is authorized but was not dispatched; nothing ran\. No further autonomous step can run/s);
    assert.doesNotMatch(textOf(step), /recorded decision|Dispatched/);
    assert.equal(dispatchesOf(sessionId).length, 1);
    // The proposal used one action; a retry reuses it instead of proposing again.
    assert.equal(fake.state.sessions.get(sessionId).action_count, used + 1);
    const retry = await t.step("q-2", rabi(sessionId));
    assert.equal(retry.details.refused, true);
    assert.equal(fake.state.sessions.get(sessionId).action_count, used + 1);
    assert.equal(dispatchesOf(sessionId).length, 1);

    // An escalation still pauses the session and reaches the expert, and says the decision is missing.
    const asked = await t.human("q-3", { sessionId, reason: "policy_limit", summary: "The audit is full.", question: "Continue in a new session?" });
    assert.equal(fake.state.sessions.get(sessionId).status, "waiting_for_human");
    assert.equal(asked.details.paused, true);
    assert.equal(asked.details.decisionRecorded, false);
    assert.equal(asked.details.auditFull, true);
    assert.match(textOf(asked), /The session is paused until an expert answers/);
    assert.match(textOf(asked), /Audit: the escalation decision was NOT recorded: QDash refused it .*audit is full.*The intervention is recorded regardless/s);
    assert.doesNotMatch(textOf(asked), /Audit: recorded/);
    assert.equal(decisionsOf(sessionId).length, 0);
  } finally {
    fake.setDecisionQuota(2000);
  }
});

test("a step whose decision QDash refuses for its evidence dispatches nothing, and the corrected step reuses the action", async () => {
  const t = tools();
  const { sessionId, firstId } = await sessionAfterResult(t);
  fake.failDecisions({ status: 409, detail: "Not evaluations of this session's task results: eval-x" });
  const used = fake.state.sessions.get(sessionId).action_count;
  const refused = await t.step("v-1", rabi(sessionId, { evaluationIds: ["eval-x"] }));
  assert.equal(refused.details.refused, true, textOf(refused));
  assert.equal(refused.details.decisionOutcome, "refused");
  assert.match(textOf(refused), /^Not dispatched: QDash refused the audit decision this step follows \(.*eval-x.*\)\. Action (action-\d+) is authorized but was not dispatched.*Correct what QDash named/s);
  assert.equal(dispatchesOf(sessionId).length, 1);
  const corrected = await t.step("v-2", rabi(sessionId));
  assert.equal(corrected.details.dispatched, true, textOf(corrected));
  assert.equal(corrected.details.actionId, refused.details.actionId);
  assert.equal(fake.state.sessions.get(sessionId).action_count, used + 1);
  assert.equal(decisionsOf(sessionId).length, 1);
  assert.deepEqual(decisionsOf(sessionId)[0].evidence_action_ids, [firstId]);
  assert.equal(decisionsOf(sessionId)[0].next_action_id, corrected.details.actionId);
});

test("an unconfirmed decision record dispatches nothing; a replay or a new call records it once and then dispatches", async () => {
  const t = tools();
  // The connection drops before QDash stores anything; the same call replays its key.
  const { sessionId } = await sessionAfterResult(t);
  fake.failDecisions({ drop: true });
  const dropped = await t.step("u-1", rabi(sessionId));
  assert.equal(dropped.details.refused, true, textOf(dropped));
  assert.equal(dropped.details.decisionOutcome, "uncertain");
  assert.match(textOf(dropped), /^Not dispatched: QDash did not confirm the audit decision this step follows .*it may or may not be stored/s);
  assert.equal(decisionsOf(sessionId).length, 0);
  assert.equal(dispatchesOf(sessionId).length, 1);
  const replay = await t.step("u-1", rabi(sessionId));
  assert.equal(replay.details.dispatched, true, textOf(replay));
  assert.equal(replay.details.actionId, dropped.details.actionId);
  assert.equal(decisionsOf(sessionId).length, 1);
  assert.equal(dispatchesOf(sessionId).length, 2);

  // QDash stores the decision but its answer is lost (500); a new call finds it by its action.
  const second = await sessionAfterResult(t);
  fake.failDecisions({ status: 500, detail: "Internal Server Error", afterStore: true });
  const lost = await t.step("u-2", rabi(second.sessionId));
  assert.equal(lost.details.refused, true, textOf(lost));
  assert.equal(lost.details.decisionOutcome, "uncertain");
  assert.equal(decisionsOf(second.sessionId).length, 1);
  assert.equal(dispatchesOf(second.sessionId).length, 1);
  const used = fake.state.sessions.get(second.sessionId).action_count;
  const recovered = await t.step("u-3", rabi(second.sessionId));
  assert.equal(recovered.details.dispatched, true, textOf(recovered));
  assert.equal(recovered.details.actionId, lost.details.actionId);
  assert.match(textOf(recovered), /Audit: decision decision-\d+ was already recorded for this step/);
  assert.equal(decisionsOf(second.sessionId).length, 1);
  assert.equal(fake.state.sessions.get(second.sessionId).action_count, used);
});

test("a step that follows a result is not proposed while QDash cannot list the session's decisions", async () => {
  const t = tools();
  const { sessionId } = await sessionAfterResult(t);
  fake.setDecisionListStatus(503);
  let step;
  try {
    step = await t.step("l-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "next" });
  } finally {
    fake.setDecisionListStatus(null);
  }
  assert.equal(step.details.refused, true, textOf(step));
  assert.match(textOf(step), /^Not run: QDash did not list the session's audit decisions .*Nothing was proposed or dispatched; try again once QDash answers/s);
  assert.equal(dispatchesOf(sessionId).length, 1);
  assert.equal(fake.state.actions.filter((action) => action.session_id === sessionId).length, 1);
});

/** QDash's form of an instant: UTC wall time without an offset, as its API returns datetimes. */
const naiveUtc = (millis) => new Date(millis).toISOString().slice(0, -1) + "000";
const MINUTE = 60_000;

test("a naive UTC expiry from QDash is read as UTC under any host zone; expired and invalid expiries refuse", async () => {
  const now = new Date("2026-11-22T02:00:00Z");
  const session = (expires_at, status = "active") => ({
    session_id: "s", project_id: "p", chip_id: "c", created_by: "alice", status, state_version: 0, action_count: 0,
    created_at: naiveUtc(now.getTime() - 5 * MINUTE), expires_at, active_intervention_id: null,
    policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 5, max_rounds_per_target: 3, allowed_overrides: {} },
  });
  const contextOf = (expires_at) => buildAgentLoopContext({ session: session(expires_at), actions: [], interventions: [], now });
  for (const zone of NON_UTC_ZONES) {
    await inZone(zone, () => {
      // Active for 30 more minutes, in every form QDash or a proxy may send.
      const soon = now.getTime() + 30 * MINUTE;
      for (const expires of [naiveUtc(soon), new Date(soon).toISOString(), "2026-11-22T11:30:00+09:00", "2026-11-21T21:30:00-05:00"]) {
        const context = contextOf(expires);
        assert.equal(context.state, "ready", `${zone}: ${expires}`);
        assert.equal(context.may_run_step, true, `${zone}: ${expires}`);
      }
      // The context names the instant unambiguously: naive gains Z, an offset is kept.
      assert.equal(contextOf(naiveUtc(soon)).session.expires_at, "2026-11-22T02:30:00.000000Z");
      assert.equal(contextOf("2026-11-22T11:30:00+09:00").session.expires_at, "2026-11-22T11:30:00+09:00");
      // Expired 30 minutes ago: refused, though the host's local reading of the naive value is in the future west of UTC.
      for (const expires of [naiveUtc(now.getTime() - 30 * MINUTE), "2026-11-22T10:30:00+09:00", naiveUtc(now.getTime())]) {
        const context = contextOf(expires);
        assert.equal(context.state, "expired", `${zone}: ${expires}`);
        assert.equal(context.may_run_step, false, `${zone}: ${expires}`);
      }
      // An expiry that is not a timestamp never extends the session.
      for (const expires of ["", "garbage", "2026-11-22", "11/22/2026 03:00", null]) {
        assert.equal(contextOf(expires).state, "expired", `${zone}: ${String(expires)}`);
      }
    });
  }
});

test("attempts and answers order by instant when QDash mixes naive and offset timestamps", async () => {
  await inZone("Asia/Tokyo", () => {
    const now = new Date("2026-11-22T03:00:00Z");
    const session = {
      session_id: "s", project_id: "p", chip_id: "c", created_by: "alice", status: "active", state_version: 3, action_count: 2,
      created_at: "2026-11-22T00:00:00", expires_at: "2026-11-22T06:00:00", active_intervention_id: null,
      policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi", "CheckChevron"], autonomy: "auto", max_actions: 5, max_rounds_per_target: 3, allowed_overrides: {} },
    };
    const action = (action_id, task_name, created_at) => ({ action_id, action_type: "run_task", decision: "authorized", task_name, qids: ["Q00"], parameter_overrides: {}, execution_status: "completed", created_at, reason: "", diagnosis: "" });
    // a-late is 02:00 UTC; a-early is 01:00 UTC written in +09:00.
    const actions = [action("a-late", "CheckChevron", "2026-11-22T02:00:00"), action("a-early", "CheckRabi", "2026-11-22T10:00:00+09:00")];
    // Answered 01:30 UTC: only a-late came after the answer.
    const answered = { intervention_id: "i1", status: "answered", attempts: [], qids: [], created_at: "2026-11-22T01:10:00", page_path: "/x", notification: { status: "sent" }, response: { decision: "continue", guidance: "go", responded_by: "e", responded_at: "2026-11-22T01:30:00" }, reason: "agent_request", summary: "s", question: "q" };
    const context = buildAgentLoopContext({ session, actions, interventions: [answered], now });
    assert.equal(context.state, "ready");
    assert.deepEqual(context.attempts.map((attempt) => attempt.action_id), ["a-early", "a-late"]);
    assert.deepEqual(context.intervention.actions_since_answer, ["a-late"]);
  });
});

test("a session QDash returns with a naive UTC expiry runs its step under Asia/Tokyo and another zone", async () => {
  for (const zone of NON_UTC_ZONES) {
    await inZone(zone, async () => {
      const sessionId = autoSession();
      // QDash returns datetimes without an offset; the fake now stores the expiry the same way.
      // An hour after creation by the fake's clock, which runs at or ahead of the real one.
      const stored = fake.state.sessions.get(sessionId);
      stored.expires_at = naiveUtc(Date.parse(stored.created_at) + 60 * MINUTE);
      fake.queueOutcome("CheckRabi", { status: "completed", candidates: [] });
      const t = tools();
      const read = await t.context(sessionId);
      assert.equal(read.details.state, "ready", `${zone}: ${textOf(read)}`);
      const step = await t.step(`tz-${zone}`, { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first." });
      assert.equal(step.details.dispatched, true, `${zone}: ${textOf(step)}`);
      const listed = await t.list({ chipId: "chip-001" });
      assert.match(textOf(listed), new RegExp(`${sessionId}: .*expires \\d{4}-\\d{2}-\\d{2}T[\\d:.]+Z`));
    });
  }
});

test("after a failed run, the context names the intervention as the stop, and a request_human decision alone says it pauses nothing", async () => {
  const sessionId = autoSession();
  fake.queueOutcome("CheckRabi", { status: "failed" });
  const failed = await tools().step("f-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first." });
  const failedId = failed.details.actionId;

  const read = textOf(await tools().context(sessionId));
  assert.match(read, new RegExp(`Action ${failedId} did not complete\\.`));
  assert.match(read, /QDash refuses every further autonomous step of this session, a repeat of the same task included, and every commit and apply under its update authority, until an expert answers an intervention that cites it: call qdash_request_agent_human now, citing it in attemptActionIds, before any wider research\./);
  assert.match(read, /Only that call opens an intervention and pauses the session/);

  // A decision that only names request_human records it and says plainly that nothing paused.
  const noted = await tools().record("f-2", { sessionId, assessment: "fail", interpretation: "CheckRabi failed; QDash reported no cause.", nextAction: "request_human", evidenceActionIds: [failedId] });
  assert.match(textOf(noted), /This decision opened no intervention and the session is not paused/);
  assert.equal(fake.state.sessions.get(sessionId).status, "active");
  // The decision covers the result, so the hint is gone; the session still runs.
  assert.doesNotMatch(textOf(await tools().context(sessionId)), /did not complete/);

  const asked = await tools().human("f-3", { sessionId, reason: "unknown_outcome", summary: "CheckRabi failed; QDash reported no cause.", question: "Retry or investigate?", attemptActionIds: [failedId] });
  assert.match(textOf(asked), /The session is paused/);
  // In a paused session the note would be false, so it is not given.
  const later = await tools().record("f-4", { sessionId, interpretation: "Waiting for the expert.", nextAction: "request_human" });
  assert.doesNotMatch(textOf(later), /opened no intervention/);
});

test("a completed run gets no failure hint", async () => {
  const sessionId = autoSession();
  fake.queueOutcome("CheckChevron", { status: "completed", candidates: [{ parameter_name: "qubit_frequency", value: 7.45 }] });
  await tools().step("c-1", { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "Chevron." });
  const read = textOf(await tools().context(sessionId));
  assert.match(read, /Results without a recorded decision/);
  assert.doesNotMatch(read, /did not complete|qdash_request_agent_human now/);
});

const GRANT = { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], apply_backend: false };

async function measuredChevron(t, sessionId, candidate = { parameter_name: "qubit_frequency", value: 7.452, qid: "Q00" }) {
  fake.queueOutcome("CheckChevron", { status: "completed", candidates: [candidate] });
  const step = await t.step(`chevron-${sessionId}`, { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency first." });
  assert.equal(step.details.dispatched, true, textOf(step));
  return step.details.actionId;
}

test("with update authority approved once, a passing result is committed without approval and the dependent step reads it", async () => {
  const sessionId = autoSession({ parameter_updates: GRANT });
  const t = tools();
  delete fake.state.calibration.Q00;
  const chevron = await measuredChevron(t, sessionId);
  const context = await t.context(sessionId);
  assert.match(textOf(context), /Parameter updates: granted for qubit_frequency from CheckChevron/);
  assert.match(textOf(context), /commit its accepted candidate with qdash_commit_agent_session_update/);

  // The dependent step waits for the update.
  const early = await t.step("rabi-early", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi next." });
  assert.equal(early.details.refused, true);
  assert.match(textOf(early), /is not committed/);

  const committed = await t.update("u-1", { sessionId, actionId: chevron, parameterName: "qubit_frequency", interpretation: "Clear Chevron peak at 7.452 GHz inside the approved range." });
  assert.equal(committed.details.committed, true, textOf(committed));
  assert.match(textOf(committed), /Committed qubit_frequency = 7\.452 on Q00 \(commit commit-\d+, was unset\) under the update authority the user approved/);
  assert.match(textOf(committed), /did not grant backend apply/);
  const commit = fake.state.commits.at(-1);
  assert.equal(commit.authority, "session_policy");
  const decision = fake.state.decisions.find((item) => item.decision_id === commit.decision_id);
  assert.deepEqual([decision.assessment, decision.next_action, decision.evidence_action_ids], ["pass", "propose_commit", [chevron]]);
  // A replay of the call commits nothing twice.
  const replay = await t.update("u-1", { sessionId, actionId: chevron, parameterName: "qubit_frequency", interpretation: "Clear Chevron peak at 7.452 GHz inside the approved range." });
  assert.equal(replay.details.commitId, committed.details.commitId, textOf(replay));
  assert.equal(fake.state.commits.filter((item) => item.session_id === sessionId).length, 1);

  const rabi = await t.step("rabi", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi on the committed frequency." });
  assert.equal(rabi.details.dispatched, true, textOf(rabi));
  assert.deepEqual(fake.state.dispatches.at(-1).calibration, { qubit_frequency: 7.452 });
});

test("without the grant, for another user, on an older QDash, or for a rejected result nothing is committed", async () => {
  const t = tools();
  const plain = autoSession();
  const plainAction = await measuredChevron(t, plain);
  const refused = await t.update("p", { sessionId: plain, actionId: plainAction, parameterName: "qubit_frequency", interpretation: "pass" });
  assert.match(textOf(refused), /^Not committed: the approval of session .* did not grant parameter updates/);

  const granted = autoSession({ parameter_updates: GRANT });
  const action = await measuredChevron(t, granted);
  fake.setCurrentUser("bob");
  try {
    const theirs = await t.update("b", { sessionId: granted, actionId: action, parameterName: "qubit_frequency", interpretation: "pass" });
    assert.match(textOf(theirs), /^Not committed: Session .* was created by alice, not by you \(bob\)/);
  } finally {
    fake.setCurrentUser("alice");
  }
  fake.setLegacyServer(true);
  try {
    const legacy = await t.update("l", { sessionId: granted, actionId: action, parameterName: "qubit_frequency", interpretation: "pass" });
    assert.match(textOf(legacy), /did not grant parameter updates, or this QDash does not support them/);
  } finally {
    fake.setLegacyServer(false);
  }
  const outside = await t.update("o", { sessionId: granted, actionId: action, parameterName: "drag_beta", interpretation: "pass" });
  assert.match(textOf(outside), /grants updates of qubit_frequency only/);

  const rejectedSession = autoSession({ parameter_updates: GRANT });
  const rejected = await measuredChevron(t, rejectedSession, { parameter_name: "qubit_frequency", value: 9.1, qid: "Q00", accepted: false });
  const gate = await t.update("g", { sessionId: rejectedSession, actionId: rejected, parameterName: "qubit_frequency", interpretation: "pass" });
  assert.match(textOf(gate), /gate rejected qubit_frequency = 9\.1 .*call qdash_request_agent_human/);
  const stillWaiting = await t.step("rabi-rejected", { sessionId: rejectedSession, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi anyway." });
  assert.match(textOf(stillWaiting), /was rejected/);
  for (const sessionId of [plain, granted, rejectedSession]) {
    assert.equal(fake.state.commits.filter((item) => item.session_id === sessionId).length, 0, sessionId);
  }
});

test("an uncertain assessment is never committed, and a failed run blocks the dependent step until an expert answers", async () => {
  const t = tools();
  const sessionId = autoSession({ parameter_updates: GRANT });
  const chevron = await measuredChevron(t, sessionId);
  await t.record("doubt", { sessionId, assessment: "inconclusive", interpretation: "Two peaks; unclear which is f01.", nextAction: "request_human", evidenceActionIds: [chevron] });
  const refused = await t.update("u", { sessionId, actionId: chevron, parameterName: "qubit_frequency", interpretation: "Looks fine now." });
  assert.match(textOf(refused), /QDash refused the update: .*never committed under the session's authority/);
  assert.equal(fake.state.commits.filter((item) => item.session_id === sessionId).length, 0);

  const failedSession = autoSession({ parameter_updates: GRANT });
  fake.queueOutcome("CheckChevron", { status: "failed", candidates: [] });
  const failed = await t.step("f", { sessionId: failedSession, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency." });
  const blocked = await t.step("f-rabi", { sessionId: failedSession, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi next." });
  assert.match(textOf(blocked), /did not complete \(failed\)/);
  const asked = await t.human("f-h", { sessionId: failedSession, reason: "unknown_outcome", summary: "Chevron failed without a known cause.", question: "Continue?", attemptActionIds: [failed.details.actionId] });
  assert.match(textOf(asked), /paused/);
  fake.respond(failedSession, { guidance: "Simulator fault cleared; continue with Rabi." });
  const after = await t.step("f-rabi-2", { sessionId: failedSession, taskName: "CheckRabi", qid: "Q00", rationale: "Expert answered; Rabi next." });
  assert.equal(after.details.dispatched, true, textOf(after));
  assert.equal(fake.state.commits.filter((item) => item.session_id === failedSession).length, 0);
});

test("a granted backend apply follows the update; it is never requested without the grant", async () => {
  const t = tools();
  const sessionId = autoSession({ parameter_updates: { ...GRANT, apply_backend: true } });
  const chevron = await measuredChevron(t, sessionId);
  const result = await t.update("a", { sessionId, actionId: chevron, parameterName: "qubit_frequency", interpretation: "Clear peak." });
  assert.equal(result.details.applied, "queued", textOf(result));
  assert.match(textOf(result), /Backend apply queued .*qdash_wait_agent_candidate_apply/);
  const apply = fake.state.requests.filter((request) => request.path.endsWith("/apply")).at(-1);
  assert.deepEqual([apply.body.autonomous, apply.body.push_to_github], [true, false]);
  assert.equal(fake.state.commits.at(-1).backend_authority, "session_policy");
});

test("the context and approval state the session's evaluator use; off never asks for qcal_evaluate", async () => {
  const { agentSessionApprovalText } = await import("../.test-dist/lib/agent-loop.js");
  const now = new Date("2026-11-22T02:00:00Z");
  const contextWith = (evaluation) =>
    buildAgentLoopContext({
      session: {
        session_id: "s", project_id: "p", chip_id: "c", created_by: "alice", status: "active", state_version: 0, action_count: 0,
        created_at: "2026-11-22T01:55:00Z", expires_at: "2026-11-22T03:00:00Z", active_intervention_id: null,
        policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 5, max_rounds_per_target: 3, allowed_overrides: {}, ...(evaluation === undefined ? {} : { evaluation }) },
      },
      actions: [],
      interventions: [],
      now,
    });
  const required = contextWith("required");
  assert.equal(required.session.scope.evaluation, "required");
  assert.match(required.next, /evaluate each result's figure with qcal_evaluate before you commit it/);
  const off = contextWith("off");
  assert.equal(off.session.scope.evaluation, "off");
  assert.match(off.next, /do not call qcal_evaluate, and do not report an evaluator verdict/);
  assert.doesNotMatch(off.next, /evaluate each result's figure/);
  // An older session keeps its earlier meaning: no mode, no new instruction.
  const legacy = contextWith(undefined);
  assert.equal(legacy.session.scope.evaluation, null);
  assert.doesNotMatch(legacy.next, /qcal_evaluate/);

  assert.match(agentSessionApprovalText("c", { qids: ["Q00"], allowed_tasks: ["CheckRabi"], evaluation: "required" }), /- evaluation: required/);
  assert.match(agentSessionApprovalText("c", { qids: ["Q00"], allowed_tasks: ["CheckRabi"] }), /- evaluation: off/);
});
