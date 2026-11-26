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

import { resolvePipelinePlanPreview } from "../../packages/pi-qdash/extensions/lib/pipeline-plan-preview.ts";
import { canonicalArgs } from "../../packages/pi-qdash/extensions/lib/write-approval.ts";
import { gateDialogMessage } from "../../packages/pi-qdash/extensions/lib/write-gate.ts";
import { PIPELINE_TOOL_ORIGIN as PI_QDASH_ORIGIN } from "../../packages/pi-qdash/extensions/tools/calibration-pipeline.ts";
import { decideApproval } from "../validation/fake-loop/approval.ts";
import { evaluateScenario, storedPlanProblems } from "../validation/fake-loop/evaluate.ts";
import { calibrationCapabilities, getPipelinePlan, QDashApi, runManualPipeline } from "../validation/fake-loop/qdash-api.ts";
import { baselinePipelineSpec, PIPELINE_TOOL_ORIGIN, SCENARIOS, selectScenarios, STORED_PLAN_TASKS } from "../validation/fake-loop/scenarios.ts";

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
  // Every scenario without calibration declines both writes.
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


// ---------------------------------------------------------------- stored-plan-pipeline

const storedScenario = SCENARIOS["stored-plan-pipeline"];
const PLAN = "cpp-1";
const DIGEST = `sha256:v1:${"a".repeat(64)}`;
const OTHER_DIGEST = `sha256:v1:${"b".repeat(64)}`;
const resolvedStep = (index, names, extra = {}) => ({
  index,
  type: "CustomOneQubit",
  name: `step-${index}`,
  kind: "calibration",
  tasks: names,
  calls: names.map((name) => ({ call_id: name, name, on_failure: "stop", settings: {} })),
  ...extra,
});
const filterStep = (index, extra = {}) => ({ index, type: "FilterByStatus", name: `filter-${index}`, kind: "transform", tasks: [], calls: [], reference: { step: "step-1" }, ...extra });
/** A stored plan as GET /calibration-pipelines/plans/{plan_id} returns it (PipelinePlanResponse). */
const storedPlan = ({ steps = [resolvedStep(1, ["CheckT1", "CheckT2Echo"])], specTargets = { qids: ["4"] }, ...extra } = {}) => ({
  plan_id: PLAN,
  chip_id: target.chipId,
  backend_name: "fake",
  created_by: "alice",
  created_at: at(0),
  expires_at: at(86_400),
  expired: false,
  review_version: 1,
  review_digest: DIGEST,
  spec: {
    spec_version: 2,
    name: "coherence",
    targets: specTargets,
    steps: steps.map((step) => (step.kind === "transform" ? { type: step.type, step: "step-1" } : { type: step.type, step_name: step.name, tasks: step.calls.map((call) => ({ name: call.name })) })),
  },
  target_qids: ["4"],
  steps,
  warnings: [],
  task_run_count: steps.reduce((total, step) => total + step.calls.length, 0),
  default_run_parameters: {},
  ...extra,
});
const planArgs = (extra = {}) => ({ chipId: target.chipId, planId: PLAN, calibrationSessionId: "cs-1", ...extra });
/** The exact text pi-qdash's write gate sends the RPC client for this call and plan. */
const dialogFor = async (args, plan) => {
  const preview = await resolvePipelinePlanPreview({ getPlan: async () => plan }, args, () => T0);
  return gateDialogMessage("qdash_run_pipeline", canonicalArgs(args), preview);
};
/**
 * One approval of a stored-plan run. `stored` is the plan the harness read (null: unreadable);
 * `shown` the plan the dialog showed (defaults to the same); `message` overrides the dialog text.
 */
