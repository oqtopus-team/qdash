import assert from "node:assert/strict";
import test from "node:test";
import { QDash } from "@oqtopus-team/qdash-sdk";

import {
  firstSentence,
  formatPipelineCatalog,
  formatTaskParameters,
  formatPipelinePlan,
  problemsFromError,
  registerCalibrationPipelineTools,
} from "../.test-dist/tools/calibration-pipeline.js";
import { sdkOver } from "./helpers/sdk-session.mjs";

// What qdash_run_pipeline reports with every launch; never taken from the model.
const TOOL_ORIGIN = { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" };

const SPEC = {
  spec_version: 2,
  name: "coarse-then-coherence",
  targets: { qids: ["0", "1"] },
  steps: [
    { type: "OneQubitCheck", execution_mode: "parallel_by_mux" },
    { type: "FilterByStatus" },
    {
      type: "CustomOneQubit",
      step_name: "coherence",
      tasks: [
        { name: "CheckRamsey", call_id: "ramsey_coarse" },
        { name: "CheckRamsey", call_id: "ramsey_fine", run: { detuning: 0.0002 } },
      ],
    },
  ],
};

const call = (name, callId = name) => ({ call_id: callId, name, on_failure: "stop", settings: { run: {}, input: {} } });
const CHECK_TASKS = ["CheckRabi", "CheckRabi", "CreateHPIPulse", "CheckHPIPulse", "CheckRabi", "CreateHPIPulse", "CheckHPIPulse", "CheckT1", "CheckT2Echo", "CheckRamsey"];

const STEPS = [
  { index: 1, type: "OneQubitCheck", name: "one_qubit_check", step_id: "one_qubit_check", kind: "calibration", tasks: CHECK_TASKS, calls: CHECK_TASKS.map((name, i) => call(name, `${name}_${i}`)) },
  { index: 2, type: "FilterByStatus", name: "filter_by_status", step_id: null, kind: "transform", tasks: [], calls: [] },
  { index: 3, type: "CustomOneQubit", name: "coherence", step_id: "coherence", kind: "calibration", tasks: ["CheckRamsey", "CheckRamsey"], calls: [call("CheckRamsey", "ramsey_coarse"), call("CheckRamsey", "ramsey_fine")] },
  { index: 4, type: "FilterByMetric", name: "filter_by_t2_star", step_id: null, kind: "transform", tasks: [], calls: [], reference: { step: "coherence", call_id: "ramsey_fine" } },
];

const VALID = {
  valid: true,
  problems: [],
  warnings: [],
  backend_name: "qubex",
  spec_version: 2,
  spec: { ...SPEC },
  targets: { qids: ["0", "1"], mux_ids: [], exclude_qids: [] },
  steps: STEPS,
  task_run_count: 12,
};

function registeredTools(api, chipId = "64Qv3", projectId = "project-1", pausedSessions = []) {
  const tools = new Map();
  const client = {
    // The pause guard: the user's agent sessions waiting for an expert.
    async listAgentSessions() { return pausedSessions; },
    // Every run is recorded under its key, so the SDK first lists the user's sessions on the chip.
    api: {
      async listCalibrationSessions() {
        return { items: [{ calibration_session_id: "cs-1", chip_id: chipId, status: "open" }], has_more: false };
      },
      ...api,
    },
    // null stands for a profile without a project.
    config: { projectId: projectId ?? undefined },
    // A tool that starts a run must not follow it.
    async getExecution() { throw new Error("must not wait"); },
    async waitForExecution() { throw new Error("must not wait"); },
  };
  registerCalibrationPipelineTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    sdk: sdkOver, async makeClient() { return client; },
    async resolveChipId(_client, explicit) { return explicit ?? chipId; },
  });
  return tools;
}

// A host that collected the user's approval of call `toolCallId` in its own UI (write-approval.ts).
const approved = (toolCallId, toolName = "qdash_run_pipeline") => ({ hasUI: false, qdashWriteApproval: { toolCallId, toolName } });
const uiContext = (answer) => ({ hasUI: true, ui: { async confirm() { return answer; } } });

