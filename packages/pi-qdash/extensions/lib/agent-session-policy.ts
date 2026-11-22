/**
 * The `policy` parameter of `qdash_create_agent_session`, shared by every host.
 *
 * It spells out QDash's `AgentSessionPolicy` (src/qdash/datamodel/agent_session.py)
 * so the model sees the exact field names and nested types, and Pi rejects a
 * malformed policy (for example `parameter_updates` sent as an array) before
 * the confirmation dialog or any API call. The pi CLI registers it on the tool
 * and the web runtime uses the same registered schema, so both hosts offer the
 * model one contract. QDash re-validates every policy; this schema only makes
 * the call precise and never grants anything by itself.
 */

import { Type, type Static } from "typebox";
import { Value } from "typebox/value";

// Written as `{ type, enum }`: a union of literals compiles to anyOf/const,
// which vLLM's guided decoding ignores.
const actionType = Type.Unsafe<"run_task" | "request_human" | "complete_session">({
  type: "string",
  enum: ["run_task", "request_human", "complete_session"],
});

const numericBounds = Type.Object(
  {
    minimum: Type.Optional(Type.Number()),
    maximum: Type.Optional(Type.Number()),
  },
  {
    additionalProperties: false,
    minProperties: 1,
    description:
      "Inclusive bounds in the parameter's own unit. Give at least one of minimum or maximum; minimum must not exceed maximum.",
  },
);

/**
 * The quality metrics QDash records on a task result, mirroring
 * RECORDED_QUALITY_METRICS in src/qdash/datamodel/quality_metrics.py.
 */
export const RECORDED_QUALITY_METRICS = ["r2"] as const;

const qualityMetricGates = Type.Object(
  { r2: Type.Optional(numericBounds) },
  {
    additionalProperties: false,
    minProperties: 1,
    description: "Quality metric -> bounds for this task's results. Only metrics QDash records: r2.",
  },
);

export const agentParameterUpdatesSchema = Type.Object(
  {
    parameters: Type.Array(Type.String(), {
      minItems: 1,
      maxItems: 50,
      description:
        "Parameters the agent may commit, as the catalog names the task outputs. No bounds are needed: a granted output is accepted when its task completed with its own checks passing, and bounds in allowed_overrides apply only if the user gave them.",
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
      'An object, not a list, e.g. {"parameters": ["qubit_frequency"], "tasks": ["CheckChevron"], "apply_backend": false}. autonomy auto only. The user\'s one-time approval, given with the session, to commit (and with apply_backend to apply) a candidate of these parameters from these tasks after a result the agent assesses as pass, its task completed with its own checks passing, and any bounds or gates the user gave hold, without asking per update. No bounds are needed to grant it. Omit it and every commit and apply is approved per call.',
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
    allowed_overrides: Type.Optional(
      Type.Record(Type.String(), numericBounds, {
        description:
          "Parameter name -> bounds the user stated; never derive them yourself (not from the current value, a percent window, or task knowledge). A step may override a task input of that name within the bounds, and a task output of that name becomes an accepted candidate only inside them. An output that is neither a key nor granted in parameter_updates is staged as rejected. QDash records the bounds as approved with the session and cannot verify their source; they are not a quality verdict.",
      }),
    ),
    task_quality_gates: Type.Optional(
      Type.Record(Type.String(), qualityMetricGates, {
        description:
          'Task name -> quality metric bounds, e.g. {"CheckRabi": {"r2": {"minimum": 0.9}}}. A candidate from a result of that task is accepted only when the result records the metric inside the bounds; results of other tasks are not checked. Each key must be in allowed_tasks. Only metrics QDash records on task results can be gated (currently r2, the fit R²); an output such as average_gate_fidelity is bounded in allowed_overrides, and a value of another task is never evidence for this one. Only with bounds the user stated; never author one.',
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
      "Agent session policy QDash accepts. Only qids and allowed_tasks are required; omitted fields take QDash's defaults.",
  },
);

export type AgentSessionPolicyInput = Static<typeof agentSessionPolicySchema>;

/**
 * Why a policy does not match the schema, or null when it does. The execute
 * path calls this before the approval and the API, so a call that reaches the
 * tool without Pi's own argument validation still fails closed.
 */
export function agentSessionPolicyProblems(policy: unknown): string | null {
  if (policy !== null && typeof policy === "object" && "quality_gates" in policy) {
    return 'Invalid agent session policy; no session was created:\n- policy.quality_gates: a session-wide gate would check results of every task, so a metric only one task reports rejects the others. Name each gate\'s task in task_quality_gates instead, e.g. {"CheckRabi": {"r2": {"minimum": ...}}}.';
  }
  if (Value.Check(agentSessionPolicySchema, policy)) return scopeProblems(policy);
  const lines = [...Value.Errors(agentSessionPolicySchema, policy)]
    .filter((error) => error.keyword !== "boolean")
    .slice(0, 5)
    .map((error) => `- ${["policy", ...error.instancePath.split("/").filter(Boolean)].join(".")}: ${error.message}`);
  return `Invalid agent session policy; no session was created:\n${lines.join("\n")}`;
}

/**
 * Cross-field checks the schema cannot express, made before the approval so the user is
 * never asked to approve a gate QDash would refuse.
 */
function scopeProblems(policy: AgentSessionPolicyInput): string | null {
  const allowed = new Set(policy.allowed_tasks);
  const outside = Object.keys(policy.task_quality_gates ?? {}).filter((task) => !allowed.has(task));
  if (outside.length === 0) return null;
  return `Invalid agent session policy; no session was created:\n- policy.task_quality_gates: ${outside.join(", ")} must also be in allowed_tasks; a gate checks only results of its own task.`;
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
