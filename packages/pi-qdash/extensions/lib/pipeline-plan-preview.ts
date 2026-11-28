/**
 * The preview a host shows before the user approves running a stored calibration pipeline
 * plan, and the binding that approval gives the call.
 *
 * `qdash_run_pipeline({ chipId, planId })` names a plan only; the model never transcribes or
 * supplies its content or digest. Before asking the user, the host itself (the pi CLI write
 * gate, the QDash web Agent runtime, or the tool's own dialog) fetches the plan from QDash,
 * refuses one that is expired or for another chip or backend, and freezes what it showed:
 * the resolved steps and calls with their settings, the qubits the targets resolve to, the
 * warnings, and the plan's `review_digest`. The approved call then runs the plan with that
 * digest as `expected_review_digest`, so QDash refuses it unless it is the plan shown. The
 * preview is stored with the approval, so a later replay or the chat history shows it after
 * the plan expired.
 *
 * The module has no runtime dependencies so both hosts can import it.
 */

/** What a host fetched and showed for a run of a stored plan; the approval covers it. */
export interface PipelinePlanApprovalPreview {
  kind: "calibration_pipeline_plan";
  planId: string;
  reviewDigest: string;
  chipId: string;
  backendName: string;
  expiresAt: string;
  /** The qubits the plan's targets resolve to when the run starts (MUXes expanded). */
  targetQids: string[];
  /** The plan as QDash returned it (`PipelinePlanResponse`), frozen for display. */
  plan: Record<string, unknown>;
}

export type ApprovalPreview = PipelinePlanApprovalPreview;

/** A reader of stored plans: the SDK's `qdash.pipelines`. */
export interface PlanReader {
  getPlan(planId: string): Promise<unknown>;
}

/** The approval of `qdash_run_pipeline` needs a fetched plan when the call names one. */
export function needsApprovalPreview(toolName: string, args: unknown): boolean {
  return toolName === "qdash_run_pipeline" && typeof planIdOf(args) === "string";
}

