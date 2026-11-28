import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CalibrationSessionPageContent } from "@/components/features/calibration-session/CalibrationSessionPageContent";
import { formatDateTime } from "@/lib/utils/datetime";

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

function renderPage(searchParams = "") {
  return render(
    <NuqsTestingAdapter searchParams={searchParams}>
      <CalibrationSessionPageContent calibrationSessionId="cs-1" />
    </NuqsTestingAdapter>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  state.detail = DETAIL;
  state.username = "alice";
  state.requests = [];
});

describe("CalibrationSessionPageContent", () => {
  it("names an automatic session and what each of its runs launched", () => {
    const [first] = DETAIL.pipeline_runs;
    state.detail = {
      ...DETAIL,
      origin: "automatic",
      objective: "Workflow nightly_1q",
      pipeline_runs: [
        { ...first, run_kind: "workflow", run_name: "nightly_1q", trigger: "schedule" },
      ],
    };
    renderPage();
    expect(screen.getByText("Automatic")).toBeTruthy();
    expect(screen.getByText(/QDash created it for a run started without a session/)).toBeTruthy();
    const [run] = screen.getAllByTestId("calibration-pipeline-run");
    expect(within(run).getByText("nightly_1q")).toBeTruthy();
    expect(within(run).getByText("Workflow")).toBeTruthy();
    expect(within(run).getByText("Scheduled")).toBeTruthy();
  });

  it("shows one pipeline run with every step execution, and the agent session with its executions", () => {
    renderPage();
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
    renderPage();
    const [manualRow, toolRow] = screen.getAllByTestId("calibration-pipeline-run");
    expect(within(manualRow).queryByTestId("reported-origin-badge")).toBeNull();
    const badge = within(toolRow).getByTestId("reported-origin-badge");
    expect(badge.textContent).toBe("Agent tool, reported");
    expect(badge.getAttribute("title")).toContain("QDash does not verify");
    expect(within(toolRow).queryByText("Agent")).toBeNull();
  });

  it("offers closing only to its creator while it is open, and says that it grants nothing", () => {
    state.username = "bob";
    const { unmount } = renderPage();
    expect(screen.queryByRole("button", { name: "Close session" })).toBeNull();
    expect(screen.getByText(/It grants nothing/)).toBeTruthy();
    unmount();

    state.username = "alice";
    state.detail = { ...DETAIL, status: "closed", closed_by: "alice", closing_note: "done" };
    renderPage();
    expect(screen.queryByRole("button", { name: "Close session" })).toBeNull();
    expect(screen.getByText("Closed", { selector: ".badge" })).toBeTruthy();
  });

  it("labels an automatic close as QDash's, not a person's", () => {
    state.detail = {
      ...DETAIL,
      origin: "automatic",
      status: "closed",
      closed_by: "system:auto-close",
      close_origin: "automatic",
      closing_note: "Closed automatically: everything started in this session ended.",
    };
    renderPage();
    expect(screen.getByText(/Automatically, when its work ended/)).toBeTruthy();
    expect(screen.queryByText(/system:auto-close/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Close session" })).toBeNull();
  });

  it("says when the lists are cut, and counts every child", () => {
    state.detail = { ...DETAIL, pipeline_run_total: 140, agent_session_total: 1 };
    renderPage();
    const [cut] = screen.getAllByTestId("calibration-list-cut");
    expect(cut.textContent).toBe(
      "Showing the latest 2 of 140 runs. Close checks every one of them.",
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
    renderPage();
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
    renderPage();
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
    renderPage();
    const row = screen.getByTestId("calibration-agent-session");
    expect(within(row).getByText("Not admitted yet")).toBeTruthy();
  });

  it("names empty sections", () => {
    state.detail = { ...DETAIL, pipeline_runs: [], agent_sessions: [], close_blockers: [] };
    renderPage();
    expect(screen.getByText("No runs")).toBeTruthy();
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
    renderPage();
    const progress = screen.getByRole("region", { name: "Experiments" });
    // The stage is a column of the comparison, not a separate stepper.
    expect(within(progress).queryByRole("list", { name: "Stages reached" })).toBeNull();
    const table = within(progress).getByRole("table", { name: "Candidate comparison" });
    expect(within(table).getAllByText("Screening")).toHaveLength(2);
    expect(within(table).getByText("256.0 ns")).toBeTruthy();
    expect(within(table).getByText("0.9900 ± 0.0020")).toBeTruthy();
    expect(within(table).getByText("adiabatic_safe_factor 0.75 → 0.8")).toBeTruthy();
    // What the task executed differs from the request, and it says so.
    expect(within(table).getByText(/Executed adiabatic_safe_factor 0.75/)).toBeTruthy();
    expect(within(table).getByText("No run carried it out")).toBeTruthy();
    expect(within(table).getByText("10.0 min")).toBeTruthy();
    // The rationale is a statement in its own column, apart from the measured values.
    const rationaleColumn = within(table)
      .getAllByRole("columnheader")
      .findIndex((header) => header.textContent === "Rationale");
    const firstRow = within(table).getAllByRole("row")[1];
    expect(within(firstRow).getAllByRole("cell")[rationaleColumn].textContent).toBe(
      "Latest validated chain",
    );
    const conclusion = within(progress).getByRole("group", { name: "Conclusion" });
    expect(within(conclusion).getByText("Keep baseline")).toBeTruthy();
    expect(within(conclusion).getByText("Agent statement")).toBeTruthy();
    expect(within(conclusion).getByText("c03 was not confirmed.")).toBeTruthy();
    const latest = within(progress).getByRole("group", { name: "Latest requested run" });
    expect(within(latest).getByText("Completed")).toBeTruthy();
    expect(within(latest).getByText("c03")).toBeTruthy();
    expect(within(latest).getByText("Not the recommended candidate incumbent")).toBeTruthy();
    // Requested and finished are separate facts; a run without an end is not shown finished.
    expect(within(latest).getByText("Requested")).toBeTruthy();
    expect(within(latest).getByText("Finished").nextElementSibling?.textContent).toBe("—");
    // A completed run is never presented as the hardware state.
    expect(within(latest).getByText("Hardware state is not tracked")).toBeTruthy();
    expect(latest.textContent).not.toMatch(/last state the session wrote|wrote its results/);
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
    renderPage();
    const latest = screen.getByRole("group", { name: "Latest requested run" });
    expect(within(latest).getByText("Refused, never ran")).toBeTruthy();
    expect(within(latest).getByText("No candidate")).toBeTruthy();
    expect(within(latest).queryByText(/recommended candidate/)).toBeNull();
  });

  it("keeps the requested and finished times of the latest run apart", () => {
    state.detail = {
      ...DETAIL,
      experiments: [],
      recommendation: null,
      latest_requested_run: {
        pipeline_run_id: "cpr-11",
        requested_at: "2026-11-23T00:40:00Z",
        finished_at: "2026-11-23T02:15:00Z",
        dispatch_status: "dispatched",
        execution_outcome: "partial",
        candidate_id: "c05",
        execution_ids: ["exec-11"],
        candidate_is_recommended: false,
        missing: [],
      },
    };
    renderPage();
    const latest = screen.getByRole("group", { name: "Latest requested run" });
    const requested = within(latest).getByText("Requested").nextElementSibling?.textContent;
    const finished = within(latest).getByText("Finished").nextElementSibling?.textContent;
    expect(requested).toBe(formatDateTime("2026-11-23T00:40:00Z"));
    expect(finished).toBe(formatDateTime("2026-11-23T02:15:00Z"));
    expect(requested).not.toBe(finished);
    expect(within(latest).getByText("Partly completed")).toBeTruthy();
    // No recommendation names the other candidate, so the mismatch stays generic.
    expect(within(latest).getByText("Not the recommended candidate")).toBeTruthy();
  });

  it.each([
    ["running", "Not finished"],
    ["unknown", "Unknown"],
  ])("shows the finish state for a %s latest run", (outcome, finishedLabel) => {
    state.detail = {
      ...DETAIL,
      experiments: [],
      recommendation: null,
      latest_requested_run: {
        pipeline_run_id: "cpr-12",
        requested_at: "2026-11-23T00:40:00Z",
        dispatch_status: outcome === "unknown" ? "unknown" : "dispatched",
        execution_outcome: outcome,
        candidate_id: "c06",
        execution_ids: ["exec-12"],
        candidate_is_recommended: true,
        missing: [],
      },
    };
    renderPage();
    const latest = screen.getByRole("group", { name: "Latest requested run" });
    expect(within(latest).getByText("Finished").nextElementSibling?.textContent).toBe(
      finishedLabel,
    );
    expect(within(latest).queryByText(/recommended candidate/)).toBeNull();
  });

  it("never shows a conclusion that was not recorded", () => {
    state.detail = {
      ...DETAIL,
      status: "closed",
      experiments: [],
      recommendation: null,
      latest_requested_run: null,
    };
    renderPage();
    expect(screen.queryByRole("region", { name: "Experiments" })).toBeNull();
    expect(screen.queryByText(/Recommend|Keep baseline/)).toBeNull();
  });

  describe("place in the Execution area", () => {
    const crumbLinks = () =>
      within(screen.getByRole("navigation", { name: "Breadcrumb" }))
        .getAllByRole("link")
        .map((link) => [link.textContent, link.getAttribute("href")]);

    it("names the session by its objective, under Execution and the session list", () => {
      renderPage();
      expect(
        screen.getByRole("heading", { level: 1, name: "Bring up qubits 0 and 1" }),
      ).toBeTruthy();
      expect(screen.getByText("Calibration session")).toBeTruthy();
      // An old bookmark or chat link has no list to return to: the plain session list.
      expect(crumbLinks()).toEqual([
        ["Execution", "/execution?project=lab-a"],
        ["Calibration sessions", "/calibration-sessions?project=lab-a"],
      ]);
    });

    it("heads an automatic session with the workflow name it recorded", () => {
      state.detail = { ...DETAIL, origin: "automatic", objective: "Workflow nightly_1q" };
      renderPage();
      expect(screen.getByRole("heading", { level: 1, name: "Workflow nightly_1q" })).toBeTruthy();
      expect(screen.getByText("Automatic calibration session")).toBeTruthy();
    });

    it("links back to the session list with the filters and page it was opened from", () => {
      renderPage("chip=64Qv3&status=closed&origin=automatic&mine=true&page=2");
      expect(crumbLinks()).toEqual([
        ["Execution", "/execution?chip=64Qv3&project=lab-a"],
        [
          "Calibration sessions",
          "/calibration-sessions?chip=64Qv3&status=closed&origin=automatic&mine=true&page=2&project=lab-a",
        ],
      ]);
    });

    it("links back to the Executions list on its chip when opened from there", () => {
      renderPage("from=executions&chip=64Qv3");
      expect(crumbLinks()).toEqual([["Execution", "/execution?chip=64Qv3&project=lab-a"]]);
    });

    it("drops return values it does not know and keeps links on Execution-area routes", () => {
      renderPage("from=https://evil.example&status=bogus&page=-4&mine=maybe&chip=//evil.example");
      expect(crumbLinks()).toEqual([
        ["Execution", "/execution?chip=%2F%2Fevil.example&project=lab-a"],
        ["Calibration sessions", "/calibration-sessions?chip=%2F%2Fevil.example&project=lab-a"],
      ]);
    });

    it("keeps a long objective whole for reading below its clamped heading", () => {
      const objective = `Bring up qubits ${"0-1 ".repeat(60)}\nthen check coherence`;
      state.detail = { ...DETAIL, objective };
      renderPage();
      const heading = screen.getByRole("heading", { level: 1 });
      expect(heading.textContent).toBe(objective);
      expect(heading.className).toContain("line-clamp-3");
      expect(heading.className).toContain("wrap-anywhere");
      const summary = screen.getByRole("region", { name: "Summary" });
      expect(within(summary).getByText("Objective")).toBeTruthy();
      expect(within(summary).getByText(/then check coherence/).className).toContain(
        "whitespace-pre-wrap",
      );
    });

    it("anchors each run so an execution's breadcrumbs can point at it", () => {
      renderPage();
      const [run] = screen.getAllByTestId("calibration-pipeline-run");
      expect(run.id).toBe("run-cpr-1");
    });

    it("returns to the Executions day, flat list and page, also from its executions", () => {
      renderPage("from=executions&chip=64Qv3&date=20261120&flat=true&page=2&status=closed");
      // Only the Executions list's own filters travel; the session list's status does not.
      expect(crumbLinks()).toEqual([
        ["Execution", "/execution?chip=64Qv3&date=20261120&flat=true&page=2&project=lab-a"],
      ]);
      const runs = screen.getByRole("region", { name: "Runs" });
      expect(within(runs).getByRole("link", { name: "exec-1" }).getAttribute("href")).toBe(
        "/execution/64Qv3/exec-1?project=lab-a&date=20261120&flat=true&page=2",
      );
    });

    it("carries no Executions view to executions of another chip", () => {
      renderPage("from=executions&chip=OTHER&date=20261120&page=2");
      const runs = screen.getByRole("region", { name: "Runs" });
      expect(within(runs).getByRole("link", { name: "exec-1" }).getAttribute("href")).toBe(
        "/execution/64Qv3/exec-1?project=lab-a",
      );
    });

    it("keeps the Executions day and grouping out of the session list's return link", () => {
      renderPage("status=open&date=20261120&flat=true&page=3");
      expect(crumbLinks()).toEqual([
        ["Execution", "/execution?project=lab-a"],
        ["Calibration sessions", "/calibration-sessions?status=open&page=3&project=lab-a"],
      ]);
      // An execution opened from a session reached from the session list carries no view.
      const runs = screen.getByRole("region", { name: "Runs" });
      expect(within(runs).getByRole("link", { name: "exec-1" }).getAttribute("href")).toBe(
        "/execution/64Qv3/exec-1?project=lab-a",
      );
    });

    describe("a link to one run", () => {
      afterEach(() => window.history.replaceState(null, "", "/"));

      it("marks and scrolls to the run when the page lists it", () => {
        const scrollIntoView = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
        window.history.replaceState(null, "", "/calibration-sessions/cs-1#run-cpr-2");
        renderPage();
        const [first, second] = screen.getAllByTestId("calibration-pipeline-run");
        expect(second.getAttribute("aria-current")).toBe("location");
        expect(first.getAttribute("aria-current")).toBeNull();
        expect(scrollIntoView).toHaveBeenCalledTimes(1);
        scrollIntoView.mockRestore();
        expect(screen.queryByTestId("calibration-run-not-listed")).toBeNull();
      });

      it("says so when the run is not among the latest runs listed", () => {
        window.history.replaceState(null, "", "/calibration-sessions/cs-1#run-cpr-old");
        state.detail = { ...DETAIL, pipeline_run_total: 30 };
        renderPage();
        expect(screen.getByTestId("calibration-run-not-listed").textContent).toBe(
          "Run cpr-old is not among the latest 2 runs listed here. Its executions stay on the Execution list.",
        );
        for (const run of screen.getAllByTestId("calibration-pipeline-run")) {
          expect(run.getAttribute("aria-current")).toBeNull();
        }
      });
    });
  });
});
