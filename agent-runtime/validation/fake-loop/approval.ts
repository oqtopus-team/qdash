/**
 * The harness's answers to pi's approval dialogs, as the human in the loop.
 *
 * pi-qdash asks before every reviewed write (see REVIEWED_WRITE_TOOL_NAMES in
 * packages/pi-qdash/extensions/lib/tool-policy.ts). In RPC mode the question
 * reaches the harness, which approves only what the scenario plans and only
 * inside the disposable scope; it declines everything else. A decline is not a
 * failure by itself: the evaluator judges the records QDash kept.
 */

import { formatPlanApprovalPreview, type PipelinePlanApprovalPreview } from "../../../packages/pi-qdash/extensions/lib/pipeline-plan-preview.ts";
import { parseServerTimestamp } from "../../../packages/pi-qdash/extensions/lib/server-time.ts";
import type { ApprovalPlan, PipelineRunPlan, ScenarioTarget } from "./scenarios.ts";

export interface ApprovalRequest {
  toolName: string;
  args: Record<string, unknown>;
  /** The complete text pi's dialog shows: what the harness, as the user, was asked to approve. */
  dialogMessage?: string;
  /**
   * For `qdash_run_pipeline` with `planId`: the plan as the harness itself read it from QDash
   * (`GET /calibration-pipelines/plans/{plan_id}`), or undefined when it could not be read.
   * The model's arguments name the plan only, so this is what the approval judges.
   */
  storedPlan?: Record<string, unknown>;
}

