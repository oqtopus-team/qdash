import assert from "node:assert/strict";
import { test } from "node:test";

import { createToolSearchExtension } from "@earendil-works/pi-durable/tool-search";
import qdashExtension from "@oqtopus-team/pi-qdash/extensions/qdash.ts";

import { ALLOWED_TOOL_NAMES, isDeferredTool, REVIEWED_WRITE_TOOL_NAMES, SESSION_GRANTED_WRITE_TOOL_NAMES } from "../src/allowed-tools.ts";
import { buildSystemPrompt } from "../src/prompt.ts";
import { buildIntentGuide } from "../src/tool-guide.ts";

/** pi-qdash's tool definitions as the runtime loads them: through pi-qdash's own policy. */
function qdashDefinitions() {
  const tools = new Map();
  qdashExtension({
    registerTool: (definition) => tools.set(definition.name, definition),
    registerCommand() {},
    appendEntry() {},
    on() {},
  });
  return tools;
}

const DEFINITIONS = qdashDefinitions();
const EXPOSED = new Set([...ALLOWED_TOOL_NAMES, ...REVIEWED_WRITE_TOOL_NAMES, ...SESSION_GRANTED_WRITE_TOOL_NAMES]);
const DEFERRED = [...DEFINITIONS.values()].filter((tool) => EXPOSED.has(tool.name) && isDeferredTool(tool.name));

/** The runtime's own `tool_search` (pi-durable) over `deferred`; the names it loads, best first. */
async function search(query, limit = 8, deferred = DEFERRED) {
  const [tool] = createToolSearchExtension().tools;
  const api = { agent: async () => ({ deferred }) };
  const result = await tool.execute({ query, limit }, api, {});
  return result.details.loaded;
}

/** The same tools without the request-type line: what search ranked before it. */
const BASELINE = DEFERRED.map((tool) => ({ ...tool, description: tool.description.replace(/\nRequest type:.*$/s, "") }));

const WRITES = new Set([...REVIEWED_WRITE_TOOL_NAMES, ...SESSION_GRANTED_WRITE_TOOL_NAMES]);

test("the evidence tool is allowlisted and deferred in the runtime", () => {
  assert.ok(ALLOWED_TOOL_NAMES.includes("qdash_get_task_result_evidence"));
  assert.ok(DEFERRED.some((tool) => tool.name === "qdash_get_task_result_evidence"));
});

/** How many tools rank before the first write. */
const readsBeforeWrite = (loaded) => {
  const index = loaded.findIndex((name) => WRITES.has(name));
  return index === -1 ? loaded.length : index;
};

test("a diagnosis search ranks the evidence tool first and diagnosis reads before writes", async () => {
  assert.equal((await search("diagnosis task result evidence"))[0], "qdash_get_task_result_evidence");
  const why = await search("diagnose why failed", 10);
  assert.equal(why[0], "qdash_get_task_result_evidence");
  assert.ok(readsBeforeWrite(why) >= 6, why.join(", "));
  // Without the request-type words, writes crowd the same search.
  const before = await search("diagnose why failed", 10, BASELINE);
  assert.ok(readsBeforeWrite(before) < readsBeforeWrite(why), before.join(", "));
});

test("a measurement preparation search loads planning reads, and no write, first", async () => {
  const loaded = await search("measurement preparation plan remeasure");
  assert.ok(["qdash_plan_calibration", "qdash_plan_pipeline"].includes(loaded[0]), loaded.join(", "));
  assert.equal(readsBeforeWrite(loaded), loaded.length, loaded.join(", "));
  const before = await search("measurement preparation plan remeasure", 8, BASELINE);
  assert.ok(readsBeforeWrite(before) < loaded.length, before.join(", "));
});

test("a write search finds writes, and a mixed request still finds both kinds", async () => {
  const writes = await search("write run execute pipeline");
  assert.ok(writes.includes("qdash_run_pipeline"), writes.join(", "));
  const mixed = await search("diagnosis evidence then plan pipeline", 12);
  assert.ok(mixed.includes("qdash_get_task_result_evidence"), mixed.join(", "));
  assert.ok(mixed.includes("qdash_plan_pipeline"), mixed.join(", "));
});

test("a tool stays loadable by its exact name whatever its request type", async () => {
  for (const name of ["qdash_list_forum_posts", "qdash_run_pipeline", "qdash_get_task_result_evidence"]) {
    assert.equal((await search(name))[0], name);
  }
});

test("the system prompt carries the request-type guide for the exposed tools", () => {
  const names = [...DEFINITIONS.keys()].filter((name) => EXPOSED.has(name));
  const guide = buildIntentGuide(names, names.filter(isDeferredTool));
  const prompt = buildSystemPrompt("en", "en", [], "- `qdash_list_chips`", null, false, null, null, { intentGuide: guide });
  assert.match(prompt, /Tools by request type:\n.*move between these at any turn/);
  assert.match(prompt, /`qdash_get_task_result_evidence`\*/);
  assert.ok(prompt.indexOf("Tools by request type:") < prompt.indexOf("Tool guide:"));
  assert.doesNotMatch(buildSystemPrompt("en", "en"), /Tools by request type/);
});
