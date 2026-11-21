import type { ReactNode } from "react";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentSessionJourneyPageContent } from "@/components/features/execution/AgentSessionJourneyPageContent";

const mocks = vi.hoisted(() => ({
  flowProps: null as Record<string, unknown> | null,
  journeyCall: null as unknown[] | null,
}));

vi.mock("@xyflow/react", () => {
  type FakeNode = { id: string; data: Record<string, unknown> };
  type FakeProps = {
    nodes?: FakeNode[];
    children?: ReactNode;
    onNodeClick?: (event: unknown, node: FakeNode) => void;
  };
  return {
    ReactFlow: (props: FakeProps) => {
      mocks.flowProps = props as Record<string, unknown>;
      return (
        <div data-testid="react-flow">
          {props.nodes?.map((node) => (
            <button
              key={node.id}
              type="button"
              data-testid={`node-${node.id}`}
              onClick={(event) => props.onNodeClick?.(event, node)}
            >
              {node.id}
            </button>
          ))}
          {props.children}
        </div>
      );
    },
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    Position: { Left: "left", Right: "right" },
    ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    Panel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    MarkerType: { ArrowClosed: "arrowclosed" },
  };
});

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/components/features/task-results/TaskResultPreviewSidebar", () => ({
  TaskResultPreviewSidebar: ({ taskId }: { taskId: string | null }) =>
    taskId ? <div data-testid="task-preview">preview {taskId}</div> : null,
}));

let linked: Record<string, unknown> = { status: "ready", projectId: "project-1" };
vi.mock("@/components/features/agent-session/useLinkedProject", () => ({
  useLinkedProject: () => linked,
  projectRequest: (projectId: string) => ({ headers: { "X-Project-Id": projectId } }),
}));

let journeyResult: Record<string, unknown> = {};
vi.mock("@/client/execution/execution", () => ({
  getGetAgentSessionJourneyQueryKey: (sessionId: string) => [
    `/executions/groups/agent-sessions/${sessionId}`,
  ],
  useGetAgentSessionJourney: (...args: unknown[]) => {
    mocks.journeyCall = args;
    return journeyResult;
  },
}));

const measurement = (
  id: string,
  order: number,
  fields: Record<string, unknown>,
  status = "completed",
) => ({
  node_id: `action:${id}`,
  kind: "measurement",
  order,
  at: `2026-11-20T00:0${order}:00Z`,
  label: String(fields.label ?? "CheckRabi on Q00"),
  status,
  status_is_current: true,
  missing: [],
  measurement: {
    action_id: id,
    task_name: "CheckRabi",
    qid: "Q00",
    sequence: order + 1,
    attempt: order + 1,
    dispatch_status: "queued",
    execution_id: `exec-${id}`,
    execution_status: status,
    task_id: `task-${id}`,
    task_status: status,
    figure_count: 1,
    intent: "",
    ...fields,
  },
});

const JOURNEY = {
  generated_at: "2026-11-20T01:00:00Z",
  session: {
    session_id: "session-1",
    project_id: "project-1",
    chip_id: "chip-1",
    created_by: "alice",
    created_at: "2026-11-20T00:00:00Z",
    updated_at: "2026-11-20T00:05:00Z",
    expires_at: "2026-11-21T00:00:00Z",
    status: "waiting_for_human",
    stored_status: "waiting_for_human",
    active_intervention_id: "int-1",
    qids: ["Q00"],
    allowed_tasks: ["CheckRabi"],
    autonomy: "auto",
    skill_name: "qdash-one-qubit-calibration",
    model_name: "",
    counts: {
      actions: 4,
      max_actions: 20,
      measurements: 2,
      pending_dispatch: 0,
      dispatch_failed: 0,
      in_flight: 0,
      rejected_proposals: 1,
      open_interventions: 1,
      decisions: 1,
    },
    latest_activity_at: "2026-11-20T00:01:00Z",
    missing: [],
  },
  nodes: [
    measurement("a1", 0, {}),
    measurement("a2", 1, { label: "CheckRabi on Q00 (attempt 2)", repeat_of_action_id: "a1" }),
    {
      node_id: "action:a3",
      kind: "proposal",
      order: 2,
      at: "2026-11-20T00:02:00Z",
      label: "Rejected: CheckT1 on Q00",
      status: "rejected",
      missing: [],
      proposal: {
        action_id: "a3",
        action_type: "run_task",
        task_name: "CheckT1",
        qids: ["Q00"],
        reason: "Task CheckT1 is not allowed",
        intent: "",
      },
    },
    {
      node_id: "decision:d1",
      kind: "decision",
      order: 3,
      at: "2026-11-20T00:03:00Z",
      label: "fail → request_human",
      status: "recorded",
      missing: [],
      decision: {
        decision_id: "d1",
        assessment: "fail",
        interpretation: "Both Rabi fits disagree by 20 percent.",
        next_action: "request_human",
        next_detail: "",
        evidence_action_ids: ["a1", "a2"],
        evaluation_ids: [],
      },
    },
    {
      node_id: "intervention:int-1",
      kind: "intervention",
      order: 4,
      at: "2026-11-20T00:04:00Z",
      label: "Expert asked: Widen the sweep?",
      status: "open",
      status_is_current: true,
      missing: [],
      intervention: {
        intervention_id: "int-1",
        reason: "evaluation_failed",
        status: "open",
        question: "Widen the sweep?",
        summary: "",
        pauses_session: true,
        response_guidance: "",
      },
    },
  ],
  edges: [
    { edge_id: "s1", kind: "sequence", source: "action:a1", target: "action:a2" },
    { edge_id: "r1", kind: "retry_of", source: "action:a1", target: "action:a2" },
    { edge_id: "e1", kind: "evidence", source: "action:a1", target: "decision:d1" },
    { edge_id: "e2", kind: "evidence", source: "action:a2", target: "decision:d1" },
    { edge_id: "x1", kind: "escalation", source: "decision:d1", target: "intervention:int-1" },
  ],
  total_nodes: 5,
  omitted_nodes: 0,
  complete: true,
  notes: [],
};

