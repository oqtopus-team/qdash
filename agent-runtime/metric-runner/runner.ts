/**
 * The metric runner: runs metric script jobs (validate a script's catalog,
 * evaluate a metric) for the API, in the dedicated metric-runner container,
 * whose entrypoint (server.ts, PID 1) starts it.
 *
 * The API connects to `metric.sock` once per job (protocol in protocol.ts).
 * The runner admits the job into one of a few global slots, starts
 * `python -m qdash.api.metric_runtime.worker` as the slot's own uid in a fresh
 * job directory, and relays the worker's data requests to the API, which
 * answers them from its broker. The worker gets no credentials and no network;
 * it sees only its stdin and stdout pipes. When the job ends, times out, or the
 * API disconnects, every process and file of the job uid is removed before the
 * slot (and so the uid) is reused. See
 * docs/developer-guide/architecture/metric-scripts.md.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { chmodSync, chownSync, lstatSync, mkdirSync, readdirSync, readFileSync, rmSync, unlinkSync } from "node:fs";
import { createServer, type Server, type Socket } from "node:net";
import { dirname, join } from "node:path";

import {
  ANSWER_MAX_BYTES,
  callMessage,
  DEFAULT_METRIC_CONCURRENCY,
  DEFAULT_METRIC_JOB_ROOT,
  DEFAULT_METRIC_MAX_MEMORY_MB,
  DEFAULT_METRIC_MAX_TIMEOUT_SECONDS,
  DEFAULT_METRIC_PYTHON,
  DEFAULT_METRIC_PYTHONPATH,
  DEFAULT_METRIC_QUEUE_LIMIT,
  DEFAULT_METRIC_QUEUE_WAIT_SECONDS,
  DEFAULT_METRIC_SOCKET,
  LineSplitter,
  METRIC_MAX_CONCURRENCY,
  METRIC_UID_BASE,
  METRIC_WORKER_MODULE,
  MIN_METRIC_MEMORY_MB,
  MIN_METRIC_TIMEOUT_SECONDS,
  type MetricFailureCode,
  type MetricWorkerRequest,
  OUTPUT_LIMIT_BYTES,
  parseAnswer,
  parseMetricRequest,
  REQUEST_MAX_BYTES,
  REQUEST_WAIT_MS,
  resultMessage,
  type RunnerMessage,
  STDERR_TAIL_BYTES,
} from "./protocol.ts";

export interface MetricRunnerOptions {
  socketPath: string;
  /** Group allowed to connect; the API container runs as root, so 0 in Compose. */
  socketGid?: number;
  /** Run each job as its slot's uid through `setpriv`; needs root. */
  isolateUsers: boolean;
  /** Python interpreter with numpy, scipy and pint. */
  python: string;
  /** Directory holding the `qdash.api.metric_runtime` package copy. */
  pythonPath: string;
  /** Parent of the per-job directories. */
  jobRoot: string;
  /** Jobs running at once across every API process. */
  concurrency?: number;
  /** Jobs allowed to wait for a slot. */
  queueLimit?: number;
  queueWaitSeconds?: number;
  maxTimeoutSeconds?: number;
  maxMemoryMb?: number;
  /** Total worker stdout per job; lowered by tests. */
  outputLimitBytes?: number;
  /** How long a connection may take to send its request line. */
  requestWaitMs?: number;
  log?: (message: string) => void;
}

export interface MetricRunner {
  socketPath: string;
  close(): Promise<void>;
}

/** Bound on killing a job uid's remaining processes. */
const KILL_SCAN_MS = 2000;
const KILL_SCAN_INTERVAL_MS = 25;
/** World-writable places a job uid can leave files outside its job directory. */
const SWEEP_DIRS = ["/tmp", "/dev/shm"];

interface Waiter {
  grant(slot: number): void;
  cancel(): void;
}