test("plan validates on the resolved chip and lists the resolved steps", async () => {
  const calls = [];
  const tools = registeredTools({
    async validateCalibrationPipeline(request) { calls.push(request); return VALID; },
  });
  const result = await tools.get("qdash_plan_pipeline").execute("t", { spec: SPEC });

  assert.deepEqual(calls, [{ chip_id: "64Qv3", spec: SPEC }]);
  assert.equal(result.details.valid, true);
  assert.equal(result.details.chipId, "64Qv3");
  const text = result.content[0].text;
  assert.match(text, /Pipeline 'coarse-then-coherence' on chip 64Qv3 \(backend qubex\)/);
  assert.match(text, /Targets: qubits 0, 1/);
  assert.match(text, /Valid\. 12 task calls per target/);
  assert.match(text, /1\. one_qubit_check \(OneQubitCheck\) — 10 calls: CheckRabi_0=CheckRabi, .*\+2 more/);
  assert.match(text, /2\. filter_by_status \(FilterByStatus\) — no tasks \(transform\)/);
  assert.match(text, /3\. coherence \(CustomOneQubit\) — 2 calls: ramsey_coarse=CheckRamsey, ramsey_fine=CheckRamsey/);
  assert.match(text, /4\. filter_by_t2_star \(FilterByMetric\) — reads coherence\.ramsey_fine/);
  assert.doesNotMatch(text, /Warnings/);
});

test("plan shows warnings without calling the spec invalid, and points to a migrated spec", async () => {
  const tools = registeredTools({
    async validateCalibrationPipeline() {
      return { ...VALID, warnings: [{ path: "steps[3]", message: "FilterByStatus has no step reference" }] };
    },
  });
  const warned = await tools.get("qdash_plan_pipeline").execute("t", { spec: SPEC });
  assert.match(warned.content[0].text, /Valid\./);
  assert.match(warned.content[0].text, /Warnings \(the spec is still valid\):\n- steps\[3\]: FilterByStatus has no step reference/);

  const legacy = registeredTools({
    async validateCalibrationPipeline() {
      return {
        valid: false,
        problems: [{ path: "spec_version", message: "this is a version 1 spec" }],
        backend_name: "qubex",
        spec_version: 1,
        migrated_spec: { spec_version: 2, steps: [] },
        steps: [],
      };
    },
  });
  const result = await legacy.get("qdash_plan_pipeline").execute("t", { spec: { steps: [{ type: "OneQubitCheck" }] } });
  assert.equal(result.details.valid, false);
  assert.match(result.content[0].text, /version 1 spec\. details\.data\.migrated_spec holds the same pipeline as spec_version 2/);
  assert.equal(result.details.data.migrated_spec.spec_version, 2);
});

test("plan reports problems without throwing and passes an explicit chip and backend", async () => {
  const calls = [];
  const tools = registeredTools({
    async validateCalibrationPipeline(request) {
      calls.push(request);
      return {
        ...VALID,
        valid: false,
        problems: [
          { path: "targets.qids[1]", message: "qubit '9' is not on chip 16Q" },
          { path: "steps[2].tasks[0]", message: "task 'Nope' is not available on backend 'fake'" },
        ],
      };
    },
  });
  const result = await tools.get("qdash_plan_pipeline").execute("t", { chipId: "16Q", backendName: "fake", spec: SPEC });

  assert.deepEqual(calls, [{ chip_id: "16Q", spec: SPEC, backend_name: "fake" }]);
  assert.equal(result.details.valid, false);
  assert.equal(result.details.problemCount, 2);
  assert.match(result.content[0].text, /Not valid: 2 problems/);
  assert.match(result.content[0].text, /- targets\.qids\[1\]: qubit '9' is not on chip 16Q/);
  assert.match(result.content[0].text, /Steps:/);
});

