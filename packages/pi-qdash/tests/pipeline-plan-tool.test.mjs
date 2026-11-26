/**
 * Stored pipeline plans: qdash_create_pipeline_plan stores a proposal, and
 * qdash_run_pipeline({ planId }) runs only the plan the host fetched and the
 * user approved, with that plan's review digest, never one from the model.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { pipelinePlanKey, registerCalibrationPipelineTools } from "../.test-dist/tools/calibration-pipeline.js";
import {
  formatPlanApprovalPreview,
  planBindingProblem,
  resolvePipelinePlanPreview,
  runPipelineArgumentProblem,
} from "../.test-dist/lib/pipeline-plan-preview.js";
import { preApprovalProblems } from "../.test-dist/lib/agent-session-policy.js";
import { canonicalArgs, hasGateApproval, HOST_WRITE_APPROVAL_KEY, recordGateApproval } from "../.test-dist/lib/write-approval.js";
import { installQDashWriteGate } from "../.test-dist/lib/write-gate.js";
import { sdkOver } from "./helpers/sdk-session.mjs";

const DIGEST = `sha256:v1:${"a".repeat(64)}`;
const OTHER_DIGEST = `sha256:v1:${"b".repeat(64)}`;
const SPEC = { spec_version: 2, name: "nightly", targets: { mux_ids: [0] }, steps: [{ type: "OneQubitCheck" }] };
const PLAN = {
  plan_id: "cpp-1",
  chip_id: "64Qv3",
  backend_name: "qubex",
  created_by: "alice",
  created_at: "2026-11-26T00:00:00Z",
  expires_at: "2999-01-01T00:00:00Z",
  expired: false,
  review_version: 1,
  review_digest: DIGEST,
  spec: SPEC,
  targets: { qids: [], mux_ids: [0], exclude_qids: [] },
  target_qids: ["0", "1", "2", "3"],
  steps: [
    {
      index: 1,
      type: "OneQubitCheck",
      name: "one_qubit_check",
      step_id: "one_qubit_check",
      kind: "calibration",
      tasks: ["CheckRabi"],
      calls: [{ call_id: "CheckRabi", name: "CheckRabi", on_failure: "stop", settings: { run: { shots: { value: 1024 } } } }],
    },
  ],
  warnings: [{ path: "steps[0]", message: "probably unintended" }],
  task_run_count: 1,
  default_run_parameters: { interval: 153600 },
  task_parameters: {},
  replayed: false,
};
const DISPATCHED = {
  execution_id: "exec-1",
  flow_run_id: "run-1",
  flow_run_url: "",
  qdash_ui_url: "",
  message: "started",
  steps: PLAN.steps,
  calibration_session_id: "cs-auto",
  pipeline_run_id: "cpr-1",
  plan_id: "cpp-1",
  review_digest: DIGEST,
};

function registeredTools(api, { paused = [] } = {}) {
  const tools = new Map();
  const client = {
    async listAgentSessions() { return paused; },
    api: { async listCalibrationSessions() { return { items: [], has_more: false }; }, ...api },
    config: { projectId: "project-1" },
  };
  registerCalibrationPipelineTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    sdk: sdkOver,
    async makeClient() { return client; },
    async resolveChipId(_client, explicit) { return explicit ?? "64Qv3"; },
  });
  return tools;
}

const previewOf = (plan = PLAN) => resolvePipelinePlanPreview({ async getPlan() { return plan; } }, { planId: plan.plan_id, chipId: plan.chip_id });
const hostApproved = (toolCallId, preview) => ({ hasUI: false, [HOST_WRITE_APPROVAL_KEY]: { toolCallId, toolName: "qdash_run_pipeline", ...(preview ? { preview } : {}) } });

test("creating a plan stores it under a key from the tool call and returns its ID", async () => {
  const requests = [];
  const tools = registeredTools({ async createCalibrationPipelinePlan(body) { requests.push(body); return PLAN; } });
  const result = await tools.get("qdash_create_pipeline_plan").execute("call-7", { spec: SPEC });
  assert.deepEqual(requests, [{ chip_id: "64Qv3", spec: SPEC, idempotency_key: pipelinePlanKey("call-7") }]);
  assert.equal(pipelinePlanKey("call-7"), "qdash_create_pipeline_plan:call-7");
  assert.equal(result.details.data.plan_id, "cpp-1");
  assert.equal(result.details.stored, true);
  assert.match(result.content[0].text, /Stored pipeline plan cpp-1 'nightly'/);
  assert.match(result.content[0].text, /qdash_run_pipeline\(\{ chipId: "64Qv3", planId: "cpp-1" \}\)/);
});

test("an invalid spec stores no plan and returns its problems as data", async () => {
  const tools = registeredTools({
    async createCalibrationPipelinePlan() {
      const error = new Error("422");
      error.statusCode = 422;
      error.payload = { detail: { message: "not valid", problems: [{ path: "targets.qids[0]", message: "unknown" }] } };
      throw error;
    },
  });
  const result = await tools.get("qdash_create_pipeline_plan").execute("c", { spec: SPEC });
  assert.equal(result.details.stored, false);
  assert.deepEqual(result.details.data.problems, [{ path: "targets.qids[0]", message: "unknown" }]);
});

test("a run names exactly one of a spec and a plan, before anyone is asked", () => {
  assert.match(runPipelineArgumentProblem({ chipId: "c", spec: {}, planId: "p" }), /exactly one/);
  assert.match(runPipelineArgumentProblem({ chipId: "c" }), /exactly one/);
  assert.match(runPipelineArgumentProblem({ chipId: "c", planId: " " }), /non-empty/);
  assert.equal(runPipelineArgumentProblem({ chipId: "c", planId: "p" }), null);
  assert.match(preApprovalProblems("qdash_run_pipeline", { chipId: "c", spec: {}, planId: "p" }), /exactly one/);
});

test("the preview refuses an expired plan and one for another chip or backend", async () => {
  await assert.rejects(previewOf({ ...PLAN, expired: true }), /expired/);
  await assert.rejects(previewOf({ ...PLAN, expires_at: "2000-01-01T00:00:00Z" }), /expired/);
  await assert.rejects(
    resolvePipelinePlanPreview({ async getPlan() { return PLAN; } }, { planId: "cpp-1", chipId: "16Qv1" }),
    /for chip 64Qv3, not 16Qv1/,
  );
  await assert.rejects(
    resolvePipelinePlanPreview({ async getPlan() { return PLAN; } }, { planId: "cpp-1", chipId: "64Qv3", backendName: "fake" }),
    /backend qubex, not fake/,
  );
  await assert.rejects(
    resolvePipelinePlanPreview({ async getPlan() { return { ...PLAN, plan_id: "cpp-2" }; } }, { planId: "cpp-1", chipId: "64Qv3" }),
    /cannot be shown/,
  );
  const text = formatPlanApprovalPreview(await previewOf());
  for (const shown of [/Review digest sha256:v1:a{64}/, /Starting qubits \(4\): 0, 1, 2, 3 \(MUX 0\)/, /CheckRabi on_failure=stop \{"run":\{"shots":\{"value":1024\}\}\}/, /steps\[0\]: probably unintended/, /"interval":153600/]) {
    assert.match(text, shown);
  }
});

test("the review shows every setting the digest binds: manual rounds and filter thresholds", async () => {
  const spec = {
    spec_version: 2,
    name: "manual",
    targets: { qids: ["0", "1"] },
    steps: [
      {
        type: "OneQubitCheck",
        step_id: "check",
        execution_mode: "manual",
        rounds: [["0"], ["1"]],
        tasks: [{ name: "CheckRabi", call_id: "CheckRabi" }],
      },
      { type: "FilterByMetric", step: "check", metric: "t1", threshold: 12.5, inverse: true },
    ],
    tags: ["nightly"],
  };
  const plan = {
    ...PLAN,
    spec,
    steps: [
      PLAN.steps[0],
      { index: 2, type: "FilterByMetric", name: "filter_by_metric", kind: "transform", tasks: [], calls: [], reference: { step: "check", call_id: null } },
    ],
  };
  const preview = await previewOf(plan);
  // The stored preview keeps the spec exactly as QDash returned it.
  assert.deepEqual(preview.plan.spec, spec);
  const text = formatPlanApprovalPreview(preview);
  assert.match(text, /settings \{"step_id":"check","execution_mode":"manual","rounds":\[\["0"\],\["1"\]\]\}/);
  assert.match(text, /settings \{"step":"check","metric":"t1","threshold":12\.5,"inverse":true\}/);
  // The full normalized spec follows, so nothing the digest covers is left out.
  const disclosed = text.slice(text.indexOf("Approved spec (normalized, as stored):"));
  assert.deepEqual(JSON.parse(disclosed.slice(disclosed.indexOf("\n") + 1, disclosed.lastIndexOf("\n\nCompleted"))), spec);
  // Formatting never changes the stored preview.
  assert.deepEqual(preview.plan.spec, spec);
});

test("a host-approved plan runs with the shown digest, never one from the arguments", async () => {
  const requests = [];
  const tools = registeredTools({ async executeCalibrationPipelinePlan(id, body) { requests.push([id, body]); return DISPATCHED; } });
  const run = tools.get("qdash_run_pipeline");
  const preview = await previewOf();
  const result = await run.execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, hostApproved("t", preview));
  assert.equal(result.details.started, true);
  assert.equal(result.details.reviewDigest, DIGEST);
  assert.deepEqual(requests, [["cpp-1", {
    chip_id: "64Qv3",
    expected_review_digest: DIGEST,
    idempotency_key: "qdash_run_pipeline:t",
    reported_origin: { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" },
  }]]);
  // A digest the model adds is not a parameter and changes nothing.
  assert.equal("expectedReviewDigest" in run.parameters.properties, false);
});

test("a plan run without the shown plan, or for another plan, is refused and sends nothing", async () => {
  let dispatched = 0;
  const tools = registeredTools({ async executeCalibrationPipelinePlan() { dispatched += 1; return DISPATCHED; } });
  const run = tools.get("qdash_run_pipeline");
  const preview = await previewOf();
  await assert.rejects(run.execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, hostApproved("t")), /does not carry the stored plan/);
  await assert.rejects(run.execute("t", { chipId: "64Qv3", planId: "cpp-2" }, undefined, undefined, hostApproved("t", preview)), /differs from the one the user approved/);
  await assert.rejects(run.execute("t", { chipId: "64Qv3", planId: "cpp-1", backendName: "fake" }, undefined, undefined, hostApproved("t", preview)), /backend differs/);
  await assert.rejects(run.execute("t", { chipId: "64Qv3", planId: "cpp-1", spec: SPEC }, undefined, undefined, hostApproved("t", preview)), /exactly one/);
  // Without any approval the plan is not run either.
  await assert.rejects(run.execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  assert.equal(dispatched, 0);
  assert.match(planBindingProblem({ kind: "calibration_pipeline_plan", planId: "cpp-1", chipId: "64Qv3", reviewDigest: "" }, { planId: "cpp-1", chipId: "64Qv3" }), /does not carry/);
});

test("the tool's own dialog shows the plan it fetched and runs that digest", async () => {
  const requests = [];
  const tools = registeredTools({
    async getCalibrationPipelinePlan(id) { assert.equal(id, "cpp-1"); return PLAN; },
    async executeCalibrationPipelinePlan(id, body) { requests.push(body); return DISPATCHED; },
  });
  const shown = [];
  const ctx = { hasUI: true, ui: { async confirm(_title, message) { shown.push(message); return true; } } };
  const result = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, ctx);
  assert.equal(result.details.started, true);
  assert.equal(requests[0].expected_review_digest, DIGEST);
  assert.match(shown.join("\n"), /Review digest sha256:v1:a{64}/);
  assert.match(shown.join("\n"), /Starting qubits \(4\)/);
});

test("an expired plan is refused before the user is asked", async () => {
  const tools = registeredTools({ async getCalibrationPipelinePlan() { return { ...PLAN, expired: true }; } });
  let asked = 0;
  const ctx = { hasUI: true, ui: { async confirm() { asked += 1; return true; } } };
  await assert.rejects(tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, ctx), /expired/);
  assert.equal(asked, 0);
});

test("a paused agent session blocks a plan on its expanded MUX qubits only", async () => {
  const session = (qid) => [{ session_id: "s-1", chip_id: "64Qv3", status: "waiting_for_human", active_intervention_id: "i", policy: { qids: [qid] } }];
  const preview = await previewOf();
  let dispatched = 0;
  const api = { async executeCalibrationPipelinePlan() { dispatched += 1; return DISPATCHED; } };
  const blocked = await registeredTools(api, { paused: session("3") }).get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, hostApproved("t", preview));
  assert.equal(blocked.details.blockedByPausedSession, true);
  assert.equal(dispatched, 0);
  const elsewhere = await registeredTools(api, { paused: session("9") }).get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, hostApproved("t", preview));
  assert.equal(elsewhere.details.started, true);
  assert.equal(dispatched, 1);
});

test("a plan run whose answer does not confirm the plan is unknown, never retried", async () => {
  for (const change of [{ plan_id: null }, { review_digest: OTHER_DIGEST }]) {
    let dispatched = 0;
    const tools = registeredTools({ async executeCalibrationPipelinePlan() { dispatched += 1; return { ...DISPATCHED, ...change }; } });
    await assert.rejects(
      tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, hostApproved("t", await previewOf())),
      /result unknown.*Do not start this run again/s,
    );
    assert.equal(dispatched, 1);
  }
});

test("a replayed approval still runs from its stored preview after the plan expired", async () => {
  // The preview was frozen with the approval; the approved call does not fetch the plan again.
  const tools = registeredTools({
    async getCalibrationPipelinePlan() { throw new Error("must not fetch"); },
    async executeCalibrationPipelinePlan() { return { ...DISPATCHED, replayed: true }; },
  });
  const preview = await previewOf();
  const result = await tools.get("qdash_run_pipeline").execute("t", { chipId: "64Qv3", planId: "cpp-1" }, undefined, undefined, hostApproved("t", preview));
  assert.equal(result.details.replayed, true);
});

/** A pi with one tool_call handler list, enough for the write gate. */
function gatePi() {
  const handlers = new Map();
  return {
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    async toolCall(event, ctx) {
      let last;
      for (const handler of handlers.get("tool_call") ?? []) {
        const result = await handler({ type: "tool_call", ...event }, ctx);
        if (result !== undefined) last = result;
      }
      return last;
    },
  };
}