const decidePlan = async ({ args = planArgs(), stored = storedPlan(), shown, message, approvals = storedScenario.approvals, calibrationSessions = ["cs-1"], approved = {} } = {}) => {
  const dialogMessage = message ?? (await dialogFor(planArgs(), shown ?? stored ?? storedPlan()));
  return decideApproval(
    { toolName: "qdash_run_pipeline", args, dialogMessage, ...(stored ? { storedPlan: stored } : {}) },
    { ...context({ calibrationSessions, approved, plan: approvals }), now: () => T0 },
  );
};

test("the stored-plan scenario asks for a stored plan run by reference and names no tool", () => {
  assert.deepEqual(selectScenarios("stored-plan-pipeline").map((item) => item.id), ["stored-plan-pipeline"]);
  const prompt = storedScenario.prompt(target);
  assert.doesNotMatch(prompt, /qdash_/);
  assert.match(prompt, /stored plan/);
  for (const task of STORED_PLAN_TASKS) assert.match(prompt, new RegExp(task));
  assert.equal(storedScenario.approvals.runPipeline.requirePlanReference, true);
  assert.equal(storedScenario.expect.calibration.storedPlan, true);
  assert.deepEqual([...storedScenario.expect.calibration.requiredPipelineTasks], [...STORED_PLAN_TASKS]);
  assert.equal(storedScenario.baseline, undefined);
});

test("a run of a stored plan is approved when the plan QDash keeps and the dialog shows stay in scope", async () => {
  const ok = await decidePlan();
  assert.equal(ok.approve, true, ok.reason);
  // A filter resolves to no call and runs no task; its resolution is known, so it is allowed.
  const filtered = storedPlan({ steps: [resolvedStep(1, ["CheckT1", "CheckT2Echo"]), filterStep(2)] });
  assert.equal((await decidePlan({ stored: filtered })).approve, true);
  // The calibration session approval is the purpose scenario's.
  const session = decideApproval({ toolName: "qdash_create_calibration_session", args: { chipId: target.chipId, objective: "Coherence check of qubit 4" } }, context({ plan: storedScenario.approvals }));
  assert.equal(session.approve, true);
});

/** Why each out-of-scope run of a stored plan is declined: the check meant to catch it. */
const REFUSAL_REASONS = {
  "a raw spec": "this scenario approves only a run of a stored plan by planId, not a spec written into the call",
  "both spec and planId": "the pipeline must name exactly one of a spec and a stored plan",
  "an empty planId": "the stored plan's planId must be a non-empty string",
  "no session": "the pipeline must be recorded in the calibration session this scenario created",
  "another session": "the pipeline must be recorded in the calibration session this scenario created",
  "another chip in the call": "the pipeline must run on the disposable chip",
  "qubex backend in the call": "the pipeline must run on the fake backend",
  "an unreadable plan": "the stored plan could not be read from QDash",
  "QDash answers another plan": "QDash answered for another plan than the call names",
  "no digest": "the stored plan has no review digest",
  "a malformed digest": "the stored plan has no review digest",
  "an expired plan": "the stored plan has expired",
  "past its expiry": "the stored plan has expired",
  "another chip": "the stored plan must be for the disposable chip",
  "another backend": "the stored plan must run on the fake backend",
  "another target qubit": "the pipeline must target exactly the selected qubit",
  "another starting qubit": "the stored plan must start on exactly the selected qubit",
  "two target qubits": "the pipeline must target exactly the selected qubit",
  "MUX targets": "the pipeline must target exactly the selected qubit",
  "excluded qubits": "the pipeline must target exactly the selected qubit",
  "a disallowed task": "the pipeline may only run CheckT1, CheckT2Echo",
  "too many task calls": "the pipeline may make at most 2 task call(s)",
  "a task count above the budget": "the pipeline may make at most 2 task call(s)",
  "a calibration step without calls": "every calibration step of the stored plan must resolve to task calls",
  "a transform step with calls": "a transform step of the stored plan resolves to task calls",
  "no resolved steps": "the stored plan has no resolved steps",
  "spec and resolved steps disagree": "the stored plan's resolved steps do not match its spec",
  "a dialog without the plan": "the dialog does not show the review of the stored plan the harness read",
  "a dialog showing another digest": "the dialog does not show the review of the stored plan the harness read",
  "a second run": "this scenario approves at most 1 pipeline run(s)",
};

