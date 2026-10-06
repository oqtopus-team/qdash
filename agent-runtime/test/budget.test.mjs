import assert from "node:assert/strict";
import { test } from "node:test";

import { compactionBudget } from "../src/budget.ts";

test("reserve covers the output tokens plus a margin", () => {
  // qwen in chat.yaml: 64k window, 16k output. Pi's default reserve of 16k let
  // a 49k-token prompt plus 16k output overflow the window.
  const budget = compactionBudget(65_536, 16_384);
  assert.equal(budget.reserveTokens, 16_384 + 6_554);
  assert.ok(65_536 - budget.reserveTokens + 16_384 < 65_536);
});

test("small windows keep room for conversation", () => {
  // gemma in chat.yaml: 16k window, 4k output.
  const budget = compactionBudget(16_384, 4_096);
  assert.equal(budget.reserveTokens, 4_096 + 2_048);
  assert.equal(budget.keepRecentTokens, 4_096);
  assert.equal(budget.backgroundTokens, 4_096);
});

test("reserve never exceeds half the window", () => {
  assert.equal(compactionBudget(8_192, 8_192).reserveTokens, 4_096);
});

test("large windows keep Pi's defaults for recent and background tokens", () => {
  const budget = compactionBudget(200_000, 8_192);
  assert.equal(budget.keepRecentTokens, 20_000);
  assert.equal(budget.backgroundTokens, 32_768);
});
