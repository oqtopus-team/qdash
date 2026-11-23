import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import type {
  AgentAuditEvent,
  CalibrationAgentSessionChild,
  CalibrationDecisionResponse,
  CalibrationExperimentRow,
  CalibrationMeasuredValue,
  CalibrationPipelineRunResponse,
  CalibrationSessionAuditResponse,
  CalibrationSessionDetailResponse,
  CalibrationSessionResponse,
  ListCalibrationSessionsResponse,
  RecordCalibrationDecisionRequest,
} from "@oqtopus-team/qdash-client/models";
import { createHash } from "node:crypto";
import { Type } from "typebox";

import { hostModelIdentity, type HostModelContext } from "../lib/host-model.js";
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
 *
 * History uses the agent session audit's semantics. `qdash_record_calibration_decision`
 * appends a decision (an experiment it proposes before a run, a next step, or a
 * final conclusion) to the session's audit, as `qdash_record_agent_decision`
 * does for an agent session; QDash checks every cited run, task result, and
 * decision and freezes what its records say about them. It is session-granted:
 * it runs without a per-call approval because it only appends the user's own
 * session's history and changes no calibration. `qdash_get_calibration_session_audit`
 * reads the audit: decisions, requests, dispatches, and measurements, each
 * marked with what is server-recorded and what is a statement.
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

function valueText(value: CalibrationMeasuredValue | null | undefined, unit = ""): string {
  if (!value) return "n/a";
  const error = value.error ? ` ± ${value.error}` : "";
  return `${value.value}${error}${value.unit || unit ? ` ${value.unit || unit}` : ""}`;
}

function experimentLine(row: CalibrationExperimentRow): string[] {
  const changes = (row.requested_changes ?? []).map((c) => `${c.task_name}.${c.parameter}=${c.value}`).join(", ") || "no change";
  const measured = row.measured;
  const lines = [
    `- #${row.sequence} ${row.stage} ${row.candidate_id} on ${row.target} (${changes}); decision ${row.decision_id}${row.pipeline_run_id ? `, run ${row.pipeline_run_id}` : ", no run carries it out"}`,
    `  measured (${measured.evidence_status}): gate time ${valueText(measured.gate_time_ns, "ns")}, fidelity ${valueText(measured.gate_fidelity)}, CR duration ${valueText(measured.cr_duration_ns, "ns")}, CR amplitude ${valueText(measured.cr_amplitude)}${measured.execution_seconds != null ? `, ${Math.round(measured.execution_seconds)} s hardware` : ""}`,
  ];
  const mismatched = (row.parameter_checks ?? []).filter((check) => check.consistent === false);
  for (const check of mismatched) {
    lines.push(`  requested ${check.task_name}.${check.parameter}=${check.requested}, spec ${check.in_spec ?? "?"}, executed ${check.executed ?? "?"}: NOT consistent`);
  }
  return lines;
}

const OUTCOME_TEXT: Record<string, string> = {
  refused: "QDash refused the launch and created no flow run",
  unknown: "the launch outcome is not known yet",
  no_execution: "the flow run exists but QDash holds no execution record for it",
  running: "an execution is still open",
  failed: "every execution ended and none completed",
  partial: "some executions completed and others failed or were cancelled",
  completed: "every execution completed",
};