test("a run of a stored plan is declined outside the target, tasks, budget, session, or what the dialog shows", async () => {
  const refused = {
    "a raw spec": { args: runArgs({ spec: spec({ steps: [{ type: "CustomOneQubit", tasks: ["CheckT1", "CheckT2Echo"] }] }) }) },
    "both spec and planId": { args: planArgs({ spec: spec() }) },
    "an empty planId": { args: planArgs({ planId: " " }) },
    "no session": { args: planArgs({ calibrationSessionId: undefined }) },
    "another session": { args: planArgs({ calibrationSessionId: "cs-other" }) },
    "another chip in the call": { args: planArgs({ chipId: "64Qv3" }) },
    "qubex backend in the call": { args: planArgs({ backendName: "qubex" }) },
    "an unreadable plan": { stored: null, shown: storedPlan() },
    "QDash answers another plan": { stored: storedPlan({ plan_id: "cpp-2" }), shown: storedPlan() },
    "no digest": { stored: storedPlan({ review_digest: "" }), shown: storedPlan() },
    "a malformed digest": { stored: storedPlan({ review_digest: "sha256:abc" }), shown: storedPlan() },
    "an expired plan": { stored: storedPlan({ expired: true }), shown: storedPlan() },
    "past its expiry": { stored: storedPlan({ expires_at: at(-1) }), shown: storedPlan() },
    "another chip": { stored: storedPlan({ chip_id: "agentval-other" }), shown: storedPlan() },
    "another backend": { stored: storedPlan({ backend_name: "qubex" }), shown: storedPlan() },
    "another target qubit": { stored: storedPlan({ target_qids: ["5"], specTargets: { qids: ["5"] } }) },
    "another starting qubit": { stored: storedPlan({ target_qids: ["5"] }) },
    "two target qubits": { stored: storedPlan({ target_qids: ["4", "5"], specTargets: { qids: ["4", "5"] } }) },
    "MUX targets": { stored: storedPlan({ specTargets: { mux_ids: [1] } }) },
    "excluded qubits": { stored: storedPlan({ specTargets: { qids: ["4"], exclude_qids: ["5"] } }) },
    "a disallowed task": { stored: storedPlan({ steps: [resolvedStep(1, ["CheckT1", "CheckRabi"])] }) },
    "too many task calls": { stored: storedPlan({ steps: [resolvedStep(1, ["CheckT1", "CheckT2Echo", "CheckT1"])] }) },
    "a task count above the budget": { stored: storedPlan({ task_run_count: 3 }) },
    "a calibration step without calls": { stored: storedPlan({ steps: [resolvedStep(1, ["CheckT1"]), resolvedStep(2, [])] }) },
    "a transform step with calls": { stored: storedPlan({ steps: [resolvedStep(1, ["CheckT1"]), filterStep(2, { calls: [{ call_id: "x", name: "CheckT2Echo" }] })] }) },
    "no resolved steps": { stored: storedPlan({ steps: [] }) },
    "spec and resolved steps disagree": { stored: { ...storedPlan(), steps: [resolvedStep(1, ["CheckT1"]), resolvedStep(2, ["CheckT2Echo"])] } },
    "a dialog without the plan": { message: "qdash_run_pipeline will create or modify data in QDash." },
    "a dialog showing another digest": { shown: storedPlan({ review_digest: OTHER_DIGEST }) },
    "a second run": { approved: { qdash_run_pipeline: 1 } },
  };
  for (const [label, extra] of Object.entries(refused)) {
    const calibrationSessions = label === "another session" ? ["cs-1"] : ["cs-1", "cs-other"];
    const decision = await decidePlan({ calibrationSessions, ...extra });
    assert.equal(decision.approve, false, label);
    assert.equal(decision.reason, REFUSAL_REASONS[label], label);
  }
  // The gate would show plan cpp-2 for a call naming it; the harness read cpp-1 for this call.
  const otherShown = await dialogFor(planArgs({ planId: "cpp-2" }), storedPlan({ plan_id: "cpp-2" }));
  assert.equal((await decidePlan({ message: otherShown })).approve, false, "a dialog showing another plan");
  // Every scenario without a pipeline declines a plan run too.
  for (const id of ["stored-t1", "t1-rerun", "dependent-commit", "unknown-failure"]) {
    assert.equal((await decidePlan({ approvals: SCENARIOS[id].approvals })).approve, false, id);
  }
});

