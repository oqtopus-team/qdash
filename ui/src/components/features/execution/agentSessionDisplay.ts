import type { AgentSessionGroupSummary } from "@/schemas";

/** Badge color of an agent session's own state; never an execution status color for failure. */
export function sessionStatusBadgeClass(status: string): string {
  switch (status) {
    case "active":
      return "badge-info";
    case "waiting_for_human":
      return "badge-warning";
    case "completed":
      return "badge-success";
    case "cancelled":
      return "badge-neutral";
    default:
      return "badge-ghost";
  }
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

/** The Execution page path of one session's journey. */
export function sessionJourneyHref(chipId: string, sessionId: string, projectId?: string | null) {
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
