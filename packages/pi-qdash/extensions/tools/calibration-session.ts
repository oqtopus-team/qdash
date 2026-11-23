import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import type {
  CalibrationAgentSessionChild,
  CalibrationPipelineRunResponse,
  CalibrationSessionDetailResponse,
  CalibrationSessionResponse,
  ListCalibrationSessionsResponse,
} from "@oqtopus-team/qdash-client/models";
import { Type } from "typebox";

import { toTextToolResult } from "../lib/results.js";
import { requireWriteApproval } from "../lib/write-approval.js";

/**
 * Calibration sessions: one calibration objective on one chip, and the pipeline
 * runs and agent sessions started for it.
 *
 * A calibration session is a record of purpose. It grants nothing and controls
 * nothing: a pipeline run is still the exact request the user approves, and an
 * agent session is still bounded by its own policy, gates, expiry, and pause.
 * QDash records a relation only when a run or agent session is started with
 * the session's ID (`qdash_run_pipeline` / `qdash_create_agent_session` with
 * `calibrationSessionId`), and checks there that the session is in the
 * project, open, on the same chip, and the user's own. A chat is only where the
 * work was asked for: the same session can be continued from another chat by
 * its ID, and deleting or branching a chat changes no record.
 */

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

export type CalibrationSessionClient = Pick<QDashClient, "api">;

export type CalibrationSessionDependencies = {
  makeClient(params: ConnectionParams): Promise<CalibrationSessionClient>;
  /** The chip to work on: the explicit id, else the session/default chip. */
  resolveChipId(client: CalibrationSessionClient, chipId?: string): Promise<string>;
};

