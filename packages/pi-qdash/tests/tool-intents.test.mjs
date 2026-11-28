import assert from "node:assert/strict";
import test from "node:test";

import { buildQDashGuidanceSection } from "../.test-dist/lib/guidance-hook.js";
import { applyToolPolicy } from "../.test-dist/lib/script-policy.js";
import {
  intentRoutingGuide,
  intentSearchLine,
  QDASH_TOOL_INTENTS,
  toolIntents,
  withIntentSearchText,
} from "../.test-dist/lib/tool-intents.js";
import {
  DEFERRED_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
  SESSION_GRANTED_WRITE_TOOL_NAMES,
} from "../.test-dist/lib/tool-policy.js";
import qdashExtension from "../.test-dist/qdash.js";

/** Every tool pi-qdash registers, with the policy applied, as pi sees them. */
function registeredTools() {
  const tools = new Map();
  qdashExtension({
    registerTool: (definition) => tools.set(definition.name, definition),
    registerCommand() {},
    appendEntry() {},
    on() {},
  });
  return tools;
}

const WRITES = new Set([...REVIEWED_WRITE_TOOL_NAMES, ...SESSION_GRANTED_WRITE_TOOL_NAMES]);
const intent = (name) => QDASH_TOOL_INTENTS.find((spec) => spec.intent === name);

test("every classified tool is registered, and only writes are classified as writes", () => {
  const registered = registeredTools();
  for (const spec of QDASH_TOOL_INTENTS) {
    for (const name of spec.tools) {
      assert.ok(registered.has(name), `${name} (${spec.intent}) is not registered`);
      if (spec.intent === "write") assert.ok(WRITES.has(name), `${name} is listed as a write but is not one`);
      else assert.ok(!WRITES.has(name), `${name} is a write listed under ${spec.intent}`);
    }
  }
});

test("measurement preparation never offers a tool that executes or saves", () => {
  for (const name of intent("measurement_preparation").tools) {
    assert.ok(!WRITES.has(name), name);
    assert.ok(NESTED_READ_TOOL_NAMES.includes(name), `${name} should be an audited read`);
  }
});

test("only deferred tools get the request-type search line, after their first line", () => {
  const registered = registeredTools();
  const deferredDiagnosis = registered.get("qdash_get_task_result_evidence");
  assert.match(deferredDiagnosis.description, /^Read one task result[^\n]*\nRequest type: diagnosis:/);
  // Direct tools keep their description: the model already sees them, and prompts stay the same size.
  assert.doesNotMatch(registered.get("qdash_get_task_result").description, /Request type:/);
  assert.doesNotMatch(registered.get("qdash_list_chips").description, /Request type:/);
  // A deferred write carries the write words, never a read type.
  assert.match(registered.get("qdash_run_pipeline").description, /Request type: write:.*needs approval/);
  for (const name of DEFERRED_TOOL_NAMES) {
    const line = intentSearchLine(name);
    if (line && registered.has(name)) assert.ok(registered.get(name).description.includes(line), name);
  }
  // Applying the policy twice does not repeat the line.
  const once = applyToolPolicy({ name: "qdash_plan_pipeline", description: "Plan." });
  assert.equal(applyToolPolicy(once).description, once.description);
  assert.equal(withIntentSearchText("qdash_unknown", "Same."), "Same.");
});

test("the guide maps request types to available tools only, and marks deferred ones", () => {
  const available = ["qdash_get_chip_metrics", "qdash_get_task_result", "qdash_get_task_result_evidence", "qdash_plan_pipeline"];
  const guide = intentRoutingGuide(available, ["qdash_get_task_result_evidence", "qdash_plan_pipeline"]);
  assert.match(guide, /- Stored values \([^)]*\): `qdash_get_chip_metrics`, `qdash_get_task_result`$/m);
  assert.match(guide, /- Diagnosis \([^)]*\): `qdash_get_task_result_evidence`\*$/m);
  assert.match(guide, /- Measurement preparation \([^)]*run and save nothing\): `qdash_plan_pipeline`\*$/m);
  assert.doesNotMatch(guide, /Writes/);
  assert.match(guide, /tool_search` "diagnosis task result evidence"/);
  assert.equal(intentRoutingGuide(["read", "bash"]), null);
  // Without deferred tools there is nothing to load and no tool_search hint.
  assert.doesNotMatch(intentRoutingGuide(available), /tool_search/);
});

test("the guide lets the request type change or mix within a conversation", () => {
  const guide = intentRoutingGuide(QDASH_TOOL_INTENTS.flatMap((spec) => spec.tools));
  assert.match(guide, /move between these at any turn, or combine them: choose again for each request/);
  assert.match(guide, /keep using tools already loaded/);
  assert.match(guide, /A tool not listed here is still available/);
  assert.match(guide, /Writes \(run, save, commit, or apply only when the user asks; each keeps its approval or session grant\)/);
  // A tool may serve several request types.
  assert.deepEqual(toolIntents("qdash_get_task_result_evidence"), ["diagnosis"]);
  assert.deepEqual(toolIntents("qdash_not_classified"), []);
});

test("the pi CLI guidance includes the request-type guide for the run's tools", () => {
  const section = buildQDashGuidanceSection(
    ["tool_search", "qdash_get_chip_metrics", "qdash_get_task_result"],
    null,
    { deferredTools: ["qdash_get_task_result_evidence", "qdash_list_cooldowns"] },
  );
  assert.match(section, /QDash tools by request type:/);
  assert.match(section, /`qdash_get_task_result_evidence`\*/);
  // A tool the guide marks is not listed again as another deferred tool.
  assert.doesNotMatch(section, /Deferred tools: .*qdash_get_task_result_evidence/);
  // Without tool_search, deferred tools are not reachable and not named.
  const noLoader = buildQDashGuidanceSection(["qdash_get_chip_metrics"], null, { deferredTools: ["qdash_get_task_result_evidence"] });
  assert.doesNotMatch(noLoader, /qdash_get_task_result_evidence|tool_search/);
});
