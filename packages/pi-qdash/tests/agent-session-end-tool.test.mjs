import assert from "node:assert/strict";
import { after, before, test } from "node:test";

import { QDash } from "@oqtopus-team/qdash-sdk";

import { QDashConnection } from "../.test-dist/lib/qdash-connection.js";

import { DEFERRED_TOOL_NAMES, NESTED_READ_TOOL_NAMES, REVIEWED_WRITE_TOOL_NAMES, SESSION_GRANTED_WRITE_TOOL_NAMES } from "../.test-dist/lib/tool-policy.js";
import { HOST_WRITE_APPROVAL_KEY } from "../.test-dist/lib/write-approval.js";
import { END_AGENT_SESSION_TOOL, registerAgentSessionEndTool } from "../.test-dist/tools/agent-session-end.js";
import { startFakeAgentQDash } from "./helpers/fake-agent-qdash.mjs";

let fake;
before(async () => {
  fake = await startFakeAgentQDash();
});
after(() => fake.close());

function endTool() {
  let tool;
  registerAgentSessionEndTool({ registerTool(registered) { tool = registered; } }, {
    async makeClient() {
      return new QDashConnection(new QDash({ baseUrl: fake.baseUrl, apiToken: "fixture-token" }));
    },
  });
  return tool;
}

/** One call the host approved, as the QDash Agent and pi's dialog both mark it. */
function end(id, params) {
  return endTool().execute(id, params, undefined, undefined, { hasUI: false, [HOST_WRITE_APPROVAL_KEY]: { toolCallId: id, toolName: END_AGENT_SESSION_TOOL } });
}

const textOf = (result) => result.content.map((block) => block.text).join("\n");

function session(policy = {}) {
  return fake.createSession({
    chip_id: "chip-001",
    policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 2, ...policy },
  }).session_id;
}

test("ending a session is a reviewed write the user approves, never script-callable or session-granted", async () => {
  assert.ok(REVIEWED_WRITE_TOOL_NAMES.includes(END_AGENT_SESSION_TOOL));
  assert.ok(DEFERRED_TOOL_NAMES.includes(END_AGENT_SESSION_TOOL));
  assert.ok(!NESTED_READ_TOOL_NAMES.includes(END_AGENT_SESSION_TOOL));
  assert.ok(!SESSION_GRANTED_WRITE_TOOL_NAMES.includes(END_AGENT_SESSION_TOOL));
  const sessionId = session();
  const requests = fake.state.requests.length;
  // No approval, no write: a session without UI refuses before QDash is called.
  await assert.rejects(
    endTool().execute("unapproved", { sessionId, outcome: "stopped", reason: "stop" }, undefined, undefined, { hasUI: false }),
    /requires explicit confirmation/,
  );
  assert.equal(fake.state.requests.length, requests);
  assert.equal(fake.state.sessions.get(sessionId).status, "active");
});

test("a stop ends the session, records the decision, and reports what QDash read back with its project page", async () => {
  const sessionId = session();
  const step = fake.submitDirect(sessionId, { idempotency_key: "run", expected_state_version: 0, action_type: "run_task", task_name: "CheckRabi", qids: ["Q00"] });
  fake.executeDirect(sessionId, step.payload.action_id);
  fake.setExecution(step.payload.action_id, "running");

  const result = await end("stop-call", { sessionId, outcome: "stopped", reason: "The user asked to stop the calibration" });
  const text = textOf(result);
  assert.equal(result.details.ended, true, text);
  assert.equal(result.details.status, "cancelled");
  assert.match(text, /QDash stopped agent session .*: its status is now cancelled/);
  // The running measurement is reported, and never claimed cancelled.
  assert.match(text, new RegExp(`NOT cancelled[\\s\\S]*measurement \\(action\\) ${step.payload.action_id}: running`));
  assert.match(text, /Recorded decision decision-\d+ \(next stop\)/);
  assert.match(text, new RegExp(`/agent-sessions/${sessionId}\\?project=lab-a`));
  assert.doesNotMatch(text, /agent-cp|\/cancel/);
  assert.equal(fake.state.sessions.get(sessionId).status, "cancelled");
  assert.equal(fake.state.sessions.get(sessionId).stop.reason, "The user asked to stop the calibration");
  const [decision] = fake.state.decisions.filter((item) => item.session_id === sessionId);
  assert.equal(decision.next_action, "stop");

  // A replayed call is the same stop, and records no second decision.
  const replay = await end("stop-call", { sessionId, outcome: "stopped", reason: "The user asked to stop the calibration" });
  assert.match(textOf(replay), /already stopped by this request/);
  assert.equal(fake.state.decisions.filter((item) => item.session_id === sessionId).length, 1);
  // A stop of the ended session says so and changes nothing.
  const late = await end("late", { sessionId, outcome: "stopped", reason: "again" });
  assert.match(textOf(late), /had already ended \(cancelled\); nothing changed/);
});

