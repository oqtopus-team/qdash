import assert from "node:assert/strict";
import test from "node:test";

import { formatCalibrationSession, registerCalibrationSessionTools } from "../.test-dist/tools/calibration-session.js";

/** The tools over a connection whose calibration-session methods are `methods`. */
function registeredTools(methods, chipId = "64Qv3") {
  const tools = new Map();
  const client = { ...methods, config: { projectId: "project-1" } };
  registerCalibrationSessionTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() { return client; },
    async resolveChipId(_client, explicit) { return explicit ?? chipId; },
  });
  return tools;
}

const approved = (toolCallId, toolName) => ({ hasUI: false, qdashWriteApproval: { toolCallId, toolName } });

const SESSION = {
  calibration_session_id: "cs-1",
  project_id: "project-1",
  chip_id: "64Qv3",
  objective: "Bring up qubits 0 and 1",
  created_by: "alice",
  status: "open",
  created_at: "2026-11-23T00:00:00Z",
  updated_at: "2026-11-23T00:00:00Z",
  closed_with_unknown_runs: [],
};

test("creating a calibration session is confirmation-gated and returns its ID", async () => {
  const calls = [];
  const tools = registeredTools({
    async createCalibrationSession(body) { calls.push(body); return SESSION; },
  });
  const create = tools.get("qdash_create_calibration_session");
  await assert.rejects(
    create.execute("c1", { objective: "Bring up qubits 0 and 1" }, undefined, undefined, { hasUI: false }),
    /requires explicit confirmation/,
  );
  assert.equal(calls.length, 0);
  await assert.rejects(create.execute("c1", { objective: "   " }, undefined, undefined, approved("c1", "qdash_create_calibration_session")), /objective is required/);

  const result = await create.execute("c1", { objective: " Bring up qubits 0 and 1 " }, undefined, undefined, approved("c1", "qdash_create_calibration_session"));
  assert.deepEqual(calls, [{ chip_id: "64Qv3", objective: "Bring up qubits 0 and 1" }]);
  // The chat discovers the new session from these details, which the agent runtime forwards as
  // the typed `calibrationSession` of a successful tool_end (agent-runtime/test/events.test.mjs).
  assert.equal(result.details.tool, "qdash_create_calibration_session");
  assert.equal(result.details.calibrationSessionId, "cs-1");
  assert.equal(result.details.chipId, "64Qv3");
  assert.match(result.content[0].text, /calibrationSessionId to qdash_run_pipeline/);
});

