/**
 * Parameter schemas the runtime puts on pi-qdash tools whose own schema is too
 * loose for a model to call correctly.
 *
 * `qdash_create_agent_session.policy` is not replaced here: pi-qdash declares
 * QDash's `AgentSessionPolicy` itself (extensions/lib/agent-session-policy.ts),
 * so the pi CLI and this runtime offer the model the same schema.
 */

import { Type, type TSchema } from "typebox";

export { agentSessionPolicySchema as agentSessionPolicy } from "@oqtopus-team/pi-qdash/extensions/lib/agent-session-policy.ts";

// pi-qdash declares `format` as a union of literals, which compiles to
// anyOf/const; vLLM's guided decoding ignores that, so spell it `{ type, enum }`.
const taskKnowledgeFormat = Type.Optional(
  Type.Unsafe<string>({
    type: "string",
    enum: ["markdown", "summary"],
    description: "Output format. Defaults to markdown.",
  }),
);

/** Replacement schemas for individual parameters, keyed by tool name. */
const PARAMETER_OVERRIDES: Record<string, Record<string, TSchema>> = {
  qdash_get_task_knowledge: { format: taskKnowledgeFormat },
};

/** The tool's parameters with any loose properties replaced by precise schemas. */
export function withParameterOverrides(toolName: string, parameters: TSchema): TSchema {
  const overrides = PARAMETER_OVERRIDES[toolName];
  const properties = (parameters as { properties?: Record<string, TSchema> }).properties;
  if (!overrides || !properties) return parameters;
  return Type.Object({ ...properties, ...overrides });
}
