/**
 * The `policy` parameter of `qdash_create_agent_session`, shared by every host.
 *
 * It spells out QDash's `AgentSessionPolicy` (src/qdash/datamodel/agent_session.py)
 * so the model sees the exact field names and nested types, and Pi rejects a
 * malformed policy (for example `parameter_updates` sent as an array) before
 * the confirmation dialog or any API call. The pi CLI registers it on the tool
 * and the web runtime uses the same registered schema, so both hosts offer the
 * model one contract. QDash re-validates every policy; this schema only makes
 * the call precise and never grants anything by itself. It deliberately leaves out
 * the policy's numeric acceptance fields (see MODEL_FORBIDDEN_POLICY_FIELDS).
 */

import { Type, type Static } from "typebox";
import { Value } from "typebox/value";

// Written as `{ type, enum }`: a union of literals compiles to anyOf/const,
// which vLLM's guided decoding ignores.
const actionType = Type.Unsafe<"run_task" | "request_human" | "complete_session">({
  type: "string",
  enum: ["run_task", "request_human", "complete_session"],
});

/**
 * Fields of QDash's `AgentSessionPolicy` that hold numbers which accept or reject a result:
 * `allowed_overrides` (bounds on task inputs and on the output of the same name),
 * `task_quality_gates`, and the legacy session-wide `quality_gates`. The model-facing schema
 * omits them and `agentSessionPolicyProblems` refuses them, so no session this tool creates
 * carries a number the model wrote: QDash cannot tell who wrote a number, and an argument
 * claiming the user stated it cannot be verified either. A granted output is accepted on
 * its task's own completion checks. Bounds a person approved through QDash itself (the
 * qdash-agent CLI or the API) keep applying in their sessions.
 */
export const MODEL_FORBIDDEN_POLICY_FIELDS = ["allowed_overrides", "task_quality_gates", "quality_gates"] as const;

export const agentParameterUpdatesSchema = Type.Object(
  {
    parameters: Type.Array(Type.String(), {
      minItems: 1,
      maxItems: 50,
      description:
        "Parameters the agent may commit, as the catalog names the task outputs. A granted output is accepted when its task completed with its own checks passing; this tool sets no numeric bounds. Name only the outputs the goal commits; another output of the same task (such as an incidental control_amplitude of CheckChevron) is staged for reference only and does not block the granted one.",
    }),
    tasks: Type.Array(Type.String(), {
      minItems: 1,
      maxItems: 50,
      description: "Tasks whose completed results may supply them; a subset of allowed_tasks.",
    }),
    apply_backend: Type.Optional(
      Type.Boolean({
        description:
          "Also write committed values to the backend configuration (never pushed to GitHub). Default false.",
      }),
    ),
  },
  {
    additionalProperties: false,
    description:
      'An object, not a list, e.g. {"parameters": ["qubit_frequency"], "tasks": ["CheckChevron"], "apply_backend": false}. autonomy auto only. The user\'s one-time approval, given with the session, to commit (and with apply_backend to apply) a candidate of these parameters from these tasks after a result the agent assesses as pass and its task completed with its own checks passing, without asking per update. Omit it and every commit and apply is approved per call.',
  },
);

