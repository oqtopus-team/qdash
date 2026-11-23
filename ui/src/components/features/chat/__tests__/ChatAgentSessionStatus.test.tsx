import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatAgentSessionStatus } from "@/components/features/chat/ChatAgentSessionStatus";

const api = vi.hoisted(() => ({
  session: null as null | Record<string, unknown>,
  sessionError: false,
  intervention: null as null | Record<string, unknown>,
  actions: [] as Record<string, unknown>[],
  candidates: [] as Record<string, unknown>[],
  requests: [] as Array<{ key: unknown[]; project: unknown }>,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "p1" }),
}));
vi.mock("@/client/agent-session/agent-session", () => {
  const hook =
    (pick: () => unknown) =>
    (...args: unknown[]) => {
      const options = args[args.length - 1] as {
        query: { queryKey: unknown[]; enabled?: boolean };
        request?: { headers: Record<string, string> };
      };
      api.requests.push({
        key: options.query.queryKey,
        project: options.request?.headers["X-Project-Id"],
      });
      const data = options.query.enabled === false ? undefined : pick();
      return {
        data: data === null || data === undefined ? undefined : { data },
        dataUpdatedAt: 1,
      };
    };
  return {
    getGetAgentSessionQueryKey: (id: string) => [`/agent-sessions/${id}`],
    getGetAgentInterventionQueryKey: (id: string, i: string) => [`/agent-sessions/${id}/i/${i}`],
    getListAgentActionsQueryKey: (id: string) => [`/agent-sessions/${id}/actions`],
    getListAgentActionCandidatesQueryKey: (id: string, a: string) => [`/c/${id}/${a}`],
    useGetAgentSession: (...args: unknown[]) => {
      const result = hook(() => api.session)(...args) as Record<string, unknown>;
      return { ...result, isError: api.sessionError };
    },
    useGetAgentIntervention: hook(() => api.intervention),
    useListAgentActions: hook(() => ({
      items: api.actions,
      total: api.actions.length,
    })),
    useListAgentActionCandidates: hook(() => ({ items: api.candidates })),
  };
});

afterEach(cleanup);

beforeEach(() => {
  api.session = null;
  api.sessionError = false;
  api.intervention = null;
  api.actions = [];
  api.candidates = [];
  api.requests = [];
});

const action = (status: string) => ({
  action_id: "a1",
  action_type: "run_task",
  decision: "allowed",
  task_name: "CheckRabi",
  qids: ["0"],
  execution_status: status,
});

describe("the agent session a chat works on", () => {
  it("shows an expert's answer as waiting for the next decision, and offers only an explicit Continue", () => {
    api.session = {
      session_id: "as-1",
      status: "waiting_for_human",
      active_intervention_id: "i1",
    };
    api.intervention = { intervention_id: "i1", status: "resume_authorized" };
    api.actions = [action("completed")];
    api.candidates = [{ parameter_name: "qubit_frequency" }];
    const onContinue = vi.fn();
    render(
      <ChatAgentSessionStatus agentSessionId="as-1" chatTurn="none" onContinue={onContinue} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Expert answered · waiting for the agent's next decision",
    );
    expect(screen.getByTestId("chat-agent-session")).toHaveTextContent(
      "Latest measurement: CheckRabi on 0 · completed · 1 candidate value",
    );
    expect(screen.getByTestId("chat-agent-session")).toHaveTextContent(
      "No chat turn is running, so nothing happens until you continue.",
    );
    expect(onContinue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("continue-agent-session"));
    expect(onContinue).toHaveBeenCalledTimes(1);
    // Every read names the project open now, and its cache key holds it.
    expect(api.requests.every((r) => r.project === "p1" && r.key.includes("p1"))).toBe(true);
  });

  it("does not offer Continue while the chat's own turn decides", () => {
    api.session = { session_id: "as-1", status: "active" };
    api.actions = [action("completed")];
    render(<ChatAgentSessionStatus agentSessionId="as-1" chatTurn="live" onContinue={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for the agent's next decision");
    expect(screen.getByTestId("chat-agent-session")).toHaveTextContent(
      "the agent decides in the turn running in this chat",
    );
    expect(screen.queryByTestId("continue-agent-session")).toBeNull();
  });

  it("names a running measurement and an open question to the expert as the next actors", () => {
    api.session = { session_id: "as-1", status: "active" };
    api.actions = [action("running")];
    const { unmount } = render(
      <ChatAgentSessionStatus agentSessionId="as-1" chatTurn="none" onContinue={vi.fn()} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Measurement running");
    expect(screen.queryByTestId("continue-agent-session")).toBeNull();
    unmount();
    api.session = {
      session_id: "as-1",
      status: "waiting_for_human",
      active_intervention_id: "i1",
    };
    api.intervention = { intervention_id: "i1", status: "open" };
    render(<ChatAgentSessionStatus agentSessionId="as-1" chatTurn="none" onContinue={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for the expert");
    expect(screen.queryByTestId("continue-agent-session")).toBeNull();
  });

  it("shows nothing for a session QDash does not find in this project", () => {
    api.sessionError = true;
    const { container } = render(<ChatAgentSessionStatus agentSessionId="as-x" chatTurn="none" />);
    expect(container).toBeEmptyDOMElement();
  });
});
