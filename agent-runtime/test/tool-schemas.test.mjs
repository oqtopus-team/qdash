import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";
import { Value } from "typebox/value";

import { agentSessionPolicy, withParameterOverrides } from "../src/tool-schemas.ts";

test("the agent session policy requires qids and allowed_tasks", () => {
  assert.equal(Value.Check(agentSessionPolicy, { qids: ["32"], allowed_tasks: ["CheckRabi"] }), true);
  // What the model sent when it had to guess the schema.
  assert.equal(
    Value.Check(agentSessionPolicy, { allowed_qids: ["32"], allowed_tasks: ["CheckRabi"] }),
    false,
  );
  assert.equal(Value.Check(agentSessionPolicy, { qids: [], allowed_tasks: ["CheckRabi"] }), false);
});

test("action types are a plain string enum", () => {
  const items = agentSessionPolicy.properties.allowed_actions.items;
  assert.deepEqual(items, { type: "string", enum: ["run_task", "request_human", "complete_session"] });
});

test("only the policy of qdash_create_agent_session is replaced", () => {
  const original = Type.Object({
    chipId: Type.Optional(Type.String()),
    policy: Type.Any(),
    confirmWrite: Type.Optional(Type.Boolean()),
  });

  const replaced = withParameterOverrides("qdash_create_agent_session", original);
  assert.equal(replaced.properties.policy, agentSessionPolicy);
  assert.deepEqual(replaced.required, ["policy"]);
  assert.equal(withParameterOverrides("qdash_query", original), original);
});

test("the task knowledge format becomes a plain string enum", () => {
  const original = Type.Object({
    taskName: Type.String(),
    format: Type.Optional(Type.Union([Type.Literal("markdown"), Type.Literal("summary")])),
  });
  const replaced = withParameterOverrides("qdash_get_task_knowledge", original);
  assert.deepEqual(replaced.properties.format.type, "string");
  assert.deepEqual(replaced.properties.format.enum, ["markdown", "summary"]);
  assert.deepEqual(replaced.required, ["taskName"]);
});
