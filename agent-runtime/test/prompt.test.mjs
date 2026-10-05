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

test("experimental write tools require explicit per-operation approval", () => {
  const prompt = buildSystemPrompt("auto", "en", true);
  assert.match(prompt, /state the exact action and target/);
  assert.match(prompt, /confirmWrite: true/);
  assert.doesNotMatch(buildSystemPrompt("auto", "en"), /confirmWrite/);
});