test("a calibration session reads as its runs, each with every step execution, and its agent sessions", async () => {
  const detail = {
    ...SESSION,
    pipeline_runs: [
      {
        run_id: "cpr-1",
        calibration_session_id: "cs-1",
        chip_id: "64Qv3",
        idempotency_key: "k",
        requested_by: "alice",
        dispatch_status: "dispatched",
        attempts: 1,
        pipeline_name: "coarse",
        backend_name: "qubex",
        flow_run_id: "fr-1",
        execution_id: "e1",
        error: "",
        requested_at: "2026-11-23T00:00:00Z",
        updated_at: "2026-11-23T00:00:00Z",
        pipeline: {
          name: "coarse",
          flow_run_id: "fr-1",
          root_execution_id: "e1",
          status: "running",
          steps: [
            { index: 1, name: "one_qubit_check", status: "completed", execution_id: "e1" },
            { index: 2, name: "filter_by_status", status: "skipped" },
            { index: 3, name: "coherence", status: "running", execution_id: "e3" },
          ],
        },
        executions: [],
      },
      {
        run_id: "cpr-2",
        calibration_session_id: "cs-1",
        chip_id: "64Qv3",
        idempotency_key: "k2",
        requested_by: "alice",
        reported_origin: { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" },
        dispatch_status: "unknown",
        attempts: 1,
        pipeline_name: "fine",
        backend_name: "",
        error: "RuntimeError",
        requested_at: "2026-11-23T00:00:00Z",
        updated_at: "2026-11-23T00:00:00Z",
        executions: [],
      },
    ],
    agent_sessions: [
      {
        session_id: "as-1",
        status: "waiting_for_human",
        created_by: "alice",
        created_at: "2026-11-23T00:00:00Z",
        expires_at: "2026-11-23T06:00:00Z",
        autonomy: "auto",
        qids: ["0"],
        allowed_tasks: ["CheckRabi"],
        action_count: 2,
        active_intervention_id: "int-1",
        executions: [{ execution_id: "e9", status: "completed" }],
      },
    ],
    close_blockers: ["pipeline run cpr-1 is running", "agent session as-1 waits for a person"],
    unknown_runs: ["cpr-2"],
  };
  const tools = registeredTools({ async getCalibrationSession(id) { assert.equal(id, "cs-1"); return detail; } });
  const result = await tools.get("qdash_get_calibration_session").execute("g", { calibrationSessionId: "cs-1" });
  const text = result.content[0].text;
  assert.match(text, /pipeline run cpr-1 'coarse': dispatched, run running/);
  assert.match(text, /1\. one_qubit_check — completed \(execution e1\)/);
  assert.match(text, /3\. coherence — running \(execution e3\)/);
  assert.match(text, /cpr-2 'fine': unknown/);
  // A run requested directly says so; a reported tool origin is labeled as unverified.
  assert.match(text, /requested by alice; no launch origin reported/);
  assert.match(text, /pi-qdash reported it was launched by the agent tool qdash_run_pipeline \(client reported, not verified by QDash; not an agent session\)/);
  assert.match(text, /may be running/);
  assert.match(text, /agent session as-1: waiting_for_human, auto, qubits 0, 2 actions/);
  assert.match(text, /execution e9 — completed/);
  assert.equal(result.details.calibrationSessionId, "cs-1");
  const cut = formatCalibrationSession({
    ...detail,
    pipeline_run_total: 140,
    unknown_starts: [{ reservation_id: "csr-1", kind: "agent_session", child_id: "as-lost", reserved_by: "alice", reserved_at: "2026-11-23T00:00:00Z" }],
  });
  assert.match(cut, /Runs \(latest 2 of 140; the close check covers all\)/);
  assert.match(cut, /- agent session as-lost/);
  // An automatic session with a scheduled saved-workflow run says both.
  const scheduled = formatCalibrationSession({
    ...detail,
    origin: "automatic",
    pipeline_runs: [{ ...detail.pipeline_runs[0], run_kind: "workflow", run_name: "nightly", trigger: "schedule", reported_origin: null }],
  });
  assert.match(scheduled, /\(open, automatic: QDash created it for a run started without one\)/);
  assert.match(scheduled, /- workflow run cpr-1 'nightly'/);
  assert.match(scheduled, /started by a cron schedule of alice; the worker recorded it/);
  assert.match(cut, /never admitted/);
  const pending = formatCalibrationSession({
    ...detail,
    agent_sessions: detail.agent_sessions.map((agent) => ({ ...agent, calibration_admission: "pending" })),
  });
  assert.match(pending, /not admitted yet/);
  // An automatic close is reported as QDash's, never as a user named system:auto-close.
  const autoClosed = formatCalibrationSession({
    ...detail,
    origin: "automatic",
    status: "closed",
    close_origin: "automatic",
    closed_by: "system:auto-close",
    closing_note: "Closed automatically: everything started in this session ended.",
  });
  assert.match(autoClosed, /Closed by QDash \(automatic close, not a person\): Closed automatically/);
  assert.doesNotMatch(autoClosed, /system:auto-close/);
  const manualClosed = formatCalibrationSession({ ...detail, status: "closed", close_origin: "manual", closed_by: "alice", closing_note: "done" });
  assert.match(manualClosed, /Closed by alice: done\./);
  assert.match(text, /may still start, even after the session is closed/);
  assert.equal(formatCalibrationSession({ ...SESSION, pipeline_runs: [], agent_sessions: [] }).includes("Nothing has been started"), true);
});

test("listing passes only the filters asked for", async () => {
  const calls = [];
  const tools = registeredTools({ async listCalibrationSessions(params) { calls.push(params); return { items: [SESSION], total: 1 }; } });
  const result = await tools.get("qdash_list_calibration_sessions").execute("l", { mine: true, openOnly: true, limit: 500 });
  assert.deepEqual(calls, [{ mine: true, status: ["open"], limit: 100 }]);
  assert.match(result.content[0].text, /cs-1 \[open\] chip 64Qv3, by alice: Bring up qubits 0 and 1/);
});

test("a decision is appended to the calibration session audit once per tool call, with the host's model", async () => {
  const calls = [];
  const tools = registeredTools({
    async recordCalibrationDecision(id, body) {
      calls.push({ id, body });
      return {
        decision_id: "cd-1",
        calibration_session_id: id,
        experiment: body.experiment ?? null,
        conclusion: body.conclusion ?? null,
        carried_out_by_run_ids: [],
      };
    },
  });
  const record = tools.get("qdash_record_calibration_decision");
  const params = {
    calibrationSessionId: "cs-1",
    interpretation: "The factor binds; raise it within the approved range.",
    nextAction: "adjust_and_retry",
    evidenceRunIds: ["cpr-1"],
    experiment: {
      candidateId: "c03",
      stage: "screening",
      target: "0-1",
      requestedChanges: [{ taskName: "CheckCrossResonance", parameter: "adiabatic_safe_factor", value: 0.8, previous: 0.75 }],
    },
    // A model argument is ignored: provenance comes from the host context only.
    model: { provider: "evil", model_id: "x" },
  };
  const ctx = { hasUI: false, model: { provider: "local", id: "qwen" } };
  // Session-granted: no approval is needed, and a replay of the same call uses the same key.
  const first = await record.execute("call-9", params, undefined, undefined, ctx);
  await record.execute("call-9", params, undefined, undefined, ctx);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].body.idempotency_key, calls[1].body.idempotency_key);
  assert.match(calls[0].body.idempotency_key, /^pi-calibration-decision-[0-9a-f]{40}$/);
  assert.deepEqual(calls[0].body.experiment, {
    candidate_id: "c03",
    stage: "screening",
    target: "0-1",
    requested_changes: [{ task_name: "CheckCrossResonance", parameter: "adiabatic_safe_factor", value: 0.8, previous: 0.75 }],
  });
  assert.equal(calls[0].body.model.provider, "local");
  assert.equal(calls[0].body.model.model_id, "qwen");
  assert.equal(first.details.decisionId, "cd-1");
  assert.match(first.content[0].text, /Pass decisionId cd-1 with calibrationSessionId to qdash_run_pipeline/);
});

