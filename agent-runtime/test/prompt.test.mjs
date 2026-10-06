import assert from "node:assert/strict";
import { test } from "node:test";

import { buildReviewSystemPrompt, buildSystemPrompt } from "../src/prompt.ts";

test("Japanese language codes become an explicit user-facing instruction", () => {
  const prompt = buildSystemPrompt("ja", "en");
  assert.match(prompt, /Reason internally in English/);
  assert.match(prompt, /entire reply.*Japanese \(日本語\)/);
});

test("review free-text fields use the configured natural language", () => {
  assert.match(buildReviewSystemPrompt("ja"), /free-text field.*Japanese \(日本語\)/);
});

test("automatic language follows the latest user message", () => {
  assert.match(buildSystemPrompt("auto", "en"), /same language as the user's latest message/);
  assert.match(buildReviewSystemPrompt("auto"), /language used by the review request/);
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
