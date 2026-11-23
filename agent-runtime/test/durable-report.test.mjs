import assert from "node:assert/strict";
import { test } from "node:test";

import { logDurableReport } from "../src/durable-report.ts";

function capture(fn) {
  const lines = [];
  const original = console.error;
  console.error = (line) => lines.push(line);
  try {
    fn();
  } finally {
    console.error = original;
  }
  return lines;
}

test("durable failure logs task state without recording error payloads or user identifiers", () => {
  const lines = capture(() =>
    logDurableReport("hashed-session.sqlite", {
      kind: "task_interrupted",
      reason: "restart_limit",
      restarts: 3,
      task: { id: 17, kind: "generation", conversationId: 1 },
      extension: "qdash-copilot",
      error: new Error("secret prompt and bearer token"),
    }),
  );

  assert.equal(lines.length, 1);
  assert.match(lines[0], /"type":"task_interrupted"/);
  assert.match(lines[0], /"task":"generation"/);
  assert.match(lines[0], /"taskId":17/);
  assert.match(lines[0], /"reason":"restart_limit"/);
  assert.match(lines[0], /"restarts":3/);
  assert.match(lines[0], /"errorType":"Error"/);
  assert.doesNotMatch(lines[0], /secret prompt|bearer token/);
});

test("durable storage failure logs only its kind and error type", () => {
  const lines = capture(() =>
    logDurableReport("hashed-session.sqlite", { kind: "storage_failed", error: "disk full" }),
  );

  assert.equal(lines.length, 1);
  const payload = JSON.parse(lines[0].replace("[agent-runtime] durable report ", ""));
  assert.deepEqual(payload, {
    type: "storage_failed",
    session: "hashed-session.sqlite",
    errorType: "string",
  });
});