export const agentSessionPolicySchema = Type.Object(
  {
    qids: Type.Array(Type.String(), {
      minItems: 1,
      description:
        'Qubit ids the session may act on, as QDash lists them (e.g. ["32"]). Keep it to the target qubit.',
    }),
    allowed_tasks: Type.Array(Type.String(), {
      minItems: 1,
      description: 'Task names the session may run, e.g. ["CheckRabi"].',
    }),
    allowed_actions: Type.Optional(
      Type.Array(actionType, {
        minItems: 1,
        description: "Defaults to run_task, request_human and complete_session.",
      }),
    ),
    allow_reconfigure: Type.Optional(
      Type.Boolean({ description: "Only true for sessions meant to run Configure. Default false." }),
    ),
    max_actions: Type.Optional(
      Type.Integer({ minimum: 1, maximum: 10_000, description: "Action budget (QDash default 100); typically 3-6." }),
    ),
    autonomy: Type.Optional(
      Type.Unsafe<"confirm_each" | "auto">({
        type: "string",
        enum: ["confirm_each", "auto"],
        description:
          "confirm_each (default): every action is approved separately. auto: the user approves this scope, budget, and expiry once, and the session's own steps then run without asking again.",
      }),
    ),
    max_rounds_per_target: Type.Optional(
      Type.Integer({
        minimum: 1,
        maximum: 20,
        description: "How many times one task may run on one qubit in the session (default 3).",
      }),
    ),
    parameter_updates: Type.Optional(agentParameterUpdatesSchema),
    evaluation: Type.Optional(
      Type.Unsafe<"off" | "required">({
        type: "string",
        enum: ["off", "required"],
        description:
          "Calibration evaluator use for the whole session, fixed at approval. off (default): qcal_evaluate is not called; the task's own completion checks decide, and an existing evaluation that is not a reliable SUCCESS still blocks an update. required: each result needs a completed qcal_evaluate evaluation with a reliable fit and a SUCCESS diagnosis before it is committed. Use required only when the user asked for the evaluator; it cannot be changed during the session.",
      }),
    ),
  },
  {
    additionalProperties: false,
    description:
      "Agent session policy QDash accepts. Only qids and allowed_tasks are required; omitted fields take QDash's defaults. It holds no numeric bounds or quality gates: a session created here overrides no task input, and each granted output is accepted on its task's own completion checks.",
  },
);

export type AgentSessionPolicyInput = Static<typeof agentSessionPolicySchema>;

/**
 * Why a policy does not match the schema, or null when it does. The execute
 * path calls this before the approval and the API, so a call that reaches the
 * tool without Pi's own argument validation still fails closed.
 */
export function agentSessionPolicyProblems(policy: unknown): string | null {
  const forbidden = numericCriteriaProblem(policy);
  if (forbidden) return forbidden;
  if (Value.Check(agentSessionPolicySchema, policy)) return scopeProblems(policy);
  const lines = [...Value.Errors(agentSessionPolicySchema, policy)]
    .filter((error) => error.keyword !== "boolean")
    .slice(0, 5)
    .map((error) => `- ${["policy", ...error.instancePath.split("/").filter(Boolean)].join(".")}: ${error.message}`);
  return `Invalid agent session policy; no session was created:\n${lines.join("\n")}`;
}

/**
 * Refuses any numeric acceptance field, even an empty one or one with a note that the user
 * stated it: no argument can prove who wrote a number.
 */
function numericCriteriaProblem(policy: unknown): string | null {
  if (policy === null || typeof policy !== "object") return null;
  const present = MODEL_FORBIDDEN_POLICY_FIELDS.filter((field) => Object.hasOwn(policy, field));
  if (present.length === 0) return null;
  return `Invalid agent session policy; no session was created:\n${present
    .map((field) => `- policy.${field}: not accepted from this tool`)
    .join("\n")}\nNumeric bounds and quality gates cannot be set through qdash_create_agent_session, whoever stated them, because QDash cannot verify where a number came from. Remove the field. A granted output is accepted when its task completed with its own checks passing; another output of the same task that is not granted is staged for reference only and does not block it. A session created here overrides no task input. If the user wants approved bounds, tell them to create the session in QDash themselves (the qdash-agent CLI or the API).`;
}

/**
 * Cross-field checks the schema cannot express, made before the approval so the user is
 * never asked to approve a policy QDash would refuse.
 */
function scopeProblems(policy: AgentSessionPolicyInput): string | null {
  const allowed = new Set(policy.allowed_tasks);
  const outside = (policy.parameter_updates?.tasks ?? []).filter((task) => !allowed.has(task));
  if (outside.length === 0) return null;
  return `Invalid agent session policy; no session was created:\n- policy.parameter_updates.tasks: ${outside.join(", ")} must also be in allowed_tasks.`;
}

/**
 * Why a reviewed write's arguments cannot succeed, checked before its approval is asked
 * for, or null. Both hosts call it (the pi CLI write gate and the web runtime's approval
 * card), so a user is never asked to approve a session policy QDash would refuse.
 */
export function preApprovalProblems(toolName: string, args: unknown): string | null {
  if (toolName !== "qdash_create_agent_session") return null;
  const policy = args !== null && typeof args === "object" ? (args as { policy?: unknown }).policy : undefined;
  // A missing policy is a shape error the tool's schema and execute report.
  if (policy === null || typeof policy !== "object") return null;
  return agentSessionPolicyProblems(policy);
}
