import assert from "node:assert/strict";
import { test } from "node:test";

import { logDurableReport } from "../src/durable-report.ts";

test("durable failure logs task state without recording error payloads or user identifiers", () => {
  const lines = [];
  const original = console.error;
  console.error = (line) => lines.push(line);
  try {
    logDurableReport("hashed-session.sqlite", new Error("secret prompt and bearer token"), {
      type: "task_parked",
      task: { id: 17, kind: "generation", conversationId: 1 },
      extension: "qdash-copilot",
    });
  } finally {
    console.error = original;
  }

  assert.equal(lines.length, 1);
  assert.match(lines[0], /"type":"task_parked"/);
  assert.match(lines[0], /"task":"generation"/);
  assert.match(lines[0], /"taskId":17/);
  assert.match(lines[0], /"errorType":"Error"/);
  assert.doesNotMatch(lines[0], /secret prompt|bearer token/);
});