test("a stop of a paused session closes the expert's question", async () => {
  const sessionId = session();
  fake.submitDirect(sessionId, { idempotency_key: "human", expected_state_version: 0, action_type: "request_human", diagnosis: "Which peak?" });
  assert.equal(fake.state.sessions.get(sessionId).status, "waiting_for_human");
  const result = await end("stop-paused", { sessionId, outcome: "stopped", reason: "No longer needed" });
  assert.equal(result.details.status, "cancelled");
  assert.match(textOf(result), /Closed expert questions: int-\d+/);
});

test("a completion ends a session even when its action budget is used, and is refused while paused", async () => {
  const sessionId = session({ max_actions: 1 });
  fake.submitDirect(sessionId, { idempotency_key: "run", expected_state_version: 0, action_type: "run_task", task_name: "CheckRabi", qids: ["Q00"] });
  const done = await end("complete", { sessionId, outcome: "completed", reason: "Rabi passed; the goal is reached" });
  assert.equal(done.details.status, "completed", textOf(done));
  assert.match(textOf(done), /QDash completed agent session .*: its status is now completed/);
  assert.match(textOf(done), /next complete/);

  const paused = session();
  fake.submitDirect(paused, { idempotency_key: "human", expected_state_version: 0, action_type: "request_human", diagnosis: "?" });
  const refused = await end("complete-paused", { sessionId: paused, outcome: "completed", reason: "done" });
  assert.equal(refused.details.ended, false);
  assert.match(textOf(refused), /Not ended: QDash refused .*not active: waiting_for_human/);
  assert.equal(fake.state.sessions.get(paused).status, "waiting_for_human");
});

test("another user's stop is QDash's to allow; the decision is left to the creator", async () => {
  const sessionId = session();
  fake.setCurrentUser("bob");
  try {
    const result = await end("bob-stop", { sessionId, outcome: "stopped", reason: "Lab maintenance" });
    assert.equal(result.details.status, "cancelled");
    assert.match(textOf(result), /Decision not recorded: only alice, who created the session, records its decisions/);
    assert.equal(fake.state.sessions.get(sessionId).stop.stopped_by, "bob");
  } finally {
    fake.setCurrentUser("alice");
  }
});

test("a QDash without stop requests, or one that does not answer, is never reported as stopped", async () => {
  const sessionId = session();
  fake.setNoStopServer(true);
  try {
    const result = await end("old-server", { sessionId, outcome: "stopped", reason: "stop" });
    assert.equal(result.details.ended, false);
    assert.match(textOf(result), /Not ended: this QDash has no stop request/);
    assert.equal(fake.state.sessions.get(sessionId).status, "active");
  } finally {
    fake.setNoStopServer(false);
  }
  fake.setStopFault(500);
  try {
    const result = await end("dropped", { sessionId, outcome: "stopped", reason: "stop" });
    assert.equal(result.details.ended, false);
    assert.equal(result.details.outcomeUnknown, true);
    assert.match(textOf(result), /Not confirmed: .*may or may not have ended/);
  } finally {
    fake.setStopFault(null);
  }
  assert.equal(fake.state.sessions.get(sessionId).status, "active");
});

test("a refused stop is read by its SDK statusCode alone; a status field does not count", async () => {
  const stopFailing = (fields) => {
    let tool;
    registerAgentSessionEndTool({ registerTool(registered) { tool = registered; } }, {
      async makeClient() {
        return {
          async getAgentSession(sessionId) { return { session_id: sessionId, project_id: "p", status: "active", state_version: 1 }; },
          async stopAgentSession() { throw Object.assign(new Error("stop failed"), fields); },
        };
      },
    });
    const id = `stop-${JSON.stringify(fields)}`;
    return tool.execute(id, { sessionId: "s-1", outcome: "stopped", reason: "stop" }, undefined, undefined, { hasUI: false, [HOST_WRITE_APPROVAL_KEY]: { toolCallId: id, toolName: END_AGENT_SESSION_TOOL } });
  };
  const unsupported = /Not ended: this QDash has no stop request/;
  const unconfirmed = /Not confirmed: QDash did not confirm the stop/;

  assert.match(textOf(await stopFailing({ statusCode: 404 })), unsupported);
  // A status alone is no status: the outcome stays unknown.
  const statusOnly = await stopFailing({ status: 404 });
  assert.match(textOf(statusOnly), unconfirmed);
  assert.equal(statusOnly.details.outcomeUnknown, true);
  // Both present: statusCode decides either way.
  assert.match(textOf(await stopFailing({ statusCode: 404, status: 500 })), unsupported);
  assert.match(textOf(await stopFailing({ statusCode: 500, status: 404 })), unconfirmed);
  assert.match(textOf(await stopFailing({ statusCode: 409, status: 500 })), /Not ended: QDash refused \(stop failed\)\. The session is still active\./);
});