export async function startMetricRunner(options: MetricRunnerOptions): Promise<MetricRunner> {
  const log = options.log ?? ((message: string) => console.log(`[metric-runner] ${message}`));
  const concurrency = options.concurrency ?? DEFAULT_METRIC_CONCURRENCY;
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > METRIC_MAX_CONCURRENCY) {
    throw new Error(`Metric runner concurrency must be an integer in 1..${METRIC_MAX_CONCURRENCY}`);
  }
  const queueLimit = options.queueLimit ?? DEFAULT_METRIC_QUEUE_LIMIT;
  const queueWaitMs = (options.queueWaitSeconds ?? DEFAULT_METRIC_QUEUE_WAIT_SECONDS) * 1000;
  const limits = {
    maxTimeoutSeconds: options.maxTimeoutSeconds ?? DEFAULT_METRIC_MAX_TIMEOUT_SECONDS,
    maxMemoryMb: options.maxMemoryMb ?? DEFAULT_METRIC_MAX_MEMORY_MB,
  };
  const outputLimit = options.outputLimitBytes ?? OUTPUT_LIMIT_BYTES;
  const requestWaitMs = options.requestWaitMs ?? REQUEST_WAIT_MS;
  const isRoot = process.getuid?.() === 0;

  prepareJobRoot(options.jobRoot, options.isolateUsers);
  // Job uids must not reach the socket: the directory is 0750 and the socket
  // 0660, both owned by root and the client's group.
  const socketDir = dirname(options.socketPath);
  mkdirSync(socketDir, { recursive: true, mode: 0o750 });
  chmodSync(socketDir, 0o750);
  const socketGid = isRoot ? options.socketGid : undefined;
  if (socketGid !== undefined) chownSync(socketDir, process.getuid!(), socketGid);
  const stale = lstatSync(options.socketPath, { throwIfNoEntry: false });
  if (stale) {
    if (!stale.isSocket()) throw new Error("Refusing to replace a non-socket path");
    unlinkSync(options.socketPath);
  }

  // Admission: a slot index is also the job's uid offset, so it is free only
  // once the previous job's processes and files are gone.
  const slots: boolean[] = Array.from({ length: concurrency }, () => false);
  const waiting: Waiter[] = [];
  const jobs = new Set<Job>();
  const sockets = new Set<Socket>();
  let closing = false;

  const takeSlot = (): number | undefined => {
    const slot = slots.indexOf(false);
    if (slot === -1) return undefined;
    slots[slot] = true;
    return slot;
  };
  const releaseSlot = (slot: number): void => {
    const next = waiting.shift();
    if (next) next.grant(slot);
    else slots[slot] = false;
  };

  const handle = (socket: Socket): void => {
    sockets.add(socket);
    let state: "request" | "waiting" | "running" | "done" = "request";
    let waiter: Waiter | undefined;
    let job: Job | undefined;

    const send = (message: RunnerMessage): void => {
      if (!socket.destroyed && socket.writable) socket.write(`${JSON.stringify(message)}\n`);
    };
    const refuse = (code: "invalid_request" | "queue_full", message: string): void => {
      state = "done";
      send({ type: "error", code, message });
      socket.end();
    };
    const requestTimer = setTimeout(() => {
      if (state === "request") refuse("invalid_request", "No request line arrived in time");
    }, requestWaitMs);

    const splitter = new LineSplitter(
      REQUEST_MAX_BYTES,
      (line) => {
        if (state === "request") {
          clearTimeout(requestTimer);
          const parsed = parseMetricRequest(line.toString("utf8"), limits);
          if ("error" in parsed) {
            log(`refused a request: ${parsed.error}`);
            refuse("invalid_request", parsed.error);
            return;
          }
          splitter.maxLineBytes = ANSWER_MAX_BYTES;
          admit(parsed.request);
        } else if (state === "waiting") {
          // No call can be pending before the job runs.
          waiter?.cancel();
          refuse("invalid_request", "Unexpected line before the job was accepted");
        } else if (state === "running") {
          job!.answer(line);
        }
      },
      () => {
        if (state === "request") {
          clearTimeout(requestTimer);
          refuse("invalid_request", "Request line is too long");
        } else if (state === "running") {
          job!.fail("protocol", `An answer line exceeded ${ANSWER_MAX_BYTES} bytes`);
        } else {
          socket.destroy();
        }
      },
    );

    const admit = (request: MetricWorkerRequest): void => {
      const run = (slot: number): void => {
        if (state === "done" || closing) {
          releaseSlot(slot);
          return;
        }
        state = "running";
        job = new Job(request, slot, send, () => socket.end(), {
          ...options,
          outputLimit,
          log,
          onCleaned: () => {
            jobs.delete(job!);
            releaseSlot(slot);
          },
        });
        jobs.add(job);
        job.start();
      };
      const slot = takeSlot();
      if (slot !== undefined) {
        run(slot);
        return;
      }
      if (waiting.length >= queueLimit) {
        refuse("queue_full", "Metric script queue is full; try again shortly");
        return;
      }
      state = "waiting";
      const timer = setTimeout(() => {
        waiting.splice(waiting.indexOf(waiter!), 1);
        refuse("queue_full", "No metric script slot became free in time; try again shortly");
      }, queueWaitMs);
      waiter = {
        grant: (granted) => {
          clearTimeout(timer);
          run(granted);
        },
        cancel: () => {
          clearTimeout(timer);
          const index = waiting.indexOf(waiter!);
          if (index !== -1) waiting.splice(index, 1);
        },
      };
      waiting.push(waiter);
    };

    socket.on("data", (chunk: Buffer) => splitter.push(chunk));
    socket.on("error", () => socket.destroy());
    socket.on("close", () => {
      sockets.delete(socket);
      clearTimeout(requestTimer);
      if (state === "waiting") waiter?.cancel();
      state = "done";
      // Closing the connection is the API's cancel signal.
      job?.disconnect().catch((error: unknown) => log(`job cleanup failed: ${messageOf(error)}`));
    });
  };

  const server: Server = createServer(handle);
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(options.socketPath, () => {
      chmodSync(options.socketPath, 0o660);
      if (socketGid !== undefined) chownSync(options.socketPath, process.getuid!(), socketGid);
      server.off("error", reject);
      resolve();
    });
  });
  return {
    socketPath: options.socketPath,
    close: async () => {
      closing = true;
      const closed = new Promise<void>((resolve) => server.close(() => resolve()));
      for (const waiter of waiting.splice(0)) waiter.cancel();
      await Promise.all([...jobs].map((job) => job.disconnect()));
      for (const socket of sockets) socket.destroy();
      await closed;
    },
  };
}