test("run requires confirmation, then reports the execution", async () => {
  const calls = [];
  const execution = {
    execution_id: "20261006-012",
    flow_run_id: "run-1",
    flow_run_url: "http://prefect/run-1",
    qdash_ui_url: "http://qdash/execution/64Qv3/20261006-012",
    message: "Calibration pipeline 'coarse-then-coherence' started",
    steps: STEPS,
    targets: VALID.targets,
    // Without a named session QDash records the run in an automatic one.
    calibration_session_id: "cs-auto",
    pipeline_run_id: "cpr-auto",
  };
  const tools = registeredTools({
    async executeCalibrationPipeline(request) { calls.push(request); return execution; },
  });
  const run = tools.get("qdash_run_pipeline");

  await assert.rejects(
    run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, uiContext(false)),
    /requires explicit confirmation/,
  );
  await assert.rejects(
    run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, { hasUI: false }),
    /requires explicit confirmation/,
  );
  assert.equal(calls.length, 0);

  const result = await run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t"));
  // Recorded under the tool call's key even without a session: QDash then creates one.
  assert.deepEqual(calls, [{ chip_id: "64Qv3", spec: SPEC, idempotency_key: "qdash_run_pipeline:t", reported_origin: TOOL_ORIGIN }]);
  assert.equal(result.details.started, true);
  assert.equal(result.details.executionId, "20261006-012");
  assert.match(result.content[0].text, /execution_id 20261006-012/);
  assert.match(result.content[0].text, /4 steps, 12 task calls per target/);
  assert.match(result.content[0].text, /qdash_wait_execution/);

  const viaUi = await run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, uiContext(true));
  assert.equal(viaUi.details.started, true);
  assert.equal(viaUi.details.data.execution_id, "20261006-012");
  assert.deepEqual(result.details.data, execution);
});

