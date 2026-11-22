import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type {
  AgentActionResponse,
  AgentCandidateCommitResponse,
  AgentCandidateResponse,
  AgentDecisionAssessment,
  AgentDecisionNextAction,
  AgentDecisionResponse,
  AgentInterventionReason,
  AgentModelIdentity,
  AgentSessionAuditResponse,
  QDashClient,
} from "@oqtopus-team/qdash-client";
import { Type } from "typebox";

import { withAbort } from "../lib/abort.js";
import { hostModelIdentity } from "../lib/host-model.js";
import {
  actionOfCall,
  buildAgentLoopContext,
  callIdempotencyKey,
  candidateActionIds,
  decideAgentStep,
  formatAgentLoopContext,
  nextActionOfStep,
  sessionOwnerRefusal,
  SETTLED_EXECUTION_STATUSES,
  type AgentLoopContext,
} from "../lib/agent-loop.js";
import { qdashWebUrl } from "../lib/links.js";
import { toTextToolResult } from "../lib/results.js";
import { serverTimestampText } from "../lib/server-time.js";
import { pollUntilSettled, WAIT_AGENT_INTERVENTION } from "../lib/waits.js";

/**
 * Tools of the model-driven calibration loop in an agent session.
 *
 * The model chooses each step; these tools only read QDash's authoritative
 * state and carry a chosen step into the session the user approved:
 *
 * - `qdash_list_agent_sessions` finds the user's sessions, so a restarted pi
 *   or a new web chat can continue one without the model's earlier context.
 * - `qdash_get_agent_session_context` reads a session's scope, budget,
 *   actions, candidates, and newest intervention with the expert's answer.
 * - `qdash_run_agent_session_step` proposes and dispatches one measurement.
 * - `qdash_request_agent_human` records an intervention and pauses the session.
 * - `qdash_wait_agent_intervention` waits, bounded, for the expert's answer.
 * - `qdash_record_agent_decision` appends the model's reading of a result and
 *   its next step to the session's audit; the step and request tools record
 *   one themselves from their rationale or summary.
 * - `qdash_get_agent_session_audit` reads the session's chronological audit.
 *
 * The writes are session-granted (`SESSION_GRANTED_WRITE_TOOL_NAMES` in
 * tool-policy.ts): they run without a per-call approval only in a session the
 * signed-in user created and approved with `autonomy: "auto"`. Each call asks
 * QDash who the client is signed in as and refuses another user's session or
 * an unknown identity, re-reads the session and refuses anything outside it,
 * and sends its write as `autonomous`, so QDash checks the same with the
 * request's authenticated user and its own records: the creator, the
 * autonomy, a running measurement, the round budget, and repeats. A server
 * that does not confirm those checks gets no dispatch. Each call's
 * idempotency key derives from its tool call id, so a host replaying an
 * interrupted call reuses the action or intervention it already created.
 */

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

export type AgentLoopDependencies = {
  makeClient(params: ConnectionParams): Promise<QDashClient>;
};

