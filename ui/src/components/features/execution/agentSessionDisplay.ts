import type { AgentModelIdentity, AgentSessionGroupSummary } from "@/schemas";

import { getStatusBadgeClass } from "./ExecutionListCard";

/** `provider/model_id` of a host-reported model, or null when the record holds none. */
export function reportedModelLabel(model?: AgentModelIdentity | null): string | null {
  return model ? `${model.provider}/${model.model_id}` : null;
}

/** Who reported a model; QDash records it as given and never verifies it. */
export function reportedModelTitle(model: AgentModelIdentity): string {
  return `Reported by ${model.host || "the client"}; QDash does not verify it`;
}

/**
 * The execution status whose color an agent session state shares: an active session reads
 * like a running execution, and a completed or cancelled one like its execution
 * counterpart. A session never takes the failed color, and waiting for a person and
 * expiring have no execution counterpart.
 */
const SESSION_EXECUTION_STATUS: Record<string, string> = {
  active: "running",
  completed: "completed",
  cancelled: "cancelled",
};

/** Badge color of an agent session's own state, from the Execution status palette. */
export function sessionStatusBadgeClass(status: string): string {
  const execution = SESSION_EXECUTION_STATUS[status];
  if (execution) return getStatusBadgeClass(execution);
  // Waiting for a person keeps the warning color the intervention badges use.
  return status === "waiting_for_human" ? "badge-warning" : "badge-ghost";
}

/** What the session is doing right now, from its state and its measurements in flight. */
export function sessionActivityLabel(summary: AgentSessionGroupSummary): string {
  const inFlight = summary.counts.in_flight;
  if (summary.status === "waiting_for_human") {
    return inFlight > 0 ? `Waiting for an expert · ${inFlight} measuring` : "Waiting for an expert";
  }
  if (summary.status === "active") {
    return inFlight > 0
      ? `${inFlight} measurement${inFlight === 1 ? "" : "s"} in flight`
      : "Idle between steps";
  }
  return inFlight > 0
    ? `Ended · ${inFlight} measurement${inFlight === 1 ? "" : "s"} still in flight`
    : "Ended";
}

/** The Execution page path of one session's graph. */
export function sessionGraphHref(chipId: string, sessionId: string, projectId?: string | null) {
  const path = `/execution/${encodeURIComponent(chipId)}/sessions/${encodeURIComponent(sessionId)}`;
  return projectId ? `${path}?project=${encodeURIComponent(projectId)}` : path;
}

/** The session's policy and audit page. */
export function sessionAuditHref(sessionId: string, projectId?: string | null) {
  const path = `/agent-sessions/${encodeURIComponent(sessionId)}`;
  return projectId ? `${path}?project=${encodeURIComponent(projectId)}` : path;
}

export function pluralize(count: number, word: string) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/**
 * The execution a measurement node holds, or why it holds none. A link conflict is not "no
 * execution yet": the action was dispatched, but its execution cannot be attributed to it.
 */
export function measurementExecutionText(
  nodeStatus: string,
  measurement: { execution_status?: string | null; dispatch_status: string },
): string {
  if (nodeStatus === "link_claimed") {
    return `Dispatched (${measurement.dispatch_status}); its execution is held by another action`;
  }
  if (nodeStatus === "link_ambiguous") {
    return `Dispatched (${measurement.dispatch_status}); its ids name different executions`;
  }
  return measurement.execution_status ?? `No execution yet (${measurement.dispatch_status})`;
}
