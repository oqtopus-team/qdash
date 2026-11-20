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
} from "../metric-runner/protocol.ts";
import {
  memoryBudget,
  metricRunnerOptionsFromEnv,
  parseCgroupMemoryLimit,
  parseTmpfsSizeMb,
  SUPERVISOR_RSS_MB,
  WORKER_BASELINE_RSS_MB,
} from "../metric-runner/runner.ts";

const limits = { maxTimeoutSeconds: 300, maxMemoryMb: 2048 };
const catalog = { v: 2, mode: "catalog", source: "x = 1\n", timeout_seconds: 60, memory_mb: 1024 };
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
    JSON.stringify({ ...catalog, v: 1 }),
    JSON.stringify({ ...catalog, v: "1" }),
    JSON.stringify({ ...catalog, mode: "exec" }),
    JSON.stringify({ ...catalog, source: 1 }),
    JSON.stringify({ v: 2, mode: "catalog", timeout_seconds: 60, memory_mb: 1024 }),
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

test("runner options come from the METRIC_RUNNER_* environment", () => {
  const defaults = metricRunnerOptionsFromEnv({}, true);
  assert.deepEqual(defaults, {
    socketPath: "/run/metric-runner/metric.sock",
    socketGid: 0,
    isolateUsers: true,
    python: "python3",
    pythonPath: "/app/metric-runtime",
    jobRoot: "/tmp/metric-jobs",
    concurrency: 2,
    queueLimit: 16,
    queueWaitSeconds: 5,
    maxTimeoutSeconds: 300,
    maxMemoryMb: 1024,
  });
  // A blank socket path means the default; the runner always listens.
  assert.equal(metricRunnerOptionsFromEnv({ METRIC_RUNNER_SOCKET: " " }, true).socketPath, "/run/metric-runner/metric.sock");
  assert.equal(metricRunnerOptionsFromEnv({}, false).isolateUsers, false);
  assert.equal(metricRunnerOptionsFromEnv({ METRIC_RUNNER_ISOLATE_USERS: "false" }, true).isolateUsers, false);
  assert.equal(metricRunnerOptionsFromEnv({ METRIC_RUNNER_ISOLATE_USERS: "1" }, false).isolateUsers, true);
  const custom = metricRunnerOptionsFromEnv(
    {
      METRIC_RUNNER_SOCKET: "/tmp/m.sock",
      METRIC_RUNNER_CONCURRENCY: "4",
      METRIC_RUNNER_QUEUE_WAIT_SECONDS: "0.5",
      METRIC_RUNNER_PYTHON: "",
      METRIC_RUNNER_MAX_MEMORY_MB: "512",
    },
    false,
  );
  assert.equal(custom.socketPath, "/tmp/m.sock");
  assert.equal(custom.concurrency, 4);
  assert.equal(custom.queueWaitSeconds, 0.5);
  assert.equal(custom.python, "python3");
  assert.equal(custom.maxMemoryMb, 512);
  // The old agent-exec names are not read any more.
  assert.equal(metricRunnerOptionsFromEnv({ AGENT_EXEC_METRIC_CONCURRENCY: "7" }, true).concurrency, 2);
  assert.throws(() => metricRunnerOptionsFromEnv({ METRIC_RUNNER_CONCURRENCY: "0" }, true), /CONCURRENCY/);
  assert.throws(() => metricRunnerOptionsFromEnv({ METRIC_RUNNER_QUEUE_LIMIT: "-1" }, true), /QUEUE_LIMIT/);
  assert.throws(() => metricRunnerOptionsFromEnv({ METRIC_RUNNER_MAX_MEMORY_MB: "64" }, true), /MAX_MEMORY_MB/);
  assert.throws(() => metricRunnerOptionsFromEnv({ METRIC_RUNNER_ISOLATE_USERS: "maybe" }, true), /ISOLATE_USERS/);
});

test("the memory budget compares every slot's worst case with the container limit", () => {
  const fits = memoryBudget({ concurrency: 2, maxMemoryMb: 1024, limitMb: 3072, tmpfsMb: 256, workerBaselineMb: 128, supervisorMb: 128 });
  assert.equal(fits.requiredMb, 2 * (1024 + 128) + 128 + 256);
  assert.equal(fits.fits, true);
  assert.match(fits.message, /2 jobs x \(1024 MiB script \+ 128 MiB worker baseline\) \+ 128 MiB supervisor \+ 256 MiB \/tmp = 2688 MiB of a 3072 MiB/);

  const tight = memoryBudget({ concurrency: 2, maxMemoryMb: 2048, limitMb: 2048, tmpfsMb: 0 });
  assert.equal(tight.fits, false);
  assert.equal(tight.requiredMb, 2 * (2048 + WORKER_BASELINE_RSS_MB) + SUPERVISOR_RSS_MB);
  assert.match(tight.message, /exceeds the 2048 MiB container limit/);
  assert.match(tight.message, /METRIC_RUNNER_CONCURRENCY/);

  const unknown = memoryBudget({ concurrency: 1, maxMemoryMb: 128, limitMb: undefined, tmpfsMb: 0 });
  assert.equal(unknown.fits, undefined);
  assert.match(unknown.message, /container limit unknown/);
});

test("cgroup limits and tmpfs sizes parse, and 'no limit' is unknown", () => {
  assert.equal(parseCgroupMemoryLimit("3221225472\n"), 3072);
  assert.equal(parseCgroupMemoryLimit("max\n"), undefined);
  assert.equal(parseCgroupMemoryLimit("9223372036854771712\n"), undefined);
  assert.equal(parseCgroupMemoryLimit(""), undefined);
  const mounts = [
    "overlay / overlay ro,relatime 0 0",
    "tmpfs /dev tmpfs rw,nosuid,size=65536k,mode=755 0 0",
    "tmpfs /tmp tmpfs rw,nosuid,nodev,noexec,relatime,size=262144k 0 0",
  ].join("\n");
  assert.equal(parseTmpfsSizeMb(mounts), 256);
  assert.equal(parseTmpfsSizeMb(mounts, "/dev"), 64);
  assert.equal(parseTmpfsSizeMb("tmpfs /tmp tmpfs rw,size=1g 0 0"), 1024);
  assert.equal(parseTmpfsSizeMb("tmpfs /tmp tmpfs rw,relatime 0 0"), undefined);
  assert.equal(parseTmpfsSizeMb("overlay / overlay ro 0 0"), undefined);
});
