/**
 * Which calibration sessions a chat's work belongs to.
 *
 * A calibration session is QDash's record of one calibration objective; the chat is only where
 * the work was asked for. The chat stores no link to it: a session is found from the chat's own
 * tool calls, either a `qdash_create_calibration_session` call that QDash completed (its ID is
 * the typed `calibrationSession` of the step, taken from the tool's result, never from the
 * model's arguments or text), or a call that names one in its `calibrationSessionId` argument
 * (reading it, or starting a pipeline run or an agent session in it). The session and what
 * belongs to it are then read from QDash under the project open now, so an ID QDash does not
 * find there shows nothing. What belongs to a session is QDash's explicit record, never this
 * chat's trace.
 *
 * Deleting the chat changes no record, and a branched chat shows the same sessions from the
 * calls it copied, without copying anything in QDash.
 */

import { CREATE_CALIBRATION_SESSION_TOOL } from "@/lib/agentChatStream";
import type { ChatMessage, AgentBlocksResult, TraceStep } from "@/types/agentChat";

/** Tools whose `calibrationSessionId` argument names one calibration session. */
const CALIBRATION_SESSION_TOOLS = new Set([
  "qdash_get_calibration_session",
  "qdash_get_calibration_session_audit",
  "qdash_record_calibration_decision",
  "qdash_run_pipeline",
  "qdash_create_agent_session",
]);

const CALIBRATION_SESSION_ID = /^[A-Za-z0-9_.:-]{1,200}$/;

function calibrationSessionIdOf(step: TraceStep): string | null {
  if (step.kind !== "tool") return null;
  if (step.tool === CREATE_CALIBRATION_SESSION_TOOL) {
    // Created only when QDash completed the call; a refused, failed, or cancelled call, or one
    // still running, has created nothing the chat may show.
    if (step.status !== "done") return null;
    const id = step.calibrationSession?.calibrationSessionId;
    return typeof id === "string" && CALIBRATION_SESSION_ID.test(id) ? id : null;
  }
  if (!CALIBRATION_SESSION_TOOLS.has(step.tool)) return null;
  // A call that was made; never a draft, a failure, or one the turn ended before.
  if (step.status !== "done" && step.status !== "running") return null;
  const args = step.args as { calibrationSessionId?: unknown } | undefined;
  const id = args?.calibrationSessionId;
  return typeof id === "string" && CALIBRATION_SESSION_ID.test(id) ? id : null;
}

function traceSteps(message: ChatMessage): TraceStep[] {
  if (message.role !== "assistant" || !message.content.startsWith("{")) return [];
  try {
    const parsed = JSON.parse(message.content) as AgentBlocksResult;
    return Array.isArray(parsed.trace?.steps) ? parsed.trace.steps : [];
  } catch {
    return [];
  }
}

/**
 * The calibration sessions the chat's tool calls named, least recently named first, each once:
 * the saved answers' traces, then the live turn's steps.
 */
export function linkedCalibrationSessions(
  messages: ChatMessage[],
  liveSteps: TraceStep[] = [],
): string[] {
  const seen: string[] = [];
  const add = (step: TraceStep) => {
    const id = calibrationSessionIdOf(step);
    if (!id) return;
    const at = seen.indexOf(id);
    if (at >= 0) seen.splice(at, 1);
    seen.push(id);
  };
  for (const message of messages) traceSteps(message).forEach(add);
  liveSteps.forEach(add);
  return seen;
}

/** Calibration session page, pinned to the project it belongs to when known. */
export function calibrationSessionHref(calibrationSessionId: string, projectId?: string | null) {
  const path = `/calibration-sessions/${encodeURIComponent(calibrationSessionId)}`;
  return projectId ? `${path}?project=${encodeURIComponent(projectId)}` : path;
}

/** The calibration session list, optionally for one chip, pinned to a project when known. */
export function calibrationSessionsHref({
  chipId,
  projectId,
}: { chipId?: string | null; projectId?: string | null } = {}) {
  const params = new URLSearchParams();
  if (chipId) params.set("chip", chipId);
  if (projectId) params.set("project", projectId);
  const query = params.toString();
  return query ? `/calibration-sessions?${query}` : "/calibration-sessions";
}

/** Launch states of a pipeline run, in words, with the badge color each takes. */
const DISPATCH_STATUS: Record<string, { label: string; badge: string }> = {
  dispatching: { label: "Starting", badge: "badge-info" },
  dispatched: { label: "Started", badge: "badge-ghost" },
  rejected: { label: "Not started", badge: "badge-ghost" },
  unknown: { label: "Start unknown", badge: "badge-warning" },
};

export function dispatchStatusStyle(status: string): { label: string; badge: string } {
  return DISPATCH_STATUS[status] ?? { label: status, badge: "badge-ghost" };
}
