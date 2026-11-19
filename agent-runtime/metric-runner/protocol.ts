/**
 * The metric runner's wire protocol: what the API sends over `metric.sock` and
 * what the runner answers, plus the limits both sides share.
 *
 * One Unix socket connection per job, newline-delimited UTF-8 JSON. The first
 * line is the request; the runner answers `accepted` (or `error` and closes),
 * relays the worker's data requests as `call` lines, takes exactly one `answer`
 * per call, and ends with `result` or `failed`. Nothing in the request names a
 * user or project: the API scopes data in its broker before it connects. The
 * worker's own line protocol (stdin/stdout) is documented in
 * src/qdash/api/metric_runtime/worker.py. This file has no dependencies because
 * the metric-runner image ships it without node_modules.
 */

export const METRIC_PROTOCOL_VERSION = 1;
export const DEFAULT_METRIC_SOCKET = "/run/metric-runner/metric.sock";
export const DEFAULT_METRIC_JOB_ROOT = "/tmp/metric-jobs";
export const DEFAULT_METRIC_PYTHON = "python3";
export const DEFAULT_METRIC_PYTHONPATH = "/app/metric-runtime";
export const METRIC_WORKER_MODULE = "qdash.api.metric_runtime.worker";

/** Longest request line, excluding the newline. */
export const REQUEST_MAX_BYTES = 1024 * 1024;
/** Longest script source; the API's `MAX_SOURCE_BYTES`. */
export const SOURCE_MAX_BYTES = 256 * 1024;
/** Longest answer line from the API, excluding the newline. */
export const ANSWER_MAX_BYTES = 32 * 1024 * 1024;
/** Total worker stdout per job; the API executor's `OUTPUT_LIMIT_BYTES`. */
export const OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024;
/** Stderr kept for a `failed` message. */
export const STDERR_TAIL_BYTES = 4096;
/** How long a connection may take to send its request line. */
export const REQUEST_WAIT_MS = 10_000;

/**
 * Job uids: one per slot. The metric-runner container has no other users; the
 * base stays outside the chat workspace owner range (20000–59999 in
 * exec/protocol.ts) so the two never share a uid, even on one host.
 */
export const METRIC_UID_BASE = 60000;
/** Upper bound on slots, so job uids stay far below `nobody` (65534). */
export const METRIC_MAX_CONCURRENCY = 256;

export const DEFAULT_METRIC_CONCURRENCY = 2;
export const DEFAULT_METRIC_QUEUE_LIMIT = 16;
export const DEFAULT_METRIC_QUEUE_WAIT_SECONDS = 5;
export const DEFAULT_METRIC_MAX_TIMEOUT_SECONDS = 300;
export const DEFAULT_METRIC_MAX_MEMORY_MB = 1024;
export const MIN_METRIC_TIMEOUT_SECONDS = 1;
export const MIN_METRIC_MEMORY_MB = 128;

export type MetricMode = "catalog" | "evaluate";

/** The worker's first stdin line, exactly as worker.py reads it. */
export interface MetricWorkerRequest {
  mode: MetricMode;
  source: string;
  memory_mb: number;
  timeout_seconds: number;
  metric_id?: string;
  chip_id?: string;
  start?: string;
  end?: string;
  params?: Record<string, unknown>;
}

export interface MetricRequestLimits {
  maxTimeoutSeconds: number;
  maxMemoryMb: number;
}

export type MetricErrorCode = "invalid_request" | "queue_full";
export type MetricFailureCode = "timeout" | "output_limit" | "crash" | "protocol" | "runner_error";

/** Runner → API. */
export type RunnerMessage =
  | { type: "accepted"; job_id: string }
  | { type: "error"; code: MetricErrorCode; message: string }
  | { type: "call"; op: string; args: Record<string, unknown> }
  | ({ type: "result" } & Record<string, unknown>)
  | {
      type: "failed";
      code: MetricFailureCode;
      message: string;
      exit_code: number | null;
      signal: string | null;
      stderr_tail: string;
    };

/** API → runner, after acceptance; forwarded to the worker without `type`. */
export type WorkerAnswer = { ok: true; data: unknown } | { ok: false; error: string };

const COMMON_FIELDS = new Set(["v", "mode", "source", "timeout_seconds", "memory_mb"]);
const EVALUATE_FIELDS = ["metric_id", "chip_id", "start", "end"] as const;
const KNOWN_FIELDS = new Set([...COMMON_FIELDS, ...EVALUATE_FIELDS, "params"]);
const ID_MAX_LENGTH = 256;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `value` within `[min, max]`; the caller has checked it is a finite number. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

export function clampTimeoutSeconds(value: number, maxTimeoutSeconds: number): number {
  return clamp(value, MIN_METRIC_TIMEOUT_SECONDS, maxTimeoutSeconds);
}

/** Whole megabytes: worker.py multiplies an int. */
export function clampMemoryMb(value: number, maxMemoryMb: number): number {
  return Math.floor(clamp(value, MIN_METRIC_MEMORY_MB, maxMemoryMb));
}