test("a run in a calibration session is recorded under a key from its tool call", async () => {
  const calls = [];
  const execution = {
    execution_id: "20261006-013",
    flow_run_id: "run-2",
    flow_run_url: "http://prefect/run-2",
    qdash_ui_url: "http://qdash/execution/64Qv3/20261006-013",
    message: "Calibration pipeline 'coarse-then-coherence' started",
    steps: STEPS,
    targets: VALID.targets,
    calibration_session_id: "cs-1",
    pipeline_run_id: "cpr-1",
    replayed: false,
  };
  let reply = execution;
  const tools = registeredTools({
    async executeCalibrationPipeline(request) { calls.push(request); return reply; },
  });
  const run = tools.get("qdash_run_pipeline");
  const params = { chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1" };
  const result = await run.execute("call-7", params, undefined, undefined, approved("call-7"));
  assert.deepEqual(calls, [{ chip_id: "64Qv3", spec: SPEC, calibration_session_id: "cs-1", idempotency_key: "qdash_run_pipeline:call-7", reported_origin: TOOL_ORIGIN }]);
  assert.equal(result.details.calibrationSessionId, "cs-1");
  assert.equal(result.details.pipelineRunId, "cpr-1");
  assert.match(result.content[0].text, /Recorded in calibration session cs-1 as pipeline run cpr-1/);

  // A replay of the same call reuses its key and says that nothing new started.
  reply = { ...execution, replayed: true };
  const again = await run.execute("call-7", params, undefined, undefined, approved("call-7"));
  assert.equal(calls[1].idempotency_key, "qdash_run_pipeline:call-7");
  assert.equal(again.details.replayed, true);
  assert.match(again.content[0].text, /^Already started/);
  assert.match(again.content[0].text, /nothing new was started/);
});

test("a run names the decision it carries out only together with its calibration session", async () => {
  const calls = [];
  const tools = registeredTools({
    async executeCalibrationPipeline(request) {
      calls.push(request);
      // QDash echoes the decision it linked; a reply without it would be refused as unknown.
      return { execution_id: "e", flow_run_id: "fr", flow_run_url: "", qdash_ui_url: "", message: "started", steps: STEPS, targets: VALID.targets, calibration_session_id: "cs-1", pipeline_run_id: "cpr-2", decision_id: request.decision_id, replayed: false };
    },
  });
  const run = tools.get("qdash_run_pipeline");
  await assert.rejects(
    run.execute("c0", { chipId: "64Qv3", spec: SPEC, decisionId: "cd-1" }, undefined, undefined, approved("c0")),
    /decisionId needs calibrationSessionId/,
  );
  assert.equal(calls.length, 0);
  const result = await run.execute("c1", { chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1", decisionId: "cd-1" }, undefined, undefined, approved("c1"));
  assert.equal(calls[0].decision_id, "cd-1");
  assert.equal(calls[0].idempotency_key, "qdash_run_pipeline:c1");
  assert.equal(result.details.decisionId, "cd-1");
});

test("a run whose launch outcome is unknown is reported, never retried", async () => {
  const error = Object.assign(new Error("conflict"), { statusCode: 409, payload: { detail: "The dispatch outcome of pipeline run cpr-1 is unknown; it may be running." } });
  const tools = registeredTools({ async executeCalibrationPipeline() { throw error; } });
  await assert.rejects(
    tools.get("qdash_run_pipeline").execute("c", { chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1" }, undefined, undefined, approved("c")),
    /Do not start this run again; no execution ID was returned, so look for the run with qdash_list_executions, passing chipId 64Qv3, and page with skip until the rows are older than this launch, and tell the user\.$/,
  );
});

test("without a project every tool keeps the server's default: the run is still confirmation-gated, then dispatched", async () => {
  const calls = [];
  const execution = { execution_id: "20261006-013", flow_run_id: "fr", flow_run_url: "", qdash_ui_url: "", message: "started", steps: STEPS, targets: VALID.targets, calibration_session_id: "cs-auto", pipeline_run_id: "cpr-auto" };
  const tools = registeredTools({
    async executeCalibrationPipeline(request) { calls.push(request); return execution; },
    async validateCalibrationPipeline(request) { calls.push(request); return VALID; },
    async getCalibrationPipelineCatalog(params) { calls.push(params); return { backend_name: "fake", step_types: [], one_qubit_execution_modes: [], tasks: {}, spec_schema: {} }; },
  }, "64Qv3", null);
  const run = tools.get("qdash_run_pipeline");
  await assert.rejects(run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  await assert.rejects(run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, uiContext(false)), /requires explicit confirmation/);
  assert.equal(calls.length, 0);

  // A model's own confirmWrite approves nothing, whatever its value.
  for (const confirmWrite of [true, "true", 1]) {
    await assert.rejects(run.execute("t", { chipId: "64Qv3", spec: SPEC, confirmWrite }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  }
  // The approval of one call does not carry over to another.
  await assert.rejects(run.execute("other", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t")), /requires explicit confirmation/);
  assert.equal(calls.length, 0);
  const viaHost = await run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t"));
  const viaUi = await run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, uiContext(true));
  for (const result of [viaHost, viaUi]) {
    assert.equal(result.details.started, true);
    assert.equal(result.details.executionId, "20261006-013");
  }
  await tools.get("qdash_plan_pipeline").execute("t", { spec: SPEC });
  await tools.get("qdash_get_pipeline_catalog").execute("t", {});
  const sent = { chip_id: "64Qv3", spec: SPEC, idempotency_key: "qdash_run_pipeline:t", reported_origin: TOOL_ORIGIN };
  assert.deepEqual(calls, [sent, sent, { chip_id: "64Qv3", spec: SPEC }, undefined]);
});

test("run turns a 422 with problems into a readable rejection and nothing else into an error", async () => {
  const rejected = Object.assign(new Error("422"), {
    statusCode: 422,
    payload: { detail: { message: "calibration pipeline spec is not valid", problems: [{ path: "steps[0].mode", message: "unknown mode" }] } },
  });
  const tools = registeredTools({
    async executeCalibrationPipeline() { throw rejected; },
  });
  const result = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t"));
  assert.equal(result.details.started, false);
  assert.equal(result.details.problemCount, 1);
  assert.match(result.content[0].text, /Nothing was started/);
  assert.match(result.content[0].text, /- steps\[0\]\.mode: unknown mode/);

  const unavailable = registeredTools({
    async executeCalibrationPipeline() { throw Object.assign(new Error("503"), { statusCode: 503 }); },
  });
  await assert.rejects(
    unavailable.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t")),
    /worker has not registered/,
  );

  const other = registeredTools({
    async executeCalibrationPipeline() { throw new Error("boom"); },
  });
  await assert.rejects(
    other.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t")),
    /boom/,
  );
});

test("catalog lists step types and tasks by type and keeps the schema in details", async () => {
  const catalog = {
    backend_name: "qubex",
    step_types: [
      { type: "OneQubitCheck", kind: "calibration", description: "Coarse one-qubit characterization.", requires: [], provides: ["one_qubit_check", "candidate_qids"], task_scope: "qubit", default_step_id: "one_qubit_check", default_tasks: [{ name: "CheckRabi" }, { name: "CheckT1" }], step_metrics: ["t1_average"] },
      { type: "FilterByStatus", kind: "transform", description: "Keep the qubits whose latest one-qubit step succeeded.", requires: ["one_qubit_check", "one_qubit_fine_tune"], provides: ["candidate_qids"], task_scope: null, default_tasks: [] },
    ],
    one_qubit_execution_modes: ["parallel_by_round", "parallel_by_mux", "manual"],
    two_qubit_execution_modes: ["automatic", "manual"],
    tasks: { qubit: ["CheckRabi", "CheckT1"], coupling: ["CheckCrossResonance"] },
    spec_version: 2,
    spec_schema: { title: "CalibrationPipelineSpec" },
  };
  const calls = [];
  const tools = registeredTools({
    async getCalibrationPipelineCatalog(params) { calls.push(params); return catalog; },
  });
  const result = await tools.get("qdash_get_pipeline_catalog").execute("t", { backendName: "qubex" });

  assert.deepEqual(calls, [{ backend_name: "qubex" }]);
  const text = result.content[0].text;
  assert.match(text, /- OneQubitCheck \[calibration qubit tasks\]: Coarse one-qubit characterization\.; default 2 calls/);
  assert.match(text, /Specs need spec_version: 2\./);
  assert.match(text, /every occurrence has its own call_id/);
  assert.match(text, /- FilterByStatus \[transform\]: .* needs one_qubit_check or one_qubit_fine_tune;/);
  assert.match(text, /- qubit \(2\): CheckRabi, CheckT1/);
  assert.match(text, /Two-qubit execution_mode values: automatic, manual/);
  assert.match(text, /"manual" requires rounds and runs them exactly as written/);
  assert.doesNotMatch(text, /CalibrationPipelineSpec/);
  assert.equal(result.details.data.spec_schema.title, "CalibrationPipelineSpec");
});

test("catalog shows declared task documentation and expands the requested tasks", async () => {
  const catalog = {
    backend_name: "qubex",
    step_types: [],
    one_qubit_execution_modes: [],
    tasks: { qubit: ["CheckRabi", "CheckT1", "CheckT2Echo"] },
    task_documentation: {
      CheckT1: {
        description: "Measures the energy relaxation time T1. It writes t1 in microseconds.",
        when_to_use: "Run it to track T1 once a half-pi pulse is calibrated.",
        prerequisites: ["Rabi parameters stored by CheckRabi."],
      },
      CheckRabi: { description: "Measures a Rabi oscillation.", when_to_use: "Run it first.", prerequisites: [] },
    },
    spec_schema: {},
  };
  const tools = registeredTools({ async getCalibrationPipelineCatalog() { return catalog; } });

  const brief = (await tools.get("qdash_get_pipeline_catalog").execute("t", {})).content[0].text;
  assert.match(brief, /Task documentation \(2 documented; pass taskNames/);
  assert.match(brief, /- CheckRabi: Measures a Rabi oscillation\.\n- CheckT1: Measures the energy relaxation time T1\./);
  assert.doesNotMatch(brief, /When to use:|Prerequisites|It writes t1/);

  const expanded = (await tools.get("qdash_get_pipeline_catalog").execute("t", { taskNames: ["CheckT1", "CheckT2Echo"] })).content[0].text;
  assert.match(expanded, /- CheckT1: Measures the energy relaxation time T1\. It writes t1 in microseconds\.\n  When to use: Run it to track T1 once a half-pi pulse is calibrated\.\n  Prerequisites \(explanatory; validation reports what is actually missing\):\n  - Rabi parameters stored by CheckRabi\./);
  assert.doesNotMatch(expanded, /References|https:/);
  assert.doesNotMatch(expanded, /When to use: Run it first\./);
  assert.match(expanded, /No declared documentation for: CheckT2Echo/);

  assert.doesNotMatch(formatPipelineCatalog({ ...catalog, task_documentation: undefined }), /Task documentation/);
  assert.equal(firstSentence("Sweeps 0.25 GHz. Then (maybe) more."), "Sweeps 0.25 GHz.");
  assert.equal(firstSentence("No terminal period"), "No terminal period");
});

test("formatting helpers cover the edge cases", () => {
  assert.match(formatPipelinePlan({ valid: true, backend_name: "fake", steps: [] }, "X"), /Pipeline on chip X/);
  assert.match(formatPipelinePlan({ valid: true, backend_name: "fake", targets: { mux_ids: [0, 1], exclude_qids: ["5"] } }, "X"), /Targets: MUX 0, 1 \(excluding 5\)/);
  assert.equal(problemsFromError(new Error("x")), null);
  assert.equal(problemsFromError({ payload: { detail: "plain string" } }), null);
  assert.deepEqual(problemsFromError({ payload: { detail: { problems: [{ path: "a", message: "b" }, { bogus: true }] } } }), [{ path: "a", message: "b" }]);
  assert.match(formatPipelineCatalog({ backend_name: "f", step_types: [], one_qubit_execution_modes: [], tasks: {}, spec_schema: {} }), /Step types:/);
});

test("a pipeline does not run on qubits of the user's agent session paused for an expert", async () => {
  const paused = [{ session_id: "s-1", chip_id: "64Qv3", status: "waiting_for_human", active_intervention_id: "int-1", policy: { qids: ["1"] } }];
  const api = { async executeCalibrationPipeline() { throw new Error("must not run"); } };
  const tools = registeredTools(api, "64Qv3", "project-1", paused);
  const result = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t"));
  assert.equal(result.details.started, false);
  assert.equal(result.details.blockedByPausedSession, true);
  assert.match(result.content[0].text, /paused for an expert on chip 64Qv3 and covers these targets/);
  // A MUX target names no qubits, so it counts as overlapping.
  const mux = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: { ...SPEC, targets: { mux_ids: [0] } } }, undefined, undefined, approved("t"));
  assert.equal(mux.details.blockedByPausedSession, true);
  // A server that cannot list sessions blocks, including one that predates the list.
  for (const [status, message] of [[500, /could not tell whether/], [503, /could not tell whether/], [404, /cannot list agent sessions \(HTTP 404; it predates GET \/agent-sessions\)/], [405, /cannot list agent sessions \(HTTP 405/]]) {
    let dispatched = 0;
    const errorClient = {
      api: { async executeCalibrationPipeline() { dispatched += 1; return { execution_id: "e-1", flow_run_id: "f", message: "" }; } },
      config: { projectId: "project-1" },
      async listAgentSessions() { const error = new Error(`HTTP ${status}`); error.statusCode = status; throw error; },
    };
    const own = new Map();
    registerCalibrationPipelineTools({ registerTool(tool) { own.set(tool.name, tool); } }, { sdk: sdkOver, async makeClient() { return errorClient; }, async resolveChipId() { return "64Qv3"; } });
    const outcome = await own.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t"));
    assert.match(outcome.content[0].text, message, String(status));
    assert.equal(outcome.details.started, false, String(status));
    assert.equal(outcome.details.blockedByPausedSession, true, String(status));
    assert.equal(dispatched, 0, String(status));
  }
});

test("a pipeline does not run when a full page of paused sessions hides older ones", async () => {
  const pausedOn = (count, qid) => Array.from({ length: count }, (_, index) => ({
    session_id: `s-${index}`, chip_id: "64Qv3", status: "waiting_for_human", active_intervention_id: `int-${index}`, policy: { qids: [qid] },
  }));
  for (const [count, started] of [[99, true], [100, false], [101, false]]) {
    let dispatched = 0;
    const api = { async executeCalibrationPipeline() { dispatched += 1; return { execution_id: "e-1", flow_run_id: "f", message: "", calibration_session_id: "cs-auto", pipeline_run_id: "cpr-auto" }; } };
    const tools = registeredTools(api, "64Qv3", "project-1", pausedOn(count, "99"));
    const result = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, approved("t"));
    assert.equal(result.details.started, started, String(count));
    assert.equal(dispatched, started ? 1 : 0, String(count));
    if (!started) {
      assert.equal(result.details.blockedByPausedSession, true, String(count));
      assert.match(result.content[0].text, /at least 100 agent sessions paused for an expert on chip 64Qv3/, String(count));
    }
  }
});

test("catalog with taskNames lists each task's declared inputs and outputs with units", async () => {
  const catalog = { backend_name: "fake", step_types: [], one_qubit_execution_modes: [], tasks: { qubit: ["CheckChevron"] }, spec_schema: {} };
  const tasks = [
    {
      name: "CheckChevron",
      input_parameters: { control_frequency: { unit: "GHz" }, readout_amplitude: { unit: "a.u." }, shots: { unit: "" } },
      output_parameters: { qubit_frequency: { unit: "GHz" }, control_amplitude: { unit: "a.u." } },
    },
  ];
  const backends = [];
  // registeredTools' client has no listTasks, standing for a task list that cannot be read.
  const tools = registeredTools({ async getCalibrationPipelineCatalog() { return catalog; } });
  const withTasks = new Map();
  const stub = {
    api: { async getCalibrationPipelineCatalog() { return catalog; } },
    config: {},
    async listTasks(backend) { backends.push(backend); return { tasks }; },
  };
  registerCalibrationPipelineTools({ registerTool(tool) { withTasks.set(tool.name, tool); } }, { sdk: sdkOver, async makeClient() { return stub; }, async resolveChipId() { return "X"; } });
  const text = (await withTasks.get("qdash_get_pipeline_catalog").execute("t", { taskNames: ["CheckChevron", "CheckMissing"] })).content[0].text;
  assert.deepEqual(backends, ["fake"]);
  assert.match(text, /Declared task parameters \(names and units as QDash stores them\):\n- CheckChevron\n  Inputs: control_frequency \(GHz\), readout_amplitude \(a\.u\.\), shots\n  Outputs: control_amplitude \(a\.u\.\), qubit_frequency \(GHz\)\n- CheckMissing: not in this backend's task list/);

  // Without taskNames nothing extra is read; a failing task list is reported, not hidden.
  const brief = (await withTasks.get("qdash_get_pipeline_catalog").execute("t", {})).content[0].text;
  assert.doesNotMatch(brief, /Declared task parameters/);
  assert.equal(backends.length, 1);
  const failing = (await tools.get("qdash_get_pipeline_catalog").execute("t", { taskNames: ["CheckChevron"] })).content[0].text;
  assert.match(failing, /Declared task parameters unavailable: /);
  assert.deepEqual(formatTaskParameters(tasks, []), []);
  assert.match(formatTaskParameters([{ name: "T" }], ["T"]).join("\n"), /Inputs: none\n  Outputs: none/);
});

// Answer the SDK's own requests here: the fake api objects above test tool presentation,
// while this contract must exercise the SDK's session preflight and post-dispatch guard.
for (const outdated of ["missing-route", "ignored-fields"]) {
  test(`associated pipeline refuses an outdated API (${outdated}) without retry`, async () => {
    const methods = [];
    const fetch = async (input, init) => {
      const request = new Request(input, init);
      methods.push(request.method);
      const isGet = request.method === "GET";
      return new Response(JSON.stringify(isGet
        ? { items: [{ calibration_session_id: "cs-1", chip_id: "64Qv3", status: "open" }], has_more: false }
        : { execution_id: "e1", flow_run_id: "f1" }), {
        status: isGet && outdated === "missing-route" ? 404 : 200,
        headers: { "Content-Type": "application/json" },
      });
    };
    const tools = new Map();
    registerCalibrationPipelineTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
      sdk: () => new QDash({ baseUrl: "http://qdash.test", apiToken: "token" }, { fetch }),
      async makeClient() { return { config: {}, async listAgentSessions() { return []; } }; },
      async resolveChipId(_client, explicit) { return explicit; },
    });
    await assert.rejects(
      tools.get("qdash_run_pipeline").execute("old", { chipId: "64Qv3", spec: SPEC, calibrationSessionId: "cs-1" }, undefined, undefined, approved("old")),
      outdated === "ignored-fields" ? /result unknown.*Do not retry automatically/ : /preflight failed; nothing dispatched/,
    );
    assert.deepEqual(methods, outdated === "missing-route" ? ["GET"] : ["GET", "POST"]);
  });
}
