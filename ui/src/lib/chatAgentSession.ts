/**
 * Which agent session a chat works on, and what that session waits for.
 *
 * The chat stores no link to an agent session. It is read from the chat's own tool calls:
 * a call of a session-scoped agent tool that QDash completed (or that still runs) names the
 * session in its `sessionId` argument. Such a call reached QDash, which checked the user and
 * the project, so the ID is one the tools actually used, never one taken from the model's
 * text. The session's state is then read from QDash under the project open now; a session of
 * another project is not found there, and nothing is shown for it.
 */

import type { ChatMessage, CopilotBlocksResult, TraceStep } from "@/types/copilotChat";

/** Agent tools whose `sessionId` names the one session they act on. */
const SESSION_TOOLS = new Set([
  "qdash_get_agent_session_context",
  "qdash_run_agent_session_step",
  "qdash_request_agent_human",
  "qdash_wait_agent_intervention",
  "qdash_wait_agent_action",
  "qdash_record_agent_decision",
  "qdash_commit_agent_session_update",
  "qdash_get_agent_session_audit",
  "qdash_end_agent_session",
]);

const SESSION_ID = /^[A-Za-z0-9_.:-]{1,200}$/;

function sessionIdOf(step: TraceStep): string | null {
  if (step.kind !== "tool" || !SESSION_TOOLS.has(step.tool)) return null;
  // A call QDash answered, or one still running; never a draft, a failure, or one not made.
  if (step.status !== "done" && step.status !== "running") return null;
  const args = step.args as { sessionId?: unknown } | undefined;
  const id = args?.sessionId;
  return typeof id === "string" && SESSION_ID.test(id) ? id : null;
}

function traceSteps(message: ChatMessage): TraceStep[] {
  if (message.role !== "assistant" || !message.content.startsWith("{")) return [];
  try {
    const parsed = JSON.parse(message.content) as CopilotBlocksResult;
    return Array.isArray(parsed.trace?.steps) ? parsed.trace.steps : [];
  } catch {
    return [];
  }
}

/**
 * The agent sessions the chat's tool calls acted on, oldest first, each once: the saved
 * answers' traces, then the live turn's steps.
 */
export function linkedAgentSessions(
  messages: ChatMessage[],
  liveSteps: TraceStep[] = [],
): string[] {
  const seen: string[] = [];
  const add = (step: TraceStep) => {
    const id = sessionIdOf(step);
    if (!id) return;
    const at = seen.indexOf(id);
    if (at >= 0) seen.splice(at, 1);
    seen.push(id);
  };
  for (const message of messages) traceSteps(message).forEach(add);
  liveSteps.forEach(add);
  return seen;
}

/** The fields of QDash's agent session state this status reads. */
export interface AgentSessionState {
  status: "active" | "waiting_for_human" | "completed" | "cancelled" | "expired";
  active_intervention_id?: string | null;
}

export interface AgentInterventionState {
  intervention_id: string;
  status: "open" | "responding" | "resume_authorized" | "resumed" | "stopped" | "discarded";
}

export interface AgentActionState {
  action_type: string;
  decision: string;
  task_name: string | null;
  qids: string[];
  execution_status: string;
  execution_id?: string | null;
}

/** Run statuses after which a measurement no longer runs (as the API's FINISHED_RUN_STATUSES). */
const FINISHED = new Set(["completed", "failed", "cancelled", "canceled", "crashed", "skipped"]);

export interface AgentSessionStatus {
  phase:
    | "measurement_running"
    | "expert_waiting"
    | "expert_answered"
    | "next_decision"
    | "completed"
    | "cancelled"
    | "expired";
  label: string;
  /** Who acts next: the expert, the measurement, the agent (a chat turn), or nobody. */
  nextActor: "expert" | "measurement" | "agent" | "none";
  /** The latest measurement of the session, if it ran one. */
  measurement: {
    taskName: string;
    qids: string[];
    status: string;
    executionId: string | null;
  } | null;
}

function latestMeasurement(actions: AgentActionState[]): AgentSessionStatus["measurement"] {
  for (let i = actions.length - 1; i >= 0; i--) {
    const action = actions[i];
    if (action.action_type !== "run_task" || !action.task_name) continue;
    if (action.execution_status === "not_started") continue;
    return {
      taskName: action.task_name,
      qids: action.qids,
      status: action.execution_status,
      executionId: action.execution_id ?? null,
    };
  }
  return null;
}

/**
 * What the session waits for, from QDash's records only. An active session is not an agent
 * at work: unless a measurement runs, it waits for the agent's next decision, which only a
 * chat turn makes. An expert's answer that let the session go on waits for that turn too.
 */
export function agentSessionStatus(
  session: AgentSessionState,
  intervention: AgentInterventionState | null,
  actions: AgentActionState[],
): AgentSessionStatus {
  const measurement = latestMeasurement(actions);
  const base = { measurement };
  switch (session.status) {
    case "completed":
      return {
        ...base,
        phase: "completed",
        label: "Agent session completed",
        nextActor: "none",
      };
    case "cancelled":
      return {
        ...base,
        phase: "cancelled",
        label: "Agent session cancelled",
        nextActor: "none",
      };
    case "expired":
      return { ...base, phase: "expired", label: "Agent session expired", nextActor: "none" };
    case "waiting_for_human":
      if (intervention?.status === "resume_authorized") {
        return {
          ...base,
          phase: "expert_answered",
          label: "Expert answered · waiting for the agent's next decision",
          nextActor: "agent",
        };
      }
      return {
        ...base,
        phase: "expert_waiting",
        label: "Waiting for the expert",
        nextActor: "expert",
      };
    default:
      if (measurement && !FINISHED.has(measurement.status)) {
        return {
          ...base,
          phase: "measurement_running",
          label: "Measurement running",
          nextActor: "measurement",
        };
      }
      return {
        ...base,
        phase: "next_decision",
        label: "Waiting for the agent's next decision",
        nextActor: "agent",
      };
  }
}
