import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  applyQDashGuidance,
  buildQDashGuidanceSection,
  BUNDLED_QDASH_SKILL_PATH,
  installQDashGuidance,
  QDASH_GUIDANCE_SECTION,
} from "../.test-dist/lib/guidance-hook.js";
import {
  extractToolRouting,
  investigationPolicyBullets,
  QDASH_INVESTIGATION_POLICY,
  QDASH_REQUEST_POLICY,
  requestPolicyBullets,
  toolRoutingNames,
} from "../.test-dist/lib/qdash-guidance.js";
import qdashExtension from "../.test-dist/qdash.js";

const SKILL = readFileSync(new URL("../skills/qdash/SKILL.md", import.meta.url), "utf8");

// Instructions that belong to the QDash Agent Runtime's chat host, not to pi CLI.
const RUNTIME_ONLY = /render_ui|render_chart|ask_user|read_skill|approval card|tool_search|codemode|deferred|no filesystem or shell/i;

/** The pi-qdash extension as pi CLI loads it, with its tools and event handlers. */
function loadExtension() {
  const tools = [];
  const handlers = new Map();
  qdashExtension({
    registerTool: (definition) => tools.push(definition.name),
    registerCommand() {},
    appendEntry() {},
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
  });
  return { tools, handlers };
}

/** Prompt inputs shaped like pi's before_agent_start `systemPromptOptions`. */
function promptOptions(selectedTools, extra = {}) {
  return {
    customPrompt: undefined,
    selectedTools: [...selectedTools],
    hiddenTools: [],
    toolSnippets: {},
    toolGuidelines: {},
    promptGuidelines: ["Keep the user's rule"],
    appendSystemPrompt: "Appended by the user",
    sections: { user_section: "kept" },
    cwd: "/work",
    contextFiles: [{ path: "/work/AGENTS.md", content: "Project rules" }],
    skills: [],
    ...extra,
  };
}

async function runHooks(handlers, options) {
  for (const handler of handlers.get("before_agent_start") ?? []) {
    await handler({ type: "before_agent_start", messageType: "user", prompt: "hi", systemPrompt: "", systemPromptOptions: options }, {});
  }
}

