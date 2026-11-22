import assert from "node:assert/strict";
import { test } from "node:test";

import { buildSystemPrompt } from "../src/prompt.ts";

test("Japanese language codes become an explicit user-facing instruction", () => {
  const prompt = buildSystemPrompt("ja", "en");
  assert.match(prompt, /Reason internally in English/);
  assert.match(prompt, /entire reply.*Japanese \(日本語\)/);
});

test("automatic language follows the latest user message", () => {
  assert.match(buildSystemPrompt("auto", "en"), /same language as the user's latest message/);
});

test("write tools always require approval by the user, not the model", () => {
  const prompt = buildSystemPrompt("auto", "en");
  assert.match(prompt, /approval card with the exact arguments/);
  assert.doesNotMatch(prompt, /confirmWrite/);
});

test("only the steps of an approved auto agent session run without a card, and nothing continues by itself", () => {
  const prompt = buildSystemPrompt("auto", "en");
  assert.match(prompt, /`qdash_run_agent_session_step` and `qdash_request_agent_human`: they run at once, without a card, because the user already approved the agent session \(autonomy auto\)/);
  // A recorded stop decision is not a stop: only the end tool ends a session.
  assert.match(prompt, /`nextAction` `stop` or `complete` changes no session state\. To stop or finish an agent session, call `qdash_end_agent_session`/);
  assert.match(prompt, /A stopped conversation does not continue by itself/);
});

test("choices go through ask_user", () => {
  assert.match(buildSystemPrompt("auto", "en"), /call `ask_user` with 2-4 short options/);
});

test("listed skills point the model at read_skill", () => {
  const prompt = buildSystemPrompt("auto", "en", [
    { name: "qdash-one-qubit-calibration", description: "Calibrate single qubits." },
  ]);
  assert.match(prompt, /call `read_skill`/);
  assert.match(prompt, /- qdash-one-qubit-calibration: Calibrate single qubits\./);
  assert.doesNotMatch(buildSystemPrompt("auto", "en"), /read_skill/);
});

test("the tool guide is inlined after the guidelines", () => {
  const prompt = buildSystemPrompt("auto", "en", [], "- `qdash_list_chips` for chips");
  assert.match(prompt, /Tool guide:\n- `qdash_list_chips` for chips/);
  assert.doesNotMatch(buildSystemPrompt("auto", "en"), /Tool guide/);
});

test("local extension tools are introduced after the pi-qdash tool guide", () => {
  const guide = "- `qcal_evaluate`: Diagnose a calibration plot\n  - Use it for every figure.";
  const prompt = buildSystemPrompt("auto", "en", [], "qdash guide", guide);
  assert.match(prompt, /Tool guide:\nqdash guide\n\nAdditional tools:\n- `qcal_evaluate`/);
  assert.doesNotMatch(buildSystemPrompt("auto", "en", [], "qdash guide"), /Additional tools/);
});

import { buildUserInstructionsSection, MAX_USER_INSTRUCTIONS_CHARS } from "../src/prompt.ts";

test("user instructions become a section that cannot lift the approval rule", () => {
  const section = buildUserInstructionsSection("  Answer in Japanese.  ");
  assert.match(section, /Answer in Japanese\.$/);
  assert.match(section, /write operations still need the user's approval/);
  assert.equal(buildUserInstructionsSection("   "), undefined);
  assert.equal(buildUserInstructionsSection(undefined), undefined);
  const long = buildUserInstructionsSection("x".repeat(MAX_USER_INSTRUCTIONS_CHARS + 50));
  assert.ok(long.endsWith("x".repeat(MAX_USER_INSTRUCTIONS_CHARS)));
  assert.ok(!long.includes("x".repeat(MAX_USER_INSTRUCTIONS_CHARS + 1)));
});

test("a language in the user's preferences sets the reply language under auto", () => {
  assert.match(buildSystemPrompt("auto", "en"), /in a message or in their preferences below/);
  assert.match(buildUserInstructionsSection("Answer in Japanese."), /a language they name here is the reply language/);
});

test("code mode and deferred tools are explained when offered", async () => {
  const { CODEMODE_GUIDELINE, deferredToolsGuideline } = await import("../src/codemode.ts");
  const prompt = buildSystemPrompt("en", "en", [], "Tool list", null, false, null, null, {
    codemode: CODEMODE_GUIDELINE,
    deferredTools: deferredToolsGuideline(["qdash_list_cryostats", "qdash_list_cooldowns"]),
  });
  assert.match(prompt, /Use `codemode` when a question needs many read-only QDash calls/);
  assert.match(prompt, /Scripts can call only QDash's read-only tools/);
  assert.match(prompt, /call `tool_search` with the tool name/);
  assert.match(prompt, /Deferred tools: qdash_list_cooldowns, qdash_list_cryostats/);
  assert.equal(deferredToolsGuideline([]), null);
  // Tools the guide names are marked there, not listed twice.
  const marked = deferredToolsGuideline(["qdash_list_cryostats", "qdash_list_cooldowns"], new Set(["qdash_list_cryostats"]));
  assert.match(marked, /Tools marked \* in the tool guide are deferred/);
  assert.match(marked, /Other deferred tools: qdash_list_cooldowns$/);
  assert.doesNotMatch(marked, /qdash_list_cryostats/);
  assert.doesNotMatch(buildSystemPrompt("en", "en"), /codemode|tool_search/);
});

test("the investigation policy shared with pi CLI sits beside the runtime's own rules", async () => {
  const { investigationPolicyBullets } = await import("@oqtopus-team/pi-qdash/extensions/lib/qdash-guidance.ts");
  const prompt = buildSystemPrompt("auto", "en");
  const guidelines = prompt.slice(prompt.indexOf("Guidelines:\n"));
  for (const bullet of investigationPolicyBullets()) {
    assert.ok(guidelines.includes(`${bullet}\n`), `missing shared rule: ${bullet}`);
    assert.equal(prompt.split(bullet).length, 2, `shared rule appears more than once: ${bullet}`);
  }
  const { requestPolicyBullets } = await import("@oqtopus-team/pi-qdash/extensions/lib/qdash-guidance.ts");
  for (const bullet of requestPolicyBullets()) {
    assert.ok(guidelines.includes(`${bullet}\n`), `missing request rule: ${bullet}`);
    assert.equal(prompt.split(bullet).length, 2, `request rule appears more than once: ${bullet}`);
  }
  // Host-specific rules stay in the runtime prompt.
  assert.match(prompt, /`render_ui`/);
  assert.match(prompt, /approval card/);
  assert.match(prompt, /You have no filesystem or shell access\./);
});
