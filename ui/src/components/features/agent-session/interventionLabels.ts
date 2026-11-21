import type { AgentInterventionResponse } from "@/schemas";

/** Reason labels; keep in sync with REASON_LABELS in src/qdash/api/services/agent_intervention_slack.py. */
const REASON_LABELS: Record<string, string> = {
  unknown_outcome: "Unknown outcome",
  recovery_exhausted: "Recovery exhausted",
  evaluation_failed: "Evaluation failed",
  platform_error: "Platform or hardware error",
  policy_limit: "Session limit",
  agent_request: "Agent request",
};

/**
 * Intervention status labels and badge colors. The Slack message uses the same labels
 * (STATUS_STYLES in src/qdash/api/services/agent_intervention_slack.py).
 */
const STATUS_STYLES: Record<string, { label: string; badge: string }> = {
  open: { label: "Waiting for an expert", badge: "badge-warning" },
  responding: { label: "Waiting for an expert", badge: "badge-warning" },
  resume_authorized: { label: "Resume authorized", badge: "badge-info" },
  resumed: { label: "Resumed", badge: "badge-success" },
  stopped: { label: "Stopped", badge: "badge-neutral" },
  discarded: { label: "Discarded", badge: "badge-ghost" },
};

const NOTIFICATION_STYLES: Record<string, { label: string; badge: string }> = {
  disabled: { label: "Slack not configured", badge: "badge-ghost" },
  pending: { label: "Slack pending", badge: "badge-warning" },
  sending: { label: "Slack sending", badge: "badge-info" },
  sent: { label: "Slack sent", badge: "badge-success" },
  failed: { label: "Slack failed", badge: "badge-error" },
};

const SESSION_LABELS: Record<string, string> = {
  active: "Active",
  waiting_for_human: "Paused for an expert",
  completed: "Completed",
  cancelled: "Cancelled",
  expired: "Expired",
};

export function interventionReasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason.replace(/_/g, " ");
}

export function interventionStatusStyle(status: string): { label: string; badge: string } {
  return STATUS_STYLES[status] ?? { label: status.replace(/_/g, " "), badge: "badge-ghost" };
}

export function notificationStyle(status: string): { label: string; badge: string } {
  return NOTIFICATION_STYLES[status] ?? { label: status, badge: "badge-ghost" };
}

export function sessionStatusLabel(status: string): string {
  return SESSION_LABELS[status] ?? status.replace(/_/g, " ");
}

/** The intervention page path, with the project selected so a Slack link opens the right one. */
export function interventionHref(intervention: AgentInterventionResponse): string {
  return `${intervention.page_path}?project=${encodeURIComponent(intervention.project_id)}`;
}

/** What the expert can do now, in the order the page offers it. */
export type InterventionActionState =
  | { kind: "answer"; canResume: boolean }
  | { kind: "ready_to_resume" }
  | { kind: "closed" };

export function interventionActionState(
  intervention: AgentInterventionResponse,
): InterventionActionState {
  if (intervention.status === "open") {
    return { kind: "answer", canResume: intervention.can_resume };
  }
  if (intervention.status === "resume_authorized") return { kind: "ready_to_resume" };
  return { kind: "closed" };
}
