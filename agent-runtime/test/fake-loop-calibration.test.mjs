/**
 * The purpose-pipeline scenario of the fake-backend agent loop validation: the harness's
 * bounded approvals for a calibration session and one pipeline run, the evidence checks that
 * every step execution links back to its calibration session with the pi-qdash tool's reported
 * origin and no agent attribution, and the manual baseline that must stay unassociated. No
 * model, deployment, or credentials are used.
 */

import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";

import { PIPELINE_TOOL_ORIGIN as PI_QDASH_ORIGIN } from "../../packages/pi-qdash/extensions/tools/calibration-pipeline.ts";
import { decideApproval } from "../validation/fake-loop/approval.ts";
import { evaluateScenario } from "../validation/fake-loop/evaluate.ts";
import { calibrationCapabilities, QDashApi, runManualPipeline } from "../validation/fake-loop/qdash-api.ts";
import { baselinePipelineSpec, PIPELINE_TOOL_ORIGIN, SCENARIOS, selectScenarios } from "../validation/fake-loop/scenarios.ts";

const target = { chipId: "agentval-loop", qid: "4" };
const scenario = SCENARIOS["purpose-pipeline"];
const T0 = Date.parse("2026-11-23T00:00:00Z");
const at = (seconds) => new Date(T0 + seconds * 1000).toISOString();
const transcript = (extra = {}) => ({ toolCalls: [], approvals: [], finalText: "answer", settled: true, timedOut: false, aborted: false, exitCode: 0, durationMs: 1, totalTokens: 1, extensionErrors: 0, stderrLines: 0, ...extra });

// ---------------------------------------------------------------- approvals

const context = ({ calibrationSessions = [], approved = {}, plan = scenario.approvals } = {}) => ({
  target,
  plan,
  scenarioSessionIds: new Set(),
  scenarioCalibrationSessionIds: new Set(calibrationSessions),
  approvedCounts: approved,
});
const spec = (overrides = {}) => ({
  spec_version: 2,
  name: "t1",
  targets: { qids: ["4"] },
  steps: [{ type: "CustomOneQubit", tasks: [{ name: "CheckT1" }] }],
  ...overrides,
});
const runArgs = (extra = {}) => ({ chipId: target.chipId, spec: spec(), calibrationSessionId: "cs-1", ...extra });

test("the scenario's tool origin is pi-qdash's own constant", () => {
  assert.deepEqual({ ...PIPELINE_TOOL_ORIGIN }, { ...PI_QDASH_ORIGIN });
  assert.deepEqual(selectScenarios("purpose-pipeline").map((item) => item.id), ["purpose-pipeline"]);
  // The request states the objective and what to learn; it names no tool.
  assert.doesNotMatch(scenario.prompt(target), /qdash_/);
});

test("a calibration session is approved only on the validation chip, and only once", () => {
  const ok = decideApproval({ toolName: "qdash_create_calibration_session", args: { chipId: target.chipId, objective: "Re-check T1 of qubit 4" } }, context());
  assert.equal(ok.approve, true);
  for (const args of [
    { objective: "x" },
    { chipId: "64Qv3", objective: "x" },
    { chipId: target.chipId, objective: "  " },
    { chipId: target.chipId, objective: "x", profile: "production" },
  ]) {
    assert.equal(decideApproval({ toolName: "qdash_create_calibration_session", args }, context()).approve, false, JSON.stringify(args));
  }
  const second = { toolName: "qdash_create_calibration_session", args: { chipId: target.chipId, objective: "again" } };
  assert.equal(decideApproval(second, context({ approved: { qdash_create_calibration_session: 1 } })).approve, false);
  assert.equal(decideApproval(second, context({ calibrationSessions: ["cs-1"] })).approve, false);
  // Every other scenario declines both writes.
  for (const id of ["stored-t1", "t1-rerun", "dependent-commit", "unknown-failure"]) {
    const plan = SCENARIOS[id].approvals;
    assert.equal(decideApproval({ toolName: "qdash_create_calibration_session", args: { chipId: target.chipId, objective: "x" } }, context({ plan })).approve, false, id);
    assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args: runArgs() }, context({ plan, calibrationSessions: ["cs-1"] })).approve, false, id);
  }
});