interface JobOptions extends MetricRunnerOptions {
  outputLimit: number;
  log: (message: string) => void;
  onCleaned: () => void;
}

/** One worker process, its job directory, and its slot until cleanup finishes. */
class Job {
  readonly id = randomBytes(8).toString("hex");
  private readonly uid: number | undefined;
  private readonly dir: string;
  private child: ChildProcess | undefined;
  private finished = false;
  private cleanup: Promise<void> | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private pendingCalls = 0;
  private outputBytes = 0;
  private stderrTail = Buffer.alloc(0);
  private readonly acceptedAt = Date.now();
  private spawnedAt: number | undefined;

  constructor(
    private readonly request: MetricWorkerRequest,
    private readonly slot: number,
    private readonly send: (message: RunnerMessage) => void,
    private readonly end: () => void,
    private readonly options: JobOptions,
  ) {
    this.uid = options.isolateUsers ? METRIC_UID_BASE + slot : undefined;
    this.dir = join(options.jobRoot, this.id);
  }

  start(): void {
    const { log } = this.options;
    this.send({ type: "accepted", job_id: this.id });
    try {
      // Fresh and chowned before the worker exists: the supervisor never
      // follows a path the worker could have replaced.
      mkdirSync(this.dir, { mode: 0o700 });
      if (this.uid !== undefined) chownSync(this.dir, this.uid, this.uid);
      chmodSync(this.dir, 0o700);
    } catch (error) {
      log(`job ${this.id} cannot prepare its directory: ${messageOf(error)}`);
      this.fail("runner_error", "The metric runner could not prepare the job directory");
      return;
    }
    const python = [this.options.python, "-u", "-B", "-P", "-s", "-m", METRIC_WORKER_MODULE];
    const command =
      this.uid === undefined
        ? python
        : [
            "setpriv",
            `--reuid=${this.uid}`,
            `--regid=${this.uid}`,
            "--clear-groups",
            "--inh-caps=-all",
            "--no-new-privs",
            "--",
            ...python,
          ];
    let child: ChildProcess;
    try {
      child = spawn(command[0]!, command.slice(1), {
        cwd: this.dir,
        env: workerEnv(this.dir, this.options.pythonPath),
        detached: true,
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (error) {
      log(`job ${this.id} failed to spawn: ${messageOf(error)}`);
      this.fail("runner_error", "The metric runner could not start the worker");
      return;
    }
    this.child = child;
    this.spawnedAt = Date.now();
    log(
      `job ${this.id} started (mode ${this.request.mode}, pid ${child.pid ?? "?"}, slot ${this.slot}, uid ${this.uid ?? "runner"})`,
    );
    child.on("error", (error) => {
      log(`job ${this.id} worker error: ${error.message}`);
      this.fail("runner_error", "The metric runner could not start the worker");
    });
    // `close`, not `exit`: the worker's last stdout line is parsed first.
    child.on("close", (code, signal) => {
      if (this.finished) return;
      this.fail("crash", `The metric script worker exited (${signal ?? code}) without a result`, code, signal);
    });
    child.stdin!.on("error", () => {});
    child.stderr!.on("data", (chunk: Buffer) => {
      const joined = Buffer.concat([this.stderrTail, chunk]);
      this.stderrTail = joined.subarray(Math.max(0, joined.length - STDERR_TAIL_BYTES));
    });
    const stdout = new LineSplitter(
      this.options.outputLimit,
      (line) => this.workerLine(line),
      () => this.overflow(),
    );
    child.stdout!.on("data", (chunk: Buffer) => {
      if (this.finished) return;
      this.outputBytes += chunk.length;
      if (this.outputBytes > this.options.outputLimit) {
        this.overflow();
        return;
      }
      stdout.push(chunk);
    });
    this.timer = setTimeout(() => {
      this.fail(
        "timeout",
        `The metric script exceeded the ${this.request.timeout_seconds} s time limit and was stopped`,
        null,
        "SIGKILL",
      );
    }, this.request.timeout_seconds * 1000);
    child.stdin!.write(`${JSON.stringify(this.request)}\n`);
  }

  /** One line from the API: an answer for the oldest unanswered call. */
  answer(line: Buffer): void {
    if (this.finished) return;
    const answer = parseAnswer(line.toString("utf8"));
    if (!answer) {
      this.fail("protocol", "The API sent a malformed or unexpected line");
      return;
    }
    if (this.pendingCalls === 0) {
      this.fail("protocol", "The API sent an answer without a pending call");
      return;
    }
    this.pendingCalls -= 1;
    this.child?.stdin?.write(`${JSON.stringify(answer)}\n`);
  }

  /** The API's connection closed: stop the job now. */
  disconnect(): Promise<void> {
    if (!this.finished) {
      this.finished = true;
      this.options.log(`job ${this.id} cancelled: the client disconnected`);
    }
    return this.kill();
  }

  fail(
    code: MetricFailureCode,
    message: string,
    exitCode: number | null = null,
    signal: NodeJS.Signals | string | null = null,
  ): void {
    if (this.finished) return;
    this.killGroup();
    this.finish({
      type: "failed",
      code,
      message,
      exit_code: exitCode,
      signal,
      stderr_tail: this.stderrTail.toString("utf8"),
    });
  }

  private workerLine(line: Buffer): void {
    if (this.finished) return;
    const text = line.toString("utf8");
    if (text.startsWith("CALL ")) {
      this.pendingCalls += 1;
      this.send(callMessage(text.slice(5)));
    } else if (text.startsWith("RESULT ")) {
      const result = resultMessage(text.slice(7));
      if (result) this.finish(result);
      else this.fail("crash", "The metric script worker printed a malformed result");
    }
    // Any other line is ignored; it still counted toward the output limit.
  }

  private overflow(): void {
    this.fail(
      "output_limit",
      `The metric script output exceeded ${Math.floor(this.options.outputLimit / (1024 * 1024))} MiB and was stopped`,
    );
  }

  private finish(message: RunnerMessage): void {
    if (this.finished) return;
    this.finished = true;
    this.send(message);
    this.end();
    const outcome =
      message.type === "failed" ? `failed (${message.code})` : `result (ok ${String((message as Record<string, unknown>).ok)})`;
    const ran = this.spawnedAt === undefined ? "not started" : `${Date.now() - this.spawnedAt} ms`;
    this.options.log(`job ${this.id} ${outcome} after ${ran}, ${Date.now() - this.acceptedAt} ms since accepted`);
    this.kill().catch((error: unknown) => this.options.log(`job ${this.id} cleanup failed: ${messageOf(error)}`));
  }

  private killGroup(): void {
    const pid = this.child?.pid;
    if (pid === undefined) return;
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      // Already gone.
    }
  }

  /** Kill every process of the job, remove its files, then free the slot. Idempotent. */
  private kill(): Promise<void> {
    this.cleanup ??= (async () => {
      if (this.timer) clearTimeout(this.timer);
      this.killGroup();
      await waitForExit(this.child);
      if (this.uid !== undefined) {
        if (process.platform === "linux") await killUid(this.uid);
        sweepUid(this.uid, this.options.log);
      }
      try {
        rmSync(this.dir, { recursive: true, force: true });
      } catch (error) {
        this.options.log(`job ${this.id} cannot remove its directory: ${messageOf(error)}`);
      }
      this.options.log(`job ${this.id} cleaned up (slot ${this.slot})`);
      this.options.onCleaned();
    })();
    return this.cleanup;
  }
}

/**
 * The job root is the only path the supervisor shares with workers. Mode 0711
 * when isolating: job uids can reach their own directory by absolute path
 * (HOME, TMPDIR) but cannot list or create entries next to it.
 */
function prepareJobRoot(root: string, isolateUsers: boolean): void {
  mkdirSync(root, { recursive: true, mode: 0o700 });
  const stat = lstatSync(root);
  if (!stat.isDirectory()) throw new Error(`Metric job root ${root} is not a directory`);
  if (isolateUsers && stat.uid !== process.getuid?.()) {
    throw new Error(`Metric job root ${root} is not owned by the runner`);
  }
  chmodSync(root, isolateUsers ? 0o711 : 0o700);
  // Leftovers of a runner that stopped mid-job; no worker can be running now.
  for (const entry of readdirSync(root)) rmSync(join(root, entry), { recursive: true, force: true });
}

/** The worker's whole environment: nothing from the runner's own. */
function workerEnv(dir: string, pythonPath: string): Record<string, string> {
  return {
    PATH: "/usr/local/bin:/usr/bin:/bin",
    PYTHONPATH: pythonPath,
    HOME: dir,
    TMPDIR: dir,
    LANG: "C.UTF-8",
    LC_ALL: "C.UTF-8",
    PYTHONDONTWRITEBYTECODE: "1",
    OPENBLAS_NUM_THREADS: "1",
    OMP_NUM_THREADS: "1",
    MKL_NUM_THREADS: "1",
  };
}

function waitForExit(child: ChildProcess | undefined): Promise<void> {
  if (!child || child.pid === undefined || child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, KILL_SCAN_MS);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

/** Processes whose uid is `uid`, from /proc (Linux). */
function processesOf(uid: number): number[] {
  const found: number[] = [];
  let entries: string[];
  try {
    entries = readdirSync("/proc");
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (!/^\d+$/.test(entry)) continue;
    let status: string;
    try {
      status = readFileSync(`/proc/${entry}/status`, "utf8");
    } catch {
      continue;
    }
    const line = status.split("\n").find((text) => text.startsWith("Uid:"));
    if (line && line.split(/\s+/).slice(1).some((value) => Number(value) === uid)) found.push(Number(entry));
  }
  return found;
}

/** SIGKILL whatever still runs as `uid` (a process that left the group), bounded. */
async function killUid(uid: number): Promise<void> {
  const deadline = Date.now() + KILL_SCAN_MS;
  for (;;) {
    const pids = processesOf(uid);
    if (pids.length === 0 || Date.now() >= deadline) return;
    for (const pid of pids) {
      try {
        process.kill(pid, "SIGKILL");
      } catch {
        // Exited between the scan and the signal.
      }
    }
    await new Promise((resolve) => setTimeout(resolve, KILL_SCAN_INTERVAL_MS));
  }
}

/** Remove what `uid` left at the top of the world-writable directories (no symlinks followed). */
function sweepUid(uid: number, log: (message: string) => void): void {
  for (const dir of SWEEP_DIRS) {
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      continue;
    }
    for (const entry of entries) {
      const path = join(dir, entry);
      try {
        if (lstatSync(path).uid === uid) rmSync(path, { recursive: true, force: true });
      } catch (error) {
        log(`cannot remove ${path}: ${messageOf(error)}`);
      }
    }
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function number(name: string, value: string | undefined, fallback: number, min: number, integer: boolean): number {
  if (value === undefined || value.trim() === "") return fallback;
  const parsed = Number(value.trim());
  if (!Number.isFinite(parsed) || parsed < min || (integer && !Number.isInteger(parsed))) {
    throw new Error(`${name}: expected ${integer ? "an integer" : "a number"} >= ${min}, got ${JSON.stringify(value)}`);
  }
  return parsed;
}

function flag(name: string, value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === "") return fallback;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  throw new Error(`${name}: expected a boolean, got ${JSON.stringify(value)}`);
}

/**
 * Runner options from the metric-runner container's environment
 * (`METRIC_RUNNER_*`). `root` is the default of `METRIC_RUNNER_ISOLATE_USERS`:
 * per-job uids need root to `setpriv`.
 */
export function metricRunnerOptionsFromEnv(
  env: Record<string, string | undefined>,
  root: boolean,
): MetricRunnerOptions {
  const text = (name: string, fallback: string) => (env[name]?.trim() ? env[name]!.trim() : fallback);
  return {
    socketPath: text("METRIC_RUNNER_SOCKET", DEFAULT_METRIC_SOCKET),
    socketGid: number("METRIC_RUNNER_SOCKET_GID", env.METRIC_RUNNER_SOCKET_GID, 0, 0, true),
    isolateUsers: flag("METRIC_RUNNER_ISOLATE_USERS", env.METRIC_RUNNER_ISOLATE_USERS, root),
    python: text("METRIC_RUNNER_PYTHON", DEFAULT_METRIC_PYTHON),
    pythonPath: text("METRIC_RUNNER_PYTHONPATH", DEFAULT_METRIC_PYTHONPATH),
    jobRoot: text("METRIC_RUNNER_JOB_ROOT", DEFAULT_METRIC_JOB_ROOT),
    concurrency: number("METRIC_RUNNER_CONCURRENCY", env.METRIC_RUNNER_CONCURRENCY, DEFAULT_METRIC_CONCURRENCY, 1, true),
    queueLimit: number("METRIC_RUNNER_QUEUE_LIMIT", env.METRIC_RUNNER_QUEUE_LIMIT, DEFAULT_METRIC_QUEUE_LIMIT, 0, true),
    queueWaitSeconds: number(
      "METRIC_RUNNER_QUEUE_WAIT_SECONDS",
      env.METRIC_RUNNER_QUEUE_WAIT_SECONDS,
      DEFAULT_METRIC_QUEUE_WAIT_SECONDS,
      0,
      false,
    ),
    maxTimeoutSeconds: number(
      "METRIC_RUNNER_MAX_TIMEOUT_SECONDS",
      env.METRIC_RUNNER_MAX_TIMEOUT_SECONDS,
      DEFAULT_METRIC_MAX_TIMEOUT_SECONDS,
      MIN_METRIC_TIMEOUT_SECONDS,
      false,
    ),
    maxMemoryMb: number(
      "METRIC_RUNNER_MAX_MEMORY_MB",
      env.METRIC_RUNNER_MAX_MEMORY_MB,
      DEFAULT_METRIC_MAX_MEMORY_MB,
      MIN_METRIC_MEMORY_MB,
      true,
    ),
  };
}

/*
 * Memory budget. A worker's RLIMIT_AS is its virtual size after preloading
 * numpy and scipy plus `memory_mb`, so the memory a job can add on top of its
 * baseline resident set is at most `memory_mb`. Every job and the supervisor
 * share the container's memory cgroup, which also charges the /tmp tmpfs.
 * The baselines are Linux measurements in the metric-runner image (python
 * 3.11, numpy 2, scipy 1.16, pint), rounded up generously; see "Memory budget"
 * in docs/developer-guide/architecture/metric-scripts.md for the numbers.
 */
/** Resident set of one worker after its imports, before the script runs. */
export const WORKER_BASELINE_RSS_MB = 128;
/** Resident set of the bun supervisor with its queue and buffers. */
export const SUPERVISOR_RSS_MB = 128;

const MIB = 1024 * 1024;
/** cgroup v1 reports "no limit" as a page-rounded 2^63 - 1. */
const UNLIMITED_BYTES = 2 ** 60;

export interface MemoryBudgetInput {
  concurrency: number;
  maxMemoryMb: number;
  /** The container's memory limit, or `undefined` when there is none or it is unreadable. */
  limitMb: number | undefined;
  /** Size of the /tmp tmpfs, whose pages count against the same limit. */
  tmpfsMb: number;
  workerBaselineMb?: number;
  supervisorMb?: number;
}

export interface MemoryBudget {
  /** Worst case when every slot runs a job that uses its whole allowance. */
  requiredMb: number;
  limitMb: number | undefined;
  /** `undefined` when the limit is unknown. */
  fits: boolean | undefined;
  message: string;
}

/** Compare the worst-case memory of the configured slots with the container limit. */
export function memoryBudget(input: MemoryBudgetInput): MemoryBudget {
  const baseline = input.workerBaselineMb ?? WORKER_BASELINE_RSS_MB;
  const supervisor = input.supervisorMb ?? SUPERVISOR_RSS_MB;
  const requiredMb = input.concurrency * (input.maxMemoryMb + baseline) + supervisor + input.tmpfsMb;
  const formula =
    `${input.concurrency} jobs x (${input.maxMemoryMb} MiB script + ${baseline} MiB worker baseline)` +
    ` + ${supervisor} MiB supervisor + ${input.tmpfsMb} MiB /tmp = ${requiredMb} MiB`;
  if (input.limitMb === undefined) {
    return { requiredMb, limitMb: undefined, fits: undefined, message: `memory budget ${formula}; container limit unknown` };
  }
  const fits = requiredMb <= input.limitMb;
  const message = fits
    ? `memory budget ${formula} of a ${input.limitMb} MiB container limit`
    : `memory budget ${formula} exceeds the ${input.limitMb} MiB container limit: jobs that use their whole ` +
      "allowance at once can be OOM-killed (the job fails; the runner stays up). Lower " +
      "METRIC_RUNNER_CONCURRENCY or METRIC_RUNNER_MAX_MEMORY_MB, or raise METRIC_RUNNER_MEMORY_LIMIT";
  return { requiredMb, limitMb: input.limitMb, fits, message };
}

/** A cgroup memory limit file's content in MiB, or `undefined` for "max" or nonsense. */
export function parseCgroupMemoryLimit(text: string): number | undefined {
  const value = text.trim();
  if (!/^\d+$/.test(value)) return undefined;
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0 || bytes >= UNLIMITED_BYTES) return undefined;
  return Math.floor(bytes / MIB);
}

/** The size of the tmpfs mounted at `mountPoint`, in MiB, from /proc/mounts content. */
export function parseTmpfsSizeMb(mounts: string, mountPoint = "/tmp"): number | undefined {
  for (const line of mounts.split("\n")) {
    const [, target, type, options] = line.split(" ");
    if (target !== mountPoint || type !== "tmpfs" || options === undefined) continue;
    const size = /(?:^|,)size=(\d+)([kmg]?)(?:,|$)/.exec(options);
    if (!size) return undefined;
    const scale = { "": 1 / MIB, k: 1 / 1024, m: 1, g: 1024 }[size[2] as "" | "k" | "m" | "g"];
    return Math.ceil(Number(size[1]) * scale);
  }
  return undefined;
}

/** The container's memory limit in MiB (cgroup v2, then v1), or `undefined`. */
export function containerMemoryLimitMb(): number | undefined {
  for (const path of ["/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"]) {
    try {
      return parseCgroupMemoryLimit(readFileSync(path, "utf8"));
    } catch {
      // Not this cgroup version, or not Linux.
    }
  }
  return undefined;
}

/** The budget of `options` against this container; logged once at startup. */
export function containerMemoryBudget(options: MetricRunnerOptions): MemoryBudget {
  let tmpfsMb = 0;
  try {
    tmpfsMb = parseTmpfsSizeMb(readFileSync("/proc/mounts", "utf8")) ?? 0;
  } catch {
    // Not Linux: no tmpfs to count.
  }
  return memoryBudget({
    concurrency: options.concurrency ?? DEFAULT_METRIC_CONCURRENCY,
    maxMemoryMb: options.maxMemoryMb ?? DEFAULT_METRIC_MAX_MEMORY_MB,
    limitMb: containerMemoryLimitMb(),
    tmpfsMb,
  });
}
