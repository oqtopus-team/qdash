import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ExecutionAgentSessionLink,
  ExecutionCalibrationSessionLink,
  ExecutionGroupItem,
  ExecutionResponseSummary,
  ReportedLaunchOrigin,
} from "@/schemas";

import { AgentSessionGroupRow } from "@/components/features/execution/AgentSessionGroupRow";
import { ExecutionCalibrationNotice } from "@/components/features/execution/ExecutionCalibrationContext";
import { ExecutionListCard } from "@/components/features/execution/ExecutionListCard";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const PIPELINE_MEMBER: ExecutionCalibrationSessionLink = {
  calibration_session_id: "cs-1",
  chip_id: "chip-1",
  objective: "Bring up qubits 0 and 1",
  status: "open",
  via: "pipeline_run",
  pipeline_run_id: "cpr-1",
  agent_session_id: null,
};

const AGENT_MEMBER: ExecutionCalibrationSessionLink = {
  ...PIPELINE_MEMBER,
  via: "agent_session",
  pipeline_run_id: null,
  agent_session_id: "session-1",
};

const AGENT_TOOL: ReportedLaunchOrigin = {
  source: "agent_tool",
  tool: "qdash_run_pipeline",
  client: "pi-qdash",
};

const LINKED: ExecutionAgentSessionLink = {
  session_id: "session-1",
  linked: true,
  action_id: "a1",
  status: "active",
  created_by: "alice",
  model_name: "",
};

function execution(fields: Partial<ExecutionResponseSummary> = {}): ExecutionResponseSummary {
  return {
    name: "pipeline-exec-1",
    execution_id: "exec-1",
    status: "completed",
    start_at: "2026-11-20T00:00:00Z",
    username: "carol",
    tags: [],
    note: {},
    ...fields,
  };
}

function renderCard(row: ExecutionResponseSummary) {
  render(
    <ExecutionListCard
      execution={row}
      isSelected={false}
      isPanelOpen={false}
      onOpen={() => {}}
      registerCard={() => {}}
    />,
  );
  return screen.getByRole("button", { name: `View ${row.name} execution details` });
}

describe("calibration session and reported origin on executions", () => {
  afterEach(cleanup);

  it("leaves an ordinary execution exactly as before", () => {
    const card = renderCard(execution());
    expect(within(card).queryByTestId("calibration-session-badge")).toBeNull();
    expect(within(card).queryByTestId("reported-origin-badge")).toBeNull();
    const { container } = render(<ExecutionCalibrationNotice link={null} origin={null} />);
    expect(container.textContent).toBe("");
  });

  it("shows a manual pipeline step's objective without calling it an agent run", () => {
    const card = renderCard(execution({ calibration_session: PIPELINE_MEMBER }));
    const badge = within(card).getByTestId("calibration-session-badge");
    expect(badge.textContent).toBe("Calibration session: Bring up qubits 0 and 1");
    expect(within(card).getByText("@carol")).toBeTruthy();
    expect(within(card).queryByText("Agent")).toBeNull();
    // The card is itself a button: the badge carries no nested link.
    expect(within(card).queryByRole("link")).toBeNull();
  });

  it("labels a reported agent tool pipeline as reported, apart from a verified agent", () => {
    const card = renderCard(execution({ reported_origin: AGENT_TOOL }));
    expect(within(card).getByTestId("reported-origin-badge").textContent).toBe(
      "Agent tool, reported",
    );
    expect(within(card).getByText("@carol")).toBeTruthy();
    expect(within(card).queryByText("Agent")).toBeNull();
    cleanup();
    // A verified agent session action keeps its own label and needs no report.
    const agent = renderCard(
      execution({ agent_session: LINKED, calibration_session: AGENT_MEMBER, username: "alice" }),
    );
    expect(within(agent).getByText("Agent").parentElement?.textContent).toBe("Agent·@alice");
    expect(within(agent).queryByTestId("reported-origin-badge")).toBeNull();
    expect(within(agent).getByTestId("calibration-session-badge")).toBeTruthy();
  });

  it("links back to the calibration session in the execution's project", () => {
    render(
      <ExecutionCalibrationNotice link={PIPELINE_MEMBER} origin={AGENT_TOOL} projectId="lab-a" />,
    );
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("Bring up qubits 0 and 1");
    expect(note.textContent).toContain("A step of run cpr-1");
    expect(note.textContent).toContain("pi-qdash reported that the agent tool qdash_run_pipeline");
    expect(note.textContent).toContain("QDash does not verify this");
    expect(
      within(note).getByRole("link", { name: "Open calibration session" }).getAttribute("href"),
    ).toBe("/calibration-sessions/cs-1?project=lab-a");
    cleanup();
    render(<ExecutionCalibrationNotice link={AGENT_MEMBER} projectId="lab-a" />);
    expect(screen.getByRole("note").textContent).toContain(
      "Run by agent session session-1, which was admitted to this calibration session",
    );
  });

  it("states a report without a session and offers no link", () => {
    render(<ExecutionCalibrationNotice origin={AGENT_TOOL} projectId="lab-a" />);
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("The recorded user started it with their own sign-in");
    expect(within(note).queryByRole("link")).toBeNull();
  });

  it("links an agent session row to its calibration session, and its children agree", () => {
    const item: ExecutionGroupItem = {
      kind: "agent_session",
      sort_at: "2026-11-20T00:00:00Z",
      agent_session: {
        session_id: "session-1",
        project_id: "lab-a",
        chip_id: "chip-1",
        created_by: "alice",
        created_at: "2026-11-20T00:00:00Z",
        updated_at: "2026-11-20T00:00:00Z",
        expires_at: "2026-11-21T00:00:00Z",
        status: "active",
        stored_status: "active",
        qids: ["0"],
        allowed_tasks: ["CheckRabi"],
        autonomy: "auto",
        calibration_session: {
          calibration_session_id: "cs-1",
          chip_id: "chip-1",
          objective: "Bring up qubits 0 and 1",
          status: "open",
        },
        counts: {
          actions: 1,
          max_actions: 4,
          measurements: 1,
          pending_dispatch: 0,
          in_flight: 0,
          rejected_proposals: 0,
          open_interventions: 0,
          decisions: 0,
        },
        latest_activity_at: "2026-11-20T00:00:00Z",
      },
      children: [
        {
          action_id: "a1",
          sequence: 1,
          attempt: 1,
          in_filter: true,
          execution: execution({
            name: "agent-exec",
            agent_session: LINKED,
            calibration_session: AGENT_MEMBER,
          }),
        },
      ],
      children_total: 1,
      children_in_filter: 1,
      children_omitted: 0,
    };
    render(
      <AgentSessionGroupRow
        item={item}
        projectId="lab-a"
        isExpanded
        onToggle={() => {}}
        selectedExecutionId={null}
        isPanelOpen={false}
        onOpenExecution={() => {}}
        registerCard={() => {}}
        hasDayFilter={false}
      />,
    );
    const parent = screen.getByRole("link", {
      name: "Calibration session: Bring up qubits 0 and 1",
    });
    expect(parent.getAttribute("href")).toBe("/calibration-sessions/cs-1?project=lab-a");
    // The link sits beside the expand button, never inside it.
    expect(screen.getByRole("button", { expanded: true }).contains(parent)).toBe(false);
    const child = screen.getByRole("button", { name: "View agent-exec execution details" });
    expect(within(child).getByTestId("calibration-session-badge").textContent).toContain(
      "Bring up qubits 0 and 1",
    );
  });
});