test("the CLI write gate fetches the plan before asking and binds the approval to it", async () => {
  const pi = gatePi();
  const resolved = [];
  installQDashWriteGate(pi, {
    async resolvePreview(toolName, args) { resolved.push([toolName, args]); return previewOf(); },
  });
  const tools = registeredTools({ async executeCalibrationPipelinePlan(_id, body) { return { ...DISPATCHED, review_digest: body.expected_review_digest }; } });
  const shown = [];
  const ctx = { hasUI: true, ui: { async confirm(_title, message) { shown.push(message); return true; } } };
  const args = { chipId: "64Qv3", planId: "cpp-1" };
  assert.equal(await pi.toolCall({ toolName: "qdash_run_pipeline", toolCallId: "g1", input: args }, ctx), undefined);
  assert.deepEqual(resolved, [["qdash_run_pipeline", args]]);
  assert.match(shown[0], /Review digest sha256:v1:a{64}/);
  assert.match(shown[0], /Arguments \(the approval covers exactly these\)/);
  assert.equal(hasGateApproval("g1"), true);
  const result = await tools.get("qdash_run_pipeline").execute("g1", args, undefined, undefined, { hasUI: false });
  assert.equal(result.details.reviewDigest, DIGEST);
  assert.equal(hasGateApproval("g1"), false);

  // A plan that cannot be shown is blocked without a dialog.
  const failing = gatePi();
  installQDashWriteGate(failing, { async resolvePreview() { throw new Error("Plan cpp-1 expired at then"); } });
  shown.length = 0;
  const blocked = await failing.toolCall({ toolName: "qdash_run_pipeline", toolCallId: "g2", input: args }, ctx);
  assert.equal(blocked.block, true);
  assert.match(blocked.reason, /expired/);
  assert.equal(shown.length, 0);
  // Without a resolver the gate cannot show a plan, so it does not ask.
  const blind = gatePi();
  installQDashWriteGate(blind);
  assert.equal((await blind.toolCall({ toolName: "qdash_run_pipeline", toolCallId: "g3", input: args }, ctx)).block, true);
});