test("the dialog must show exactly the plan the harness read, by whole lines, not by matching substrings", async () => {
  const gate = await dialogFor(planArgs(), storedPlan());
  assert.equal((await decidePlan({ message: gate })).approve, true);
  const declines = async (message, label) => {
    const decision = await decidePlan({ message });
    assert.equal(decision.approve, false, `${label}: ${decision.reason}`);
    return decision.reason;
  };
  // 1. A plan whose ID starts with the expected one: the harness read cpp-1, the dialog shows cpp-10.
  const prefixed = storedPlan({ plan_id: "cpp-10" });
  await declines(await dialogFor(planArgs({ planId: "cpp-10" }), prefixed), "cpp-10 for cpp-1");
  await declines(gate.replace(`Stored pipeline plan ${PLAN} `, "Stored pipeline plan cpp-10 "), "cpp-10 header in the cpp-1 review");
  // 2. Another digest is shown while the expected one sits in an unrelated note.
  const otherReview = await dialogFor(planArgs(), storedPlan({ review_digest: OTHER_DIGEST }));
  await declines(`${otherReview}\nNote: the plan you reviewed earlier had Review digest ${DIGEST}.`, "other digest with expected note");
  await declines(`${otherReview}\nReview digest ${DIGEST}`, "other digest with an expected digest line");
  // The expected review, plus another digest anywhere else in the text.
  assert.equal(await declines(gate.replace("Arguments (the approval covers", `Note: also see ${OTHER_DIGEST}.\n\nArguments (the approval covers`), "extra digest"), "the dialog shows another review digest");
  // 3. The markers only inside arbitrary text, never as the review itself.
  await declines(`Please approve. Stored pipeline plan ${PLAN} 'coherence' on chip ${target.chipId} (backend fake). Review digest ${DIGEST}; fine.`, "markers in one note");
  await declines(`Note:\nStored pipeline plan ${PLAN} 'coherence' on chip ${target.chipId} (backend fake).\nReview digest ${DIGEST}; expires ${at(86_400)}. The approval covers exactly this content.`, "marker lines without the review");
  await declines(gate.split("\n").map((line) => `> ${line}`).join("\n"), "quoted review");
  // A second plan review in the same dialog, or an argument listing for another call.
  const second = await dialogFor(planArgs({ planId: "cpp-2" }), storedPlan({ plan_id: "cpp-2" }));
  await declines(`${gate}\n\n${second}`, "two reviews");
  await declines(await dialogFor(planArgs({ calibrationSessionId: "cs-other" }), storedPlan()), "another call's arguments");
  await declines(gate.slice(0, gate.indexOf("Arguments (the approval covers")), "no argument listing");
});

test("a scenario that does not require a plan reference judges a stored plan by its own bounds", async () => {
  const t1Only = storedPlan({ steps: [resolvedStep(1, ["CheckT1"])] });
  assert.equal((await decidePlan({ stored: t1Only, approvals: scenario.approvals })).approve, true);
  // The stored-plan scenario's coherence plan runs CheckT2Echo, which purpose-pipeline does not allow.
  assert.equal((await decidePlan({ approvals: scenario.approvals })).approve, false);
  // The purpose scenario still approves a raw spec; the stored-plan scenario never does.
  assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args: runArgs() }, context({ calibrationSessions: ["cs-1"] })).approve, true);
  assert.equal(decideApproval({ toolName: "qdash_run_pipeline", args: runArgs() }, context({ calibrationSessions: ["cs-1"], plan: storedScenario.approvals })).approve, false);
});

