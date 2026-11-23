import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CalibrationSessionPageContent } from "@/components/features/calibration-session/CalibrationSessionPageContent";

const state = vi.hoisted(() => ({
  detail: null as null | Record<string, unknown>,
  username: "alice",
  requests: [] as Array<{ key: unknown[]; project: unknown }>,
}));

vi.mock("@/components/features/agent-session/useLinkedProject", () => ({
  useLinkedProject: () => ({ status: "ready", projectId: "lab-a" }),
  projectRequest: (projectId: string) => ({ headers: { "X-Project-Id": projectId } }),
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ username: state.username }) }));
// The audit timeline reads its own pages; it is tested on its own.
vi.mock("@/components/features/calibration-session/CalibrationSessionAuditTimeline", () => ({
  CalibrationSessionAuditTimeline: ({ projectId }: { projectId: string }) => (
    <div data-testid="calibration-audit" data-project={projectId} />
  ),
}));
vi.mock("@/client/calibration-session/calibration-session", () => ({
  getGetCalibrationSessionQueryKey: (id: string) => [`/calibration-sessions/${id}`],
  useGetCalibrationSession: (
    _id: string,
    options: { query: { queryKey: unknown[] }; request?: { headers: Record<string, string> } },
  ) => {
    state.requests.push({
      key: options.query.queryKey,
      project: options.request?.headers["X-Project-Id"],
    });
    return {
      data: state.detail ? { data: state.detail } : undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  },
  useCloseCalibrationSession: () => ({ mutate: vi.fn(), isPending: false }),
}));

const DETAIL = {
  calibration_session_id: "cs-1",
  project_id: "lab-a",
  chip_id: "64Qv3",
  objective: "Bring up qubits 0 and 1",
  created_by: "alice",
  status: "open",
  created_at: "2026-11-23T00:00:00Z",
  updated_at: "2026-11-23T00:00:00Z",
  pipeline_runs: [
    {
      run_id: "cpr-1",
      calibration_session_id: "cs-1",
      chip_id: "64Qv3",
      idempotency_key: "k",
      requested_by: "alice",
      dispatch_status: "dispatched",
      attempts: 1,
      pipeline_name: "coarse-then-coherence",
      backend_name: "qubex",
      flow_run_id: "fr-1",
      execution_id: "exec-1",
      error: "",
      requested_at: "2026-11-23T00:00:00Z",
      updated_at: "2026-11-23T00:00:00Z",
      pipeline: {
        name: "coarse-then-coherence",
        flow_run_id: "fr-1",
        root_execution_id: "exec-1",
        status: "running",
        steps: [
          { index: 1, name: "one_qubit_check", status: "completed", execution_id: "exec-1" },
          { index: 2, name: "filter_by_status", status: "skipped", kind: "transform" },
          { index: 3, name: "coherence", status: "running", execution_id: "exec-3" },
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
      executions: [{ execution_id: "exec-9", status: "completed" }],
    },
  ],
  close_blockers: ["pipeline run cpr-1 is running", "agent session as-1 waits for a person"],
  unknown_runs: ["cpr-2"],
};

afterEach(cleanup);
beforeEach(() => {
  state.detail = DETAIL;
  state.username = "alice";
  state.requests = [];
});

describe("CalibrationSessionPageContent", () => {
  it("shows one pipeline run with every step execution, and the agent session with its executions", () => {
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    expect(state.requests[0]).toEqual({
      key: ["/calibration-sessions/cs-1", "lab-a"],
      project: "lab-a",
    });
    expect(screen.getByText("Bring up qubits 0 and 1")).toBeTruthy();

    const [run, unknown] = screen.getAllByTestId("calibration-pipeline-run");
    expect(within(run).getByRole("link", { name: "exec-1" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-1?project=lab-a",
    );
    expect(within(run).getByRole("link", { name: "exec-3" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-3?project=lab-a",
    );
    expect(within(run).getByText("2. filter_by_status")).toBeTruthy();
    expect(within(unknown).getByText("Start unknown")).toBeTruthy();
    expect(within(unknown).getByText(/may be running/)).toBeTruthy();

    const agent = screen.getByTestId("calibration-agent-session");
    expect(within(agent).getByRole("link", { name: "Agent session" }).getAttribute("href")).toBe(
      "/agent-sessions/as-1?project=lab-a",
    );
    expect(within(agent).getByText(/Autonomous calibration/)).toBeTruthy();
    expect(within(agent).getByRole("link", { name: "exec-9" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close session" })).toBeTruthy();
  });

  it("labels only a reported agent tool run, and says it is reported", () => {
    const [manual, tool] = [
      (DETAIL.pipeline_runs as Array<Record<string, unknown>>)[0],
      {
        ...(DETAIL.pipeline_runs as Array<Record<string, unknown>>)[0],
        run_id: "cpr-3",
        reported_origin: { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" },
      },
    ];
    state.detail = { ...DETAIL, pipeline_runs: [manual, tool] };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    const [manualRow, toolRow] = screen.getAllByTestId("calibration-pipeline-run");
    expect(within(manualRow).queryByTestId("reported-origin-badge")).toBeNull();
    const badge = within(toolRow).getByTestId("reported-origin-badge");
    expect(badge.textContent).toBe("Agent tool, reported");
    expect(badge.getAttribute("title")).toContain("QDash does not verify");
    expect(within(toolRow).queryByText("Agent")).toBeNull();
  });

  it("offers closing only to its creator while it is open, and says that it grants nothing", () => {
    state.username = "bob";
    const { unmount } = render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    expect(screen.queryByRole("button", { name: "Close session" })).toBeNull();
    expect(screen.getByText(/It grants nothing/)).toBeTruthy();
    unmount();

    state.username = "alice";
    state.detail = { ...DETAIL, status: "closed", closed_by: "alice", closing_note: "done" };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    expect(screen.queryByRole("button", { name: "Close session" })).toBeNull();
    expect(screen.getByText("Closed", { selector: ".badge" })).toBeTruthy();
  });

  it("says when the lists are cut, and counts every child", () => {
    state.detail = { ...DETAIL, pipeline_run_total: 140, agent_session_total: 1 };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    const [cut] = screen.getAllByTestId("calibration-list-cut");
    expect(cut.textContent).toBe(
      "Showing the latest 2 of 140 pipeline runs. Close checks every one of them.",
    );
    expect(screen.getAllByTestId("calibration-list-cut")).toHaveLength(1);
    expect(screen.getByText("140")).toBeTruthy();
  });

  it("asks to acknowledge agent session starts whose outcome is unknown", () => {
    state.detail = {
      ...DETAIL,
      close_blockers: [],
      unknown_runs: [],
      unknown_starts: [
        {
          reservation_id: "csr-1",
          kind: "agent_session",
          child_id: "as-lost",
          reserved_by: "alice",
          reserved_at: "2026-11-23T00:00:00Z",
        },
      ],
    };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Close session" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/agent sessions as-lost were being started/)).toBeTruthy();
    expect(within(dialog).getByText(/never admitted/)).toBeTruthy();
    const confirm = within(dialog).getByRole("button", { name: "Close session" });
    expect(confirm.hasAttribute("disabled")).toBe(true);
    fireEvent.click(within(dialog).getByRole("checkbox"));
    expect(confirm.hasAttribute("disabled")).toBe(false);
  });

  it("says an admitted pipeline run with an unknown start may still start after closing", () => {
    state.detail = { ...DETAIL, close_blockers: [], unknown_runs: ["cpr-2"] };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Close session" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/may still start after I close/)).toBeTruthy();
    expect(within(dialog).getByText(/cancels nothing already admitted/)).toBeTruthy();
  });

  it("marks an agent session that is not admitted", () => {
    const [agent] = DETAIL.agent_sessions;
    state.detail = {
      ...DETAIL,
      agent_sessions: [{ ...agent, calibration_admission: "pending" }],
    };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    const row = screen.getByTestId("calibration-agent-session");
    expect(within(row).getByText("Not admitted yet")).toBeTruthy();
  });

  it("names empty sections", () => {
    state.detail = { ...DETAIL, pipeline_runs: [], agent_sessions: [], close_blockers: [] };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    expect(screen.getByText("No pipeline runs")).toBeTruthy();
    expect(screen.getByText("No agent sessions")).toBeTruthy();
  });

  it("shows the search progression from recorded decisions and the audit for the same project", () => {
    const measured = (fields: Record<string, unknown>) => ({
      evidence_status: "complete",
      execution_ids: ["exec-9"],
      tasks: [],
      ...fields,
    });
    state.detail = {
      ...DETAIL,
      decision_total: 4,
      experiments: [
        {
          sequence: 1,
          decision_id: "cd-1",
          stage: "baseline",
          candidate_id: "incumbent",
          target: "0-1",
          requested_changes: [],
          rationale: "Latest validated chain",
          recorded_at: "2026-11-23T00:00:00Z",
          pipeline_run_id: null,
          parameter_checks: [],
          measured: measured({
            gate_time_ns: {
              value: 256,
              unit: "ns",
              task_id: "t1",
              task_name: "CreateZX90",
              execution_id: "e",
            },
            gate_fidelity: {
              value: 0.99,
              error: 0.002,
              unit: "",
              task_id: "t2",
              task_name: "IRB",
              execution_id: "e",
            },
          }),
        },
        {
          sequence: 2,
          decision_id: "cd-2",
          stage: "screening",
          candidate_id: "c03",
          target: "0-1",
          requested_changes: [
            {
              task_name: "CheckCrossResonance",
              parameter: "adiabatic_safe_factor",
              value: 0.8,
              previous: 0.75,
            },
          ],
          rationale: "The factor binds",
          recorded_at: "2026-11-23T00:10:00Z",
          pipeline_run_id: "cpr-9",
          parameter_checks: [
            {
              task_name: "CheckCrossResonance",
              parameter: "adiabatic_safe_factor",
              requested: 0.8,
              in_spec: 0.8,
              executed: 0.75,
              consistent: false,
              missing: [],
            },
          ],
          measured: measured({
            gate_time_ns: {
              value: 208,
              unit: "ns",
              task_id: "t3",
              task_name: "CreateZX90",
              execution_id: "e",
            },
            execution_seconds: 600,
          }),
        },
        {
          sequence: 3,
          decision_id: "cd-3",
          stage: "screening",
          candidate_id: "c04",
          target: "0-1",
          requested_changes: [],
          rationale: "Declined by the user",
          recorded_at: "2026-11-23T00:20:00Z",
          pipeline_run_id: null,
          parameter_checks: [],
          measured: { evidence_status: "not_run" },
        },
      ],
      recommendation: {
        decision_id: "cd-4",
        calibration_session_id: "cs-1",
        final: true,
        conclusion: { outcome: "keep_baseline", recommended_candidate_id: "incumbent" },
        interpretation: "c03 was not confirmed.",
        next_action: "complete",
        recorded_by: "alice",
        recorded_at: "2026-11-23T00:30:00Z",
        model: { provider: "local", model_id: "qwen", host: "pi" },
      },
      latest_requested_run: {
        pipeline_run_id: "cpr-9",
        requested_at: "2026-11-23T00:10:00Z",
        dispatch_status: "dispatched",
        execution_outcome: "completed",
        decision_id: "cd-3",
        candidate_id: "c03",
        execution_ids: ["exec-9"],
        candidate_is_recommended: false,
        missing: ["an authoritative record of what this run wrote to the hardware"],
      },
    };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    const progress = screen.getByRole("region", { name: "Search progression" });
    const stages = within(progress).getByRole("list", { name: "Stages reached" });
    expect(within(stages).getByText("Baseline").className).toContain("step-primary");
    expect(within(stages).getByText("Confirmation").className).not.toContain("step-primary");
    const table = within(progress).getByRole("table", { name: "Candidate comparison" });
    expect(within(table).getByText("256.0 ns")).toBeTruthy();
    expect(within(table).getByText("0.9900 ± 0.0020")).toBeTruthy();
    expect(within(table).getByText("adiabatic_safe_factor 0.75 → 0.8")).toBeTruthy();
    // What the task executed differs from the request, and it says so.
    expect(within(table).getByText(/Executed adiabatic_safe_factor 0.75/)).toBeTruthy();
    expect(within(table).getByText("No run carried it out")).toBeTruthy();
    expect(within(table).getByText("10.0 min")).toBeTruthy();
    expect(within(progress).getByText("Keeps the baseline")).toBeTruthy();
    expect(within(progress).getByText("Agent statement")).toBeTruthy();
    const notice = within(progress).getByRole("status").textContent ?? "";
    expect(notice).toMatch(/The latest requested run \(candidate c03/);
    expect(notice).toMatch(/completed every execution/);
    expect(notice).toMatch(/requested candidate is not the recommended candidate incumbent/);
    // A completed run is never presented as the hardware state.
    expect(notice).toMatch(/QDash records no authoritative hardware write/);
    expect(notice).not.toMatch(/last state the session wrote|wrote its results/);
    const link = within(table).getAllByRole("link", { name: "Execution" })[0];
    expect(link.getAttribute("href")).toBe("/execution/64Qv3/exec-9?project=lab-a");
    expect(screen.getByTestId("calibration-audit").getAttribute("data-project")).toBe("lab-a");
  });

  it("reports a refused latest request as never run, not as a write", () => {
    state.detail = {
      ...DETAIL,
      experiments: [],
      recommendation: null,
      latest_requested_run: {
        pipeline_run_id: "cpr-10",
        requested_at: "2026-11-23T00:40:00Z",
        dispatch_status: "rejected",
        execution_outcome: "refused",
        candidate_id: null,
        execution_ids: [],
        candidate_is_recommended: null,
        missing: [],
      },
    };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    const notice = screen.getByRole("status");
    expect(notice.className).toContain("alert-warning");
    expect(notice.textContent).toMatch(/names no decision.*QDash refused its launch/);
  });

  it("never shows a conclusion that was not recorded", () => {
    state.detail = {
      ...DETAIL,
      status: "closed",
      experiments: [],
      recommendation: null,
      latest_requested_run: null,
    };
    render(<CalibrationSessionPageContent calibrationSessionId="cs-1" />);
    expect(screen.queryByRole("region", { name: "Search progression" })).toBeNull();
    expect(screen.queryByText(/Recommends|Keeps the baseline/)).toBeNull();
  });
});
