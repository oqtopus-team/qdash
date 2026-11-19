import assert from "node:assert/strict";
import { test } from "node:test";

import {
  callMessage,
  clampMemoryMb,
  clampTimeoutSeconds,
  LineSplitter,
  parseAnswer,
  parseMetricRequest,
  REQUEST_MAX_BYTES,
  resultMessage,
  SOURCE_MAX_BYTES,
} from "../exec/metric-protocol.ts";
import { metricRunnerOptionsFromEnv } from "../exec/metric-runner.ts";

const limits = { maxTimeoutSeconds: 300, maxMemoryMb: 2048 };
const catalog = { v: 1, mode: "catalog", source: "x = 1\n", timeout_seconds: 60, memory_mb: 1024 };
const evaluate = {
  ...catalog,
  mode: "evaluate",
  metric_id: "m",
  chip_id: "chip-1",
  start: "2026-11-01T00:00:00+00:00",
  end: "2026-11-20T00:00:00+00:00",
  params: { min_samples: 3 },
};

test("a catalog request becomes the worker's request line without the version", () => {
  assert.deepEqual(parseMetricRequest(JSON.stringify(catalog), limits), {
    request: { mode: "catalog", source: "x = 1\n", memory_mb: 1024, timeout_seconds: 60 },
  });
  // Evaluate-only fields are not forwarded for a catalog.
  const extra = parseMetricRequest(JSON.stringify({ ...catalog, chip_id: "chip-1" }), limits);
  assert.deepEqual(Object.keys(extra.request).sort(), ["memory_mb", "mode", "source", "timeout_seconds"]);
});

test("an evaluate request carries the metric, chip, period and parameters", () => {
  const { request } = parseMetricRequest(JSON.stringify(evaluate), limits);
  assert.deepEqual(request, {
    mode: "evaluate",
    source: "x = 1\n",
    memory_mb: 1024,
    timeout_seconds: 60,
    metric_id: "m",
    chip_id: "chip-1",
    start: evaluate.start,
    end: evaluate.end,
    params: { min_samples: 3 },
  });
});

test("limits are clamped to the runner's bounds", () => {
  const low = parseMetricRequest(JSON.stringify({ ...catalog, timeout_seconds: 0, memory_mb: 1 }), limits).request;
  assert.equal(low.timeout_seconds, 1);
  assert.equal(low.memory_mb, 128);
  const high = parseMetricRequest(JSON.stringify({ ...catalog, timeout_seconds: 1e9, memory_mb: 1e9 }), limits).request;
  assert.equal(high.timeout_seconds, 300);
  assert.equal(high.memory_mb, 2048);
  assert.equal(clampTimeoutSeconds(1.5, 300), 1.5);
  assert.equal(clampMemoryMb(512.9, 2048), 512);
  assert.equal(clampTimeoutSeconds(10, 0), 1);
});

test("malformed requests are refused with a reason", () => {
  const { metric_id: _m, ...noMetric } = evaluate;
  for (const bad of [
    "not json",
    "[]",
    "null",
    JSON.stringify({ ...catalog, v: 2 }),
    JSON.stringify({ ...catalog, v: "1" }),
    JSON.stringify({ ...catalog, mode: "exec" }),
    JSON.stringify({ ...catalog, source: 1 }),
    JSON.stringify({ v: 1, mode: "catalog", timeout_seconds: 60, memory_mb: 1024 }),
    JSON.stringify({ ...catalog, timeout_seconds: "60" }),
    JSON.stringify({ ...catalog, memory_mb: null }),
    JSON.stringify({ ...catalog, owner: "alice" }),
    JSON.stringify({ ...catalog, source: "x".repeat(SOURCE_MAX_BYTES + 1) }),
    JSON.stringify(noMetric),
    JSON.stringify({ ...evaluate, chip_id: "" }),
    JSON.stringify({ ...evaluate, start: 5 }),
    JSON.stringify({ ...evaluate, params: [] }),
    JSON.stringify({ ...evaluate, params: undefined }),
    `{"pad": "${"x".repeat(REQUEST_MAX_BYTES)}"}`,
  ]) {
    const parsed = parseMetricRequest(bad, limits);
    assert.ok("error" in parsed, bad.slice(0, 80));
    assert.equal(typeof parsed.error, "string");
  }
});

