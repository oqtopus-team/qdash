/**
 * Parameter schemas the runtime puts on pi-qdash tools whose own schema is too
 * loose for a model to call correctly.
 *
 * pi-qdash declares `qdash_create_agent_session.policy` as `Type.Any`, so the
 * model guesses field names and QDash rejects the request with a 422 whose
 * detail the client renders as "[object Object]". Spelling out QDash's
 * `AgentSessionPolicy` (src/qdash/datamodel/agent_session.py) lets Pi validate
 * the call first and tell the model exactly which field is wrong.
 */

import { Type, type TSchema } from "typebox";

// Written as `{ type, enum }`: a union of literals compiles to anyOf/const,
// which vLLM's guided decoding ignores.
const actionType = Type.Unsafe<string>({
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
    description: "Inclusive bounds. Give at least one of minimum or maximum.",
  },
);

export const agentSessionPolicy = Type.Object(
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
        description: "Parameters a run_task action may override, with their allowed bounds.",
      }),
    ),
    quality_gates: Type.Optional(
      Type.Record(Type.String(), numericBounds, {
        description: "Bounds a resulting parameter must meet before it can be committed.",
      }),
    ),
    allow_reconfigure: Type.Optional(
      Type.Boolean({ description: "Only true for sessions meant to run Configure." }),
    ),
    max_actions: Type.Optional(
      Type.Integer({ minimum: 1, maximum: 10_000, description: "Typically 3-6." }),
    ),
  },
  { additionalProperties: false },
);

// pi-qdash declares `format` as a union of literals; same vLLM caveat as above.
const taskKnowledgeFormat = Type.Optional(
  Type.Unsafe<string>({
    type: "string",
    enum: ["markdown", "summary"],
    description: "Output format. Defaults to markdown.",
  }),
);

/** Replacement schemas for individual parameters, keyed by tool name. */
const PARAMETER_OVERRIDES: Record<string, Record<string, TSchema>> = {
  qdash_create_agent_session: { policy: agentSessionPolicy },
  qdash_get_task_knowledge: { format: taskKnowledgeFormat },
};

/** The tool's parameters with any loose properties replaced by precise schemas. */
export function withParameterOverrides(toolName: string, parameters: TSchema): TSchema {
  const overrides = PARAMETER_OVERRIDES[toolName];
  const properties = (parameters as { properties?: Record<string, TSchema> }).properties;
  if (!overrides || !properties) return parameters;
  return Type.Object({ ...properties, ...overrides });
}
