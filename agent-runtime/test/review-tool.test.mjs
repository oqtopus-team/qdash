import assert from "node:assert/strict";
import { test } from "node:test";

import { normalizeVerdict } from "../src/review-tool.ts";

test("a verdict already in the closed set is left alone", () => {
  const verdict = normalizeVerdict({
    decision: "PASS",
    human_label: "CORRECT",
    primary_reason: "Fit converged.",
  });
  assert.equal(verdict.decision, "PASS");
  assert.equal(verdict.human_label, "CORRECT");
  assert.equal(verdict.primary_reason, "Fit converged.");
});

test("case and separator near-misses are mapped onto the closed set", () => {
  const verdict = normalizeVerdict({
    decision: " pass-with-note ",
    human_label: "no signal",
  });
  assert.equal(verdict.decision, "PASS_WITH_NOTE");
  assert.equal(verdict.human_label, "NO_SIGNAL");
});

test("an unrecognised verdict falls back to human review, never to a pass", () => {
  const verdict = normalizeVerdict({ decision: "ACCEPTED", human_label: "fine" });
  assert.equal(verdict.decision, "REVIEW");
  assert.equal(verdict.human_label, "SUSPICIOUS");
});

test("missing fields fall back the same way", () => {
  const verdict = normalizeVerdict({});
  assert.equal(verdict.decision, "REVIEW");
  assert.equal(verdict.human_label, "SUSPICIOUS");
});