test("the audit reads as events marked server-recorded or stated, with unrecorded facts named", async () => {
  const tools = registeredTools({
    async getCalibrationSessionAudit(id, params) {
      assert.equal(id, "cs-1");
      assert.deepEqual(params, { limit: 50 });
      return {
        calibration_session: { calibration_session_id: "cs-1", status: "open", chip_id: "64Qv3", objective: "Shorten the 0-1 ZX90" },
        events: [
          { sequence: 0, at: "2026-11-23T00:00:00Z", kind: "decision", summary: "Proposed screening of c03 on 0-1", provenance: "agent_reported", missing: [] },
          { sequence: 1, at: "2026-11-23T00:01:00Z", kind: "pipeline_requested", summary: "alice requested pipeline", provenance: "server_record", missing: ["host_approval"] },
          { sequence: 2, at: "2026-11-23T00:02:00Z", kind: "measurement", summary: "e1: completed", provenance: "server_record", missing: [], agent_session_id: null },
        ],
        total_events: 3,
        complete: true,
        next_cursor: null,
      };
    },
  });
  const result = await tools.get("qdash_get_calibration_session_audit").execute("c", { calibrationSessionId: "cs-1", limit: 50 });
  const text = result.content[0].text;
  assert.match(text, /0\. .* decision: Proposed screening of c03 on 0-1 \[agent reported\]/);
  assert.match(text, /pipeline_requested: .*\[server\] \(not recorded: host_approval\)/);
});

test("the session detail shows experiments, mismatched parameters, and a recommendation that differs from the latest requested run", () => {
  const text = formatCalibrationSession({
    ...SESSION,
    pipeline_runs: [],
    agent_sessions: [],
    decision_total: 3,
    experiments: [
      {
        sequence: 1,
        decision_id: "cd-1",
        stage: "screening",
        candidate_id: "c03",
        target: "0-1",
        requested_changes: [{ task_name: "CheckCrossResonance", parameter: "adiabatic_safe_factor", value: 0.8 }],
        rationale: "x",
        recorded_at: "2026-11-23T00:00:00Z",
        pipeline_run_id: "cpr-1",
        parameter_checks: [{ task_name: "CheckCrossResonance", parameter: "adiabatic_safe_factor", requested: 0.8, in_spec: 0.8, executed: 0.75, consistent: false, missing: [] }],
        measured: {
          evidence_status: "complete",
          gate_time_ns: { value: 192, unit: "ns", task_id: "t", task_name: "CreateZX90", execution_id: "e" },
          gate_fidelity: { value: 0.991, error: 0.002, unit: "", task_id: "t2", task_name: "ZX90InterleavedRandomizedBenchmarking", execution_id: "e" },
          execution_seconds: 600,
        },
      },
    ],
    recommendation: { decision_id: "cd-3", conclusion: { outcome: "keep_baseline", recommended_candidate_id: "incumbent" } },
    latest_requested_run: { pipeline_run_id: "cpr-1", requested_at: "2026-01-01T00:00:00Z", dispatch_status: "dispatched", execution_outcome: "completed", candidate_id: "c03", candidate_is_recommended: false, execution_ids: [], missing: [] },
  });
  assert.match(text, /#1 screening c03 on 0-1 .*run cpr-1/);
  assert.match(text, /gate time 192 ns, fidelity 0.991 ± 0.002/);
  assert.match(text, /executed 0.75: NOT consistent/);
  assert.match(text, /Recommendation .*keep_baseline incumbent/);
  assert.match(text, /Latest requested run in this session \(by request time\): cpr-1 \(candidate c03\), dispatch dispatched, execution outcome completed: every execution completed\./);
  assert.match(text, /requested candidate is not the recommended candidate \(a comparison of records, not of the hardware\)/);
  assert.match(text, /not the current or last written hardware state/);
  assert.doesNotMatch(text, /hardware write in this session/i);
});