export interface ApprovalContext {
  target: ScenarioTarget;
  plan: ApprovalPlan;
  /** Sessions this scenario created; a commit is approved only in one of them. */
  scenarioSessionIds: ReadonlySet<string>;
  /** Calibration sessions this scenario created, read from QDash; a pipeline must name one. */
  scenarioCalibrationSessionIds?: ReadonlySet<string>;
  /** Dialogs of each tool the harness already approved in this scenario. */
  approvedCounts?: Readonly<Record<string, number>>;
  /** The current time, for a stored plan's expiry (defaults to Date.now). */
  now?: () => number;
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

/** Whether the calibration session the model proposes stays on the validation chip. */
export function reviewCalibrationSessionCreation(args: Record<string, unknown>, context: ApprovalContext): ApprovalDecision {
  const bounds = context.plan.createCalibrationSession;
  if (!bounds) return decline("this scenario approves no calibration session");
  if (args.chipId !== context.target.chipId) return decline("the calibration session must name the disposable chip explicitly");
  if (typeof args.objective !== "string" || args.objective.trim() === "") return decline("the calibration session needs an objective");
  if (args.profile !== undefined || args.configPath !== undefined) return decline("the calibration session must use the validation connection");
  const created = Math.max(context.approvedCounts?.qdash_create_calibration_session ?? 0, context.scenarioCalibrationSessionIds?.size ?? 0);
  if (created >= bounds.max) return decline(`this scenario approves at most ${bounds.max} calibration session(s)`);
  return { approve: true, reason: "a calibration session on the disposable chip, within the scenario's count" };
}

/** Task names a pipeline step names explicitly, or undefined when a step relies on defaults. */
function explicitTasks(step: Record<string, unknown>): string[] | undefined {
  const tasks = step.tasks;
  if (!Array.isArray(tasks) || tasks.length === 0) return undefined;
  const names: string[] = [];
  for (const task of tasks) {
    if (typeof task === "string") names.push(task);
    else if (record(task) && typeof record(task)?.name === "string") names.push(String(record(task)?.name));
    else return undefined;
  }
  return names;
}

/** Why spec targets are not exactly the selected qubit, or undefined when they are. */
function targetsProblem(targets: Record<string, unknown> | undefined, qid: string): string | undefined {
  const qids = strings(targets?.qids);
  const muxes = targets?.mux_ids !== undefined && targets?.mux_ids !== null;
  const excludes = targets?.exclude_qids !== undefined && targets?.exclude_qids !== null;
  if (!targets || muxes || excludes || !qids || qids.length !== 1 || qids[0] !== qid) {
    return "the pipeline must target exactly the selected qubit";
  }
  return undefined;
}

/** A review digest as QDash writes it (`sha256:v<version>:<hex>`, ExecutePipelinePlanRequest). */
export const REVIEW_DIGEST_PATTERN = /^sha256:v[0-9]+:[0-9a-f]{64}$/;

/**
 * Whether the pipeline the model proposes stays inside the scenario's bounds: the validation
 * chip, the fake (default) backend, exactly the selected qubit, only explicitly named tasks
 * from the plan, a bounded number of task calls, and recorded in this scenario's calibration
 * session. A step that relies on its default tasks is declined: the harness cannot tell from
 * the spec alone what it would run.
 *
 * A call that names a stored plan (`planId`) carries no spec; the stored plan the harness read
 * from QDash is judged instead (`reviewStoredPlan`). A scenario that requires a plan reference
 * declines a raw spec, and every scenario declines a call with both.
 */
export function reviewPipelineRun(args: Record<string, unknown>, context: ApprovalContext, request: Pick<ApprovalRequest, "dialogMessage" | "storedPlan"> = {}): ApprovalDecision {
  const bounds = context.plan.runPipeline;
  if (!bounds) return decline("this scenario approves no pipeline run");
  if (args.chipId !== context.target.chipId) return decline("the pipeline must run on the disposable chip");
  if (args.backendName !== undefined && args.backendName !== "fake") return decline("the pipeline must run on the fake backend");
  if (args.profile !== undefined || args.configPath !== undefined) return decline("the pipeline must use the validation connection");
  if ((context.approvedCounts?.qdash_run_pipeline ?? 0) >= bounds.maxRuns) return decline(`this scenario approves at most ${bounds.maxRuns} pipeline run(s)`);
  const sessionId = args.calibrationSessionId;
  if (typeof sessionId !== "string" || !context.scenarioCalibrationSessionIds?.has(sessionId)) {
    return decline("the pipeline must be recorded in the calibration session this scenario created");
  }
  if (args.spec !== undefined && args.planId !== undefined) return decline("the pipeline must name exactly one of a spec and a stored plan");
  if (args.planId !== undefined) return reviewStoredPlan(args, bounds, context, request);
  if (bounds.requirePlanReference) return decline("this scenario approves only a run of a stored plan by planId, not a spec written into the call");
  const spec = record(args.spec);
  if (!spec) return decline("the pipeline has no spec object");
  const targets = targetsProblem(record(spec.targets), context.target.qid);
  if (targets) return decline(targets);
  const steps = Array.isArray(spec.steps) ? spec.steps : [];
  if (steps.length === 0) return decline("the pipeline has no steps");
  let calls = 0;
  for (const step of steps) {
    const fields = record(step);
    const names = fields ? explicitTasks(fields) : undefined;
    if (!names) return decline("every pipeline step must name its tasks explicitly");
    if (!names.every((name) => bounds.tasks.includes(name))) return decline(`the pipeline may only run ${bounds.tasks.join(", ")}`);
    calls += names.length;
  }
  if (calls > bounds.maxTaskCalls) return decline(`the pipeline may make at most ${bounds.maxTaskCalls} task call(s)`);
  return { approve: true, reason: "a bounded pipeline on the disposable qubit, recorded in the scenario's calibration session" };
}

/**
 * Whether a stored plan the call names stays inside the scenario's bounds, judged from the
 * plan the harness read from QDash itself: the call's plan, unexpired, with a review digest,
 * on the validation chip and the fake backend, starting on exactly the selected qubit, and
 * resolving to at most `maxTaskCalls` calls of the scenario's tasks. The dialog must show the
 * same plan and digest, so what the harness checked is what pi asked the user to approve (the
 * host fetched it independently; plans are immutable, so the two agree only on the same plan).
 *
 * The plan's resolved steps are what its digest binds, so they decide what it runs. A transform
 * step (a filter) resolves to no call and runs no task; it is allowed here because, unlike a raw
 * spec step that relies on defaults, its resolution is known.
 */
function reviewStoredPlan(args: Record<string, unknown>, bounds: PipelineRunPlan, context: ApprovalContext, request: Pick<ApprovalRequest, "dialogMessage" | "storedPlan">): ApprovalDecision {
  const planId = args.planId;
  if (typeof planId !== "string" || planId.trim() === "") return decline("the stored plan's planId must be a non-empty string");
  const plan = request.storedPlan;
  if (!plan) return decline("the stored plan could not be read from QDash");
  if (plan.plan_id !== planId) return decline("QDash answered for another plan than the call names");
  const digest = typeof plan.review_digest === "string" ? plan.review_digest : "";
  if (!REVIEW_DIGEST_PATTERN.test(digest)) return decline("the stored plan has no review digest");
  const expiresAt = parseServerTimestamp(plan.expires_at);
  if (plan.expired === true || !Number.isFinite(expiresAt) || !(expiresAt > (context.now ?? Date.now)())) return decline("the stored plan has expired");
  if (plan.chip_id !== context.target.chipId) return decline("the stored plan must be for the disposable chip");
  if (plan.backend_name !== "fake") return decline("the stored plan must run on the fake backend");
  const shown = dialogShowsPlan(request.dialogMessage ?? "", plan, args);
  if (shown) return decline(shown);
  const spec = record(plan.spec);
  const targets = targetsProblem(record(spec?.targets), context.target.qid);
  if (targets) return decline(targets);
  const targetQids = strings(plan.target_qids);
  if (!targetQids || targetQids.length !== 1 || targetQids[0] !== context.target.qid) return decline("the stored plan must start on exactly the selected qubit");
  const steps = Array.isArray(plan.steps) ? plan.steps.map(record) : [];
  if (steps.length === 0 || steps.some((step) => step === undefined)) return decline("the stored plan has no resolved steps");
  const specSteps = Array.isArray(spec?.steps) ? spec.steps : [];
  if (specSteps.length !== steps.length) return decline("the stored plan's resolved steps do not match its spec");
  const names: string[] = [];
  for (const step of steps as Record<string, unknown>[]) {
    const calls = Array.isArray(step.calls) ? step.calls.map(record) : [];
    if (calls.some((call) => call === undefined || typeof call.name !== "string")) return decline("every resolved call must name its task");
    if (step.kind === "transform") {
      if (calls.length > 0) return decline("a transform step of the stored plan resolves to task calls");
      continue;
    }
    if (calls.length === 0) return decline("every calibration step of the stored plan must resolve to task calls");
    names.push(...calls.map((call) => String(call?.name)));
  }
  if (names.length === 0) return decline("the stored plan runs no task");
  if (!names.every((name) => bounds.tasks.includes(name))) return decline(`the pipeline may only run ${bounds.tasks.join(", ")}`);
  const counted = typeof plan.task_run_count === "number" ? plan.task_run_count : names.length;
  if (Math.max(names.length, counted) > bounds.maxTaskCalls) return decline(`the pipeline may make at most ${bounds.maxTaskCalls} task call(s)`);
  return { approve: true, reason: "a stored plan on the disposable qubit within the scenario's tasks, shown with its review digest, recorded in the scenario's calibration session" };
}

/** The review line that names a stored plan, and the one that names its digest (formatPlanApprovalPreview). */
const PLAN_LINE = /^Stored pipeline plan /;
const DIGEST_LINE = /^Review digest /;
const ARGUMENTS_LINE = "Arguments (the approval covers exactly these):";
const ANY_DIGEST = /sha256:v[0-9]+:[0-9a-f]+/g;

/**
 * The review pi-qdash shows for this plan (formatPlanApprovalPreview), built from the plan the
 * harness read, as `resolvePipelinePlanPreview` builds it from the plan the host read.
 */
export function expectedPlanReview(plan: Record<string, unknown>): string {
  const preview: PipelinePlanApprovalPreview = {
    kind: "calibration_pipeline_plan",
    planId: String(plan.plan_id),
    reviewDigest: String(plan.review_digest),
    chipId: String(plan.chip_id),
    backendName: String(plan.backend_name),
    expiresAt: String(plan.expires_at),
    targetQids: Array.isArray(plan.target_qids) ? plan.target_qids.filter((qid): qid is string => typeof qid === "string") : [],
    plan: JSON.parse(JSON.stringify(plan)) as Record<string, unknown>,
  };
  return formatPlanApprovalPreview(preview);
}

/**
 * Why the dialog text does not show exactly this plan for exactly this call, or undefined when it
 * does. Judged by structure, never by a substring that could sit in a longer ID or a note:
 *
 * - the complete review of the plan the harness read appears as whole, consecutive lines;
 * - it is the only line naming a stored plan and the only line naming a review digest, and no
 *   other digest appears anywhere in the text;
 * - the text ends with the one argument listing the approval covers, and that listing is this
 *   call's arguments.
 */
export function dialogShowsPlan(message: string, plan: Record<string, unknown>, args: Record<string, unknown>): string | undefined {
  const lines = message.split("\n");
  const review = expectedPlanReview(plan).split("\n");
  const at = lines.findIndex((_, start) => review.every((line, offset) => lines[start + offset] === line));
  if (at < 0) return "the dialog does not show the review of the stored plan the harness read";
  if (lines.filter((line) => PLAN_LINE.test(line)).length !== 1 || lines.filter((line) => DIGEST_LINE.test(line)).length !== 1) {
    return "the dialog names more than one stored plan or review digest";
  }
  const digests = message.match(ANY_DIGEST) ?? [];
  if (digests.some((digest) => digest !== plan.review_digest)) return "the dialog shows another review digest";
  const listings = lines.flatMap((line, index) => (line === ARGUMENTS_LINE ? [index] : []));
  if (listings.length !== 1 || listings[0] < at + review.length) return "the dialog does not end with the one argument listing the approval covers";
  let listed: unknown;
  try {
    listed = JSON.parse(lines.slice(listings[0] + 1).join("\n"));
  } catch {
    return "the dialog's argument listing is not the call's arguments";
  }
  const fields = record(listed);
  const keys = (value: Record<string, unknown>) => Object.keys(value).filter((key) => value[key] !== undefined).sort();
  if (!fields || JSON.stringify(keys(fields)) !== JSON.stringify(keys(args)) || keys(args).some((key) => JSON.stringify(fields[key]) !== JSON.stringify(args[key]))) {
    return "the dialog's argument listing is not the call's arguments";
  }
  return undefined;
}

/** Decide one approval dialog. */
export function decideApproval(request: ApprovalRequest, context: ApprovalContext): ApprovalDecision {
  switch (request.toolName) {
    case "qdash_create_agent_session":
      return reviewSessionCreation(request.args, context);
    case "qdash_create_calibration_session":
      return reviewCalibrationSessionCreation(request.args, context);
    case "qdash_run_pipeline":
      return reviewPipelineRun(request.args, context, request);
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
