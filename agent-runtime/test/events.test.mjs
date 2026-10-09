import assert from "node:assert/strict";
import { test } from "node:test";

import { encodeLine, formatSettledDetail, toNdjsonEvents } from "../src/events.ts";

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

test("durable tool-result entries expose chart details and failures", () => {
  const events = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "render_chart",
    entry: {
      model: [
        {
          role: "toolResult",
          isError: true,
          details: { chart: { data: [{ y: [1] }], layout: { title: "T1" } } },
        },
      ],
    },
  });
  assert.equal(events[0].type, "chart");
  assert.deepEqual(events[0].chart.layout, { title: "T1" });
  assert.deepEqual(events[1], { type: "tool_end", name: "render_chart", isError: true });
});

test("tool start and end carry the call id and args when present", () => {
  assert.deepEqual(
    toNdjsonEvents({
      type: "tool_execution_start",
      toolName: "qdash_get_timeseries",
      toolCallId: "call_1",
      args: { qid: "0" },
    }),
    [{ type: "tool_start", name: "qdash_get_timeseries", id: "call_1", args: { qid: "0" } }],
  );
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_end", toolName: "qdash_query", toolCallId: "call_1" }),
    [{ type: "tool_end", name: "qdash_query", isError: false, id: "call_1" }],
  );
});

test("text and thinking deltas are forwarded in order", () => {
  assert.deepEqual(
    toNdjsonEvents({
      type: "message_update",
      changes: [
        { type: "thinking_start" },
        { type: "thinking_delta", delta: "Let me " },
        { type: "text_delta", delta: "T1 is " },
        { type: "toolcall_delta", delta: '{"q' },
        { type: "text_delta", delta: "" },
      ],
    }),
    [
      { type: "thinking_delta", delta: "Let me " },
      { type: "text_delta", delta: "T1 is " },
    ],
  );
});

test("ask and approval requests become their own lines", () => {
  const ask = { question: "Which qubit?", options: [{ label: "Q32" }, { label: "Q33" }] };
  const approval = { id: "call-1", tool: "qdash_execute_agent_action", label: "Execute", args: {} };
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_end", toolName: "ask_user", result: { details: { ask } } }),
    [
      { type: "ask", ask },
      { type: "tool_end", name: "ask_user", isError: false },
    ],
  );
  const [line] = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qdash_execute_agent_action",
    entry: { model: [{ role: "toolResult", details: { approval } }] },
  });
  assert.deepEqual(line, { type: "approval", approval });
});

test("unrelated events are dropped", () => {
  assert.deepEqual(toNdjsonEvents({ type: "message_update" }), []);
  assert.deepEqual(toNdjsonEvents({ type: "agent_end" }), []);
});

test("lines are newline terminated json", () => {
  assert.equal(encodeLine({ type: "tool_start", name: "x" }), '{"type":"tool_start","name":"x"}\n');
});

test("a ping line carries no content", () => {
  assert.equal(encodeLine({ type: "ping" }), '{"type":"ping"}\n');
});

test("figures a tool fetched travel with tool_end as paths", () => {
  const events = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qdash_get_task_figures",
    toolCallId: "c7",
    isError: false,
    result: {
      details: {
        tool: "qdash_get_task_figures",
        path: "exec/20261006-001/CheckRabi_0.png",
        mediaType: "image/png",
        base64: "AAAA",
        figurePaths: ["exec/20261006-001/CheckRabi_0.png", "exec/20261006-001/CheckRabi_1.png"],
      },
    },
  });
  assert.deepEqual(events, [
    {
      type: "tool_end",
      name: "qdash_get_task_figures",
      id: "c7",
      isError: false,
      figures: ["exec/20261006-001/CheckRabi_0.png", "exec/20261006-001/CheckRabi_1.png"],
    },
  ]);
  // A JSON figure is not an image; a tool without figures adds nothing.
  const json = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qdash_get_figure",
    isError: false,
    result: { details: { path: "a.json", mediaType: "application/json", figurePaths: [] } },
  });
  assert.equal("figures" in json[0], false);
});

test("formatSettledDetail appends the provider error text to an unanswered reason", () => {
  assert.equal(formatSettledDetail(undefined), "");
  assert.equal(formatSettledDetail(""), "");
  assert.equal(
    formatSettledDetail("400: tool choice requires --enable-auto-tool-choice"),
    ": 400: tool choice requires --enable-auto-tool-choice",
  );
  assert.equal(formatSettledDetail({ code: 400 }), ': {"code":400}');
});
