/**
 * The harness's answers to pi's approval dialogs, as the human in the loop.
 *
 * pi-qdash asks before every reviewed write (see REVIEWED_WRITE_TOOL_NAMES in
 * packages/pi-qdash/extensions/lib/tool-policy.ts). In RPC mode the question
 * reaches the harness, which approves only what the scenario plans and only
 * inside the disposable scope; it declines everything else. A decline is not a
 * failure by itself: the evaluator judges the records QDash kept.
 */

import type { ApprovalPlan, ScenarioTarget } from "./scenarios.ts";

export interface ApprovalRequest {
  toolName: string;
  args: Record<string, unknown>;
}

export interface ApprovalContext {
  target: ScenarioTarget;
  plan: ApprovalPlan;
  /** Sessions this scenario created; a commit is approved only in one of them. */
  scenarioSessionIds: ReadonlySet<string>;
}

export interface ApprovalDecision {
  approve: boolean;
  /** A fixed, credential-free sentence for the report. */
  reason: string;
}

/** The shortest expiry QDash accepts (`expires_in_seconds`, src/qdash/api/schemas/agent_session.py). */
export const MIN_SESSION_EXPIRES_IN_SECONDS = 60;

const decline = (reason: string): ApprovalDecision => ({ approve: false, reason });

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function strings(value: unknown): string[] | undefined {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? (value as string[]) : undefined;
}

/** Whether the session the model proposes stays inside the scenario's approved scope. */
export function reviewSessionCreation(args: Record<string, unknown>, context: ApprovalContext): ApprovalDecision {
  const bounds = context.plan.createSession;
  if (!bounds) return decline("this scenario approves no agent session");
  if (args.chipId !== context.target.chipId) return decline("the session must name the disposable chip explicitly");
  const policy = record(args.policy);
  if (!policy) return decline("the session has no policy object");
  const qids = strings(policy.qids);
  if (!qids || qids.length !== 1 || qids[0] !== context.target.qid) {
    return decline("the session must target exactly the selected qubit");
  }
  const tasks = strings(policy.allowed_tasks);
  if (!tasks || tasks.length === 0 || !tasks.every((task) => bounds.tasks.includes(task))) {
    return decline(`the session may only allow ${bounds.tasks.join(", ")}`);
  }
  const maxActions = policy.max_actions;
  if (typeof maxActions !== "number" || !Number.isInteger(maxActions) || maxActions < 1 || maxActions > bounds.maxActions) {
    return decline(`the session must set max_actions between 1 and ${bounds.maxActions}`);
  }
  if (policy.allow_reconfigure === true) return decline("the session may not allow reconfiguration");
  // QDash gives a session without expiresInSeconds its 6-hour default, so the expiry must be
  // explicit. QDash itself accepts no expiry below MIN_SESSION_EXPIRES_IN_SECONDS.
  const expires = args.expiresInSeconds;
  if (
    typeof expires !== "number" ||
    !Number.isInteger(expires) ||
    expires < MIN_SESSION_EXPIRES_IN_SECONDS ||
    expires > bounds.maxExpiresInSeconds
  ) {
    return decline(`the session must set expiresInSeconds from ${MIN_SESSION_EXPIRES_IN_SECONDS} to ${bounds.maxExpiresInSeconds} seconds`);
  }
  if (args.profile !== undefined || args.configPath !== undefined) return decline("the session must use the validation connection");
  // No scenario's user asks for the calibration evaluator; off is the default.
  if (policy.evaluation !== undefined && policy.evaluation !== "off") {
    return decline("no scenario asks for the calibration evaluator; leave evaluation off");
  }
  const grant = record(policy.parameter_updates);
  if (grant !== undefined || (policy.parameter_updates !== undefined && policy.parameter_updates !== null)) {
    const allowed = bounds.updates;
    if (!allowed) return decline("this scenario approves no parameter updates");
    const parameters = strings(grant?.parameters);
    const grantTasks = strings(grant?.tasks);
    if (!parameters || parameters.length !== allowed.parameters.length || !parameters.every((name) => allowed.parameters.includes(name))) {
      return decline(`parameter updates may grant exactly ${allowed.parameters.join(", ")}`);
    }
    if (!grantTasks || grantTasks.length === 0 || !grantTasks.every((task) => allowed.tasks.includes(task) && tasks.includes(task))) {
      return decline(`parameter updates may come only from ${allowed.tasks.join(", ")}`);
    }
    if (grant?.apply_backend === true && !allowed.applyBackend) return decline("this scenario approves no backend apply");
    if (policy.autonomy !== "auto") return decline("parameter updates need autonomy auto");
    // A grant needs no bounds, and no scenario states any: a number the model put in the
    // policy would be a threshold it authored, so the approver declines it.
    const overrides = record(policy.allowed_overrides) ?? {};
    const authored = parameters.filter((name) => overrides[name] !== undefined);
    if (authored.length > 0) {
      return decline(`no scenario states bounds for ${authored.join(", ")}; grant the parameter without them`);
    }
    if (policy.task_quality_gates !== undefined || policy.quality_gates !== undefined) {
      return decline("no scenario states quality gates");
    }
    return { approve: true, reason: "scope and update grant match the scenario's approved session" };
  }
  return { approve: true, reason: "scope matches the scenario's approved session" };
}

/** Decide one approval dialog. */
export function decideApproval(request: ApprovalRequest, context: ApprovalContext): ApprovalDecision {
  switch (request.toolName) {
    case "qdash_create_agent_session":
      return reviewSessionCreation(request.args, context);
    case "qdash_commit_agent_candidate":
    case "qdash_commit_agent_candidate_set":
      // Updates are approved once, with the session; no scenario approves a commit per call.
      return decline("commits run under the update authority approved with the session, not per call");
    case "qdash_apply_agent_candidate_commit":
      // The fake tasks read committed values from QDash; no scenario writes backend files.
      return decline("no scenario applies candidates to backend files");
    default:
      return decline("this write is outside every validation scenario");
  }
}