test("the policy is host-neutral", () => {
  assert.ok(QDASH_INVESTIGATION_POLICY.length > 0);
  assert.deepEqual(investigationPolicyBullets(), QDASH_INVESTIGATION_POLICY.map((rule) => `- ${rule}`));
  for (const rule of QDASH_INVESTIGATION_POLICY) assert.doesNotMatch(rule, RUNTIME_ONLY);
  assert.match(QDASH_INVESTIGATION_POLICY.join("\n"), /tool result or from the user/);
  assert.match(QDASH_INVESTIGATION_POLICY.join("\n"), /call `qdash_current_time` each time.*answer in UTC; never infer their time zone from their language or the host's setting/);
});

test("the request policy is host-neutral and grants no write", () => {
  assert.ok(QDASH_REQUEST_POLICY.length > 0);
  assert.deepEqual(requestPolicyBullets(), QDASH_REQUEST_POLICY.map((rule) => `- ${rule}`));
  for (const rule of QDASH_REQUEST_POLICY) {
    assert.doesNotMatch(rule, RUNTIME_ONLY);
    // Skills own flows and tasks; the shared rules name none.
    assert.doesNotMatch(rule, /`|\bCheck[A-Z]|qdash-|_calibration\b/);
  }
  const text = QDASH_REQUEST_POLICY.join("\n");
  assert.match(text, /not approval for a write/);
  assert.match(text, /call no tool that executes or saves/);
  // Targets come from the open page and read-only tools before a question.
  assert.match(text, /page the user has open, then from read-only tools/);
});

test("a broad calibration asks agentic or workflow once, and the answer approves nothing", () => {
  // These check the guidance both hosts send; whether a live model asks at the right moment is
  // not something a scripted test shows.
  const rule = QDASH_REQUEST_POLICY.find((item) => /can run two ways/.test(item));
  assert.ok(rule, "no execution-mode rule");
  // Two options, asked before anything is created or run, only when nothing settles it.
  assert.match(rule, /agentic, where you choose each next measurement from the results inside the scope the user approves/);
  assert.match(rule, /as a workflow, where the whole sequence \(a saved template or flow, or a composed pipeline\) is set out for review first/);
  assert.match(rule, /When neither the request, the conversation, nor the host's context settles which one/);
  assert.match(rule, /ask one short question with those two options before you create an agent session or compose, save, or run a flow or pipeline/);
  // Explicit wording and an earlier answer are reused, not asked again.
  assert.match(rule, /keep the answer for the rest of the conversation/);
  assert.match(rule, /"Step by step based on the results" or continuing a session means agentic; "run this flow" or a named template means a workflow; do not ask again/);
  // Reads and single remeasurements never get the question.
  assert.match(rule, /A question about stored values or a remeasurement of one property needs no such question/);
  // A preference only: approvals, session scope, and stops stay; no switching past a stop.
  assert.match(rule, /The answer is a preference, not an approval: every write keeps its own approval/);
  assert.match(rule, /keeps its approved scope, update authority, and stops for a human/);
  assert.match(rule, /do not switch to the other way to get past the stop/);
  // The rule that forbids procedural questions names this one exception.
  assert.match(QDASH_REQUEST_POLICY[0], /the one question you may need is how a broad calibration should run/);
  assert.match(QDASH_REQUEST_POLICY.join("\n"), /not approval for a write/);
});

test("the calibration skills carry the same execution-mode choice", () => {
  assert.match(SKILL, /For single-qubit calibration both paths fit/);
  assert.match(SKILL, /ask once, with those two options, before creating a session or composing,\nsaving, or running a flow or pipeline/);
  assert.match(SKILL, /A workflow does not have to be a new pipeline: a saved\ntemplate or flow that fits the goal is the simpler choice/);
  assert.match(SKILL, /a read of stored\nresults, or a remeasurement of one property such as T1 needs no question/);
  assert.match(SKILL, /it approves no write, so each path's own approvals still apply/);
  // Neither path is a fallback for the other.
  assert.match(SKILL, /Do not run the same task through a flow or pipeline instead/);
  assert.match(SKILL, /is reported, not routed into an agent session; changing path is\nthe user's decision/);
  const oneQubit = readFileSync(new URL("../skills/qdash-one-qubit-calibration/SKILL.md", import.meta.url), "utf8");
  assert.match(oneQubit, /ask once as the `qdash` skill describes; once they\nchoose the agentic path, follow `qdash-agent-calibration`/);
});

test("the bundled skill has a routing guide that names real pi-qdash tools", () => {
  const { tools } = loadExtension();
  const routing = extractToolRouting(SKILL, tools);
  assert.ok(routing);
  assert.doesNotMatch(routing, /## Composing|## Session context|Cooldown-aware/);
  const named = [...toolRoutingNames(routing)];
  assert.ok(named.length > 20);
  for (const name of named) assert.ok(tools.includes(name), `${name} is not registered by pi-qdash`);
});

test("routing keeps only available tools", () => {
  const routing = extractToolRouting(SKILL, ["qdash_list_chips", "qdash_get_default_chip", "qdash_query"]);
  assert.match(routing, /^\s*- `qdash_list_chips`, `qdash_get_default_chip` — list chips or resolve the active chip$/m);
  assert.match(routing, /`qdash_query` — fallback/);
  assert.doesNotMatch(routing, /qdash_list_cryostats|qdash_create_forum_post|Confirmation-gated write tools/);
  // A described line goes as a whole when one of its tools is unavailable.
  assert.doesNotMatch(extractToolRouting(SKILL, ["qdash_list_chips", "qdash_query"]), /qdash_list_chips/);
  assert.equal(extractToolRouting("# no routing section", ["qdash_list_chips"]), null);
  assert.equal(extractToolRouting(SKILL, []), null);
});

test("the CLI section carries the policy and routing without runtime-only instructions", () => {
  const { tools } = loadExtension();
  const section = buildQDashGuidanceSection(["read", "bash", ...tools], SKILL);
  for (const bullet of investigationPolicyBullets()) assert.ok(section.includes(bullet));
  assert.match(section, /Plain-language requests:\n/);
  for (const bullet of requestPolicyBullets()) assert.equal(section.split(bullet).length, 2, bullet);
  assert.match(section, /QDash tool routing:\nPrefer the dedicated tool/);
  assert.doesNotMatch(section, RUNTIME_ONLY);
  // Deferred tools are marked only by the runtime.
  assert.doesNotMatch(section, /`qdash_[a-z0-9_]+`\*/);
});

test("the section needs a QDash tool, and keeps the policy without the skill", () => {
  assert.equal(buildQDashGuidanceSection(["read", "bash"], SKILL), null);
  const policyOnly = buildQDashGuidanceSection(["qdash_list_chips"], null);
  assert.match(policyOnly, /Investigation and evidence:/);
  assert.match(policyOnly, /Plain-language requests:/);
  assert.doesNotMatch(policyOnly, /QDash tool routing/);
});

test("the extension sets one section per run and leaves the user's prompt inputs alone", async () => {
  const { tools, handlers } = loadExtension();
  assert.equal(handlers.get("before_agent_start")?.length, 1);
  const options = promptOptions(["read", "bash", "edit", "write", ...tools]);
  await runHooks(handlers, options);
  const first = options.sections[QDASH_GUIDANCE_SECTION];
  assert.ok(first);

  for (let turn = 0; turn < 3; turn++) await runHooks(handlers, options);
  assert.equal(options.sections[QDASH_GUIDANCE_SECTION], first);
  assert.deepEqual(Object.keys(options.sections).sort(), [QDASH_GUIDANCE_SECTION, "user_section"].sort());
  assert.deepEqual(options.promptGuidelines, ["Keep the user's rule"]);
  assert.equal(options.appendSystemPrompt, "Appended by the user");
  assert.equal(options.customPrompt, undefined);
  assert.deepEqual(options.contextFiles, [{ path: "/work/AGENTS.md", content: "Project rules" }]);
});

test("a custom system prompt is kept and still gets the section", async () => {
  const { tools, handlers } = loadExtension();
  const options = promptOptions(tools, { customPrompt: "You are my assistant." });
  await runHooks(handlers, options);
  assert.equal(options.customPrompt, "You are my assistant.");
  assert.ok(options.sections[QDASH_GUIDANCE_SECTION]);
});

test("routing follows the selected tools between runs", async () => {
  const { handlers } = loadExtension();
  const qdashTools = ["qdash_list_chips", "qdash_get_default_chip", "qdash_list_cryostats", "qdash_list_cooldowns"];
  const options = promptOptions(["read", ...qdashTools]);
  await runHooks(handlers, options);
  assert.match(options.sections[QDASH_GUIDANCE_SECTION], /qdash_get_default_chip/);
  assert.match(options.sections[QDASH_GUIDANCE_SECTION], /qdash_list_cooldowns/);

  // A hidden tool is not callable directly, so the routing leaves it out.
  options.hiddenTools = ["qdash_list_cryostats"];
  await runHooks(handlers, options);
  const hiddenRouting = options.sections[QDASH_GUIDANCE_SECTION].split("QDash tool routing:")[1] ?? "";
  assert.doesNotMatch(hiddenRouting, /qdash_list_cryostats|qdash_list_cooldowns/);
  // The request-type guide never names a hidden tool; a declared one stays.
  assert.doesNotMatch(options.sections[QDASH_GUIDANCE_SECTION], /qdash_list_cryostats/);
  assert.match(options.sections[QDASH_GUIDANCE_SECTION], /QDash tools by request type:[\s\S]*`qdash_list_cooldowns`/);
  assert.match(options.sections[QDASH_GUIDANCE_SECTION], /qdash_get_default_chip/);

  options.selectedTools = ["read", "qdash_list_chips"];
  options.hiddenTools = [];
  await runHooks(handlers, options);
  assert.doesNotMatch(options.sections[QDASH_GUIDANCE_SECTION], /QDash tool routing/);
  assert.match(options.sections[QDASH_GUIDANCE_SECTION], /Investigation and evidence/);

  options.selectedTools = ["read", "bash"];
  options.hiddenTools = [];
  await runHooks(handlers, options);
  assert.equal(options.sections[QDASH_GUIDANCE_SECTION], undefined);
  assert.equal(options.sections.user_section, "kept");
});

test("applyQDashGuidance creates missing sections and tolerates absent fields", () => {
  const options = { selectedTools: ["qdash_list_chips"] };
  applyQDashGuidance(options, SKILL);
  assert.ok(options.sections[QDASH_GUIDANCE_SECTION]);
  const none = {};
  applyQDashGuidance(none, SKILL);
  assert.deepEqual(none, {});
});

test("an unreadable skill leaves the policy in place", async () => {
  const handlers = [];
  installQDashGuidance({ on: (_event, handler) => handlers.push(handler) }, "/nonexistent/qdash/SKILL.md");
  const options = promptOptions(["qdash_list_chips"]);
  await handlers[0]({ systemPromptOptions: options });
  await handlers[0]({ systemPromptOptions: options });
  assert.match(options.sections[QDASH_GUIDANCE_SECTION], /Investigation and evidence:/);
  assert.doesNotMatch(options.sections[QDASH_GUIDANCE_SECTION], /QDash tool routing/);
  assert.match(BUNDLED_QDASH_SKILL_PATH, /skills\/qdash\/SKILL\.md$/);
});

test("with pi's codemode and tool_search active, the section gives chat's script and deferred-tool rules", () => {
  const declared = ["read", "codemode", "tool_search", "qdash_list_chips", "qdash_get_default_chip", "qdash_list_chip_qubits"];
  const section = buildQDashGuidanceSection(declared, SKILL, { deferredTools: ["qdash_list_cooldowns", "qdash_list_cryostats", "qdash_config_info"] });
  assert.match(section, /QDash scripts and tool loading:/);
  assert.match(section, /Use `codemode` when a question needs many read-only QDash calls/);
  assert.match(section, /call `tool_search` with the tool name/);
  // Deferred tools the routing guide names are marked there.
  if (extractToolRouting(SKILL, ["qdash_list_cooldowns"])) assert.match(section, /`qdash_list_cooldowns`\*/);
  // Without tool_search the deferred tools are unreachable and go unmentioned.
  const noLoader = buildQDashGuidanceSection(["codemode", "qdash_list_chips"], SKILL, { deferredTools: ["qdash_list_cooldowns"] });
  assert.doesNotMatch(noLoader, /tool_search|qdash_list_cooldowns/);
  assert.match(noLoader, /Use `codemode`/);
  // Neither active: no orchestration rules at all.
  assert.doesNotMatch(buildQDashGuidanceSection(["qdash_list_chips"], SKILL, { deferredTools: ["qdash_list_cooldowns"] }), RUNTIME_ONLY);
});

test("chat and the pi CLI give the same script and deferred-tool rules", async () => {
  const { QDASH_SCRIPT_GUIDELINE, deferredToolsGuideline } = await import("../.test-dist/lib/qdash-guidance.js");
  const section = buildQDashGuidanceSection(["codemode", "tool_search", "qdash_list_chips"], null, { deferredTools: ["qdash_list_cryostats"] });
  assert.ok(section.includes(QDASH_SCRIPT_GUIDELINE));
  assert.ok(section.includes(deferredToolsGuideline(["qdash_list_cryostats"])));
});

test("an unexpected tool failure may be reported by the user; ordinary refusals are not bugs", () => {
  const rule = QDASH_INVESTIGATION_POLICY.find((item) => item.includes("GitHub bug form"));
  assert.ok(rule);
  assert.match(rule, /an HTTP 5xx, or a response the tool could not read/);
  assert.match(rule, /A refused step, a failed measurement, a rejected candidate or quality gate, a declined approval, or input to correct is not a bug/);
  assert.match(rule, /Never say an issue was filed\./);
  assert.match(rule, /without credentials, prompts, or full results/);
});