// Evidence of a stored-plan run: the purpose fixtures, with the run naming its plan and digest.
const planStepDetail = (tasks = [{ name: "CheckT1", qid: "4", status: "completed" }, { name: "CheckT2Echo", qid: "4", status: "completed" }], extra = {}) => stepView({ task: tasks, ...extra });
const planSession = (runExtra = {}) => calibrationSession({ plan_id: PLAN, review_digest: DIGEST, ...runExtra });
const planModelRun = (runCallArgs = { chipId: target.chipId, planId: PLAN, calibrationSessionId: SESSION }, extraCalls = []) => {
  const toolCalls = [
    { toolCallId: "c1", toolName: "qdash_create_calibration_session", args: { chipId: target.chipId }, outcome: "ok" },
    { toolCallId: "c2", toolName: "codemode", args: { code: "..." }, outcome: "ok" },
    { toolCallId: "c3", toolName: "qdash_run_pipeline", args: runCallArgs, outcome: "ok" },
    { toolCallId: "c4", toolName: "qdash_wait_execution", args: { executionId: STEP }, outcome: "ok" },
    ...extraCalls,
  ];
  const writes = toolCalls.filter((call) => ["qdash_create_calibration_session", "qdash_run_pipeline"].includes(call.toolName));
  return transcript({ toolCalls, approvals: writes.map((call) => approval(call.toolCallId, call.toolName)), finalText: `Plan ${PLAN} (review digest ${DIGEST}) ran as ${STEP}.` });
};
const evaluatePlan = ({ initial = planModelRun(), session = planSession(), detail = planStepDetail(), row = stepView(), plans = { [PLAN]: storedPlan() }, sessions, chipExecutions } = {}) =>
  evaluateScenario({
    scenario: storedScenario,
    target,
    username: "alice",
    startedAt: at(0),
    initial,
    sessions: [],
    chipExecutions: chipExecutions ?? [row],
    calibration: { sessions: sessions ?? [session], executionDetails: { [STEP]: detail }, plans },
  });

test("a stored-plan run passes when QDash records the plan and digest it ran, inside the target and tasks", () => {
  const verdict = evaluatePlan();
  assert.deepEqual(failedChecks(verdict), []);
  assert.equal(verdict.status, "passed");
  assert.equal(check(verdict, `pipeline_run_stored_plan:${RUN}`).actual, `plan ${PLAN}, digest ${DIGEST}`);
  assert.equal(check(verdict, "pipeline_run_by_plan_reference").passed, true);
  for (const task of STORED_PLAN_TASKS) assert.equal(check(verdict, `pipeline_task_completed:${task}`).passed, true, task);
  assert.equal(check(verdict, "plan_preparation").gating, false);
  // No baseline is planned, so none is judged; the read-back is not required here.
  assert.equal(verdict.checks.some((item) => item.id.startsWith("baseline_")), false);
  assert.equal(verdict.checks.some((item) => item.id === "calibration_session_read_back"), false);
  // A filter step in the plan runs no task and still passes.
  assert.deepEqual(failedChecks(evaluatePlan({ plans: { [PLAN]: storedPlan({ steps: [resolvedStep(1, ["CheckT1", "CheckT2Echo"]), filterStep(2)] }) } })), []);
});