function searchLines(detail: CalibrationSessionDetailResponse): string[] {
  const rows = detail.experiments ?? [];
  const lines: string[] = [];
  if (rows.length) {
    lines.push("", "Experiments (from recorded decisions and the runs that named them; measured values are QDash's task results):");
    for (const row of rows) lines.push(...experimentLine(row));
  }
  const total = detail.decision_total ?? 0;
  if (total) lines.push("", `Decisions recorded: ${total}. Read them with qdash_get_calibration_session_audit.`);
  const recommendation = detail.recommendation;
  if (recommendation?.conclusion) {
    lines.push(`Recommendation (a recorded conclusion, decision ${recommendation.decision_id}): ${recommendation.conclusion.outcome}${recommendation.conclusion.recommended_candidate_id ? ` ${recommendation.conclusion.recommended_candidate_id}` : ""}`);
  } else if (total) {
    lines.push("No final conclusion recorded.");
  }
  const latest = detail.latest_requested_run;
  if (latest) {
    const candidate = latest.candidate_id ? `candidate ${latest.candidate_id}` : "names no decision";
    const outcome = OUTCOME_TEXT[latest.execution_outcome] ?? latest.execution_outcome;
    const comparison =
      latest.candidate_is_recommended === false
        ? " Its requested candidate is not the recommended candidate (a comparison of records, not of the hardware)."
        : latest.candidate_is_recommended
          ? " Its requested candidate is the recommended candidate (a comparison of records, not of the hardware)."
          : "";
    lines.push(
      `Latest requested run in this session (by request time): ${latest.pipeline_run_id} (${candidate}), dispatch ${latest.dispatch_status}, execution outcome ${latest.execution_outcome}: ${outcome}.${comparison}`,
      "QDash records no authoritative hardware write, so this is not the current or last written hardware state; a run requested earlier can finish later.",
    );
  }
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
  lines.push(...searchLines(detail));
  if (detail.status === "closed") {
    lines.push("", `Closed by ${detail.closed_by ?? "unknown"}${detail.closing_note ? `: ${detail.closing_note}` : ""}. Start a new calibration session for further work.`);
  }
  return lines.join("\n");
}

function eventLine(event: AgentAuditEvent): string {
  const source = event.provenance === "server_record" || event.provenance === "server_computed" ? "server" : event.provenance.replace("_", " ");
  const agent = event.agent_session_id ? ` [agent session ${event.agent_session_id}]` : "";
  const missing = event.missing?.length ? ` (not recorded: ${event.missing.join(", ")})` : "";
  return `${event.sequence}. ${event.at} ${event.kind}${agent}: ${event.summary} [${source}]${missing}`;
}

/** Text for one page of a calibration session's audit. */
export function formatCalibrationAudit(audit: CalibrationSessionAuditResponse): string {
  const header = audit.calibration_session;
  return [
    `Audit of calibration session ${header.calibration_session_id} (${header.status}) on chip ${header.chip_id}: ${audit.events.length} of ${audit.total_events} events${audit.complete ? "" : `; more with cursor ${audit.next_cursor}`}`,
    `Objective: ${objectiveLine(header.objective)}`,
    "",
    ...audit.events.map(eventLine),
  ].join("\n");
}

/** The idempotency key of one decision call: a replay returns the decision it recorded. */
export function calibrationDecisionKey(calibrationSessionId: string, toolCallId: string): string {
  const digest = createHash("sha256").update(`${calibrationSessionId}\u0000${toolCallId}`).digest("hex").slice(0, 40);
  return `pi-calibration-decision-${digest}`;
}

const ASSESSMENTS = ["pass", "fail", "inconclusive"] as const;
const NEXT_ACTIONS = ["next_task", "repeat", "adjust_and_retry", "rollback", "propose_commit", "request_human", "skip_target", "complete", "stop"] as const;
const STAGES = ["baseline", "screening", "confirmation"] as const;
const OUTCOMES = ["recommend_candidate", "keep_baseline", "inconclusive"] as const;

type DecisionParams = ConnectionParams & {
  calibrationSessionId: string;
  assessment?: (typeof ASSESSMENTS)[number];
  interpretation: string;
  nextAction: (typeof NEXT_ACTIONS)[number];
  nextDetail?: string;
  evidenceRunIds?: string[];
  evidenceTaskIds?: string[];
  evidenceDecisionIds?: string[];
  supersedesDecisionId?: string;
  experiment?: {
    candidateId: string;
    stage: (typeof STAGES)[number];
    target: string;
    requestedChanges?: { taskName: string; parameter: string; value: string | number | boolean | null; previous?: string | number | boolean | null; callId?: string }[];
  };
  conclusion?: { outcome: (typeof OUTCOMES)[number]; recommendedCandidateId?: string };
};