/**
 * Validate a request line and build the worker's request from it. Anything
 * unexpected is an error with a message for the API's logs; nothing is
 * partially trusted, and unknown fields are refused rather than forwarded.
 */
export function parseMetricRequest(
  line: string,
  limits: MetricRequestLimits,
): { request: MetricWorkerRequest } | { error: string } {
  if (Buffer.byteLength(line, "utf8") > REQUEST_MAX_BYTES) return { error: "Request line is too long" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return { error: "Request is not valid JSON" };
  }
  if (!isRecord(parsed)) return { error: "Request must be a JSON object" };
  if (parsed.v !== METRIC_PROTOCOL_VERSION) return { error: `Unsupported protocol version; expected v=${METRIC_PROTOCOL_VERSION}` };
  const unknown = Object.keys(parsed).filter((key) => !KNOWN_FIELDS.has(key));
  if (unknown.length > 0) return { error: `Unknown request field: ${unknown[0]!.slice(0, 64)}` };
  const { mode, source, timeout_seconds: timeout, memory_mb: memory } = parsed;
  if (mode !== "catalog" && mode !== "evaluate") return { error: "mode must be 'catalog' or 'evaluate'" };
  if (typeof source !== "string") return { error: "source must be a string" };
  if (Buffer.byteLength(source, "utf8") > SOURCE_MAX_BYTES) return { error: `source exceeds ${SOURCE_MAX_BYTES} bytes` };
  if (typeof timeout !== "number" || !Number.isFinite(timeout)) return { error: "timeout_seconds must be a number" };
  if (typeof memory !== "number" || !Number.isFinite(memory)) return { error: "memory_mb must be a number" };
  const request: MetricWorkerRequest = {
    mode,
    source,
    memory_mb: clampMemoryMb(memory, limits.maxMemoryMb),
    timeout_seconds: clampTimeoutSeconds(timeout, limits.maxTimeoutSeconds),
  };
  if (mode === "catalog") return { request };
  for (const field of EVALUATE_FIELDS) {
    const value = parsed[field];
    if (typeof value !== "string" || value.length === 0 || value.length > ID_MAX_LENGTH) {
      return { error: `${field} must be a non-empty string of at most ${ID_MAX_LENGTH} characters` };
    }
  }
  if (!isRecord(parsed.params)) return { error: "params must be a JSON object" };
  return {
    request: {
      ...request,
      metric_id: parsed.metric_id as string,
      chip_id: parsed.chip_id as string,
      start: parsed.start as string,
      end: parsed.end as string,
      params: parsed.params,
    },
  };
}

/** An `answer` line from the API as the worker expects it, or `undefined` when malformed. */
export function parseAnswer(line: string): WorkerAnswer | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed) || parsed.type !== "answer") return undefined;
  if (parsed.ok === true) return { ok: true, data: parsed.data ?? null };
  if (parsed.ok === false && typeof parsed.error === "string") return { ok: false, error: parsed.error };
  return undefined;
}

/**
 * The text after a worker's `CALL ` as a `call` message. Like the API's local
 * executor, a malformed call is still relayed (with an empty op) so the API's
 * answer keeps the one-answer-per-call order.
 */
export function callMessage(text: string): RunnerMessage {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = undefined;
  }
  const call = isRecord(parsed) ? parsed : {};
  return {
    type: "call",
    op: typeof call.op === "string" ? call.op : "",
    args: isRecord(call.args) ? call.args : {},
  };
}

/** The text after a worker's `RESULT ` as a `result` message, or `undefined` when malformed. */
export function resultMessage(text: string): RunnerMessage | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  // `type` last: the worker's object cannot turn its result into another message.
  return isRecord(parsed) ? { ...parsed, type: "result" } : undefined;
}

/**
 * Splits a byte stream into lines without re-copying the pending bytes on
 * every chunk, so a 32 MiB answer arriving in small chunks stays linear.
 * A line longer than `maxLineBytes` calls `onOverflow` once and stops output.
 */
export class LineSplitter {
  private pending: Buffer[] = [];
  private pendingBytes = 0;
  private overflowed = false;

  constructor(
    public maxLineBytes: number,
    private readonly onLine: (line: Buffer) => void,
    private readonly onOverflow: () => void,
  ) {}

  push(chunk: Buffer): void {
    let start = 0;
    while (!this.overflowed) {
      const newline = chunk.indexOf(10, start);
      if (newline === -1) {
        if (start < chunk.length) {
          this.pending.push(chunk.subarray(start));
          this.pendingBytes += chunk.length - start;
        }
        if (this.pendingBytes > this.maxLineBytes) this.overflow();
        return;
      }
      const length = this.pendingBytes + newline - start;
      if (length > this.maxLineBytes) {
        this.overflow();
        return;
      }
      const tail = chunk.subarray(start, newline);
      const line = this.pending.length === 0 ? tail : Buffer.concat([...this.pending, tail], length);
      this.pending = [];
      this.pendingBytes = 0;
      start = newline + 1;
      this.onLine(line);
    }
  }

  private overflow(): void {
    this.overflowed = true;
    this.pending = [];
    this.pendingBytes = 0;
    this.onOverflow();
  }
}
