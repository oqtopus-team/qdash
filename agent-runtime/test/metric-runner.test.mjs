import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { mkdtemp, readdir, rm, stat } from "node:fs/promises";
import { connect } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { startMetricRunner } from "../metric-runner/runner.ts";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const python = process.env.METRIC_RUNNER_TEST_PYTHON || join(repo, ".venv", "bin", "python");
const pythonPath = join(repo, "src");
const canRunWorker =
  existsSync(python) &&
  spawnSync(python, ["-c", "import numpy, scipy, pint"], { env: { PYTHONPATH: pythonPath }, timeout: 30_000 }).status === 0;
// The worker tests need an interpreter with the metric SDK's dependencies.
const live = canRunWorker ? test : test.skip;

/** A runner on a private socket and job root; never isolates (tests are not root). */
async function startRunner(t, overrides = {}) {
  const root = await mkdtemp(join(tmpdir(), "metric-runner-"));
  const logs = [];
  const runner = await startMetricRunner({
    socketPath: join(root, "run", "metric.sock"),
    isolateUsers: false,
    python,
    pythonPath,
    jobRoot: join(root, "jobs"),
    log: (message) => logs.push(message),
    ...overrides,
  });
  t.after(async () => {
    await runner.close();
    await rm(root, { recursive: true, force: true });
  });
  return { root, logs, socketPath: runner.socketPath, jobRoot: join(root, "jobs") };
}

/** One API-side connection: send lines, await messages in order. */
function client(socketPath) {
  const socket = connect({ path: socketPath });
  const messages = [];
  const waiters = [];
  let buffered = "";
  let closed = false;
  const flush = () => {
    while (waiters.length > 0 && (messages.length > 0 || closed)) {
      waiters.shift()(messages.length > 0 ? messages.shift() : undefined);
    }
  };
  socket.on("data", (chunk) => {
    buffered += chunk.toString("utf8");
    let newline;
    while ((newline = buffered.indexOf("\n")) !== -1) {
      messages.push(JSON.parse(buffered.slice(0, newline)));
      buffered = buffered.slice(newline + 1);
    }
    flush();
  });
  const ended = new Promise((resolve) => {
    socket.on("close", () => {
      closed = true;
      flush();
      resolve();
    });
  });
  socket.on("error", () => {});
  return {
    socket,
    ended,
    send: (value) => socket.write(`${typeof value === "string" ? value : JSON.stringify(value)}\n`),
    /** The next message, or `undefined` once the runner closed the connection. */
    next: () => new Promise((resolve) => {
      waiters.push(resolve);
      flush();
    }),
  };
}

const request = (source, extra = {}) => ({ v: 1, mode: "catalog", source, timeout_seconds: 10, memory_mb: 1024, ...extra });

const TINY = `from qdash_metrics import metric


@metric(title="Tiny", unit="GHz")
def tiny(target, ctx):
    return 1.0
`;

const FREQUENCY = `from qdash_metrics import metric


@metric(title="Frequency", unit="GHz")
def frequency(target, ctx):
    return ctx.data["qubit_frequency"][target].latest()
`;

const LOOP = `while True:
    pass
`;

const PRINTER = `from qdash_metrics import metric

print("x" * 100000)


@metric(title="Printer", unit="GHz")
def printer(target, ctx):
    return 1.0
`;

