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

test("experimental write tools are approved by the user, not the model", () => {
  const prompt = buildSystemPrompt("auto", "en", true);
  assert.match(prompt, /approval card with the exact arguments/);
  assert.doesNotMatch(prompt, /confirmWrite/);
  assert.doesNotMatch(buildSystemPrompt("auto", "en"), /approval card/);
});

test("choices go through ask_user", () => {
  assert.match(buildSystemPrompt("auto", "en"), /call `ask_user` with 2-4 short options/);
});

test("listed skills point the model at read_skill", () => {
  const prompt = buildSystemPrompt("auto", "en", false, [
    { name: "qdash-calibration-agent", description: "Run agent calibration sessions." },
  ]);
  assert.match(prompt, /call `read_skill`/);
  assert.match(prompt, /- qdash-calibration-agent: Run agent calibration sessions\./);
  assert.doesNotMatch(buildSystemPrompt("auto", "en"), /read_skill/);
});

test("the tool guide is inlined after the guidelines", () => {
  const prompt = buildSystemPrompt("auto", "en", false, [], "- `qdash_list_chips` for chips");
  assert.match(prompt, /Tool guide:\n- `qdash_list_chips` for chips/);
  assert.doesNotMatch(buildSystemPrompt("auto", "en"), /Tool guide/);
});

test("local extension tools are introduced after the pi-qdash tool guide", () => {
  const guide = "- `qcal_evaluate`: Diagnose a calibration plot\n  - Use it for every figure.";
  const prompt = buildSystemPrompt("auto", "en", false, [], "qdash guide", guide);
  assert.match(prompt, /Tool guide:\nqdash guide\n\nAdditional tools:\n- `qcal_evaluate`/);
  assert.doesNotMatch(buildSystemPrompt("auto", "en", false, [], "qdash guide"), /Additional tools/);
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
