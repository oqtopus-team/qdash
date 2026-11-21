import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ExecutionAgentSessionLink,
  ExecutionGroupItem,
  ExecutionResponseSummary,
} from "@/schemas";

import { AgentSessionGroupRow } from "@/components/features/execution/AgentSessionGroupRow";
import { ExecutionAgentSessionNotice } from "@/components/features/execution/ExecutionAgentSessionNotice";
import { ExecutionListCard } from "@/components/features/execution/ExecutionListCard";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

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
    name: "agent:CheckRabi-exec-1",
    execution_id: "exec-1",
    status: "completed",
    start_at: "2026-11-20T00:00:00Z",
    username: "alice",
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

describe("execution attribution", () => {
  afterEach(cleanup);

  it("shows a manual run as its recorded user, with no agent badge", () => {
    const card = renderCard(execution({ name: "manual-exec-1", username: "carol" }));
    expect(within(card).getByText("@carol")).toBeTruthy();
    expect(within(card).queryByText("Agent")).toBeNull();
  });

  it("shows a verified agent dispatch as Agent · the recorded user", () => {
    const card = renderCard(execution({ agent_session: LINKED }));
    const badge = within(card).getByText("Agent");
    expect(badge.className).toContain("badge");
    expect(within(card).getByText("@alice")).toBeTruthy();
    expect(badge.parentElement?.textContent).toBe("Agent·@alice");
  });

  it("never treats an agent-like name, a tag, or an unlinked hint as an agent run", () => {
    const card = renderCard(
      execution({
        tags: ["agent-session:session-1"],
        agent_session: { session_id: "session-1", linked: false },
      }),
    );
    expect(within(card).queryByText("Agent")).toBeNull();
    expect(within(card).getByText("@alice")).toBeTruthy();
  });

  it("labels a missing recorded user without guessing who it was", () => {
    const manual = renderCard(execution({ name: "no-user", username: "", user_id: null }));
    expect(within(manual).getByText("Unknown")).toBeTruthy();
    cleanup();
    // An agent row without a recorded user falls back to the session creator only.
    const agent = renderCard(
      execution({ name: "agent-no-user", username: "", user_id: null, agent_session: LINKED }),
    );
    expect(within(agent).getByText("@alice")).toBeTruthy();
    cleanup();
    const neither = renderCard(
      execution({
        name: "agent-no-one",
        username: "",
        user_id: null,
        agent_session: { ...LINKED, created_by: null },
      }),
    );
    expect(within(neither).getByText("Agent")).toBeTruthy();
    expect(within(neither).getByText("Unknown")).toBeTruthy();
  });

  it("names the responsible user apart from the agent in the detail notice", () => {
    render(
      <ExecutionAgentSessionNotice link={{ ...LINKED, model_name: "gpt-x" }} chipId="chip-1" />,
    );
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("Run by an agent");
    expect(note.textContent).toContain("@alice created the session and is responsible for it");
    expect(note.textContent).toContain("Model: gpt-x");
    expect(note.textContent).toContain("Expert answers and commits keep their own users");
  });

  it("does not claim delegation for a tag-only legacy execution", () => {
    render(
      <ExecutionAgentSessionNotice
        link={{ session_id: "session-1", linked: false, created_by: "alice" }}
        chipId="chip-1"
      />,
    );
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("Tagged for agent session");
    expect(note.textContent).not.toContain("Run by an agent");
    expect(note.textContent).not.toContain("responsible");
  });

  it("attributes a session row and its children the same way", () => {
    const item: ExecutionGroupItem = {
      kind: "agent_session",
      sort_at: "2026-11-20T00:00:00Z",
      agent_session: {
        session_id: "session-1",
        project_id: "project-1",
        chip_id: "chip-1",
        created_by: "alice",
        created_at: "2026-11-20T00:00:00Z",
        updated_at: "2026-11-20T00:00:00Z",
        expires_at: "2026-11-21T00:00:00Z",
        status: "active",
        stored_status: "active",
        qids: ["Q00"],
        allowed_tasks: ["CheckRabi"],
        autonomy: "auto",
        counts: {
          actions: 1,
          max_actions: 10,
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
          execution: execution({ agent_session: LINKED }),
        },
      ],
      children_total: 1,
      children_in_filter: 1,
      children_omitted: 0,
    };
    render(
      <AgentSessionGroupRow
        item={item}
        projectId="project-1"
        isExpanded
        onToggle={() => {}}
        selectedExecutionId={null}
        isPanelOpen={false}
        onOpenExecution={() => {}}
        registerCard={() => {}}
        hasDayFilter={false}
      />,
    );
    const header = screen.getByRole("button", { expanded: true });
    expect(within(header).getByText("Agent").parentElement?.textContent).toBe("Agent·@alice");
    const child = screen.getByRole("button", {
      name: "View agent:CheckRabi-exec-1 execution details",
    });
    expect(within(child).getByText("Agent").parentElement?.textContent).toBe("Agent·@alice");
  });
});