const connectionParams = {
  profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
  configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

/** The objective as the approval card and the summaries show it: one line, bounded. */
export function objectiveLine(objective: string): string {
  const line = objective.replace(/\s+/g, " ").trim();
  return line.length > 200 ? `${line.slice(0, 199)}…` : line;
}

function runLine(run: CalibrationPipelineRunResponse): string[] {
  const executions = run.executions ?? [];
  const name = run.pipeline_name ? ` '${run.pipeline_name}'` : "";
  const outcome = run.pipeline?.status ?? (executions.length ? executions[executions.length - 1].status : null);
  const head = `- pipeline run ${run.run_id}${name}: ${run.dispatch_status}${outcome ? `, run ${outcome}` : ""}`;
  const origin = run.reported_origin;
  const lines = [
    head,
    origin
      ? `  requested by ${run.requested_by}; ${origin.client || "the caller"} reported it was launched by the agent tool ${origin.tool} (client reported, not verified by QDash; not an agent session)`
      : `  requested by ${run.requested_by}; no launch origin reported`,
  ];
  if (run.dispatch_status === "unknown") {
    lines.push("  Launch outcome unknown: it was admitted, so it may be running or may still start, even after the session is closed. Check qdash_list_executions before starting another run.");
  }
  if (run.dispatch_status === "rejected" && run.error) lines.push(`  Not started: ${run.error}`);
  const steps = run.pipeline?.steps ?? [];
  if (steps.length) {
    for (const step of steps) {
      lines.push(`  ${step.index}. ${step.name} — ${step.status}${step.execution_id ? ` (execution ${step.execution_id})` : ""}`);
    }
  } else {
    for (const execution of executions) lines.push(`  execution ${execution.execution_id} — ${execution.status}`);
  }
  return lines;
}

function agentLine(agent: CalibrationAgentSessionChild): string[] {
  const head = `- agent session ${agent.session_id}: ${agent.status}, ${agent.autonomy}, qubits ${agent.qids.join(", ")}, ${agent.action_count} action${agent.action_count === 1 ? "" : "s"}`;
  const lines = [head];
  if (agent.calibration_admission === "pending") lines.push("  not admitted yet: its start is not finalized, so QDash refuses every operation in it");
  if (agent.calibration_admission === "rejected") lines.push("  rejected: the calibration session was closed before its start was finalized; it never operates");
  if (agent.active_intervention_id) lines.push(`  waits on intervention ${agent.active_intervention_id}`);
  for (const execution of agent.executions ?? []) lines.push(`  execution ${execution.execution_id} — ${execution.status}`);
  return lines;
}

/** Text for one calibration session and what was started in it. */
export function formatCalibrationSession(detail: CalibrationSessionDetailResponse): string {
  const runs = detail.pipeline_runs ?? [];
  const agents = detail.agent_sessions ?? [];
  const blockers = detail.close_blockers ?? [];
  const runTotal = detail.pipeline_run_total ?? runs.length;
  const agentTotal = detail.agent_session_total ?? agents.length;
  const unknownStarts = detail.unknown_starts ?? [];
  const lines = [
    `Calibration session ${detail.calibration_session_id} (${detail.status}) on chip ${detail.chip_id}`,
    `Objective: ${objectiveLine(detail.objective)}`,
    `Created by ${detail.created_by}`,
    "",
  ];
  if (!runTotal && !agentTotal) {
    lines.push("Nothing has been started in it yet.");
  }
  if (runs.length) {
    lines.push(
      runTotal > runs.length
        ? `Pipeline runs (latest ${runs.length} of ${runTotal}; the close check covers all):`
        : `Pipeline runs (${runs.length}):`,
    );
    for (const run of runs) lines.push(...runLine(run));
  }
  if (agents.length) {
    if (runs.length) lines.push("");
    lines.push(
      agentTotal > agents.length
        ? `Agent sessions (latest ${agents.length} of ${agentTotal}; the close check covers all):`
        : `Agent sessions (${agents.length}):`,
    );
    for (const agent of agents) lines.push(...agentLine(agent));
  }
  if (blockers.length) {
    lines.push("", "Still running, waiting, or being started:", ...blockers.map((item) => `- ${item}`));
  }
  if (unknownStarts.length) {
    lines.push(
      "",
      "Agent session starts whose request stopped before the session was recorded (never admitted: one recorded later is rejected and never operates; closing needs the user's acknowledgment):",
      ...unknownStarts.map((start) => `- agent session ${start.child_id}`),
    );
  }
  if (detail.status === "closed") {
    lines.push("", `Closed by ${detail.closed_by ?? "unknown"}${detail.closing_note ? `: ${detail.closing_note}` : ""}. Start a new calibration session for further work.`);
  }
  return lines.join("\n");
}

export function formatCalibrationSessionList(sessions: CalibrationSessionResponse[]): string {
  if (!sessions.length) return "No calibration sessions match.";
  return [
    `Calibration sessions (${sessions.length}, newest first):`,
    ...sessions.map((session) => `- ${session.calibration_session_id} [${session.status}] chip ${session.chip_id}, by ${session.created_by}: ${objectiveLine(session.objective)}`),
  ].join("\n");
}

export function registerCalibrationSessionTools(pi: Pick<ExtensionAPI, "registerTool">, deps: CalibrationSessionDependencies): void {
  pi.registerTool({
    name: "qdash_create_calibration_session",
    label: "QDash Create Calibration Session",
    description: "Create a QDash calibration session: a record of one calibration objective on one chip that groups the pipeline runs and agent sessions started for it. It grants and starts nothing. Write operation; requires confirmation.",
    promptSnippet: "Record a calibration objective that groups the pipeline runs and agent sessions started for it",
    promptGuidelines: [
      "When the user asks for calibration work that will take one or more pipeline runs or agent sessions toward one goal, create a calibration session for that goal first (or reuse one the user names), then pass its calibrationSessionId to qdash_run_pipeline and qdash_create_agent_session.",
      "A calibration session grants nothing: every pipeline run is still approved on its own, and an agent session is still bounded by its own policy. Never describe it as permission.",
      "Write the objective in the user's own terms (target qubits and what should be achieved); do not claim an outcome in it.",
      "One chat may work on several objectives: use a separate calibration session for each, and never move a run into a session it was not started in.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Chip of the objective. Defaults to the session or default chip." })),
      objective: Type.String({ description: "What the calibration is for, in the user's words (at most 500 characters)." }),
    }),
    async execute(toolCallId, params: ConnectionParams & { chipId?: string; objective: string }, _signal, _onUpdate, ctx) {
      const objective = params.objective?.trim() ?? "";
      if (!objective) throw new Error("objective is required: say what the calibration is for.");
      if (objective.length > 500) throw new Error("objective is longer than 500 characters; shorten it.");
      const client = await deps.makeClient(params);
      const chipId = await deps.resolveChipId(client, params.chipId);
      await requireWriteApproval("qdash_create_calibration_session", toolCallId, params, ctx, {
        title: "Create QDash calibration session?",
        message: `This records the objective "${objectiveLine(objective)}" on chip ${chipId}. It starts nothing and grants nothing; each run started in it is still approved on its own.`,
      });
      const created = (await client.api.createCalibrationSession({ chip_id: chipId, objective })) as CalibrationSessionResponse;
      const text = [
        `Created calibration session ${created.calibration_session_id} on chip ${created.chip_id}.`,
        `Objective: ${objectiveLine(created.objective)}`,
        "",
        "Pass this calibrationSessionId to qdash_run_pipeline and qdash_create_agent_session to record their runs in it.",
      ].join("\n");
      return toTextToolResult(text, created, {
        tool: "qdash_create_calibration_session",
        chipId: created.chip_id,
        calibrationSessionId: created.calibration_session_id,
      });
    },
  });

  pi.registerTool({
    name: "qdash_get_calibration_session",
    label: "QDash Get Calibration Session",
    description: "Get a QDash calibration session with its pipeline runs (each with every step execution) and its agent sessions (each with the executions it dispatched). Read-only.",
    promptSnippet: "Read a calibration session and everything started in it",
    promptGuidelines: [
      "Use qdash_get_calibration_session to report progress on an objective, and to continue one from an earlier chat by its ID.",
      "Statuses belong to each run and agent session; do not conclude that the objective was met from them. Judge the results themselves.",
      "A pipeline run with dispatch status unknown was admitted and may be running or may still start, even after the session is closed: check qdash_list_executions before starting another run for it.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      calibrationSessionId: Type.String({ description: "The calibration session's ID (cs-...)." }),
    }),
    async execute(_toolCallId, params: ConnectionParams & { calibrationSessionId: string }) {
      const client = await deps.makeClient(params);
      const detail = (await client.api.getCalibrationSession(params.calibrationSessionId)) as CalibrationSessionDetailResponse;
      return toTextToolResult(formatCalibrationSession(detail), detail, {
        tool: "qdash_get_calibration_session",
        chipId: detail.chip_id,
        calibrationSessionId: detail.calibration_session_id,
        status: detail.status,
      });
    },
  });

  pi.registerTool({
    name: "qdash_list_calibration_sessions",
    label: "QDash List Calibration Sessions",
    description: "List the project's QDash calibration sessions, newest first, optionally only the user's own, one chip's, or open ones. Read-only.",
    promptSnippet: "Find calibration sessions to continue",
    promptGuidelines: [
      "Use qdash_list_calibration_sessions when the user wants to continue earlier calibration work and has not given its ID; confirm with the user which one before starting runs in it.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Only this chip's sessions." })),
      mine: Type.Optional(Type.Boolean({ description: "Only sessions the signed-in user created." })),
      openOnly: Type.Optional(Type.Boolean({ description: "Only open sessions." })),
      limit: Type.Optional(Type.Number({ description: "At most this many (1-100, default 20)." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { chipId?: string; mine?: boolean; openOnly?: boolean; limit?: number }) {
      const client = await deps.makeClient(params);
      const listed = (await client.api.listCalibrationSessions({
        ...(params.chipId ? { chip_id: params.chipId } : {}),
        ...(params.mine ? { mine: true } : {}),
        ...(params.openOnly ? { status: ["open"] } : {}),
        ...(params.limit ? { limit: Math.max(1, Math.min(100, Math.trunc(params.limit))) } : {}),
      })) as ListCalibrationSessionsResponse;
      return toTextToolResult(formatCalibrationSessionList(listed.items), listed, {
        tool: "qdash_list_calibration_sessions",
        count: listed.items.length,
      });
    },
  });
}