test("answers are forwarded without their type; anything else is refused", () => {
  assert.deepEqual(parseAnswer(JSON.stringify({ type: "answer", ok: true, data: { a: 1 } })), { ok: true, data: { a: 1 } });
  assert.deepEqual(parseAnswer(JSON.stringify({ type: "answer", ok: true })), { ok: true, data: null });
  assert.deepEqual(parseAnswer(JSON.stringify({ type: "answer", ok: false, error: "no" })), { ok: false, error: "no" });
  for (const bad of [
    "nope",
    JSON.stringify({ ok: true, data: 1 }),
    JSON.stringify({ type: "call", ok: true }),
    JSON.stringify({ type: "answer", ok: false }),
    JSON.stringify({ type: "answer", ok: "yes" }),
  ]) {
    assert.equal(parseAnswer(bad), undefined, bad);
  }
});

test("worker calls and results become runner messages", () => {
  assert.deepEqual(callMessage('{"op": "latest", "args": {"kind": "qubit"}}'), {
    type: "call",
    op: "latest",
    args: { kind: "qubit" },
  });
  assert.deepEqual(callMessage("garbage"), { type: "call", op: "", args: {} });
  assert.deepEqual(callMessage('{"op": 1, "args": []}'), { type: "call", op: "", args: {} });
  assert.deepEqual(resultMessage('{"ok": true, "result": {}, "type": "call"}'), {
    ok: true,
    result: {},
    type: "result",
  });
  assert.equal(resultMessage("[1]"), undefined);
  assert.equal(resultMessage("{"), undefined);
});

test("the line splitter joins chunks and stops at an oversized line", () => {
  const lines = [];
  let overflowed = 0;
  const splitter = new LineSplitter(8, (line) => lines.push(line.toString()), () => overflowed++);
  splitter.push(Buffer.from("ab"));
  splitter.push(Buffer.from("c\nde"));
  splitter.push(Buffer.from("f\n\nxy"));
  assert.deepEqual(lines, ["abc", "def", ""]);
  splitter.push(Buffer.from("123456789"));
  assert.equal(overflowed, 1);
  splitter.push(Buffer.from("\nok\n"));
  assert.deepEqual(lines, ["abc", "def", ""]);
  assert.equal(overflowed, 1);

  const raised = [];
  const late = new LineSplitter(4, (line) => raised.push(line.toString()), () => raised.push("overflow"));
  late.push(Buffer.from("1234\n12345\n"));
  assert.deepEqual(raised, ["1234", "overflow"]);
});

test("runner options come from the environment, and a blank socket disables the runner", () => {
  const defaults = metricRunnerOptionsFromEnv({}, true);
  assert.deepEqual(defaults, {
    socketPath: "/run/agent-exec/metric.sock",
    socketGid: 0,
    isolateUsers: true,
    python: "python3",
    pythonPath: "/app/metric-runtime",
    jobRoot: "/tmp/metric-jobs",
    concurrency: 2,
    queueLimit: 16,
    queueWaitSeconds: 5,
    maxTimeoutSeconds: 300,
    maxMemoryMb: 2048,
  });
  assert.equal(metricRunnerOptionsFromEnv({ AGENT_EXEC_METRIC_SOCKET: " " }, true), undefined);
  const custom = metricRunnerOptionsFromEnv(
    { AGENT_EXEC_METRIC_CONCURRENCY: "4", AGENT_EXEC_METRIC_QUEUE_WAIT_SECONDS: "0.5", AGENT_EXEC_METRIC_PYTHON: "" },
    false,
  );
  assert.equal(custom.concurrency, 4);
  assert.equal(custom.queueWaitSeconds, 0.5);
  assert.equal(custom.python, "python3");
  assert.throws(() => metricRunnerOptionsFromEnv({ AGENT_EXEC_METRIC_CONCURRENCY: "0" }, true), /CONCURRENCY/);
  assert.throws(() => metricRunnerOptionsFromEnv({ AGENT_EXEC_METRIC_QUEUE_LIMIT: "-1" }, true), /QUEUE_LIMIT/);
  assert.throws(() => metricRunnerOptionsFromEnv({ AGENT_EXEC_METRIC_MAX_MEMORY_MB: "64" }, true), /MAX_MEMORY_MB/);
});