test("a run without a stored plan, or with a plan that disagrees with the run or the scope, fails", () => {
  const storedCheck = `pipeline_run_stored_plan:${RUN}`;
  // Started from a spec: QDash records no plan on the run, and the call named none.
  const specCall = { chipId: target.chipId, spec: spec(), calibrationSessionId: SESSION };
  assert.deepEqual(failedChecks(evaluatePlan({ initial: planModelRun(specCall), session: calibrationSession(), plans: {} })), ["pipeline_run_by_plan_reference", storedCheck].sort());
  // The run records no plan even though the call named one.
  assert.deepEqual(failedChecks(evaluatePlan({ session: calibrationSession() })), ["pipeline_run_by_plan_reference", storedCheck].sort());
  // The call carried a spec beside the planId.
  assert.deepEqual(failedChecks(evaluatePlan({ initial: planModelRun({ chipId: target.chipId, planId: PLAN, spec: spec(), calibrationSessionId: SESSION }) })), ["pipeline_run_by_plan_reference"]);
  // The run carries out a plan no call named.
  assert.deepEqual(failedChecks(evaluatePlan({ initial: planModelRun({ chipId: target.chipId, planId: "cpp-2", calibrationSessionId: SESSION }) })), ["pipeline_run_by_plan_reference"]);
  // No run call went through at all.
  const noRun = planModelRun();
  noRun.toolCalls = noRun.toolCalls.filter((call) => call.toolName !== "qdash_run_pipeline");
  noRun.approvals = noRun.approvals.filter((item) => item.toolName !== "qdash_run_pipeline");
  assert.deepEqual(failedChecks(evaluatePlan({ initial: noRun })), ["pipeline_run_by_plan_reference"]);
  const cases = {
    "a digest the stored plan does not have": { session: planSession({ review_digest: OTHER_DIGEST }) },
    "no digest on the run": { session: planSession({ review_digest: null }) },
    "an unreadable plan": { plans: {} },
    "a plan for another chip": { plans: { [PLAN]: storedPlan({ chip_id: "agentval-other" }) } },
    "a plan stored by another user": { plans: { [PLAN]: storedPlan({ created_by: "bob" }) } },
    "a plan on another qubit": { plans: { [PLAN]: storedPlan({ target_qids: ["5"] }) } },
    "a plan on two qubits": { plans: { [PLAN]: storedPlan({ target_qids: ["4", "5"] }) } },
    "a plan calling a disallowed task": { plans: { [PLAN]: storedPlan({ steps: [resolvedStep(1, ["CheckT1", "CheckRabi"])] }) } },
    "a plan without calls": { plans: { [PLAN]: storedPlan({ steps: [filterStep(1)] }) } },
    "QDash answers another plan": { plans: { [PLAN]: storedPlan({ plan_id: "cpp-2" }) } },
  };
  for (const [label, extra] of Object.entries(cases)) {
    assert.deepEqual(failedChecks(evaluatePlan(extra)), [storedCheck], label);
  }
});

test("a stored-plan run whose steps leave the allowed tasks or the qubit, or skip a required task, fails", () => {
  const step = `pipeline_step_linked:${STEP}`;
  const t1 = { name: "CheckT1", qid: "4", status: "completed" };
  assert.deepEqual(failedChecks(evaluatePlan({ detail: planStepDetail([t1, { name: "CheckRabi", qid: "4", status: "completed" }]) })), [step, "pipeline_task_completed:CheckT2Echo"].sort());
  assert.deepEqual(failedChecks(evaluatePlan({ detail: planStepDetail([t1, { name: "CheckT2Echo", qid: "5", status: "completed" }]) })), [step, "pipeline_task_completed:CheckT2Echo"].sort());
  assert.deepEqual(failedChecks(evaluatePlan({ detail: planStepDetail([t1]) })), ["pipeline_task_completed:CheckT2Echo"]);
  const failedEcho = evaluatePlan({ detail: planStepDetail([t1, { name: "CheckT2Echo", qid: "4", status: "failed" }]) });
  assert.deepEqual(failedChecks(failedEcho), ["pipeline_task_completed:CheckT2Echo"]);
  assert.equal(check(failedEcho, "pipeline_task_completed:CheckT2Echo").actual, "ran, never completed on the qubit");
  // The tool's reported origin still gates.
  assert.deepEqual(failedChecks(evaluatePlan({ session: planSession({ reported_origin: null }) })), [`pipeline_run_reported_origin:${RUN}`]);
  assert.deepEqual(failedChecks(evaluatePlan({ row: stepView({ reported_origin: { source: "agent_tool", tool: "qdash_run_pipeline", client: "other" } }) })), [step]);
  // An execution outside the recorded run.
  const stray = { execution_id: "e-manual", status: "completed", start_at: at(40), agent_session: null, calibration_session: null, reported_origin: null };
  assert.deepEqual(failedChecks(evaluatePlan({ chipExecutions: [stepView(), stray] })), ["chip_executions_accounted"]);
});