test("the CLI write gate records the plan it showed, even if the resolver changes it later", async () => {
  const pi = gatePi();
  const returned = await previewOf();
  installQDashWriteGate(pi, { async resolvePreview() { return returned; } });
  const sent = [];
  const tools = registeredTools({ async executeCalibrationPipelinePlan(_id, body) { sent.push(body); return { ...DISPATCHED, review_digest: body.expected_review_digest }; } });
  const shown = [];
  const ctx = {
    hasUI: true,
    ui: {
      async confirm(_title, message) {
        shown.push(message);
        // The resolver still holds the object it returned and changes it while asking.
        returned.reviewDigest = OTHER_DIGEST;
        returned.plan.review_digest = OTHER_DIGEST;
        return true;
      },
    },
  };
  const args = { chipId: "64Qv3", planId: "cpp-1" };
  assert.equal(await pi.toolCall({ toolName: "qdash_run_pipeline", toolCallId: "g6", input: args }, ctx), undefined);
  assert.match(shown[0], /Review digest sha256:v1:a{64}/);
  const result = await tools.get("qdash_run_pipeline").execute("g6", args, undefined, undefined, { hasUI: false });
  assert.equal(sent[0].expected_review_digest, DIGEST);
  assert.equal(result.details.reviewDigest, DIGEST);

  // A preview that cannot be copied blocks the call before the user is asked.
  const uncopyable = gatePi();
  installQDashWriteGate(uncopyable, { async resolvePreview() { return { ...(await previewOf()), plan: { bad: () => 1 } }; } });
  shown.length = 0;
  const blocked = await uncopyable.toolCall({ toolName: "qdash_run_pipeline", toolCallId: "g7", input: args }, ctx);
  assert.equal(blocked.block, true);
  assert.equal(shown.length, 0);
});

test("a gate approval recorded without the plan does not run the plan", async () => {
  const tools = registeredTools({ async executeCalibrationPipelinePlan() { throw new Error("must not run"); } });
  const args = { chipId: "64Qv3", planId: "cpp-1" };
  recordGateApproval("g4", "qdash_run_pipeline", canonicalArgs(args));
  await assert.rejects(tools.get("qdash_run_pipeline").execute("g4", args, undefined, undefined, { hasUI: false }), /does not carry the stored plan/);
  // Changed arguments are refused as for every reviewed write.
  recordGateApproval("g5", "qdash_run_pipeline", canonicalArgs(args), await previewOf());
  await assert.rejects(tools.get("qdash_run_pipeline").execute("g5", { ...args, planId: "cpp-2" }, undefined, undefined, { hasUI: false }), /arguments changed/);
});