function planIdOf(args: unknown): unknown {
  return args !== null && typeof args === "object" ? (args as { planId?: unknown }).planId : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

/** Why a call's arguments are not a single, well-formed source for `qdash_run_pipeline`. */
export function runPipelineArgumentProblem(args: unknown): string | null {
  if (args === null || typeof args !== "object") return null;
  const { spec, planId } = args as { spec?: unknown; planId?: unknown };
  if (spec !== undefined && planId !== undefined) {
    return "qdash_run_pipeline takes exactly one of spec and planId, not both: pass the planId of a plan stored with qdash_create_pipeline_plan, or a spec.";
  }
  if (spec === undefined && planId === undefined) {
    return "qdash_run_pipeline needs exactly one of spec and planId.";
  }
  if (planId !== undefined && !text(planId)) return "qdash_run_pipeline: planId must be a non-empty string.";
  return null;
}

/**
 * Fetch the plan a `qdash_run_pipeline` call names and build the preview its approval shows.
 * Throws when the plan cannot be read, has expired, or is not for the call's chip or backend:
 * then no approval is asked for.
 */
export async function resolvePipelinePlanPreview(
  pipelines: PlanReader,
  args: { planId?: unknown; chipId?: unknown; backendName?: unknown },
  now: () => number = Date.now,
): Promise<PipelinePlanApprovalPreview> {
  const planId = text(args.planId);
  if (!planId) throw new Error("qdash_run_pipeline: planId must be a non-empty string.");
  const plan = (await pipelines.getPlan(planId)) as Record<string, unknown> | undefined;
  if (!plan || typeof plan !== "object") throw new Error(`Plan ${planId} could not be read from QDash.`);
  const reviewDigest = text(plan.review_digest);
  const chipId = text(plan.chip_id);
  const backendName = text(plan.backend_name);
  const expiresAt = text(plan.expires_at instanceof Date ? plan.expires_at.toISOString() : plan.expires_at);
  if (plan.plan_id !== planId || !reviewDigest || !chipId || !backendName || !expiresAt) {
    throw new Error(`QDash answered for plan ${planId} without its ID, chip, backend, expiry or review digest; it cannot be shown for approval.`);
  }
  if (plan.expired === true || !(Date.parse(expiresAt) > now())) {
    throw new Error(`Plan ${planId} expired at ${expiresAt}; it cannot be run or renewed. Build the spec again and store a new plan with qdash_create_pipeline_plan.`);
  }
  if (text(args.chipId) !== chipId) {
    throw new Error(`Plan ${planId} is for chip ${chipId}, not ${String(args.chipId)}; nothing was started.`);
  }
  if (args.backendName !== undefined && text(args.backendName) !== backendName) {
    throw new Error(`Plan ${planId} is for backend ${backendName}, not ${String(args.backendName)}; nothing was started.`);
  }
  const targetQids = Array.isArray(plan.target_qids) ? plan.target_qids.filter((qid): qid is string => typeof qid === "string") : [];
  return {
    kind: "calibration_pipeline_plan",
    planId,
    reviewDigest,
    chipId,
    backendName,
    expiresAt,
    targetQids,
    plan: JSON.parse(JSON.stringify(plan)) as Record<string, unknown>,
  };
}

/** Why an approval's preview does not cover a `qdash_run_pipeline` call, or null when it does. */
export function planBindingProblem(
  preview: unknown,
  args: { planId?: unknown; chipId?: unknown; backendName?: unknown },
): string | null {
  const shown = preview as Partial<PipelinePlanApprovalPreview> | undefined;
  if (!shown || shown.kind !== "calibration_pipeline_plan" || !text(shown.reviewDigest)) {
    return "qdash_run_pipeline was not run: its approval does not carry the plan the user was shown, so it does not cover running plan " +
      `${String(args.planId)}. Call qdash_run_pipeline again so the plan is shown for approval.`;
  }
  if (shown.planId !== args.planId || shown.chipId !== args.chipId) {
    return "qdash_run_pipeline was not run: the plan or chip differs from the one the user approved.";
  }
  if (args.backendName !== undefined && shown.backendName !== args.backendName) {
    return "qdash_run_pipeline was not run: the backend differs from the plan the user approved.";
  }
  return null;
}

type PreviewStep = {
  index?: number;
  name?: string;
  type?: string;
  kind?: string;
  calls?: Array<{ call_id?: string; name?: string; on_failure?: string; settings?: unknown }>;
  reference?: { step?: string | null; call_id?: string | null } | null;
};

/**
 * A spec step's own settings: every field the normalized spec gives it besides its type and
 * its task list (shown as resolved calls). For example `execution_mode` and manual `rounds`,
 * a filter's `metric`, `threshold` and `inverse`, `continue_on_failure`, or a two-qubit
 * `max_parallel_ops`. The review digest binds them, so the review shows them all.
 */
export function stepSpecSettings(specStep: unknown): Record<string, unknown> {
  if (!specStep || typeof specStep !== "object" || Array.isArray(specStep)) return {};
  const { type: _type, tasks: _tasks, ...settings } = specStep as Record<string, unknown>;
  return settings;
}

function specStepAt(spec: unknown, index: number | undefined): unknown {
  const steps = spec && typeof spec === "object" ? (spec as { steps?: unknown }).steps : undefined;
  return Array.isArray(steps) && typeof index === "number" ? steps[index - 1] : undefined;
}

function stepLine(step: PreviewStep, spec: unknown): string[] {
  const label = step.name && step.name !== step.type ? `${step.name} (${step.type})` : String(step.type ?? "?");
  const lines = [`${step.index ?? "?"}. ${label}${step.kind === "transform" ? " [transform]" : ""}`];
  if (step.kind === "transform" && step.reference?.step) {
    lines.push(`   reads ${step.reference.step}${step.reference.call_id ? `.${step.reference.call_id}` : ""}`);
  }
  const settings = stepSpecSettings(specStepAt(spec, step.index));
  if (Object.keys(settings).length) lines.push(`   settings ${JSON.stringify(settings)}`);
  for (const call of step.calls ?? []) {
    const id = call.call_id && call.call_id !== call.name ? ` [${call.call_id}]` : "";
    const settings = call.settings && Object.keys(call.settings as object).length ? ` ${JSON.stringify(call.settings)}` : "";
    lines.push(`   - ${call.name}${id} on_failure=${call.on_failure ?? "stop"}${settings}`);
  }
  return lines;
}

/** The complete text a review shows for a plan: nothing is shortened, the review scrolls. */
export function formatPlanApprovalPreview(preview: PipelinePlanApprovalPreview): string {
  const plan = preview.plan as {
    spec?: { name?: unknown; steps?: unknown };
    targets?: { mux_ids?: number[]; exclude_qids?: string[]; pairs?: string[][] } | null;
    steps?: PreviewStep[];
    warnings?: Array<{ path?: string; message?: string }>;
    default_run_parameters?: Record<string, unknown>;
    task_run_count?: number;
  };
  const name = typeof plan.spec?.name === "string" ? ` '${plan.spec.name}'` : "";
  const targets = plan.targets;
  const lines = [
    `Stored pipeline plan ${preview.planId}${name} on chip ${preview.chipId} (backend ${preview.backendName}).`,
    `Review digest ${preview.reviewDigest}; expires ${preview.expiresAt}. The approval covers exactly this content.`,
    `Starting qubits (${preview.targetQids.length}): ${preview.targetQids.join(", ") || "none"}` +
      (targets?.mux_ids?.length ? ` (MUX ${targets.mux_ids.join(", ")}${targets.exclude_qids?.length ? `, excluding ${targets.exclude_qids.join(", ")}` : ""})` : "") +
      (targets?.pairs?.length ? ` (pairs ${targets.pairs.map((pair) => pair.join("->")).join(", ")})` : ""),
    "Filters and CR schedules choose later qubits and couplings from results while the run goes.",
    `${plan.task_run_count ?? 0} task calls per target. Default run parameters: ${JSON.stringify(plan.default_run_parameters ?? {})}`,
    "",
    "Steps:",
    ...(plan.steps ?? []).flatMap((step) => stepLine(step, plan.spec)),
  ];
  const warnings = plan.warnings ?? [];
  if (warnings.length) {
    lines.push("", "Warnings:", ...warnings.map((warning) => `- ${warning.path}: ${warning.message}`));
  }
  // The whole normalized spec, as stored: every setting the digest binds is in it, including
  // any the summary above does not name.
  lines.push("", "Approved spec (normalized, as stored):", JSON.stringify(plan.spec ?? {}, null, 2));
  lines.push("", "Completed tasks update calibrated parameters in QDash directly.");
  return lines.join("\n");
}