function ok(data: unknown) {
  return { data: { data }, isLoading: false, isError: false, error: null };
}

describe("AgentSessionJourneyPageContent", () => {
  beforeEach(() => {
    linked = { status: "ready", projectId: "project-1" };
    journeyResult = ok(JOURNEY);
  });

  afterEach(() => {
    cleanup();
    mocks.flowProps = null;
  });

  it("pins the request to the linked project and shows the session's own status", () => {
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    const [sessionId, options] = mocks.journeyCall as [
      string,
      { query: { queryKey: unknown[] }; request: { headers: Record<string, string> } },
    ];
    expect(sessionId).toBe("session-1");
    expect(options.query.queryKey).toContain("project-1");
    expect(options.request.headers["X-Project-Id"]).toBe("project-1");

    const session = within(screen.getByRole("region", { name: "Session" }));
    expect(session.getByText("Paused for an expert")).toBeTruthy();
    expect(session.getByText("Waiting for an expert")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Policy and audit" }).getAttribute("href")).toBe(
      "/agent-sessions/session-1?project=project-1",
    );
    expect(
      screen.getByRole("link", { name: "Answer the expert request" }).getAttribute("href"),
    ).toBe("/agent-sessions/session-1/interventions/int-1?project=project-1");
  });

  it("draws dispatch order apart from recorded links", () => {
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    const edges = (mocks.flowProps?.edges ?? []) as {
      id: string;
      label?: string;
      style: { strokeDasharray?: string };
      target: string;
    }[];
    const sequence = edges.find((edge) => edge.id === "s1");
    expect(sequence?.label).toBeUndefined();
    expect(sequence?.style.strokeDasharray).toBe("6 4");
    const evidence = edges.filter((edge) => edge.label === "Evidence for");
    // One decision citing two earlier results.
    expect(evidence.map((edge) => edge.target)).toEqual(["decision:d1", "decision:d1"]);
    expect(evidence.every((edge) => edge.style.strokeDasharray === undefined)).toBe(true);
    expect(edges.find((edge) => edge.id === "r1")?.label).toBe("Repeated as");
    expect(screen.getByText("Dispatch order, time only")).toBeTruthy();
  });

  it("opens a measurement in the task result preview", () => {
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    fireEvent.click(screen.getByTestId("node-action:a2"));
    expect(screen.getByTestId("task-preview").textContent).toBe("preview task-a2");
    expect(screen.queryByTestId("journey-selected")).toBeNull();
  });

  it("shows a decision's rationale, next action, evidence, and audit link", () => {
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    fireEvent.click(screen.getByTestId("node-decision:d1"));
    const detail = screen.getByTestId("journey-selected");
    expect(within(detail).getByText("Both Rabi fits disagree by 20 percent.")).toBeTruthy();
    expect(within(detail).getByText("request human")).toBeTruthy();
    expect(within(detail).getByText("1. CheckRabi on Q00")).toBeTruthy();
    expect(within(detail).getByText("2. CheckRabi on Q00 (attempt 2)")).toBeTruthy();
    expect(within(detail).getByRole("link", { name: "Audit" }).getAttribute("href")).toBe(
      "/agent-sessions/session-1?project=project-1",
    );

    // Following the evidence selects the measurement it names.
    fireEvent.click(within(detail).getByText("1. CheckRabi on Q00"));
    expect(screen.getByTestId("task-preview").textContent).toBe("preview task-a1");
  });

  it("shows an expert request with its intervention link, and a rejected proposal", () => {
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    fireEvent.click(screen.getByTestId("node-intervention:int-1"));
    let detail = screen.getByTestId("journey-selected");
    expect(within(detail).getByText("Widen the sweep?")).toBeTruthy();
    expect(within(detail).getByText("Not answered yet")).toBeTruthy();
    expect(within(detail).getByRole("link", { name: "Intervention" }).getAttribute("href")).toBe(
      "/agent-sessions/session-1/interventions/int-1?project=project-1",
    );

    fireEvent.click(screen.getByTestId("node-action:a3"));
    detail = screen.getByTestId("journey-selected");
    expect(within(detail).getByText("Task CheckT1 is not allowed")).toBeTruthy();
    expect(within(detail).getByText(/never reached hardware/)).toBeTruthy();
    expect(within(detail).queryByRole("link", { name: "Execution" })).toBeNull();
  });

  it("lists every step in time order with links to the real records", () => {
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(5);
    const first = within(rows[0]);
    expect(first.getByRole("link", { name: "Execution" }).getAttribute("href")).toBe(
      "/execution/chip-1/exec-a1",
    );
    expect(first.getByRole("link", { name: "Result and figures" }).getAttribute("href")).toBe(
      "/task-results/task-a1",
    );
    expect(first.getByText("Evidence for 4")).toBeTruthy();
    // The temporal sequence edge is not listed as a link.
    expect(first.queryByText(/Dispatched next/)).toBeNull();
  });

  it("shows a link conflict as dispatched without an execution", () => {
    const conflicted = {
      ...measurement(
        "a9",
        5,
        { execution_id: null, execution_status: null, task_id: null, task_status: null },
        "link_claimed",
      ),
      missing: ["execution_link_claimed"],
    };
    journeyResult = ok({ ...JOURNEY, nodes: [...JOURNEY.nodes, conflicted], total_nodes: 6 });
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    fireEvent.click(screen.getByTestId("node-action:a9"));
    const detail = screen.getByTestId("journey-selected");
    expect(
      within(detail).getByText("Dispatched (queued); its execution is held by another action"),
    ).toBeTruthy();
    expect(within(detail).queryByText(/No execution yet/)).toBeNull();
    expect(within(detail).queryByRole("link", { name: "Execution" })).toBeNull();
  });

  it("says when the journey is truncated", () => {
    journeyResult = ok({ ...JOURNEY, complete: false, total_nodes: 1500, omitted_nodes: 1495 });
    render(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    expect(screen.getByText(/Showing the latest 5 of 1500 steps/)).toBeTruthy();
  });

  it("reports a load error, a project without access, and a session of another chip", () => {
    journeyResult = {
      data: undefined,
      isLoading: false,
      isError: true,
      error: { response: { data: { detail: "Agent session 'session-1' not found" } } },
    };
    const { rerender } = render(
      <AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />,
    );
    expect(screen.getByRole("alert").textContent).toContain("not found");

    linked = { status: "unavailable", projectId: "lab-b" };
    rerender(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    expect(screen.getByRole("alert").textContent).toContain("project lab-b");

    linked = { status: "ready", projectId: "project-1" };
    journeyResult = ok(JOURNEY);
    rerender(<AgentSessionJourneyPageContent chipId="chip-9" sessionId="session-1" />);
    expect(screen.getByRole("alert").textContent).toContain("ran on chip chip-1");
    expect(screen.getByRole("link", { name: "Open it on chip-1" }).getAttribute("href")).toBe(
      "/execution/chip-1/sessions/session-1?project=project-1",
    );
  });

  it("starts with nothing selected after a project switch", () => {
    const { rerender } = render(
      <AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />,
    );
    fireEvent.click(screen.getByTestId("node-decision:d1"));
    expect(screen.getByTestId("journey-selected")).toBeTruthy();

    linked = { status: "ready", projectId: "project-2" };
    journeyResult = ok({ ...JOURNEY, session: { ...JOURNEY.session, project_id: "project-2" } });
    rerender(<AgentSessionJourneyPageContent chipId="chip-1" sessionId="session-1" />);
    expect(screen.queryByTestId("journey-selected")).toBeNull();
    const [, options] = mocks.journeyCall as [string, { query: { queryKey: unknown[] } }];
    expect(options.query.queryKey).toContain("project-2");
  });
});
