import assert from "node:assert/strict";
import test from "node:test";

import {
  formatPipelineCatalog,
  formatPipelinePlan,
  problemsFromError,
  registerCalibrationPipelineTools,
} from "../.test-dist/tools/calibration-pipeline.js";

const SPEC = {
  name: "coarse-then-coherence",
  targets: { qids: ["0", "1"] },
  steps: [
    { type: "OneQubitCheck", mode: "scheduled" },
    { type: "FilterByStatus" },
    { type: "CustomOneQubit", step_name: "coherence", tasks: ["CheckT1", "CheckT2Echo"] },
  ],
};

const STEPS = [
  { index: 1, type: "OneQubitCheck", name: "one_qubit_check", kind: "calibration", tasks: ["CheckRabi", "CheckRabi", "CreateHPIPulse", "CheckHPIPulse", "CheckRabi", "CreateHPIPulse", "CheckHPIPulse", "CheckT1", "CheckT2Echo", "CheckRamsey"] },
  { index: 2, type: "FilterByStatus", name: "filter_by_status", kind: "transform", tasks: [] },
  { index: 3, type: "CustomOneQubit", name: "coherence", kind: "calibration", tasks: ["CheckT1", "CheckT2Echo"] },
];

const VALID = {
  valid: true,
  problems: [],
  backend_name: "qubex",
  spec: { ...SPEC },
  targets: { qids: ["0", "1"], mux_ids: [], exclude_qids: [] },
  steps: STEPS,
  task_run_count: 12,
};

function registeredTools(api, chipId = "64Qv3") {
  const tools = new Map();
  registerCalibrationPipelineTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() { return { api }; },
    async resolveChipId(_client, explicit) { return explicit ?? chipId; },
  });
  return tools;
}

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
  assert.match(text, /Valid\. 12 task runs per target/);
  assert.match(text, /1\. one_qubit_check \(OneQubitCheck\) — 10 tasks: CheckRabi, .*\+2 more/);
  assert.match(text, /2\. filter_by_status \(FilterByStatus\) — no tasks \(transform\)/);
  assert.match(text, /3\. coherence \(CustomOneQubit\) — 2 tasks: CheckT1, CheckT2Echo/);
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

  const result = await run.execute("t", { chipId: "64Qv3", spec: SPEC, confirmWrite: true }, undefined, undefined, { hasUI: false });
  assert.deepEqual(calls, [{ chip_id: "64Qv3", spec: SPEC }]);
  assert.equal(result.details.started, true);
  assert.equal(result.details.executionId, "20261006-012");
  assert.match(result.content[0].text, /execution_id 20261006-012/);
  assert.match(result.content[0].text, /3 steps, 12 task runs per target/);
  assert.match(result.content[0].text, /qdash_wait_execution/);

  const viaUi = await run.execute("t", { chipId: "64Qv3", spec: SPEC }, undefined, undefined, uiContext(true));
  assert.equal(viaUi.details.started, true);
});

test("run turns a 422 with problems into a readable rejection and nothing else into an error", async () => {
  const rejected = Object.assign(new Error("422"), {
    statusCode: 422,
    payload: { detail: { message: "calibration pipeline spec is not valid", problems: [{ path: "steps[0].mode", message: "unknown mode" }] } },
  });
  const tools = registeredTools({
    async executeCalibrationPipeline() { throw rejected; },
  });
  const result = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC, confirmWrite: true }, undefined, undefined, { hasUI: false });
  assert.equal(result.details.started, false);
  assert.equal(result.details.problemCount, 1);
  assert.match(result.content[0].text, /Nothing was started/);
  assert.match(result.content[0].text, /- steps\[0\]\.mode: unknown mode/);

  const unavailable = registeredTools({
    async executeCalibrationPipeline() { throw Object.assign(new Error("503"), { statusCode: 503 }); },
  });
  await assert.rejects(
    unavailable.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC, confirmWrite: true }, undefined, undefined, { hasUI: false }),
    /worker has not registered/,
  );

  const other = registeredTools({
    async executeCalibrationPipeline() { throw new Error("boom"); },
  });
  await assert.rejects(
    other.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", spec: SPEC, confirmWrite: true }, undefined, undefined, { hasUI: false }),
    /boom/,
  );
});

test("catalog lists step types and tasks by type and keeps the schema in details", async () => {
  const catalog = {
    backend_name: "qubex",
    step_types: [
      { type: "OneQubitCheck", kind: "calibration", description: "Coarse one-qubit characterization.", requires: [], provides: ["one_qubit_check", "candidate_qids"], task_scope: "qubit", default_tasks: ["CheckRabi", "CheckT1"] },
      { type: "FilterByStatus", kind: "transform", description: "Keep the qubits whose latest one-qubit step succeeded.", requires: ["one_qubit_check", "one_qubit_fine_tune"], provides: ["candidate_qids"], task_scope: null, default_tasks: [] },
    ],
    one_qubit_modes: ["synchronized", "scheduled"],
    tasks: { qubit: ["CheckRabi", "CheckT1"], coupling: ["CheckCrossResonance"] },
    spec_schema: { title: "CalibrationPipelineSpec" },
  };
  const calls = [];
  const tools = registeredTools({
    async getCalibrationPipelineCatalog(params) { calls.push(params); return catalog; },
  });
  const result = await tools.get("qdash_get_pipeline_catalog").execute("t", { backendName: "qubex" });

  assert.deepEqual(calls, [{ backend_name: "qubex" }]);
  const text = result.content[0].text;
  assert.match(text, /- OneQubitCheck \[calibration qubit tasks\]: Coarse one-qubit characterization\.; default 2 tasks/);
  assert.match(text, /- FilterByStatus \[transform\]: .* needs one_qubit_check or one_qubit_fine_tune;/);
  assert.match(text, /- qubit \(2\): CheckRabi, CheckT1/);
  assert.doesNotMatch(text, /CalibrationPipelineSpec/);
  assert.equal(result.details.data.spec_schema.title, "CalibrationPipelineSpec");
});

test("formatting helpers cover the edge cases", () => {
  assert.match(formatPipelinePlan({ valid: true, backend_name: "fake", steps: [] }, "X"), /Pipeline on chip X/);
  assert.match(formatPipelinePlan({ valid: true, backend_name: "fake", targets: { mux_ids: [0, 1], exclude_qids: ["5"] } }, "X"), /Targets: MUX 0, 1 \(excluding 5\)/);
  assert.equal(problemsFromError(new Error("x")), null);
  assert.equal(problemsFromError({ payload: { detail: "plain string" } }), null);
  assert.deepEqual(problemsFromError({ payload: { detail: { problems: [{ path: "a", message: "b" }, { bogus: true }] } } }), [{ path: "a", message: "b" }]);
  assert.match(formatPipelineCatalog({ backend_name: "f", step_types: [], one_qubit_modes: [], tasks: {}, spec_schema: {} }), /Step types:/);
});