test("a pipeline is approved only within the disposable qubit, the planned task, and the scenario's session", () => {
  const ok = decideApproval({ toolName: "qdash_run_pipeline", args: runArgs() }, context({ calibrationSessions: ["cs-1"] }));
  assert.equal(ok.approve, true, ok.reason);
  assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args: runArgs({ spec: spec({ steps: [{ type: "CustomOneQubit", tasks: ["CheckT1", "CheckT1"] }] }) }) }, context({ calibrationSessions: ["cs-1"] })).approve, true);
  const refused = {
    "no session": runArgs({ calibrationSessionId: undefined }),
    "another session": runArgs({ calibrationSessionId: "cs-other" }),
    "another chip": runArgs({ chipId: "64Qv3" }),
    "qubex backend": runArgs({ backendName: "qubex" }),
    profile: runArgs({ profile: "production" }),
    "two qubits": runArgs({ spec: spec({ targets: { qids: ["4", "5"] } }) }),
    mux: runArgs({ spec: spec({ targets: { mux_ids: [1] } }) }),
    "mux with qids": runArgs({ spec: spec({ targets: { qids: ["4"], mux_ids: [1] } }) }),
    excludes: runArgs({ spec: spec({ targets: { qids: ["4"], exclude_qids: ["5"] } }) }),
    "default tasks": runArgs({ spec: spec({ steps: [{ type: "OneQubitCheck" }] }) }),
    "other task": runArgs({ spec: spec({ steps: [{ type: "CustomOneQubit", tasks: [{ name: "CheckRabi" }] }] }) }),
    "too many calls": runArgs({ spec: spec({ steps: [{ type: "CustomOneQubit", tasks: ["CheckT1", "CheckT1", "CheckT1"] }] }) }),
    "a transform step": runArgs({ spec: spec({ steps: [{ type: "CustomOneQubit", tasks: ["CheckT1"] }, { type: "FilterByStatus" }] }) }),
    "no steps": runArgs({ spec: spec({ steps: [] }) }),
    "no spec": runArgs({ spec: undefined }),
  };
  for (const [label, args] of Object.entries(refused)) {
    assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args }, context({ calibrationSessions: ["cs-1", "cs-other"].filter((id) => label !== "another session" || id === "cs-1") })).approve, false, label);
  }
  assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args: runArgs() }, context({ calibrationSessions: ["cs-1"], approved: { qdash_run_pipeline: 1 } })).approve, false, "second run");
  // No agent session, flow, or commit is approved in this scenario.
  for (const toolName of ["qdash_create_agent_session", "qdash_execute_flow", "qdash_save_flow", "qdash_commit_agent_candidate"]) {
    assert.equal(decideApproval({ toolName, args: { chipId: target.chipId } }, context({ calibrationSessions: ["cs-1"] })).approve, false, toolName);
  }
});

// ---------------------------------------------------------------- evidence

const SESSION = "cs-1";
const RUN = "cpr-1";
const STEP = "e-step-1";
const member = { calibration_session_id: SESSION, chip_id: target.chipId, objective: "Re-check T1 of qubit 4", status: "open", via: "pipeline_run", pipeline_run_id: RUN, agent_session_id: null };
const stepView = (extra = {}) => ({ execution_id: STEP, status: "completed", username: "alice", start_at: at(30), note: { flow_run_id: "fr-1" }, agent_session: null, calibration_session: member, reported_origin: PIPELINE_TOOL_ORIGIN, ...extra });
const stepDetail = (extra = {}) => stepView({ task: [{ name: "CheckT1", qid: "4", status: "completed" }], ...extra });
const calibrationSession = (runExtra = {}) => ({
  calibration_session_id: SESSION,
  chip_id: target.chipId,
  objective: "Re-check T1 of qubit 4",
  created_by: "alice",
  status: "open",
  pipeline_runs: [
    {
      run_id: RUN,
      calibration_session_id: SESSION,
      requested_by: "alice",
      reported_origin: PIPELINE_TOOL_ORIGIN,
      dispatch_status: "dispatched",
      flow_run_id: "fr-1",
      pipeline: { status: "completed", steps: [{ index: 1, name: "t1", status: "completed", execution_id: STEP }] },
      executions: [{ execution_id: STEP, status: "completed" }],
      ...runExtra,
    },
  ],
  agent_sessions: [],
});
const baselineRow = (extra = {}) => ({ execution_id: "e-base", status: "completed", username: "alice", note: { flow_run_id: "fr-base" }, agent_session: null, calibration_session: null, reported_origin: null, ...extra });
const baseline = (rowExtra = {}, detailExtra = {}) => ({ flowRunId: "fr-base", status: "completed", listRows: [baselineRow(rowExtra)], details: [baselineRow(detailExtra)] });
const approval = (toolCallId, toolName) => ({ title: "Approve", toolName, toolCallId, confirmed: true, reason: "ok" });
const modelRun = (calls = ["create", "run", "read"], finalText = `Execution ${STEP} belongs to the objective; it is a step of a pipeline my tool (qdash_run_pipeline) launched, reported by pi-qdash, not run by an agent session.`) => {
  const all = {
    create: { toolCallId: "c1", toolName: "qdash_create_calibration_session", args: { chipId: target.chipId }, outcome: "ok" },
    run: { toolCallId: "c2", toolName: "qdash_run_pipeline", args: { calibrationSessionId: SESSION }, outcome: "ok" },
    read: { toolCallId: "c3", toolName: "qdash_get_calibration_session", args: { calibrationSessionId: SESSION }, outcome: "ok" },
    readOther: { toolCallId: "c4", toolName: "qdash_get_calibration_session", args: { calibrationSessionId: "cs-x" }, outcome: "ok" },
  };
  const toolCalls = calls.map((name) => all[name]);
  return transcript({ toolCalls, approvals: toolCalls.filter((call) => call.toolName !== "qdash_get_calibration_session").map((call) => approval(call.toolCallId, call.toolName)), finalText });
};
const evaluate = ({ initial = modelRun(), session = calibrationSession(), detail = stepDetail(), row = stepView(), chipExecutions, base = baseline(), sessions } = {}) =>
  evaluateScenario({
    scenario,
    target,
    username: "alice",
    startedAt: at(0),
    initial,
    sessions: [],
    chipExecutions: chipExecutions ?? [row],
    calibration: { sessions: sessions ?? [session], executionDetails: { [STEP]: detail }, ...(base ? { baseline: base } : {}) },
  });