/** The worker pid of a job, from the runner's log. */
function pidOf(logs, jobId) {
  const line = logs.find((text) => text.startsWith(`job ${jobId} started`));
  const match = line && /pid (\d+)/.exec(line);
  assert.ok(match, `no start log for ${jobId}: ${logs.join("\n")}`);
  return Number(match[1]);
}

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function eventually(condition, ms = 2000) {
  const deadline = Date.now() + ms;
  while (!condition()) {
    if (Date.now() > deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return true;
}

async function waitForStart(logs, jobId) {
  assert.ok(await eventually(() => logs.some((text) => text.startsWith(`job ${jobId} started`))));
  return pidOf(logs, jobId);
}

test("malformed requests get invalid_request and the connection closes", async (t) => {
  const { socketPath, logs } = await startRunner(t);
  for (const line of [
    "not json",
    JSON.stringify({ ...request(TINY), v: 2 }),
    JSON.stringify({ ...request(TINY), mode: "shell" }),
    JSON.stringify({ v: 1, mode: "catalog", timeout_seconds: 10, memory_mb: 1024 }),
  ]) {
    const api = client(socketPath);
    api.send(line);
    const message = await api.next();
    assert.equal(message.type, "error", line);
    assert.equal(message.code, "invalid_request");
    assert.equal(await api.next(), undefined);
  }
  // A request line longer than 1 MiB is refused before its newline arrives.
  const api = client(socketPath);
  api.socket.write("x".repeat(1024 * 1024 + 10));
  assert.deepEqual(await api.next(), { type: "error", code: "invalid_request", message: "Request line is too long" });
  await api.ended;
  assert.equal(logs.filter((text) => text.startsWith("refused")).length, 4);
});

test("a connection that sends no request in time is closed", async (t) => {
  const { socketPath } = await startRunner(t, { requestWaitMs: 100 });
  const api = client(socketPath);
  const message = await api.next();
  assert.equal(message.code, "invalid_request");
  await api.ended;
});

test("the socket admits only its owner and group", async (t) => {
  const { socketPath } = await startRunner(t);
  assert.equal((await stat(socketPath)).mode & 0o777, 0o660);
});

live("catalog compiles a script and returns its metric metadata", async (t) => {
  const { socketPath, jobRoot, logs } = await startRunner(t);
  const api = client(socketPath);
  api.send(request(TINY));
  const accepted = await api.next();
  assert.equal(accepted.type, "accepted");
  assert.match(accepted.job_id, /^[0-9a-f]{16}$/);
  const result = await api.next();
  assert.equal(result.type, "result");
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.deepEqual(result.result.metrics.map((metric) => metric.id), ["tiny"]);
  assert.equal(result.log_truncated, false);
  assert.equal(await api.next(), undefined);
  assert.ok(await eventually(() => logs.some((text) => text.startsWith(`job ${accepted.job_id} cleaned up`))));
  assert.deepEqual(await readdir(jobRoot), []);
  // Neither the source nor broker data reach the log.
  assert.ok(!logs.some((text) => text.includes("qdash_metrics")));
});

live("evaluate relays the worker's data requests to the API in order", async (t) => {
  const { socketPath } = await startRunner(t);
  const api = client(socketPath);
  api.send(
    request(FREQUENCY, {
      mode: "evaluate",
      metric_id: "frequency",
      chip_id: "chip-1",
      start: "2026-11-06T00:00:00+00:00",
      end: "2026-11-20T00:00:00+00:00",
      params: {},
    }),
  );
  assert.equal((await api.next()).type, "accepted");
  const answers = {
    topology: { qubits: { 0: { row: 0, col: 0 }, 1: { row: 0, col: 1 } }, couplings: [[0, 1]], muxes: {} },
    metrics_config: {
      qubit_metrics: { qubit_frequency: { title: "Qubit Frequency", unit: "GHz", scale: 1, description: "" } },
      coupling_metrics: {},
    },
    latest: { 0: { value: 7.25, task_id: "task-0", execution_id: "exec-1" } },
  };
  const calls = [];
  let message;
  while ((message = await api.next()).type === "call") {
    calls.push(message);
    api.send({ type: "answer", ok: true, data: answers[message.op] });
  }
  assert.deepEqual(calls, [
    { type: "call", op: "topology", args: {} },
    { type: "call", op: "metrics_config", args: {} },
    { type: "call", op: "latest", args: { kind: "qubit", metric: "qubit_frequency" } },
  ]);
  assert.equal(message.type, "result");
  assert.equal(message.ok, true, JSON.stringify(message));
  const cells = Object.fromEntries(message.result.cells.map((cell) => [cell.key, cell]));
  assert.equal(cells["0"].status, "ok");
  assert.equal(cells["0"].value, 7.25);
  assert.equal(cells["0"].references[0].task_id, "task-0");
  assert.equal(cells["1"].status, "missing");
});

live("a broker error answer reaches the script and a stray line is a protocol failure", async (t) => {
  const { socketPath } = await startRunner(t);
  const evaluate = request(FREQUENCY, {
    mode: "evaluate",
    metric_id: "frequency",
    chip_id: "chip-1",
    start: "2026-11-06T00:00:00+00:00",
    end: "2026-11-20T00:00:00+00:00",
    params: {},
  });
  const refused = client(socketPath);
  refused.send(evaluate);
  assert.equal((await refused.next()).type, "accepted");
  assert.equal((await refused.next()).op, "topology");
  refused.send({ type: "answer", ok: false, error: "Chip has no topology" });
  const result = await refused.next();
  assert.equal(result.type, "result");
  assert.equal(result.ok, false);
  assert.match(result.error, /Chip has no topology/);

  const stray = client(socketPath);
  stray.send(evaluate);
  assert.equal((await stray.next()).type, "accepted");
  assert.equal((await stray.next()).op, "topology");
  stray.send({ type: "bogus" });
  const failed = await stray.next();
  assert.equal(failed.type, "failed");
  assert.equal(failed.code, "protocol");
  assert.equal(await stray.next(), undefined);
});

live("a full queue refuses a job while another holds the only slot", async (t) => {
  const { socketPath, logs } = await startRunner(t, { concurrency: 1, queueLimit: 0 });
  const slow = client(socketPath);
  slow.send(request(LOOP, { timeout_seconds: 30 }));
  const accepted = await slow.next();
  assert.equal(accepted.type, "accepted");
  const pid = await waitForStart(logs, accepted.job_id);

  const refused = client(socketPath);
  refused.send(request(TINY));
  assert.equal((await refused.next()).code, "queue_full");
  assert.equal(await refused.next(), undefined);

  slow.socket.destroy();
  assert.ok(await eventually(() => !alive(pid)), "the slow job's worker survived its client");
  // The slot frees once cleanup ends; a queued job would get it next.
  assert.ok(await eventually(() => logs.some((text) => text.startsWith(`job ${accepted.job_id} cleaned up`))));
  const next = client(socketPath);
  next.send(request(TINY));
  assert.equal((await next.next()).type, "accepted");
  assert.equal((await next.next()).ok, true);
});

live("a waiting job gets the slot when the running one ends", async (t) => {
  const { socketPath } = await startRunner(t, { concurrency: 1, queueLimit: 1, queueWaitSeconds: 4 });
  const first = client(socketPath);
  const second = client(socketPath);
  first.send(request(TINY));
  assert.equal((await first.next()).type, "accepted");
  second.send(request(TINY));
  assert.equal((await first.next()).ok, true);
  assert.equal((await second.next()).type, "accepted");
  assert.equal((await second.next()).ok, true);
});

live("the wall-clock limit kills a looping script", async (t) => {
  const { socketPath, logs, jobRoot } = await startRunner(t);
  const api = client(socketPath);
  api.send(request(LOOP, { timeout_seconds: 1 }));
  const accepted = await api.next();
  const pid = await waitForStart(logs, accepted.job_id);
  const failed = await api.next();
  assert.equal(failed.type, "failed");
  assert.equal(failed.code, "timeout");
  assert.equal(failed.signal, "SIGKILL");
  assert.equal(failed.exit_code, null);
  assert.match(failed.message, /1 s time limit/);
  assert.ok(await eventually(() => !alive(pid)), "the worker outlived its timeout");
  assert.ok(await eventually(() => logs.some((text) => text.startsWith(`job ${accepted.job_id} cleaned up`))));
  assert.deepEqual(await readdir(jobRoot), []);
});

live("a client disconnect kills the worker", async (t) => {
  const { socketPath, logs, jobRoot } = await startRunner(t);
  const api = client(socketPath);
  api.send(request(LOOP, { timeout_seconds: 30 }));
  const accepted = await api.next();
  const pid = await waitForStart(logs, accepted.job_id);
  assert.ok(alive(pid));
  assert.equal((await readdir(jobRoot)).length, 1);
  api.socket.destroy();
  assert.ok(await eventually(() => !alive(pid)), "the worker outlived its client");
  assert.ok(await eventually(() => logs.some((text) => text.startsWith(`job ${accepted.job_id} cleaned up`))));
  assert.deepEqual(await readdir(jobRoot), []);
  assert.ok(logs.some((text) => text.includes("client disconnected")));
});

live("worker output beyond the limit stops the job", async (t) => {
  const { socketPath } = await startRunner(t, { outputLimitBytes: 2000 });
  const api = client(socketPath);
  api.send(request(PRINTER));
  assert.equal((await api.next()).type, "accepted");
  const failed = await api.next();
  assert.equal(failed.type, "failed");
  assert.equal(failed.code, "output_limit");
});

test("a worker that cannot start fails the job and frees the slot", async (t) => {
  const { socketPath, jobRoot } = await startRunner(t, { python: "/nonexistent/python3", concurrency: 1 });
  for (let attempt = 0; attempt < 2; attempt++) {
    const api = client(socketPath);
    api.send(request(TINY));
    assert.equal((await api.next()).type, "accepted");
    const failed = await api.next();
    assert.equal(failed.type, "failed");
    assert.ok(["runner_error", "crash"].includes(failed.code), failed.code);
    assert.equal(await api.next(), undefined);
  }
  assert.ok(await eventually(() => readdirSync(jobRoot).length === 0));
});
