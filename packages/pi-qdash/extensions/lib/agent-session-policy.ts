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

export const agentParameterUpdatesSchema = Type.Object(
  {
    parameters: Type.Array(Type.String(), {
      minItems: 1,
      maxItems: 50,
      description:
        "Parameters the agent may commit; each needs both minimum and maximum in allowed_overrides.",
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
      'An object, not a list, e.g. {"parameters": ["qubit_frequency"], "tasks": ["CheckChevron"], "apply_backend": false}. autonomy auto only. The user\'s one-time approval, given with the session, to commit (and with apply_backend to apply) a candidate of these parameters from these tasks after a result the agent assesses as pass and QDash\'s gates hold, without asking per update. Omit it and every commit and apply is approved per call.',
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
          "Parameter name -> bounds. A step may override a task input of that name within the bounds, and a task output of that name becomes an accepted candidate only inside them. An output that is not a key is staged as rejected and cannot be committed from this session, so a value a later step needs must be a key, with bounds the user approved. QDash checks bounds only; they are not a quality verdict.",
      }),
    ),
    quality_gates: Type.Optional(
      Type.Record(Type.String(), numericBounds, {
        description: "Parameter name -> bounds a resulting value must meet before it can be committed.",
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
  if (Value.Check(agentSessionPolicySchema, policy)) return null;
  const lines = [...Value.Errors(agentSessionPolicySchema, policy)]
    .filter((error) => error.keyword !== "boolean")
    .slice(0, 5)
    .map((error) => `- ${["policy", ...error.instancePath.split("/").filter(Boolean)].join(".")}: ${error.message}`);
  return `Invalid agent session policy; no session was created:\n${lines.join("\n")}`;
}
