import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type {
  AgentSessionResponse,
  QDashConnection,
  StopAgentSessionResponse,
} from "../lib/qdash-connection.js";
import { Type } from "typebox";

import { withAbort } from "../lib/abort.js";
import { callIdempotencyKey } from "../lib/agent-loop.js";
import { hostModelIdentity } from "../lib/host-model.js";
import { qdashWebUrl } from "../lib/links.js";
import { toTextToolResult } from "../lib/results.js";
import { requireWriteApproval } from "../lib/write-approval.js";

export const END_AGENT_SESSION_TOOL = "qdash_end_agent_session";

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };
type Outcome = "stopped" | "completed";

export interface AgentSessionEndDependencies {
  makeClient(params: ConnectionParams): Promise<QDashConnection>;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function statusOf(error: unknown): number | undefined {
  const status = (error as { statusCode?: unknown } | null)?.statusCode;
  return typeof status === "number" ? status : undefined;
}

/** The session page, scoped to the session's own project. */
export function sessionPageUrl(client: QDashConnection, session: Pick<AgentSessionResponse, "session_id" | "project_id">): string {
  return qdashWebUrl(client, `/agent-sessions/${encodeURIComponent(session.session_id)}?project=${encodeURIComponent(session.project_id)}`);
}

/** What QDash says still runs after the end; it does not cancel any of it. */
function inFlightLines(operations: StopAgentSessionResponse["in_flight"] = []): string[] {
  if (!operations.length) return ["Nothing the session started is still running in QDash's records."];
  const label: Record<string, string> = {
    measurement: "measurement (action)",
    candidate_commit: "calibration commit",
    candidate_set_commit: "candidate set commit",
    backend_apply: "backend apply (commit)",
  };
  return [
    "Still in progress and NOT cancelled (it passed the session gate before the end; QDash records its result when it finishes):",
    ...operations.map((op) => `- ${label[op.kind] ?? op.kind} ${op.id}: ${op.status}${op.execution_id ? `, execution ${op.execution_id}` : ""}`),
  ];
}

/**
 * Append the end to the session's decision audit, as `qdash_record_agent_decision` would: only the session's creator
 * records decisions there. The end itself is already on QDash's records (the stop record or the complete_session
 * action); this line says whether the decision was added too.
 */
async function recordEnd(
  client: QDashConnection,
  params: { sessionId: string; outcome: Outcome },
  session: AgentSessionResponse,
  reason: string,
  toolCallId: string,
  signal: AbortSignal | undefined,
  ctx: unknown,
): Promise<string> {
  try {
    const user = await withAbort(client.getCurrentUser(), signal, "Signed-in user");
    if (user?.username !== session.created_by) {
      return `Decision not recorded: only ${session.created_by}, who created the session, records its decisions; QDash's own record of the end stands.`;
    }
    const decision = await withAbort(
      client.recordAgentDecision(params.sessionId, {
        idempotencyKey: callIdempotencyKey("end-decision", params.sessionId, toolCallId),
        interpretation: reason,
        nextAction: params.outcome === "stopped" ? "stop" : "complete",
        model: hostModelIdentity(ctx as Parameters<typeof hostModelIdentity>[0]),
      }),
      signal,
      "Recording the decision",
    );
    return `Recorded decision ${decision.decision_id} (next ${decision.next_action}).`;
  } catch (error) {
    if (signal?.aborted) throw error;
    return `Decision not recorded (${errorText(error)}); QDash's own record of the end stands.`;
  }
}

/**
 * End an agent session the user asked to end: `stopped` (the goal is not reached) through
 * QDash's stop request, or `completed` (the goal is reached) through an authorized
 * `complete_session` action. Each call is a reviewed write the user approves. What the
 * tool reports comes from QDash's own answer and a read of the session afterwards, never
 * from the model: a refused or unconfirmed end is reported as such.
 */
export function registerAgentSessionEndTool(pi: ExtensionAPI, deps: AgentSessionEndDependencies): void {
  pi.registerTool({
    name: END_AGENT_SESSION_TOOL,
    label: "QDash End Agent Session",
    description:
      "End a QDash agent session: outcome stopped (the user wants it stopped; QDash marks it cancelled) or completed (the goal is reached; QDash marks it completed). After it, QDash refuses every new step, commit, apply, and resume in the session. It does not cancel a measurement, commit, or backend apply that already started: those are listed, and QDash records their results. The tool reads the session back and reports its status from QDash. A write the user approves on every call.",
    promptSnippet: "Stop or complete a QDash agent session the user asked to end, and read back its status",
    promptGuidelines: [
      "When the user asks to stop an agent session, call qdash_end_agent_session with outcome stopped; when the goal is reached and the user agrees, outcome completed. A decision with nextAction stop or complete (qdash_record_agent_decision) only records a choice and changes no session state.",
      "Report only what the tool reports: the status QDash read back, and the operations it lists as still running. Never say a session is stopped or that hardware was cancelled unless the tool said so; QDash has no API that cancels a measurement already sent.",
      "Link the session with the page link the tool returns (/agent-sessions/<id>?project=<project>); do not compose other paths.",
    ],
    parameters: Type.Object({
      profile: Type.Optional(Type.String()),
      configPath: Type.Optional(Type.String()),
      useEnv: Type.Optional(Type.Boolean()),
      sessionId: Type.String(),
      outcome: Type.Union([Type.Literal("stopped"), Type.Literal("completed")], {
        description: "stopped: end it without reaching the goal. completed: the goal is reached.",
      }),
      reason: Type.String({ description: "Why, in the user's terms; recorded in the audit (2000 characters)." }),
    }),
    async execute(
      toolCallId,
      params: ConnectionParams & { sessionId: string; outcome: Outcome; reason: string },
      signal,
      _onUpdate,
      ctx,
    ) {
      const verb = params.outcome === "stopped" ? "Stop" : "Complete";
      await requireWriteApproval(END_AGENT_SESSION_TOOL, toolCallId, params, ctx, {
        title: `${verb} QDash agent session?`,
        message: `${verb} agent session '${params.sessionId}'? QDash refuses every new step in it afterwards; a measurement already running is not cancelled.`,
      });
      const client = await deps.makeClient(params);
      const details = { tool: END_AGENT_SESSION_TOOL, sessionId: params.sessionId, outcome: params.outcome };
      const reason = params.reason.slice(0, 2000);
      const before = await withAbort(client.getAgentSession(params.sessionId), signal, `Agent session ${params.sessionId}`);

      let stop: StopAgentSessionResponse | undefined;
      try {
        if (params.outcome === "stopped") {
          stop = await withAbort(
            client.stopAgentSession(params.sessionId, { idempotencyKey: callIdempotencyKey("stop", params.sessionId, toolCallId), reason }),
            signal,
            "Stopping the session",
          );
        } else {
          const action = await withAbort(
            client.submitAgentAction(params.sessionId, {
              idempotencyKey: callIdempotencyKey("complete", params.sessionId, toolCallId),
              expectedStateVersion: before.state_version,
              actionType: "complete_session",
              diagnosis: reason,
              model: hostModelIdentity(ctx),
            }),
            signal,
            "Completing the session",
          );
          if (action.decision !== "authorized") {
            return toTextToolResult(
              `Not completed: QDash rejected complete_session: ${action.reason}. The session is still ${before.status}.`,
              { action },
              { ...details, ended: false },
            );
          }
        }
      } catch (error) {
        if (signal?.aborted) throw error;
        const status = statusOf(error);
        const unconfirmed = status === undefined || status >= 500;
        const text = unconfirmed
          ? `Not confirmed: QDash did not confirm the ${params.outcome === "stopped" ? "stop" : "completion"} (${errorText(error)}); the session may or may not have ended. Read it with qdash_get_agent_session before saying either.`
          : status === 404 || status === 405
            ? `Not ended: this QDash has no ${params.outcome === "stopped" ? "stop request" : "completion"} for agent sessions (${errorText(error)}). Ask the user to stop it from the session page instead; nothing changed.`
            : `Not ended: QDash refused (${errorText(error)}). The session is still ${before.status}.`;
        return toTextToolResult(text, { reason: errorText(error) }, { ...details, ended: false, ...(unconfirmed ? { outcomeUnknown: true } : {}) });
      }

      // The status QDash holds now, whatever the request returned.
      const after = await withAbort(client.getAgentSession(params.sessionId), signal, `Agent session ${params.sessionId}`);
      const page = sessionPageUrl(client, after);
      const ended = after.status === "cancelled" || after.status === "completed" || after.status === "expired";
      const headline =
        stop?.outcome === "already_ended"
          ? `Agent session ${after.session_id} had already ended (${after.status}); nothing changed.`
          : stop?.outcome === "already_stopped"
            ? `Agent session ${after.session_id} was already stopped by this request; its status is ${after.status}.`
            : ended
              ? `QDash ${after.status === "cancelled" ? "stopped" : after.status} agent session ${after.session_id}: its status is now ${after.status} (state version ${after.state_version}).`
              : `QDash still reports agent session ${after.session_id} as ${after.status}; it did not end.`;
      const decision = ended && stop?.outcome !== "already_ended" ? await recordEnd(client, params, after, reason, toolCallId, signal, ctx) : undefined;
      const lines = [
        headline,
        ...(ended ? ["No new step, commit, apply, or resume will be accepted in it."] : []),
        ...(stop ? inFlightLines(stop.in_flight) : []),
        ...(stop?.closed_intervention_ids?.length ? [`Closed expert questions: ${stop.closed_intervention_ids.join(", ")}.`] : []),
        ...(decision ? [decision] : []),
        `Session page: ${page}`,
      ];
      return toTextToolResult(lines.join("\n"), { session: after, stop: stop ?? null }, { ...details, ended, status: after.status, sessionUrl: page });
    },
  });
}
