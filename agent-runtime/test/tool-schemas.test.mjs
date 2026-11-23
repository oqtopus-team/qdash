import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";
import { Value } from "typebox/value";
import { validateToolArguments } from "@earendil-works/pi-ai";

import qdashExtension from "@oqtopus-team/pi-qdash/extensions/qdash.ts";

import { buildQDashExtension } from "../src/durable-tools.ts";
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

test("the policy carries the autonomy grant and its round budget", () => {
  assert.equal(
    Value.Check(agentSessionPolicy, { qids: ["32"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_rounds_per_target: 2 }),
    true,
  );
  assert.equal(Value.Check(agentSessionPolicy, { qids: ["32"], allowed_tasks: ["CheckRabi"], autonomy: "always" }), false);
  assert.equal(Value.Check(agentSessionPolicy, { qids: ["32"], allowed_tasks: ["CheckRabi"], max_rounds_per_target: 0 }), false);
  assert.deepEqual(agentSessionPolicy.properties.autonomy.enum, ["confirm_each", "auto"]);
});

test("action types are a plain string enum", () => {
  const items = agentSessionPolicy.properties.allowed_actions.items;
  assert.deepEqual(items, { type: "string", enum: ["run_task", "request_human", "complete_session"] });
});

test("the agent session policy is not overridden by the runtime", () => {
  const original = Type.Object({ chipId: Type.Optional(Type.String()), policy: Type.Any() });
  assert.equal(withParameterOverrides("qdash_create_agent_session", original), original);
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

// Pi 1.5 validates tool arguments with pi-schema, not TypeBox's own checker.
// Check the schemas both hosts register the way Pi validates a model's call:
// the pi CLI's tool as pi-qdash registers it, and the web runtime's tool as
// buildQDashExtension exposes it.
function installedTools() {
  const tools = new Map();
  qdashExtension({
    registerTool: (definition) => tools.set(definition.name, { definition }),
    registerCommand() {},
    on() {},
  });
  return [{ tools }];
}

const installed = installedTools();
const cliTool = installed[0].tools.get("qdash_create_agent_session").definition;
const webTool = buildQDashExtension(installed, {}, "/tmp/work", { toolArgs: { profile: "runtime", configPath: "/x", useEnv: false } })
  .extension.tools.find((tool) => tool.name === "qdash_create_agent_session");
const HOSTS = [["pi CLI", cliTool], ["web runtime", webTool]];

function validateWith(tool, policy) {
  return validateToolArguments(tool, { type: "toolCall", id: "call-1", name: tool.name, arguments: { chipId: "chip-001", policy } });
}

const GRANT_POLICY = {
  qids: ["0"],
  allowed_tasks: ["CheckChevron", "CheckRabi"],
  autonomy: "auto",
  max_actions: 4,
  parameter_updates: { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], apply_backend: false },
};

test("both hosts offer the model the same nested policy schema", () => {
  assert.ok(webTool, "the web runtime registers qdash_create_agent_session");
  const cli = JSON.parse(JSON.stringify(cliTool.parameters.properties.policy));
  const web = JSON.parse(JSON.stringify(webTool.parameters.properties.policy));
  assert.deepEqual(web, cli);
  assert.deepEqual(cli, JSON.parse(JSON.stringify(agentSessionPolicy)));
  const updates = cli.properties.parameter_updates;
  assert.equal(updates.type, "object");
  assert.deepEqual(updates.required, ["parameters", "tasks"]);
  assert.equal(updates.properties.parameters.type, "array");
  assert.equal(updates.properties.tasks.type, "array");
  assert.equal(updates.properties.apply_backend.type, "boolean");
  assert.equal(updates.additionalProperties, false);
  // No numeric acceptance field is offered to the model in either host.
  for (const field of ["allowed_overrides", "task_quality_gates", "quality_gates"]) assert.equal(cli.properties[field], undefined, field);
  assert.deepEqual(cli.required, ["qids", "allowed_tasks"]);
});

for (const [host, tool] of HOSTS) {
  test(`${host}: Pi accepts a valid policy with an update grant and coerces loose scalars`, () => {
    assert.deepEqual(validateWith(tool, GRANT_POLICY).policy, GRANT_POLICY);
    const args = validateWith(tool, { qids: ["32"], allowed_tasks: ["CheckRabi"], max_actions: "4" });
    assert.equal(args.policy.max_actions, 4);
  });

  test(`${host}: Pi rejects parameter_updates sent as a list, never coercing it into a grant`, () => {
    // What a real model sent in the dependent-commit validation run.
    const asList = { ...GRANT_POLICY, parameter_updates: [{ parameter: "qubit_frequency", task: "CheckChevron" }] };
    assert.throws(() => validateWith(tool, asList), /policy\.parameter_updates/);
    assert.throws(() => validateWith(tool, { ...GRANT_POLICY, parameter_updates: ["qubit_frequency"] }), /policy\.parameter_updates/);
    assert.throws(
      () => validateWith(tool, { ...GRANT_POLICY, parameter_updates: { parameters: ["qubit_frequency"] } }),
      /policy\.parameter_updates\.tasks: missing/,
    );
    assert.throws(
      () => validateWith(tool, { ...GRANT_POLICY, parameter_updates: { ...GRANT_POLICY.parameter_updates, apply: true } }),
      /policy\.parameter_updates\.apply: unknown field/,
    );
  });

  test(`${host}: Pi rejects guessed fields and names the path`, () => {
    assert.throws(() => validateWith(tool, { allowed_qids: ["32"], allowed_tasks: ["CheckRabi"] }), /- policy\.qids: missing/);
    assert.throws(
      () => validateWith(tool, { qids: ["32"], allowed_tasks: ["CheckRabi"], allowed_actions: ["delete_chip"] }),
      /- policy\.allowed_actions\.0: expected one of/,
    );
    // Bounds and gates are not part of the schema, so Pi's own validation refuses them too.
    for (const field of ["allowed_overrides", "task_quality_gates", "quality_gates"]) {
      assert.throws(() => validateWith(tool, { qids: ["32"], allowed_tasks: ["CheckRabi"], [field]: {} }), new RegExp(`- policy\\.${field}: unknown field`));
    }
    assert.throws(() => validateWith(tool, { qids: ["32"], allowed_tasks: ["CheckRabi"], max_actions: 0 }), /policy\.max_actions/);
  });
}
