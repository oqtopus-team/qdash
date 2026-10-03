import assert from "node:assert/strict";
import { test } from "node:test";

import { encodeLine, toNdjsonEvents } from "../src/events.ts";

test("tool start becomes a tool_start line", () => {
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_start", toolName: "qdash_get_timeseries" }),
    [{ type: "tool_start", name: "qdash_get_timeseries" }],
  );
});

test("tool end becomes a tool_end line", () => {
  assert.deepEqual(
    toNdjsonEvents({
      type: "tool_execution_end",
      toolName: "qdash_get_timeseries",
      isError: false,
      result: { details: {} },
    }),
    [{ type: "tool_end", name: "qdash_get_timeseries", isError: false }],
  );
});

test("a chart in tool details is emitted before tool_end", () => {
  const chart = { data: [{ x: [1], y: [2] }], layout: { title: "T1" } };
  assert.deepEqual(
    toNdjsonEvents({
      type: "tool_execution_end",
      toolName: "render_chart",
      isError: false,
      result: { details: { chart } },
    }),
    [
      { type: "chart", chart },
      { type: "tool_end", name: "render_chart", isError: false },
    ],
  );
});

test("failed tools keep the error flag", () => {
  const [event] = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qdash_query",
    isError: true,
  });
  assert.equal(event.isError, true);
});

test("token deltas and other events are dropped", () => {
  assert.deepEqual(toNdjsonEvents({ type: "message_update" }), []);
  assert.deepEqual(toNdjsonEvents({ type: "agent_end" }), []);
});

test("lines are newline terminated json", () => {
  assert.equal(encodeLine({ type: "tool_start", name: "x" }), '{"type":"tool_start","name":"x"}\n');
});