const failedChecks = (verdict) => verdict.checks.filter((check) => check.gating && !check.passed).map((check) => check.id).sort();
const check = (verdict, id) => verdict.checks.find((item) => item.id === id);

test("a purpose-level pipeline passes when every record links its steps back with the reported origin", () => {
  const verdict = evaluate();
  assert.deepEqual(failedChecks(verdict), []);
  assert.equal(verdict.status, "passed");
  assert.equal(check(verdict, "reported_provenance").passed, true);
  assert.equal(check(verdict, "reported_executions_named").passed, true);
  // The agent session checks still hold: no session, no measurement, no commit.
  assert.equal(check(verdict, "session_count").passed, true);
  assert.equal(verdict.checks.some((item) => item.id === "no_unlinked_executions"), false);
});

test("a missing session, run, or read-back fails, and the model's account never gates", () => {
  // With no session there is nothing to read back either.
  assert.deepEqual(failedChecks(evaluate({ sessions: [], chipExecutions: [] })), ["calibration_session_count", "calibration_session_read_back", "pipeline_run_count"]);
  assert.deepEqual(failedChecks(evaluate({ session: { ...calibrationSession(), pipeline_runs: [] }, chipExecutions: [] })), ["pipeline_run_count"]);
  assert.deepEqual(failedChecks(evaluate({ initial: modelRun(["create", "run"]) })), ["calibration_session_read_back"]);
  assert.deepEqual(failedChecks(evaluate({ initial: modelRun(["create", "read", "run"]) })), ["calibration_session_read_back"]);
  assert.deepEqual(failedChecks(evaluate({ initial: modelRun(["create", "run", "readOther"]) })), ["calibration_session_read_back"]);
  const wrongStory = evaluate({ initial: modelRun(undefined, `Execution ${STEP} was run by an agent session.`) });
  assert.equal(wrongStory.status, "passed");
  assert.equal(check(wrongStory, "reported_provenance").passed, false);
  assert.equal(check(wrongStory, "reported_provenance").gating, false);
  const unapproved = modelRun();
  unapproved.approvals = unapproved.approvals.filter((item) => item.toolName !== "qdash_run_pipeline");
  assert.deepEqual(failedChecks(evaluate({ initial: unapproved })), ["reviewed_writes_approved"]);
});

test("a step whose link, origin, or attribution disagrees fails, in the list row or the detail", () => {
  const cases = {
    "no link in the detail": { detail: stepDetail({ calibration_session: null }) },
    "no link in the list": { row: stepView({ calibration_session: null }) },
    "another session": { row: stepView({ calibration_session: { ...member, calibration_session_id: "cs-x" } }) },
    "agent session via": { detail: stepDetail({ calibration_session: { ...member, via: "agent_session", pipeline_run_id: null } }) },
    "no origin": { row: stepView({ reported_origin: null }) },
    "another origin": { detail: stepDetail({ reported_origin: { source: "agent_tool", tool: "other", client: "pi-qdash" } }) },
    "agent attribution": { detail: stepDetail({ agent_session: { session_id: "s-1", linked: true } }) },
    "another user": { row: stepView({ username: "bob" }) },
    "out of scope task": { detail: stepDetail({ task: [{ name: "CheckRabi", qid: "4" }] }) },
    "another qubit": { detail: stepDetail({ task: [{ name: "CheckT1", qid: "5" }] }) },
    "failed step": { detail: stepDetail({ status: "failed" }) },
  };
  for (const [label, extra] of Object.entries(cases)) {
    assert.deepEqual(failedChecks(evaluate(extra)), [`pipeline_step_linked:${STEP}`], label);
  }
  assert.deepEqual(failedChecks(evaluate({ session: calibrationSession({ reported_origin: null }) })), [`pipeline_run_reported_origin:${RUN}`]);
  assert.deepEqual(failedChecks(evaluate({ session: calibrationSession({ pipeline: { status: "failed", steps: [{ index: 1, execution_id: STEP }] } }) })), [`pipeline_run_dispatched:${RUN}`]);
  assert.deepEqual(failedChecks(evaluate({ session: calibrationSession({ executions: [], pipeline: { status: "completed", steps: [] } }) })).sort(), ["chip_executions_accounted", `pipeline_run_steps:${RUN}`].sort());
});