/** The API request of a decision call; the model comes from the host, never the arguments. */
export function decisionRequest(params: DecisionParams, key: string, ctx: HostModelContext | undefined): RecordCalibrationDecisionRequest {
  const model = hostModelIdentity(ctx);
  return {
    idempotency_key: key,
    interpretation: params.interpretation,
    next_action: params.nextAction,
    ...(params.assessment ? { assessment: params.assessment } : {}),
    ...(params.nextDetail ? { next_detail: params.nextDetail } : {}),
    evidence_run_ids: params.evidenceRunIds ?? [],
    evidence_task_ids: params.evidenceTaskIds ?? [],
    evidence_decision_ids: params.evidenceDecisionIds ?? [],
    ...(params.supersedesDecisionId ? { supersedes_decision_id: params.supersedesDecisionId } : {}),
    ...(params.experiment
      ? {
          experiment: {
            candidate_id: params.experiment.candidateId,
            stage: params.experiment.stage,
            target: params.experiment.target,
            requested_changes: (params.experiment.requestedChanges ?? []).map((change) => ({
              task_name: change.taskName,
              parameter: change.parameter,
              value: change.value,
              ...(change.previous !== undefined ? { previous: change.previous } : {}),
              ...(change.callId ? { call_id: change.callId } : {}),
            })),
          },
        }
      : {}),
    ...(params.conclusion
      ? { conclusion: { outcome: params.conclusion.outcome, ...(params.conclusion.recommendedCandidateId ? { recommended_candidate_id: params.conclusion.recommendedCandidateId } : {}) } }
      : {}),
    ...(model ? { model } : {}),
  } as RecordCalibrationDecisionRequest;
}