const connectionParams = {
  profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
  configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

const SESSION_STATUSES = ["active", "waiting_for_human", "completed", "cancelled", "expired"] as const;
type SessionStatus = (typeof SESSION_STATUSES)[number];

const INTERVENTION_REASONS = [
  "unknown_outcome",
  "recovery_exhausted",
  "evaluation_failed",
  "platform_error",
  "policy_limit",
  "agent_request",
] as const;

const ASSESSMENTS = ["pass", "fail", "inconclusive"] as const;
const NEXT_ACTIONS = [
  "next_task",
  "repeat",
  "adjust_and_retry",
  "rollback",
  "propose_commit",
  "request_human",
  "skip_target",
  "complete",
  "stop",
] as const;

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function statusOf(error: unknown): number | undefined {
  const status = (error as { statusCode?: unknown } | null)?.statusCode;
  return typeof status === "number" ? status : undefined;
}

/** Most reads of a session's history while its state version keeps changing. */
export const SNAPSHOT_ATTEMPTS = 3;

/** Said after a decision, in an active session, whose next step is request_human but which names no intervention. */
export const REQUEST_HUMAN_DECISION_NOTE =
  "This decision opened no intervention and the session is not paused: it only records that a person should decide. To ask an expert through QDash, call qdash_request_agent_human; if you are asking the user in this conversation instead, say so in your answer.";

/**
 * The loop context of a session, read from QDash; candidates only when asked for.
 *
 * The history is read between two reads of the session. When both show the
 * same state version, no submission, commit, pause, or answer happened in
 * between, so the history holds every action that version counted (QDash
 * writes an action's record before any later read returns its version). When
 * the version keeps changing for `SNAPSHOT_ATTEMPTS` reads, the context says
 * so and allows no step. Dispatch progress does not change the version; QDash
 * checks running measurements itself when an autonomous step is submitted and
 * dispatched.
 */
export async function loadAgentLoopContext(
  client: QDashClient,
  sessionId: string,
  options: { withCandidates?: boolean; signal?: AbortSignal } = {},
): Promise<{ context: AgentLoopContext; actions: AgentActionResponse[]; decisions: AgentDecisionResponse[] | null; decisionsUnavailable: DecisionsUnavailable | null }> {
  const read = <T>(promise: Promise<T>, what: string) => withAbort(promise, options.signal, what);
  let session = await read(client.getAgentSession(sessionId), `Agent session ${sessionId}`);
  let actions: AgentActionResponse[] = [];
  let interventions: Awaited<ReturnType<QDashClient["listAgentInterventions"]>> = [];
  let listed: DecisionList = { items: null, unavailable: { unsupported: false, reason: "not read" } };
  let consistent = false;
  for (let attempt = 0; attempt < SNAPSHOT_ATTEMPTS && !consistent; attempt++) {
    [actions, interventions, listed] = await Promise.all([
      read(client.listAgentActions(sessionId), `Agent actions of ${sessionId}`),
      read(client.listAgentInterventions(sessionId), `Interventions of ${sessionId}`),
      listDecisions(client, sessionId, options.signal),
    ]);
    const after = await read(client.getAgentSession(sessionId), `Agent session ${sessionId}`);
    consistent = after.state_version === session.state_version;
    session = after;
  }
  const candidates = new Map<string, AgentCandidateResponse[] | { error: string }>();
  if (options.withCandidates) {
    await Promise.all(
      candidateActionIds(actions).map(async (actionId) => {
        try {
          candidates.set(actionId, await read(client.listAgentActionCandidates(sessionId, actionId), `Candidates of ${actionId}`));
        } catch (error) {
          if (options.signal?.aborted) throw error;
          candidates.set(actionId, { error: errorText(error) });
        }
      }),
    );
  }
  const decisions = listed.items;
  return {
    context: buildAgentLoopContext({ session, actions, interventions, candidates, snapshotConsistent: consistent, decisions }),
    actions,
    decisions,
    decisionsUnavailable: listed.items === null ? listed.unavailable : null,
  };
}

/** Why the session's decisions could not be listed: an older release (404/405) or a failed read. */
type DecisionsUnavailable = { unsupported: boolean; reason: string };
type DecisionList = { items: AgentDecisionResponse[]; unavailable?: undefined } | { items: null; unavailable: DecisionsUnavailable };

/** The session's decisions, or why QDash did not list them. */
async function listDecisions(client: QDashClient, sessionId: string, signal: AbortSignal | undefined): Promise<DecisionList> {
  try {
    return { items: await withAbort(client.listAgentDecisions(sessionId), signal, `Decisions of ${sessionId}`) };
  } catch (error) {
    if (signal?.aborted) throw error;
    const status = statusOf(error);
    return { items: null, unavailable: { unsupported: status === 404 || status === 405, reason: errorText(error) } };
  }
}

type DecisionFields = {
  assessment?: AgentDecisionAssessment;
  interpretation: string;
  nextAction: AgentDecisionNextAction;
  nextDetail?: string;
  evidenceActionIds?: string[];
  evaluationIds?: string[];
  nextActionId?: string;
  interventionId?: string;
  /** The host's model (`hostModelIdentity`), never a tool argument. */
  model?: AgentModelIdentity;
};

/**
 * What became of the decision a tool call records:
 *
 * - `recorded`: QDash stored it, now or in an earlier run of the call.
 * - `unsupported`: this QDash records no decisions (404/405).
 * - `refused`: QDash answered with another 4xx and stored nothing; `quotaFull` when the
 *   session's audit holds every decision it may.
 * - `uncertain`: no answer, or a 5xx; QDash may or may not have stored it. A retry with
 *   the same idempotency key records it at most once.
 */
type DecisionOutcome =
  | { kind: "recorded"; line: string; decision: AgentDecisionResponse }
  | { kind: "unsupported" | "refused" | "uncertain"; line: string; reason: string; quotaFull?: boolean };

/** Matches QDash's refusal of a decision when the session's audit is full. */
const QUOTA_FULL = /audit is full|already holds \d+ decisions/i;

/**
 * Record one decision with the idempotency key of the tool call, unless a run of
 * the same call already recorded it, or (`linkedActionId`) an earlier call
 * already recorded the decision of the step that action carries out. Never
 * throws for a failed write, so the caller decides what may still run.
 */
async function recordCallDecision(
  client: QDashClient,
  sessionId: string,
  key: string,
  fields: DecisionFields,
  known: readonly AgentDecisionResponse[] | null,
  signal: AbortSignal | undefined,
  what = "decision",
): Promise<DecisionOutcome> {
  const existing =
    known?.find((item) => item.idempotency_key === key) ??
    (fields.nextActionId ? known?.find((item) => item.next_action_id === fields.nextActionId) : undefined);
  if (existing) return { kind: "recorded", line: `Audit: ${what} ${existing.decision_id} was already recorded for this step.`, decision: existing };
  try {
    const decision = await withAbort(
      client.recordAgentDecision(sessionId, {
        idempotencyKey: key,
        ...fields,
        interpretation: fields.interpretation.slice(0, 2000),
        nextDetail: fields.nextDetail?.slice(0, 500),
        evidenceActionIds: fields.evidenceActionIds?.slice(0, 20),
        evaluationIds: fields.evaluationIds?.slice(0, 20),
      }),
      signal,
      "Recording the decision",
    );
    const cited = decision.evidence_action_ids.length ? ` on ${decision.evidence_action_ids.join(", ")}` : "";
    return { kind: "recorded", line: `Audit: recorded ${what} ${decision.decision_id}${cited} (next ${decision.next_action}).`, decision };
  } catch (error) {
    if (signal?.aborted) throw error;
    const status = statusOf(error);
    const reason = errorText(error);
    if (status === 404 || status === 405) {
      return { kind: "unsupported", line: `Audit: the ${what} was NOT recorded: this QDash does not record decisions.`, reason: "this QDash does not record decisions" };
    }
    if (status !== undefined && status >= 400 && status < 500) {
      const quotaFull = status === 409 && QUOTA_FULL.test(reason);
      return { kind: "refused", line: `Audit: the ${what} was NOT recorded: QDash refused it (${reason}).`, reason, quotaFull };
    }
    return {
      kind: "uncertain",
      line: `Audit: QDash did not confirm the ${what} record (${reason}); it may not be stored, so it is not counted as recorded.`,
      reason,
    };
  }
}

/** Why a step whose decision was not recorded was not dispatched, and how to continue. */
function undispatchedText(outcome: Exclude<DecisionOutcome, { kind: "recorded" }>, action: AgentActionResponse): string {
  const kept = `Action ${action.action_id} is authorized but was not dispatched; nothing ran.`;
  const again = `Call qdash_run_agent_session_step again with the same task, qubit, and overrides: it reuses action ${action.action_id} without using more of the action budget, and dispatches only once the decision is recorded.`;
  if (outcome.kind === "uncertain") {
    return `Not dispatched: QDash did not confirm the audit decision this step follows (${outcome.reason}); it may or may not be stored. ${kept} ${again} A decision QDash did store for this action is found and not recorded twice.`;
  }
  if (outcome.quotaFull) {
    return `Not dispatched: the session's audit is full (${outcome.reason}), so the decision this step follows cannot be recorded. ${kept} No further autonomous step can run in this session: report the results to the user, or ask for a person with qdash_request_agent_human.`;
  }
  if (outcome.kind === "unsupported") {
    return `Not dispatched: this QDash does not record audit decisions, and a step that follows a result needs its decision recorded first. ${kept} Use the reviewed tools (qdash_submit_agent_action, qdash_execute_agent_action) with per-call approval, or a QDash release that records decisions.`;
  }
  return `Not dispatched: QDash refused the audit decision this step follows (${outcome.reason}). ${kept} Correct what QDash named (evidenceActionIds, evaluationIds, assessment, interpretation); then ${again.charAt(0).toLowerCase()}${again.slice(1)}`;
}

/** The user QDash authenticated this client as, or undefined when QDash cannot say. */
async function signedInUser(client: QDashClient, signal: AbortSignal | undefined): Promise<string | undefined> {
  try {
    const user = await withAbort(client.getCurrentUser(), signal, "Signed-in user");
    return typeof user?.username === "string" && user.username ? user.username : undefined;
  } catch (error) {
    if (signal?.aborted) throw error;
    return undefined;
  }
}

/**
 * The context of a session for a session-granted write, or why the write must
 * not run for the signed-in user (see `sessionOwnerRefusal`).
 */
async function ownedSessionContext(
  client: QDashClient,
  sessionId: string,
  signal: AbortSignal | undefined,
): Promise<{ context: AgentLoopContext; actions: AgentActionResponse[]; decisions: AgentDecisionResponse[] | null; decisionsUnavailable: DecisionsUnavailable | null; refusal: string | null }> {
  const [loaded, username] = await Promise.all([loadAgentLoopContext(client, sessionId, { signal }), signedInUser(client, signal)]);
  return { ...loaded, refusal: sessionOwnerRefusal(loaded.context.session, username) };
}

/** QDash's refusal of an autonomous write (403 or 409), as text; other errors propagate. */
function refusedByQDash(error: unknown): string | undefined {
  const status = statusOf(error);
  return status === 403 || status === 409 ? errorText(error) : undefined;
}

const UNVERIFIED_SERVER =
  "This QDash server did not confirm that it checks autonomous steps (the action has no `autonomous` field), so nothing was dispatched. Session-granted steps need a QDash release that checks the session creator, running measurements, rounds, and repeats itself; until then use the reviewed tools with per-call approval.";

function contextLinks(client: QDashClient, context: AgentLoopContext) {
  return {
    sessionUrl: qdashWebUrl(client, `/agent-sessions/${encodeURIComponent(context.session.session_id)}`),
    interventionUrl: context.intervention ? qdashWebUrl(client, context.intervention.page_path) : undefined,
  };
}

function actionSummary(action: AgentActionResponse): Record<string, unknown> {
  return {
    action_id: action.action_id,
    task_name: action.task_name,
    qids: action.qids,
    parameter_overrides: action.parameter_overrides,
    decision: action.decision,
    reason: action.reason,
    execution_status: action.execution_status,
    operation_id: action.operation_id ?? null,
    execution_id: action.execution_id ?? null,
    state_version_after: action.state_version_after,
  };
}

export function registerAgentLoopTools(pi: ExtensionAPI, deps: AgentLoopDependencies): void {
  pi.registerTool({
    name: "qdash_list_agent_sessions",
    label: "QDash List Agent Sessions",
    description:
      "List QDash agent calibration sessions of the current project, newest first, with their status, scope, budget, and expiry. Read-only. Defaults to your own active and paused sessions.",
    promptSnippet: "Find your QDash agent sessions, for example to continue one",
    promptGuidelines: [
      "Use qdash_list_agent_sessions when the user asks to continue an agent calibration and no session id is known in this conversation; then read the chosen session with qdash_get_agent_session_context.",
      "A session belongs to one project and chip; never mix the evidence of different sessions, chips, or projects.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Only sessions on this chip." })),
      statuses: Type.Optional(Type.Array(Type.Union(SESSION_STATUSES.map((status) => Type.Literal(status))), { description: "Statuses to list; default active and waiting_for_human." })),
      mine: Type.Optional(Type.Boolean({ description: "Only sessions you created (default true)." })),
      limit: Type.Optional(Type.Number({ description: "At most this many sessions (default 10, at most 100)." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { chipId?: string; statuses?: SessionStatus[]; mine?: boolean; limit?: number }, signal) {
      const client = await deps.makeClient(params);
      const statuses = params.statuses?.length ? params.statuses : (["active", "waiting_for_human"] as SessionStatus[]);
      const limit = Math.min(100, Math.max(1, Math.floor(params.limit ?? 10)));
      const sessions = await withAbort(
        client.listAgentSessions({ chipId: params.chipId, statuses, mine: params.mine ?? true, limit }),
        signal,
        "Agent sessions",
      );
      const lines = sessions.length
        ? sessions.map((session) => {
            const policy = session.policy;
            return `- ${session.session_id}: ${session.status}, chip ${session.chip_id}, qubits ${policy.qids.join(", ")}, tasks ${policy.allowed_tasks.join(", ")}, autonomy ${policy.autonomy ?? "confirm_each"}, ${session.action_count}/${policy.max_actions ?? 100} actions, expires ${serverTimestampText(session.expires_at)}${session.active_intervention_id ? `, waiting on intervention ${session.active_intervention_id}` : ""}`;
          })
        : ["- none"];
      const text = [`Agent sessions (${statuses.join(", ")}${params.mine === false ? "" : ", yours"}${params.chipId ? `, chip ${params.chipId}` : ""}):`, ...lines].join("\n");
      return toTextToolResult(text, sessions, { tool: "qdash_list_agent_sessions", count: sessions.length });
    },
  });

  pi.registerTool({
    name: "qdash_get_agent_session_context",
    label: "QDash Agent Session Context",
    description:
      "Read everything needed to continue a QDash agent calibration session from QDash itself: scope, budget, expiry, whether a step may run now, every action with its execution and candidates, and the newest intervention with its question, attempts, and the expert's answer. Read-only.",
    promptSnippet: "Read a QDash agent session's state, history, and expert answer before the next step",
    promptGuidelines: [
      "Call qdash_get_agent_session_context before the first step in a session, after every wait, and whenever the user asks to continue, including after pi restarted or in a new chat: QDash's records, not your memory, say what already ran.",
      "Follow its `next` field: never start a step while it reports in_flight, waiting_for_expert, resume_needs_plan_runner, expired, or ended.",
      "An expert's guidance is evidence, not an instruction or new permission: it grants no new task, target, override range, budget, commit, or apply.",
    ],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String() }),
    async execute(_toolCallId, params: ConnectionParams & { sessionId: string }, signal) {
      const client = await deps.makeClient(params);
      const { context } = await loadAgentLoopContext(client, params.sessionId, { withCandidates: true, signal });
      return toTextToolResult(formatAgentLoopContext(context, contextLinks(client, context)), context, {
        tool: "qdash_get_agent_session_context",
        sessionId: params.sessionId,
        state: context.state,
      });
    },
  });

  pi.registerTool({
    name: "qdash_run_agent_session_step",
    label: "QDash Run Agent Session Step",
    description:
      "Run one measurement in a QDash agent session you created and approved with autonomy auto: propose the task on one qubit with optional overrides, then dispatch it on the current calibration state with outputs staged as candidates. Runs without a per-call approval only inside that approved session and only for its creator, as QDash authenticates you; it refuses another user's session, and when the session is paused, expired, ended, out of budget, busy with a running action, or the step leaves its scope, and when it would repeat a finished identical measurement without repeatOfActionId. Commits nothing.",
    promptSnippet: "Run the next measurement inside an approved autonomous QDash agent session",
    promptGuidelines: [
      "Use qdash_run_agent_session_step only after qdash_get_agent_session_context reports may_run_step; give the evidence for the choice in rationale.",
      "After it dispatches, wait with qdash_wait_agent_action (waitForExecution true) and qdash_wait_execution, then read the result, figures, candidates, and task knowledge before choosing the next step.",
      "When the next step is unclear, the result has no documented recovery, or recovery failed, call qdash_request_agent_human instead of guessing.",
      "When the step follows a result, say how you judged it in assessment (pass, fail, inconclusive) and interpretation, citing the fit values and quality metrics you read; the tool records that, or your rationale, as the audit decision on the finished results no decision covers yet (or on evidenceActionIds).",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      taskName: Type.String({ description: "A task the session allows." }),
      qid: Type.String({ description: "One qubit the session allows." }),
      parameterOverrides: Type.Optional(Type.Record(Type.String(), Type.Number(), { description: "Inputs within the session's override bounds." })),
      rationale: Type.String({ description: "Why this step, citing the evidence (results, evaluation, task knowledge, expert guidance)." }),
      reconfigure: Type.Optional(Type.Boolean({ description: "Reconfigure the hardware before measuring; only when the session allows it." })),
      sourceExecutionId: Type.Optional(Type.String({ description: "Execution the step was decided from, recorded for provenance." })),
      repeatOfActionId: Type.Optional(Type.String({ description: "The finished action this step deliberately measures again with identical settings." })),
      assessment: Type.Optional(Type.Union(ASSESSMENTS.map((value) => Type.Literal(value)), { description: "How you judged the result this step follows: pass, fail, or inconclusive. Omit when you did not judge one." })),
      interpretation: Type.Optional(Type.String({ description: "Your concise reading of that result for the audit (2000 characters); defaults to rationale." })),
      evidenceActionIds: Type.Optional(Type.Array(Type.String(), { description: "Actions of this session whose results the decision reads; defaults to the finished results no decision covers yet." })),
      evaluationIds: Type.Optional(Type.Array(Type.String(), { description: "qcal_evaluate evaluations of those results." })),
    }),
    async execute(
      toolCallId,
      params: ConnectionParams & {
        sessionId: string;
        taskName: string;
        qid: string;
        parameterOverrides?: Record<string, number>;
        rationale: string;
        reconfigure?: boolean;
        sourceExecutionId?: string;
        repeatOfActionId?: string;
        assessment?: AgentDecisionAssessment;
        interpretation?: string;
        evidenceActionIds?: string[];
        evaluationIds?: string[];
      },
      signal,
      _onUpdate,
      ctx,
    ) {
      // The host's current model, recorded with every record this call writes.
      const model = hostModelIdentity(ctx);
      const client = await deps.makeClient(params);
      const key = callIdempotencyKey("step", params.sessionId, toolCallId);
      const decisionKey = callIdempotencyKey("decision", params.sessionId, toolCallId);
      const details = { tool: "qdash_run_agent_session_step", sessionId: params.sessionId };
      const refuse = (reason: string, extra: Record<string, unknown> = {}) =>
        toTextToolResult(`Not run: ${reason}`, { reason, ...extra }, { ...details, refused: true, ...extra });
      let actionsById: (ids: string[]) => AgentActionResponse[] = () => [];
      // The decision on the results this step follows, linked to the action that carries it
      // out. It is recorded before the dispatch, and the dispatch waits for QDash to confirm
      // it, so no measurement runs without its decision in the audit. Null when the step
      // follows no result and carries no assessment.
      const audit = async (action: AgentActionResponse, evidence: string[], known: AgentDecisionResponse[] | null): Promise<DecisionOutcome | null> => {
        if (!evidence.length && !params.evaluationIds?.length && !params.interpretation && !params.assessment) return null;
        const evidenceActions = actionsById(evidence);
        return recordCallDecision(
          client,
          params.sessionId,
          decisionKey,
          {
            assessment: params.assessment,
            interpretation: params.interpretation?.trim() || params.rationale,
            nextAction: nextActionOfStep(evidenceActions, params),
            nextDetail: `${params.taskName} on ${params.qid}${Object.keys(params.parameterOverrides ?? {}).length ? ` with ${JSON.stringify(params.parameterOverrides)}` : ""}${action.decision === "authorized" ? "" : " (rejected by QDash, not executed)"}`,
            evidenceActionIds: evidence,
            evaluationIds: params.evaluationIds,
            nextActionId: action.action_id,
            model,
          },
          known,
          signal,
        );
      };
      const auditDetails = (outcome: DecisionOutcome | null) =>
        outcome === null
          ? {}
          : outcome.kind === "recorded"
            ? { decisionRecorded: true, decisionId: outcome.decision.decision_id }
            : { decisionRecorded: false, decisionOutcome: outcome.kind, ...(outcome.quotaFull ? { auditFull: true } : {}) };
      const dispatch = async (action: AgentActionResponse, how: string, outcome: DecisionOutcome | null) => {
        // Only a server that checks autonomous steps itself gets one dispatched.
        if (typeof action.autonomous !== "boolean") return refuse(UNVERIFIED_SERVER, { actionId: action.action_id });
        if (outcome !== null && outcome.kind !== "recorded") {
          const text = undispatchedText(outcome, action);
          return toTextToolResult(text, { reason: text, ...actionSummary(action) }, { ...details, refused: true, actionId: action.action_id, ...auditDetails(outcome) });
        }
        let executed: AgentActionResponse;
        try {
          executed = await withAbort(
            client.executeAgentAction(params.sessionId, action.action_id, {
              sourceExecutionId: params.sourceExecutionId,
              reconfigure: params.reconfigure ?? false,
              autonomous: true,
            }),
            signal,
            `Dispatching agent action ${action.action_id}`,
          );
        } catch (error) {
          const refusal = refusedByQDash(error);
          if (refusal === undefined) throw error;
          return refuse(`QDash refused to dispatch action ${action.action_id}: ${refusal}. Nothing was dispatched; the action stays authorized. Read qdash_get_agent_session_context before the next step.${outcome ? `\n${outcome.line}` : ""}`, { actionId: action.action_id, ...auditDetails(outcome) });
        }
        const text = [
          `${how} action ${executed.action_id}: ${executed.task_name} on ${executed.qids.join(", ")}; execution ${executed.execution_status}${executed.execution_id ? ` ${executed.execution_id}` : ""}${executed.operation_id ? ` (operation ${executed.operation_id})` : ""}.`,
          "Outputs stay staged as candidates; nothing was committed.",
          ...(outcome ? [outcome.line] : []),
          `Next: qdash_wait_agent_action with sessionId ${params.sessionId}, actionId ${executed.action_id}, waitForExecution true; then qdash_wait_execution, and read the result before choosing another step.`,
        ].join("\n");
        return toTextToolResult(text, actionSummary(executed), { ...details, actionId: executed.action_id, dispatched: true, ...auditDetails(outcome) });
      };
      const rejectedText = (action: AgentActionResponse, lead: string, outcome: DecisionOutcome | null) =>
        toTextToolResult(`${lead}${outcome ? `\n${outcome.line}` : ""}`, actionSummary(action), { ...details, refused: true, actionId: action.action_id, ...auditDetails(outcome) });

      // The grant belongs to the user who approved the session, as QDash authenticates them.
      const { context, actions, decisions, decisionsUnavailable, refusal } = await ownedSessionContext(client, params.sessionId, signal);
      if (refusal) return refuse(refusal, { state: context.state, createdBy: context.session.created_by });
      const byId = new Map(actions.map((action) => [action.action_id, action]));
      actionsById = (ids) => ids.flatMap((id) => (byId.has(id) ? [byId.get(id)!] : []));
      const unknownEvidence = (params.evidenceActionIds ?? []).filter((id) => !byId.has(id));
      if (unknownEvidence.length) {
        return refuse(`${unknownEvidence.join(", ")} ${unknownEvidence.length === 1 ? "is not an action" : "are not actions"} of session ${params.sessionId}; nothing was proposed.`, { unknown: unknownEvidence });
      }
      // Without the session's decisions, the step cannot tell which results still need one.
      // It runs only when it follows no result and states no assessment, so nothing it would
      // record is lost; otherwise it stops before proposing, so no budget is used.
      if (decisionsUnavailable) {
        const followsResult = actions.some((action) => action.action_type === "run_task" && action.decision === "authorized" && SETTLED_EXECUTION_STATUSES.has(String(action.execution_status).toLowerCase()));
        if (followsResult || params.evidenceActionIds?.length || params.interpretation || params.assessment) {
          const reason = decisionsUnavailable.unsupported
            ? "this QDash does not record audit decisions, and a step that follows a result needs its decision recorded first. Nothing was proposed or dispatched. Use the reviewed tools (qdash_submit_agent_action, qdash_execute_agent_action) with per-call approval, or a QDash release that records decisions."
            : `QDash did not list the session's audit decisions (${decisionsUnavailable.reason}), so the step cannot record the decision on the results it follows. Nothing was proposed or dispatched; try again once QDash answers.`;
          return refuse(reason, { state: context.state, decisionRecorded: false });
        }
      }
      const evidence = params.evidenceActionIds ?? (decisions === null ? [] : context.undecided_results);

      // A replay of this call (the host was interrupted) continues the action it created.
      const replayed = actionOfCall(actions, key);
      if (replayed) {
        const outcome = await audit(replayed, evidence, decisions);
        if (replayed.decision !== "authorized") return rejectedText(replayed, `Not run: QDash rejected this step earlier: ${replayed.reason}`, outcome);
        return dispatch(replayed, "Continued", outcome);
      }

      const decision = decideAgentStep(context, actions, params);
      if (decision.kind === "refuse") {
        return toTextToolResult(`Not run: ${decision.reason}`, { state: context.state, reason: decision.reason, next: context.next }, { ...details, refused: true, state: context.state });
      }
      if (decision.kind === "reuse") {
        const action = actions.find((item) => item.action_id === decision.actionId)!;
        return dispatch(action, "Dispatched the earlier authorized", await audit(action, evidence, decisions));
      }
      let proposed: AgentActionResponse;
      try {
        proposed = await withAbort(
          client.submitAgentAction(params.sessionId, {
            idempotencyKey: key,
            expectedStateVersion: context.session.state_version,
            actionType: "run_task",
            taskName: params.taskName,
            qids: [params.qid],
            parameterOverrides: params.parameterOverrides,
            diagnosis: params.rationale,
            autonomous: true,
            repeatOfActionId: params.repeatOfActionId,
            model,
          }),
          signal,
          "Proposing agent action",
        );
      } catch (error) {
        const refusal = refusedByQDash(error);
        if (refusal === undefined) throw error;
        return refuse(`QDash refused the step: ${refusal}. Nothing was recorded and no action budget was used. Read qdash_get_agent_session_context before choosing again.`, { state: context.state });
      }
      if (proposed.decision === "authorized" && proposed.autonomous !== true) {
        return refuse(UNVERIFIED_SERVER, { actionId: proposed.action_id });
      }
      byId.set(proposed.action_id, proposed);
      const outcome = await audit(proposed, evidence, decisions);
      if (proposed.decision !== "authorized") {
        return rejectedText(proposed, `Not run: QDash rejected the step: ${proposed.reason}. The proposal used one action of the session budget; it was not executed.`, outcome);
      }
      return dispatch(proposed, "Dispatched", outcome);
    },
  });

  pi.registerTool({
    name: "qdash_request_agent_human",
    label: "QDash Request Human",
    description:
      "Stop an autonomous QDash agent session you created and approved for a person: record an intervention with the reason, a short summary, the question for the expert, and the actions tried. QDash pauses the session (no new measurement, commit, or apply starts in it) and notifies the agent Slack channel when configured; the expert answers on the QDash intervention page. Uses no action budget.",
    promptSnippet: "Pause an autonomous QDash agent session and ask an expert",
    promptGuidelines: [
      "Use qdash_request_agent_human when a result has no documented next step, recovery is exhausted or failed, the evaluation is unreliable, QDash reports an error, or the next step would leave the session's scope.",
      "Ask one concrete question and list the actions you tried in attemptActionIds, so the expert sees the executions and results.",
      "Afterwards start nothing in the session: wait with qdash_wait_agent_intervention or tell the user, and continue only after qdash_get_agent_session_context shows the expert's answer.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      reason: Type.Union(INTERVENTION_REASONS.map((reason) => Type.Literal(reason)), {
        description: "unknown_outcome, recovery_exhausted, evaluation_failed, platform_error, policy_limit, or agent_request.",
      }),
      summary: Type.String({ description: "What happened, in at most a few sentences (2000 characters)." }),
      question: Type.String({ description: "The concrete question for the expert (2000 characters)." }),
      taskName: Type.Optional(Type.String()),
      qids: Type.Optional(Type.Array(Type.String())),
      attemptActionIds: Type.Optional(Type.Array(Type.String(), { description: "Actions of this session the expert should look at, at most 20." })),
      assessment: Type.Optional(Type.Union(ASSESSMENTS.map((value) => Type.Literal(value)), { description: "How you judged the latest result: pass, fail, or inconclusive. Omit when you did not judge one." })),
    }),
    async execute(
      toolCallId,
      params: ConnectionParams & {
        sessionId: string;
        reason: AgentInterventionReason;
        summary: string;
        question: string;
        taskName?: string;
        qids?: string[];
        attemptActionIds?: string[];
        assessment?: AgentDecisionAssessment;
      },
      signal,
      _onUpdate,
      ctx,
    ) {
      // The host's current model, recorded with every record this call writes.
      const model = hostModelIdentity(ctx);
      const client = await deps.makeClient(params);
      const key = callIdempotencyKey("human", params.sessionId, toolCallId);
      const decisionKey = callIdempotencyKey("decision", params.sessionId, toolCallId);
      const details = { tool: "qdash_request_agent_human", sessionId: params.sessionId };
      const existing = (await withAbort(client.listAgentInterventions(params.sessionId), signal, "Interventions")).find(
        (item) => item.idempotency_key === key,
      );
      let context: AgentLoopContext | undefined;
      let actions: AgentActionResponse[] = [];
      let decisions: AgentDecisionResponse[] | null = null;
      if (!existing) {
        let refusal: string | null;
        ({ context, actions, decisions, refusal } = await ownedSessionContext(client, params.sessionId, signal));
        if (refusal) {
          return toTextToolResult(`Not recorded: ${refusal}`, { state: context.state, reason: refusal }, { ...details, refused: true, state: context.state });
        }
        if (!context.may_request_human) {
          const reason =
            context.state === "confirm_each"
              ? "This session was approved with autonomy confirm_each; ask for a person with qdash_submit_agent_action (request_human), which the user approves."
              : context.state === "in_flight"
                ? `${context.next} Then record the intervention with the finished result.`
                : context.next;
          return toTextToolResult(`Not recorded: ${reason}`, { state: context.state, reason }, { ...details, refused: true, state: context.state });
        }
      }
      const byId = new Map(actions.map((action) => [action.action_id, action]));
      const unknown = (params.attemptActionIds ?? []).filter((id) => !existing && !byId.has(id));
      if (unknown.length) {
        return toTextToolResult(`Not recorded: ${unknown.join(", ")} ${unknown.length === 1 ? "is not an action" : "are not actions"} of session ${params.sessionId}.`, { unknown }, { ...details, refused: true });
      }
      const attempts = (params.attemptActionIds ?? []).slice(0, 20).flatMap((id) => {
        const action = byId.get(id);
        if (!action) return [];
        return [
          {
            action_id: action.action_id,
            task_name: action.task_name ?? "",
            qid: action.qids[0] ?? "",
            status: String(action.execution_status).slice(0, 200),
            reason: (action.diagnosis || action.reason || "").slice(0, 1000),
            ...(action.execution_id ? { execution_id: action.execution_id } : {}),
          },
        ];
      });
      let intervention = existing;
      if (!intervention) {
        try {
          intervention = await withAbort(
            client.createAgentIntervention(params.sessionId, {
              idempotencyKey: key,
              reason: params.reason,
              summary: params.summary.slice(0, 2000),
              question: params.question.slice(0, 2000),
              taskName: params.taskName,
              qids: params.qids,
              attempts,
              autonomous: true,
              model,
            }),
            signal,
            "Recording intervention",
          );
        } catch (error) {
          const refusal = refusedByQDash(error);
          if (refusal === undefined) throw error;
          return toTextToolResult(`Not recorded: QDash refused the intervention: ${refusal}`, { reason: refusal }, { ...details, refused: true });
        }
      }
      // The escalation is a decision too: recorded after the intervention, so the session is
      // already paused and the expert asked whatever becomes of the decision, and linked to
      // it. Recording changes no session state. A decision QDash did not store (a full audit,
      // a refusal, no answer) is reported as missing, never as recorded.
      if (existing) decisions = (await listDecisions(client, params.sessionId, signal)).items;
      const evidence = params.attemptActionIds?.length ? params.attemptActionIds : (context?.undecided_results ?? []);
      const recorded = await recordCallDecision(
        client,
        params.sessionId,
        decisionKey,
        {
          assessment: params.assessment,
          interpretation: params.summary,
          nextAction: "request_human",
          nextDetail: params.question,
          evidenceActionIds: evidence,
          interventionId: intervention.intervention_id,
          model,
        },
        decisions,
        signal,
        "escalation decision",
      );
      const auditLine =
        recorded.kind === "recorded"
          ? recorded.line
          : `${recorded.line} The intervention is recorded regardless and holds the summary and the question; the audit shows this escalation without a decision.`;
      const page = qdashWebUrl(client, intervention.page_path);
      const paused = intervention.pauses_session && intervention.session_status === "waiting_for_human";
      const text = [
        `Recorded intervention ${intervention.intervention_id} (${intervention.reason}). ${paused ? "The session is paused until an expert answers in QDash." : `The session is ${intervention.session_status}; the record cannot resume it.`}`,
        `Question: ${intervention.question}`,
        `Intervention page: ${page}`,
        `Slack: ${intervention.notification.status}`,
        auditLine,
        "Start no measurement, commit, apply, flow, or pipeline for this session now. Wait with qdash_wait_agent_intervention or tell the user; continue only after qdash_get_agent_session_context shows the expert's answer.",
      ].join("\n");
      const decisionDetails =
        recorded.kind === "recorded"
          ? { decisionRecorded: true, decisionId: recorded.decision.decision_id }
          : { decisionRecorded: false, decisionOutcome: recorded.kind, ...(recorded.quotaFull ? { auditFull: true } : {}) };
      return toTextToolResult(text, intervention, { ...details, interventionId: intervention.intervention_id, paused, pageUrl: page, ...decisionDetails });
    },
  });

  pi.registerTool({
    name: "qdash_wait_agent_intervention",
    label: "QDash Wait Agent Intervention",
    description:
      "Wait, bounded (default 15 minutes, at most one hour), for an expert to answer the intervention a QDash agent session is paused on, then return the same state as qdash_get_agent_session_context. Read-only: it never answers, resumes, or reactivates anything.",
    promptSnippet: "Wait for an expert's answer to a QDash agent intervention",
    promptGuidelines: [
      "Use qdash_wait_agent_intervention after qdash_request_agent_human when the user wants the session continued as soon as the expert answers; otherwise end the turn and tell the user what the expert is asked.",
      "When it times out, the session stays paused: tell the user and stop; do not poll again unasked.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      timeoutSeconds: Type.Optional(Type.Number({ description: "Longest wait; default 900, at most 3600." })),
      pollIntervalSeconds: Type.Optional(Type.Number({ description: "Seconds between reads; default 15, at least 5." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { sessionId: string; timeoutSeconds?: number; pollIntervalSeconds?: number }, signal) {
      const client = await deps.makeClient(params);
      return pollUntilSettled(WAIT_AGENT_INTERVENTION, client, params, signal);
    },
  });
  pi.registerTool({
    name: "qdash_record_agent_decision",
    label: "QDash Record Agent Decision",
    description:
      "Append your decision to a QDash agent session's audit: how you judged a result, your concise reasoning citing the evidence, and the next step you chose. QDash checks that every cited action, evaluation, intervention, and earlier decision belongs to the session and freezes what its records say about the cited results. Works in your own session in any status, including a paused or ended one; it changes no session state and runs nothing. Records are append-only: to correct one, record a new decision with supersedesDecisionId.",
    promptSnippet: "Record your reading of a result and your next step in a QDash agent session's audit",
    promptGuidelines: [
      "qdash_run_agent_session_step and qdash_request_agent_human already record a decision from their rationale or summary; call qdash_record_agent_decision for a decision no step carries: a result you accept before proposing a commit, a target you skip, stopping, or finishing the goal.",
      "Write the interpretation as the evidence and the conclusion (fit values, quality metrics, evaluation status, task-knowledge criterion), in a few sentences. Do not paste raw arrays, logs, or credentials.",
      "Never claim a commit or apply happened in a decision; QDash records those itself.",
      "nextAction request_human only records your choice; it opens no intervention and pauses nothing. To stop for an expert, call qdash_request_agent_human, which records the decision itself.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      assessment: Type.Optional(Type.Union(ASSESSMENTS.map((value) => Type.Literal(value)), { description: "pass, fail, or inconclusive; omit when you did not judge a result." })),
      interpretation: Type.String({ description: "Your concise reasoning, citing the evidence (2000 characters)." }),
      nextAction: Type.Union(NEXT_ACTIONS.map((value) => Type.Literal(value)), {
        description: "next_task, repeat, adjust_and_retry, rollback, propose_commit, request_human, skip_target, complete, or stop.",
      }),
      nextDetail: Type.Optional(Type.String({ description: "The chosen next step in a few words (500 characters)." })),
      evidenceActionIds: Type.Optional(Type.Array(Type.String(), { description: "Actions of this session whose results the decision reads, at most 20." })),
      evaluationIds: Type.Optional(Type.Array(Type.String(), { description: "Evaluations of those results, at most 20." })),
      nextActionId: Type.Optional(Type.String({ description: "The action of this session that carries out the next step, when one exists." })),
      interventionId: Type.Optional(Type.String({ description: "The intervention of this session the decision opened or acts on." })),
      supersedesDecisionId: Type.Optional(Type.String({ description: "An earlier decision of this session this one corrects." })),
    }),
    async execute(
      toolCallId,
      params: ConnectionParams & {
        sessionId: string;
        assessment?: AgentDecisionAssessment;
        interpretation: string;
        nextAction: AgentDecisionNextAction;
        nextDetail?: string;
        evidenceActionIds?: string[];
        evaluationIds?: string[];
        nextActionId?: string;
        interventionId?: string;
        supersedesDecisionId?: string;
      },
      signal,
      _onUpdate,
      ctx,
    ) {
      // The host's current model, recorded with every record this call writes.
      const model = hostModelIdentity(ctx);
      const client = await deps.makeClient(params);
      const key = callIdempotencyKey("decision", params.sessionId, toolCallId);
      const details = { tool: "qdash_record_agent_decision", sessionId: params.sessionId };
      const [session, username, listed] = await Promise.all([
        withAbort(client.getAgentSession(params.sessionId), signal, `Agent session ${params.sessionId}`),
        signedInUser(client, signal),
        listDecisions(client, params.sessionId, signal),
      ]);
      const decisions = listed.items;
      const refusal = sessionOwnerRefusal(session, username);
      if (refusal) return toTextToolResult(`Not recorded: ${refusal}`, { reason: refusal }, { ...details, refused: true });
      const existing = decisions?.find((item) => item.idempotency_key === key);
      let decision = existing;
      if (!decision) {
        try {
          decision = await withAbort(
            client.recordAgentDecision(params.sessionId, {
              idempotencyKey: key,
              assessment: params.assessment,
              interpretation: params.interpretation.slice(0, 2000),
              nextAction: params.nextAction,
              nextDetail: params.nextDetail?.slice(0, 500),
              evidenceActionIds: params.evidenceActionIds,
              evaluationIds: params.evaluationIds,
              nextActionId: params.nextActionId,
              interventionId: params.interventionId,
              supersedesDecisionId: params.supersedesDecisionId,
              model,
            }),
            signal,
            "Recording the decision",
          );
        } catch (error) {
          if (signal?.aborted) throw error;
          const status = statusOf(error);
          if (status === undefined || status >= 500) {
            const reason = errorText(error);
            return toTextToolResult(
              `Not confirmed: QDash did not confirm the decision record (${reason}); it may or may not be stored, so do not report it as recorded. Check the session's decisions with qdash_get_agent_session_context or qdash_get_agent_session_audit before recording it again.`,
              { reason },
              { ...details, refused: true, decisionRecorded: false, decisionOutcome: "uncertain" },
            );
          }
          const reason = status === 404 || status === 405 ? "this QDash does not record decisions" : errorText(error);
          const full = status === 409 && QUOTA_FULL.test(reason);
          return toTextToolResult(
            `Not recorded: QDash refused the decision: ${reason}${full ? ". The session's audit holds no more decisions; report to the user instead." : ""}`,
            { reason },
            { ...details, refused: true, decisionRecorded: false, ...(full ? { auditFull: true } : {}) },
          );
        }
      }
      const snapshot = decision.evidence_snapshot as { actions?: Array<Record<string, unknown>> };
      const cited = (snapshot.actions ?? []).map(
        (item) => `- ${String(item.action_id)}: ${String(item.task_name ?? item.action_type)} ${String(item.execution_status ?? "")}${item.task_id ? `, task ${String(item.task_id)}` : ""}`,
      );
      const text = [
        `${existing ? "Already recorded" : "Recorded"} decision ${decision.decision_id}: ${decision.assessment ?? "no assessment"}; next ${decision.next_action}${decision.next_detail ? ` (${decision.next_detail})` : ""}.`,
        ...(cited.length ? ["Evidence QDash froze with it:", ...cited] : []),
        "It changes no session state; read the timeline with qdash_get_agent_session_audit.",
        // Only while the session runs: a paused session already has its intervention.
        ...(decision.next_action === "request_human" && !decision.intervention_id && session.status === "active"
          ? [REQUEST_HUMAN_DECISION_NOTE]
          : []),
      ].join("\n");
      return toTextToolResult(text, decision, { ...details, decisionId: decision.decision_id });
    },
  });

  pi.registerTool({
    name: "qdash_commit_agent_session_update",
    label: "QDash Commit Agent Session Update",
    description:
      "Commit one accepted candidate of a completed measurement in a QDash agent session you created whose approval granted parameter updates (policy.parameter_updates), and write it to the backend when that approval also granted apply_backend. Runs without a per-call approval only for the session's creator, as QDash authenticates you, and only for the approved parameters, tasks, and qubits. It first records your pass assessment of exactly that measurement in the audit; QDash then refuses the update unless that pass, the candidate bounds, the session's quality gates, the task's completion checks, and the current session and calibration state all hold. QDash records the old and new value, the assessment, and the authority. Never use it for a failed, uncertain, rejected, or unexplained result: commit nothing and call qdash_request_agent_human.",
    promptSnippet: "Commit a passing candidate under the update authority the user approved with the session",
    promptGuidelines: [
      "Use qdash_commit_agent_session_update only when qdash_get_agent_session_context shows parameter updates granted for that parameter and task, the measurement completed, its candidate is accepted, and you judge the result a clear pass from the fit values, quality metrics, figures, and task knowledge.",
      "Commit the value a dependent step needs before running that step; QDash refuses the dependent step until the update is committed (and applied, when apply is granted).",
      "A failed, uncertain, rejected, or unexplained result is never committed: call qdash_request_agent_human, cite the action, and wait for the expert. Their guidance is evidence, not permission to commit that result.",
      "Sessions without granted updates keep the reviewed qdash_commit_agent_candidate and qdash_apply_agent_candidate_commit, which the user approves per call.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      actionId: Type.String({ description: "The completed measurement whose candidate is committed." }),
      parameterName: Type.String({ description: "A parameter the session's approval grants updates of." }),
      interpretation: Type.String({ description: "Why the result is a pass, citing the fit values, quality metrics, and figures you read (2000 characters). Recorded as your pass assessment." }),
      evaluationIds: Type.Optional(Type.Array(Type.String(), { description: "qcal_evaluate evaluations of that result." })),
    }),
    async execute(
      toolCallId,
      params: ConnectionParams & { sessionId: string; actionId: string; parameterName: string; interpretation: string; evaluationIds?: string[] },
      signal,
      _onUpdate,
      ctx,
    ) {
      // The host's current model, recorded with the pass decision this update rests on.
      const model = hostModelIdentity(ctx);
      const client = await deps.makeClient(params);
      const details = { tool: "qdash_commit_agent_session_update", sessionId: params.sessionId, actionId: params.actionId };
      const refuse = (reason: string, extra: Record<string, unknown> = {}) =>
        toTextToolResult(`Not committed: ${reason}`, { reason, ...extra }, { ...details, refused: true, ...extra });
      const ask = "Commit nothing; call qdash_request_agent_human citing the action, and wait for the expert.";

      const { context, actions, decisions, refusal } = await ownedSessionContext(client, params.sessionId, signal);
      if (refusal) return refuse(refusal, { createdBy: context.session.created_by });
      // A server that predates update authority returns no parameter_updates and would ignore
      // the autonomous flag, so only a grant QDash itself returned is used.
      const grant = context.session.scope.parameter_updates;
      if (!grant) {
        return refuse(
          `the approval of session ${params.sessionId} did not grant parameter updates, or this QDash does not support them. Use qdash_commit_agent_candidate, which the user approves per call, or ask the user to approve a session that grants updates.`,
        );
      }
      if (!["ready", "budget_exhausted"].includes(context.state) || !context.snapshot_consistent) {
        return refuse(context.next, { state: context.state });
      }
      const action = actions.find((item) => item.action_id === params.actionId);
      if (!action) return refuse(`${params.actionId} is not an action of session ${params.sessionId}.`);
      if (!grant.parameters.includes(params.parameterName)) {
        return refuse(`the approval grants updates of ${grant.parameters.join(", ")} only, not ${params.parameterName}.`);
      }
      if (!action.task_name || !grant.tasks.includes(action.task_name)) {
        return refuse(`the approval grants updates from ${grant.tasks.join(", ")} only, not ${action.task_name ?? "this action"}.`);
      }
      if (String(action.execution_status).toLowerCase() !== "completed") {
        return refuse(`action ${action.action_id} did not complete (${action.execution_status}). ${ask}`);
      }
      let candidates: AgentCandidateResponse[];
      try {
        candidates = await withAbort(client.listAgentActionCandidates(params.sessionId, params.actionId), signal, `Candidates of ${params.actionId}`);
      } catch (error) {
        if (signal?.aborted) throw error;
        return refuse(`QDash could not read the candidates of ${params.actionId} (${errorText(error)}). ${ask}`);
      }
      const candidate = candidates.find((item) => item.parameter_name === params.parameterName);
      if (!candidate) return refuse(`the result of ${params.actionId} has no ${params.parameterName} candidate (missing evidence). ${ask}`);
      if (!candidate.accepted) return refuse(`QDash's gate rejected ${params.parameterName} = ${candidate.value} (${candidate.reason}). ${ask}`);

      const assessed = await recordCallDecision(
        client,
        params.sessionId,
        callIdempotencyKey("decision", params.sessionId, toolCallId),
        {
          assessment: "pass",
          interpretation: params.interpretation,
          nextAction: "propose_commit",
          nextDetail: `commit ${params.parameterName} = ${candidate.value}${candidate.unit ? ` ${candidate.unit}` : ""} from ${params.actionId}`,
          evidenceActionIds: [params.actionId],
          evaluationIds: params.evaluationIds,
          model,
        },
        decisions,
        signal,
        "assessment",
      );
      if (assessed.kind !== "recorded") {
        return refuse(`QDash did not record the pass assessment the update rests on (${assessed.reason}). Nothing was committed; call the tool again once QDash answers.`, { decisionRecorded: false });
      }
      let commit: AgentCandidateCommitResponse;
      try {
        commit = await withAbort(
          client.commitAgentActionCandidate(params.sessionId, params.actionId, params.parameterName, {
            idempotencyKey: callIdempotencyKey("update", params.sessionId, toolCallId),
            // The version the assessment was recorded at, so a replay of this call sends the same request.
            expectedStateVersion: assessed.decision.session_state_version_at_record,
            taskId: candidate.task_id,
            autonomous: true,
            decisionId: assessed.decision.decision_id,
          }),
          signal,
          `Committing ${params.parameterName}`,
        );
      } catch (error) {
        const refused = refusedByQDash(error);
        if (refused === undefined) throw error;
        return refuse(`QDash refused the update: ${refused}. Nothing was committed.\n${assessed.line}`, { decisionId: assessed.decision.decision_id });
      }
      if (commit.authority !== "session_policy") {
        return toTextToolResult(
          `QDash did not confirm that it committed commit ${commit.commit_id} under the session's update authority (authority ${commit.authority ?? "missing"}). Stop and tell the user; run no dependent step.`,
          commit,
          { ...details, refused: true, commitId: commit.commit_id },
        );
      }
      const before = (commit.before_snapshot as { value?: unknown } | null | undefined)?.value;
      const lines = [
        `Committed ${commit.parameter_name} = ${commit.value}${candidate.unit ? ` ${candidate.unit}` : ""} on ${commit.qid} (commit ${commit.commit_id}, was ${before ?? "unset"}) under the update authority the user approved with the session; QDash recorded the old and new value, your pass assessment, and its own gate checks.`,
        assessed.line,
      ];
      let applied: AgentCandidateCommitResponse | undefined;
      if (grant.apply_backend) {
        try {
          applied = await withAbort(
            client.applyAgentCandidateCommit(params.sessionId, commit.commit_id, {
              idempotencyKey: callIdempotencyKey("apply", params.sessionId, toolCallId),
              expectedStateVersion: commit.state_version_after,
              autonomous: true,
            }),
            signal,
            `Applying commit ${commit.commit_id}`,
          );
          lines.push(
            `Backend apply ${applied.backend_status}${applied.backend_operation_id ? ` (operation ${applied.backend_operation_id})` : ""}. Wait for it with qdash_wait_agent_candidate_apply before a dependent step; if it fails, call qdash_request_agent_human.`,
          );
        } catch (error) {
          const refused = refusedByQDash(error);
          if (refused === undefined) throw error;
          lines.push(`QDash refused the backend apply: ${refused}. The value is committed in QDash but not applied. ${ask}`);
        }
      } else {
        lines.push("The approval did not grant backend apply: the value is in QDash's calibration state only.");
      }
      return toTextToolResult(lines.join("\n"), { commit, apply: applied ?? null }, { ...details, commitId: commit.commit_id, committed: true, applied: applied?.backend_status ?? null, decisionId: assessed.decision.decision_id });
    },
  });

  pi.registerTool({
    name: "qdash_get_agent_session_audit",
    label: "QDash Agent Session Audit",
    description:
      "Read a QDash agent session's chronological experiment audit, oldest first, a page at a time: the approved scope, each proposed action with its intent and QDash's authorization, each measurement with its requested and effective parameters, fitted outputs, quality metrics, gate results, and task-result reference, evaluations, recorded decisions, commits with before and after values, backend applies, and expert questions and answers. Each event says who supplied it (QDash, the agent, an expert, an evaluator) and which facts the records lack. Read-only.",
    promptSnippet: "Read a QDash agent session's audit timeline",
    promptGuidelines: [
      "Use qdash_get_agent_session_audit to review or summarize what a session did, or to report its results; follow nextCursor until it says the snapshot is complete before claiming you read all of it.",
      "Each read is a snapshot of the records at one instant. If a page is refused because the audit changed, discard the pages you read and start again without a cursor; never combine pages of different snapshots. Records written after the snapshot (a run that finished later) are not in it.",
      "Report agent_reported text as the agent's statement and server facts as QDash's; never fill in a fact an event lists as missing.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      cursor: Type.Optional(Type.String({ description: "nextCursor of the previous page of the same snapshot." })),
      limit: Type.Optional(Type.Number({ description: "Events per page; default 50, at most 200." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { sessionId: string; cursor?: string; limit?: number }, signal) {
      const client = await deps.makeClient(params);
      const limit = Math.min(200, Math.max(1, Math.floor(params.limit ?? 50)));
      const details = { tool: "qdash_get_agent_session_audit", sessionId: params.sessionId };
      let audit: AgentSessionAuditResponse;
      try {
        audit = await withAbort(client.getAgentSessionAudit(params.sessionId, { cursor: params.cursor, limit }), signal, `Audit of ${params.sessionId}`);
      } catch (error) {
        if (signal?.aborted) throw error;
        const status = statusOf(error);
        if (status === 409 && params.cursor) {
          const text = `The audit of ${params.sessionId} changed after its first page was read (${errorText(error)}). Discard the pages read so far: they belong to an older snapshot. Call qdash_get_agent_session_audit again without a cursor to read a fresh snapshot from the start.`;
          return toTextToolResult(text, { reason: errorText(error) }, { ...details, complete: false, restart: true, nextCursor: null });
        }
        if (status === 503) {
          const text = `QDash could not take a consistent snapshot of the audit of ${params.sessionId} because its records kept changing (${errorText(error)}). Nothing was read; try again shortly.`;
          return toTextToolResult(text, { reason: errorText(error) }, { ...details, complete: false, nextCursor: null });
        }
        throw error;
      }
      const header = audit.session;
      const lines = [
        `Audit of agent session ${header.session_id} (${audit.schema_version}): chip ${header.chip_id}, created by ${header.created_by}, status ${header.status}`,
        `Identity reported at creation: skill ${header.skill_name || "?"} ${header.skill_version || ""}, model ${header.model_name || "not reported"}${header.model?.host ? ` (reported by ${header.model.host})` : ""}${header.missing?.length ? `; not recorded: ${header.missing.join(", ")}` : ""}. Models are reported by the client host and not verified by QDash.`,
        `Events ${audit.events[0]?.sequence ?? 0}-${audit.events.at(-1)?.sequence ?? 0} of ${audit.total_events} in snapshot ${audit.snapshot_id} (read ${String(audit.generated_at)}):`,
      ];
      for (const event of audit.events) {
        const missing = event.missing?.length ? ` [missing: ${event.missing.join(", ")}]` : "";
        const current = event.status_is_current ? " (current status)" : "";
        const model = event.model ? ` {model ${event.model.provider}/${event.model.model_id}${event.model.host ? ` via ${event.model.host}` : ""}}` : "";
        lines.push(`- #${event.sequence} ${String(event.at)} ${event.kind} [${event.provenance}${event.actor ? `, ${event.actor}` : ""}]${model}: ${event.summary}${current}${missing}`);
      }
      lines.push(
        audit.complete
          ? `The timeline of snapshot ${audit.snapshot_id} is complete; records written after the snapshot was taken are not in it.`
          : `More events of snapshot ${audit.snapshot_id} follow: call again with cursor ${audit.next_cursor}.`,
        `Full JSON export: the session page (${qdashWebUrl(client, `/agent-sessions/${encodeURIComponent(params.sessionId)}`)}) or GET /agent-sessions/${params.sessionId}/audit/export.`,
      );
      return toTextToolResult(lines.join("\n"), audit, {
        ...details,
        snapshotId: audit.snapshot_id,
        complete: audit.complete,
        nextCursor: audit.next_cursor ?? null,
        totalEvents: audit.total_events,
      });
    },
  });
}