test("an execution outside the recorded run fails, and the manual baseline must stay unassociated", () => {
  const stray = { execution_id: "e-manual", status: "completed", start_at: at(40), agent_session: null, calibration_session: null, reported_origin: null };
  assert.deepEqual(failedChecks(evaluate({ chipExecutions: [stepView(), stray] })), ["chip_executions_accounted"]);
  assert.deepEqual(failedChecks(evaluate({ base: baseline({ calibration_session: member }) })), ["baseline_unassociated"]);
  assert.deepEqual(failedChecks(evaluate({ base: baseline({}, { reported_origin: PIPELINE_TOOL_ORIGIN }) })), ["baseline_unassociated"]);
  assert.deepEqual(failedChecks(evaluate({ base: baseline({}, { agent_session: { session_id: "s", linked: true } }) })), ["baseline_unassociated"]);
  assert.deepEqual(failedChecks(evaluate({ base: { flowRunId: "fr-base", status: "completed", listRows: [], details: [] } })), ["baseline_unassociated"]);
  assert.deepEqual(failedChecks(evaluate({ base: null })), ["baseline_completed"]);
  assert.deepEqual(failedChecks(evaluate({ base: { ...baseline(), status: "failed" } })), ["baseline_completed"]);
});

// ---------------------------------------------------------------- API helpers

function serve(handler) {
  const requests = [];
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => (body += chunk));
    request.on("end", () => {
      requests.push({ method: request.method, url: request.url, body: body ? JSON.parse(body) : undefined });
      const [status, payload] = handler(request, body);
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(payload));
    });
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ url: `http://127.0.0.1:${server.address().port}`, requests, close: () => new Promise((done) => server.close(done)) })));
}

test("the scenario is blocked on a QDash without calibration sessions or reported origins", async () => {
  const full = {
    paths: { "/calibration-sessions": {}, "/calibration-sessions/{calibration_session_id}": {}, "/calibration-pipelines/execute": {} },
    components: { schemas: { ExecutePipelineRequest: { properties: { reported_origin: {} } }, ExecutionResponseSummary: { properties: { calibration_session: {}, reported_origin: {} } } } },
  };
  for (const [document, ok] of [
    [full, true],
    [{ ...full, components: { schemas: { ExecutePipelineRequest: { properties: {} }, ExecutionResponseSummary: { properties: {} } } } }, false],
    [{ ...full, paths: { "/calibration-pipelines/execute": {} } }, false],
  ]) {
    const fake = await serve(() => [200, document]);
    try {
      const result = await calibrationCapabilities(new QDashApi({ baseUrl: fake.url, token: "t", projectId: "p" }));
      assert.equal(result.ok, ok, result.detail);
    } finally {
      await fake.close();
    }
  }
});

test("the manual baseline posts a sessionless, originless pipeline and only on a validation chip", async () => {
  const fake = await serve(() => [202, { execution_id: "e-base", flow_run_id: "fr-base" }]);
  try {
    const api = new QDashApi({ baseUrl: fake.url, token: "t", projectId: "p" });
    const started = await runManualPipeline(api, target.chipId, baselinePipelineSpec(target));
    assert.deepEqual(started, { executionId: "e-base", flowRunId: "fr-base" });
    assert.equal(fake.requests.length, 1);
    const { body } = fake.requests[0];
    assert.equal(fake.requests[0].url, "/calibration-pipelines/execute");
    assert.deepEqual(Object.keys(body).sort(), ["chip_id", "spec"]);
    assert.deepEqual(body.spec.targets, { qids: ["4"] });
    // The baseline stays inside what the scenario itself may run.
    assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args: { chipId: target.chipId, spec: body.spec, calibrationSessionId: "cs-1" } }, context({ calibrationSessions: ["cs-1"] })).approve, true);
    await assert.rejects(runManualPipeline(api, "64Qv3", baselinePipelineSpec(target)), /agentval/);
    assert.equal(fake.requests.length, 1);
  } finally {
    await fake.close();
  }
});
