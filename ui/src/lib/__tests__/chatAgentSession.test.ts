import { describe, expect, it } from "vitest";

import {
  agentSessionStatus,
  linkedAgentSessions,
  type AgentActionState,
} from "@/lib/chatAgentSession";
import type { ChatMessage, TraceStep } from "@/types/copilotChat";

const tool = (
  name: string,
  status: "done" | "running" | "error" | "drafting",
  sessionId: unknown,
): TraceStep => ({
  kind: "tool",
  id: `${name}-${String(sessionId)}`,
  tool: name,
  label: name,
  status,
  startedAt: 0,
  args: { sessionId },
});

const answer = (steps: TraceStep[]): ChatMessage => ({
  role: "assistant",
  content: JSON.stringify({ blocks: [], assessment: null, trace: { steps, durationMs: 1 } }),
});

describe("the agent sessions a chat acted on", () => {
  it("comes from session tools QDash completed or still runs, never from text or failed calls", () => {
    const messages: ChatMessage[] = [
      { role: "user", content: "Use session as-evil please" },
      answer([
        tool("qdash_get_agent_session_context", "done", "as-1"),
        tool("qdash_run_agent_session_step", "error", "as-bad"),
        tool("qdash_list_agent_sessions", "done", "as-list"),
        tool("qdash_record_agent_decision", "drafting", "as-draft"),
      ]),
      { role: "assistant", content: "Error: failed with as-text" },
    ];
    expect(linkedAgentSessions(messages)).toEqual(["as-1"]);
    // The live turn's wait counts, and the latest session comes last.
    expect(
      linkedAgentSessions(messages, [
        tool("qdash_wait_agent_intervention", "running", "as-2"),
        tool("qdash_get_agent_session_context", "done", "as-1"),
      ]),
    ).toEqual(["as-2", "as-1"]);
    expect(
      linkedAgentSessions([answer([tool("qdash_end_agent_session", "done", "../x")])]),
    ).toEqual([]);
  });
});

const measured = (status: string): AgentActionState => ({
  action_type: "run_task",
  decision: "allowed",
  task_name: "CheckRabi",
  qids: ["0"],
  execution_status: status,
  execution_id: "e1",
});

describe("what a calibration session waits for", () => {
  it("never takes an active session for an agent at work", () => {
    const status = agentSessionStatus({ status: "active" }, null, [measured("completed")]);
    expect(status).toMatchObject({ phase: "next_decision", nextActor: "agent" });
    expect(status.measurement).toMatchObject({ taskName: "CheckRabi", status: "completed" });
  });

  it("shows a running measurement as the next actor", () => {
    expect(agentSessionStatus({ status: "active" }, null, [measured("running")])).toMatchObject({
      phase: "measurement_running",
      nextActor: "measurement",
    });
  });

  it("tells an expert still to answer from an expert who answered", () => {
    const session = { status: "waiting_for_human" as const, active_intervention_id: "i1" };
    expect(
      agentSessionStatus(session, { intervention_id: "i1", status: "open" }, []),
    ).toMatchObject({ phase: "expert_waiting", nextActor: "expert" });
    expect(
      agentSessionStatus(session, { intervention_id: "i1", status: "resume_authorized" }, []),
    ).toMatchObject({ phase: "expert_answered", nextActor: "agent" });
  });

  it("says an ended session needs no one", () => {
    expect(agentSessionStatus({ status: "completed" }, null, [])).toMatchObject({
      phase: "completed",
      nextActor: "none",
    });
  });
});