function decisionText(decision: CalibrationDecisionResponse): string {
  const lines = [`Recorded decision ${decision.decision_id} in calibration session ${decision.calibration_session_id}.`];
  if (decision.experiment) {
    lines.push(`It proposes ${decision.experiment.stage} of ${decision.experiment.candidate_id} on ${decision.experiment.target}. Pass decisionId ${decision.decision_id} with calibrationSessionId to qdash_run_pipeline for the run that carries it out.`);
  }
  if (decision.conclusion) {
    lines.push(`Conclusion: ${decision.conclusion.outcome}${decision.conclusion.recommended_candidate_id ? ` ${decision.conclusion.recommended_candidate_id}` : ""}. It is a statement; it changes no calibration.`);
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
    name: "qdash_record_calibration_decision",
    label: "QDash Record Calibration Decision",
    description:
      "Append a decision to a QDash calibration session's audit, as qdash_record_agent_decision does for an agent session: your reading of the evidence, the next step, and optionally the experiment the next run carries out (candidate, stage, target, requested run parameter changes) or the final conclusion. QDash checks that every cited pipeline run, task result, and decision belongs to the session's project and chip and freezes what its records say about them. Only the session's creator records; it works in any status, runs nothing, and changes no calibration. Records are append-only: correct one with supersedesDecisionId.",
    promptSnippet: "Record an experiment, next step, or conclusion in a calibration session's audit",
    promptGuidelines: [
      "Before each qdash_run_pipeline of a search, record the experiment it carries out (nextAction next_task, repeat, or adjust_and_retry, with experiment), then pass the returned decisionId to qdash_run_pipeline.",
      "After reading a run's results, record your reading citing evidenceRunIds (and evidenceTaskIds for results outside the session, such as the incumbent's baseline). The measured values are QDash's; your interpretation is your statement.",
      "Finish with nextAction complete or stop and a conclusion: recommend_candidate needs a confirmation run of that candidate, keep_baseline a baseline candidate. Never infer a conclusion from a status or from closing the session.",
      "If the user declined a run's approval, record that as a decision (nextAction stop or another step) instead of leaving the proposed experiment unexplained.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      calibrationSessionId: Type.String({ description: "The calibration session's ID (cs-...)." }),
      assessment: Type.Optional(Type.Union(ASSESSMENTS.map((value) => Type.Literal(value)), { description: "pass, fail, or inconclusive; omit when you did not judge a result." })),
      interpretation: Type.String({ description: "Your concise reasoning, citing the evidence (2000 characters)." }),
      nextAction: Type.Union(NEXT_ACTIONS.map((value) => Type.Literal(value)), { description: "The next step: next_task, repeat, adjust_and_retry (an experiment may be attached), complete or stop (a conclusion may be attached), or another agent next step." }),
      nextDetail: Type.Optional(Type.String({ description: "The next step in a few words (500 characters)." })),
      evidenceRunIds: Type.Optional(Type.Array(Type.String(), { description: "Pipeline runs of this session the decision reads, at most 20." })),
      evidenceTaskIds: Type.Optional(Type.Array(Type.String(), { description: "Task results on the session's chip (and on the experiment's target), at most 50." })),
      evidenceDecisionIds: Type.Optional(Type.Array(Type.String(), { description: "Earlier decisions of this session, at most 50." })),
      supersedesDecisionId: Type.Optional(Type.String({ description: "An earlier decision of this session this one corrects." })),
      experiment: Type.Optional(
        Type.Object({
          candidateId: Type.String({ description: "Your name for the condition, such as incumbent or c03 (letters, digits, _.:-)." }),
          stage: Type.Union(STAGES.map((value) => Type.Literal(value))),
          target: Type.String({ description: "The qubit (0) or directed coupling (0-1)." }),
          requestedChanges: Type.Optional(
            Type.Array(
              Type.Object({
                taskName: Type.String(),
                parameter: Type.String(),
                value: Type.Union([Type.String(), Type.Number(), Type.Boolean(), Type.Null()]),
                previous: Type.Optional(Type.Union([Type.String(), Type.Number(), Type.Boolean(), Type.Null()])),
                callId: Type.Optional(Type.String({ description: "The task call, when the step calls the task more than once." })),
              }),
            ),
          ),
        }),
      ),
      conclusion: Type.Optional(
        Type.Object({
          outcome: Type.Union(OUTCOMES.map((value) => Type.Literal(value))),
          recommendedCandidateId: Type.Optional(Type.String()),
        }),
      ),
    }),
    async execute(toolCallId, params: DecisionParams, _signal, _onUpdate, ctx) {
      const client = await deps.makeClient(params);
      const key = calibrationDecisionKey(params.calibrationSessionId, toolCallId);
      const decision = (await client.api.recordCalibrationDecision(
        params.calibrationSessionId,
        decisionRequest(params, key, ctx as HostModelContext | undefined),
      )) as CalibrationDecisionResponse;
      return toTextToolResult(decisionText(decision), decision, {
        tool: "qdash_record_calibration_decision",
        calibrationSessionId: decision.calibration_session_id,
        decisionId: decision.decision_id,
      });
    },
  });

  pi.registerTool({
    name: "qdash_get_calibration_session_audit",
    label: "QDash Get Calibration Session Audit",
    description:
      "Read a QDash calibration session's audit timeline, oldest first: its decisions, each pipeline request (exact requested run parameters, the decision it carries out, the reported origin), dispatch outcomes including refused and unknown ones, step executions with executed run parameters and outputs, and the events of its admitted agent sessions. Each event says whether QDash recorded it or someone stated it, and what is not recorded. Read-only.",
    promptSnippet: "Read a calibration session's audit to resume or report a search",
    promptGuidelines: [
      "Use it to resume a search from QDash's records rather than from memory: which experiments were proposed, which runs carried them out, their outcomes, and the decisions taken.",
      "Never re-dispatch an experiment whose run is dispatching, running, or unknown in the audit; wait for it or check qdash_list_executions.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      calibrationSessionId: Type.String({ description: "The calibration session's ID (cs-...)." }),
      cursor: Type.Optional(Type.String({ description: "next_cursor of the previous page." })),
      limit: Type.Optional(Type.Number({ description: "Events per page (1-500, default 100)." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { calibrationSessionId: string; cursor?: string; limit?: number }) {
      const client = await deps.makeClient(params);
      const audit = (await client.api.getCalibrationSessionAudit(params.calibrationSessionId, {
        ...(params.cursor ? { cursor: params.cursor } : {}),
        ...(params.limit ? { limit: Math.max(1, Math.min(500, Math.trunc(params.limit))) } : {}),
      })) as CalibrationSessionAuditResponse;
      return toTextToolResult(formatCalibrationAudit(audit), audit, {
        tool: "qdash_get_calibration_session_audit",
        calibrationSessionId: audit.calibration_session.calibration_session_id,
        complete: audit.complete,
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