test("storedPlanProblems names each disagreement", () => {
  const evidence = { target, username: "alice" };
  assert.deepEqual(storedPlanProblems({ plan_id: PLAN, review_digest: DIGEST }, storedPlan(), evidence, STORED_PLAN_TASKS), []);
  assert.deepEqual(storedPlanProblems({ plan_id: null, review_digest: null }, undefined, evidence, STORED_PLAN_TASKS), ["the run records no plan_id (started from a spec)", "the run records no review digest"]);
  assert.deepEqual(storedPlanProblems({ plan_id: PLAN, review_digest: DIGEST }, undefined, evidence, STORED_PLAN_TASKS), [`plan ${PLAN} could not be read from QDash`]);
  assert.deepEqual(
    storedPlanProblems({ plan_id: PLAN, review_digest: DIGEST }, storedPlan({ review_digest: OTHER_DIGEST, target_qids: ["5"], steps: [resolvedStep(1, ["CheckRabi"])] }), evidence, STORED_PLAN_TASKS),
    [`the stored plan's digest is ${OTHER_DIGEST}`, "plan starts on 5", "plan calls CheckRabi"],
  );
});

test("the harness reads a stored plan by its encoded ID and blocks a QDash without stored plans on runs", async () => {
  const fake = await serve(() => [200, storedPlan()]);
  try {
    const api = new QDashApi({ baseUrl: fake.url, token: "t", projectId: "p" });
    assert.equal((await getPipelinePlan(api, "cpp/1")).plan_id, PLAN);
    assert.equal(fake.requests[0].method, "GET");
    assert.equal(fake.requests[0].url, "/calibration-pipelines/plans/cpp%2F1");
  } finally {
    await fake.close();
  }
  const paths = {
    "/calibration-sessions": {},
    "/calibration-sessions/{calibration_session_id}": {},
    "/calibration-pipelines/execute": {},
    "/calibration-pipelines/plans": {},
    "/calibration-pipelines/plans/{plan_id}": {},
    "/calibration-pipelines/plans/{plan_id}/execute": {},
  };
  const schemas = {
    ExecutePipelineRequest: { properties: { reported_origin: {} } },
    ExecutionResponseSummary: { properties: { calibration_session: {}, reported_origin: {} } },
    CalibrationPipelineRunResponse: { properties: { plan_id: {}, review_digest: {} } },
  };
  const { "/calibration-pipelines/plans/{plan_id}/execute": _execute, ...noPlanExecute } = paths;
  for (const [document, storedOk, purposeOk] of [
    [{ paths, components: { schemas } }, true, true],
    [{ paths: noPlanExecute, components: { schemas } }, false, true],
    [{ paths, components: { schemas: { ...schemas, CalibrationPipelineRunResponse: { properties: { run_id: {} } } } } }, false, true],
  ]) {
    const fakeApi = await serve(() => [200, document]);
    try {
      const api = new QDashApi({ baseUrl: fakeApi.url, token: "t", projectId: "p" });
      const stored = await calibrationCapabilities(api, { storedPlan: true });
      assert.equal(stored.ok, storedOk, stored.detail);
      assert.equal((await calibrationCapabilities(api)).ok, purposeOk);
    } finally {
      await fakeApi.close();
    }
  }
});
