import assert from "node:assert/strict";
import test from "node:test";

import { formatCalibrationSession, registerCalibrationSessionTools } from "../.test-dist/tools/calibration-session.js";

function registeredTools(api, chipId = "64Qv3") {
  const tools = new Map();
  const client = { api, config: { projectId: "project-1" } };
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
  assert.match(cut, /Pipeline runs \(latest 2 of 140; the close check covers all\)/);
  assert.match(cut, /- agent session as-lost/);
  assert.match(cut, /never admitted/);
  const pending = formatCalibrationSession({
    ...detail,
    agent_sessions: detail.agent_sessions.map((agent) => ({ ...agent, calibration_admission: "pending" })),
  });
  assert.match(pending, /not admitted yet/);
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
