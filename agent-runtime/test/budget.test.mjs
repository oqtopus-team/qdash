import assert from "node:assert/strict";
import { test } from "node:test";

import { ESTIMATE_UNDERCOUNT, compactionBudget } from "../src/budget.ts";

test("thresholds give out the provider's room divided by the estimate undercount", () => {
  // qwen in chat.yaml: 64k window, 16k output. A prompt pi estimated under its
  // threshold was counted at 53k tokens by vLLM and rejected with 16k output.
  const budget = compactionBudget(65_536, 16_384);
  const estimatedRoom = Math.floor((65_536 - 16_384) / ESTIMATE_UNDERCOUNT);
  assert.equal(budget.reserveTokens, 65_536 - estimatedRoom);
  assert.equal(budget.reserveTokens, 32_768);
  // Even undercounted by the factor, a prompt at the threshold fits with the output.
  assert.ok(estimatedRoom * ESTIMATE_UNDERCOUNT + 16_384 <= 65_536);
  assert.equal(budget.keepRecentTokens, 8_192);
  assert.equal(budget.backgroundTokens, 8_192);
});

test("small windows keep room for conversation", () => {
  // Ising in review.yaml: 16k window, 2k output.
  const budget = compactionBudget(16_384, 2_048);
  assert.equal(budget.reserveTokens, 16_384 - Math.floor(14_336 / ESTIMATE_UNDERCOUNT));
  assert.ok(budget.reserveTokens < 8_192);
  assert.equal(budget.keepRecentTokens, Math.floor(Math.floor(14_336 / ESTIMATE_UNDERCOUNT) / 4));
});

test("reserve never exceeds half the window and recent tokens never vanish", () => {
  const budget = compactionBudget(8_192, 8_192);
  assert.equal(budget.reserveTokens, 4_096);
  assert.equal(budget.keepRecentTokens, 1_024);
});

test("large windows keep Pi's defaults for recent and background tokens", () => {
  const budget = compactionBudget(200_000, 8_192);
  assert.equal(budget.keepRecentTokens, 20_000);
  assert.equal(budget.backgroundTokens, 31_968);
});
