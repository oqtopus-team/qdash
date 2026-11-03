import { MAX_TOOL_OUTPUT_CHARS } from "../src/events.ts";
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

test("tool results may have non-object JSON details", () => {
  for (const details of [null, "text", 42, false, []]) {
    assert.deepEqual(
      toNdjsonEvents({ type: "tool_execution_end", toolName: "qdash_query", result: { details } }),
      [{ type: "tool_end", name: "qdash_query", isError: false }],
    );
  }
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

test("an evaluation tool's prompt and model travel with tool_end", () => {
  const details = {
    prompt: "Reference for this experiment:\n## Experiment: CheckRabi",
    model: {
      provider: "openai-compatible-evaluation",
      modelId: "nvidia/Ising-Calibration-1.5-31B-NVFP4",
    },
    diagnosis: { success: true },
  };
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_end", toolName: "qcal_evaluate", result: { details } }),
    [
      {
        type: "tool_end",
        name: "qcal_evaluate",
        evaluation: {
          prompt: details.prompt,
          model: "openai-compatible-evaluation/nvidia/Ising-Calibration-1.5-31B-NVFP4",
        },
        isError: false,
      },
    ],
  );
  // A fallback judge is flagged; details without a prompt add nothing.
  const [withFallback] = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qcal_evaluate",
    result: { details: { prompt: "p", fallback: true } },
  });
  assert.deepEqual(withFallback.evaluation, { prompt: "p", fallback: true });
  const [plain] = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qdash_query",
    result: { details: { model: { provider: "a", modelId: "b" } } },
  });
  assert.equal("evaluation" in plain, false);
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

test("a stamped evaluation result also carries the record the API stores", () => {
  const [end] = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "qcal_evaluate",
    toolCallId: "c1",
    isError: false,
    result: {
      details: {
        prompt: "p",
        model: { provider: "openai-compatible-evaluation", modelId: "ising" },
        diagnosis: { success: true },
        host: { context: "ctx", task_name: "CheckRabi", figures: [], knowledge: null, task_id: "task-7", duration_ms: 12 },
      },
    },
  });
  assert.equal(end.evaluation.model, "openai-compatible-evaluation/ising");
  assert.equal(end.evaluation.record.task_id, "task-7");
  assert.equal(end.evaluation.record.mode, "planner");
  assert.deepEqual(end.evaluation.record.evaluation.diagnosis, { success: true });
  assert.equal(end.evaluation.record.evaluation.duration_ms, 12);
});

test("a workspace tool's answer travels with tool_end; a QDash tool's does not", () => {
  assert.deepEqual(
    toNdjsonEvents({
      type: "tool_execution_end",
      toolName: "bash",
      isError: true,
      result: { structuredOutput: { output: "ls: no such file\n", truncated: false, exitCode: 2 } },
    }),
    [{ type: "tool_end", name: "bash", output: "ls: no such file", exitCode: 2, isError: true }],
  );
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_end", toolName: "write", result: { structuredOutput: "Wrote 12 bytes to data.csv" } }),
    [{ type: "tool_end", name: "write", output: "Wrote 12 bytes to data.csv", isError: false }],
  );
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_end", toolName: "qdash_query", result: { structuredOutput: "secret-ish payload" } }),
    [{ type: "tool_end", name: "qdash_query", isError: false }],
  );
  // Without a structured output (a result the harness wrote), the entry's text is used.
  assert.deepEqual(
    toNdjsonEvents({
      type: "tool_execution_end",
      toolName: "edit",
      isError: true,
      entry: { model: [{ role: "toolResult", isError: true, content: [{ type: "text", text: "interrupted" }] }] },
    }),
    [{ type: "tool_end", name: "edit", output: "interrupted", isError: true }],
  );
});

test("a long answer keeps its tail", () => {
  const long = "x".repeat(MAX_TOOL_OUTPUT_CHARS) + "TAIL";
  const [event] = toNdjsonEvents({ type: "tool_execution_end", toolName: "read", result: { structuredOutput: long } });
  assert.equal(event.output.length, MAX_TOOL_OUTPUT_CHARS + 1);
  assert.ok(event.output.startsWith("…") && event.output.endsWith("TAIL"));
});

test("a tool call being written streams as a draft and argument deltas", () => {
  assert.deepEqual(
    toNdjsonEvents({
      type: "message_update",
      changes: [
        { type: "toolcall_start", contentIndex: 1, block: { type: "toolCall", id: "call_1", name: "write", arguments: {} } },
        { type: "toolcall_delta", contentIndex: 1, path: ["path"], delta: "fit.py" },
        { type: "toolcall_delta", contentIndex: 1, path: ["content"], delta: "import numpy" },
        { type: "toolcall_delta", contentIndex: 1, path: ["content"], delta: "" },
        { type: "text_delta", contentIndex: 0, delta: "Now " },
      ],
    }),
    [
      { type: "tool_draft", name: "write", index: 1, id: "call_1" },
      { type: "tool_args_delta", index: 1, path: ["path"], delta: "fit.py" },
      { type: "tool_args_delta", index: 1, path: ["content"], delta: "import numpy" },
      { type: "text_delta", delta: "Now " },
    ],
  );
});

test("a proposed edit is emitted before tool_end", () => {
  const edit = { summary: "Add T2", code: "new", flowName: "t1" };
  assert.deepEqual(
    toNdjsonEvents({ type: "tool_execution_end", toolName: "propose_code_edit", result: { details: { edit } } }),
    [
      { type: "edit", edit },
      { type: "tool_end", name: "propose_code_edit", isError: false },
    ],
  );
});
