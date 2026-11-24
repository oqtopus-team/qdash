/** Reading and waiting for dispatched runs, shared by calibrations, pipelines and workflows. */
import type { QDashApi } from "./_generated/index.js";
import { read, type Context } from "./_http.js";
import { QDashNotFoundError, QDashTimeoutError } from "./errors.js";

type ExecutionResponseDetail = QDashApi.ExecutionResponseDetail;

// Execution and pipeline statuses after which nothing more runs.
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "canceled", "crashed"]);

/**
 * How long `wait()` polls `GET /executions/{id}`; the run is never cancelled.
 *
 * The timeout bounds the waits between reads, not a read in flight: subsequent reads start before
 * the deadline and may take up to the config's `timeoutSec` per attempt, with read retries.
 */
export interface WaitOptions {
  /** Give up after this many seconds with `QDashTimeoutError` (default 3600). */
  timeoutSeconds?: number;
  /** Seconds between reads (default 5); the last wait is shortened to end at the deadline. */
  pollIntervalSeconds?: number;
}

/**
 * The state of a run when it was read.
 *
 * `status` is the whole run's: `detail.pipeline.status`, which stays `running` until the last
 * step ends even when the first step's execution has completed. A run without pipeline
 * progress keeps `detail.status`. `detail` is the execution detail as the API returned it.
 */
export interface RunResult {
  readonly executionId: string;
  readonly status: string;
  readonly detail: ExecutionResponseDetail;
}

/** The whole pipeline run's status, or the execution's own without pipeline progress. */
export function runStatus(detail: ExecutionResponseDetail): string {
  return detail.pipeline ? detail.pipeline.status : detail.status;
}

export function runResult(executionId: string, detail: ExecutionResponseDetail): RunResult {
  return Object.freeze({ executionId, status: runStatus(detail), detail });
}

function checkedSeconds(name: string, value: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new RangeError(`${name} must be a non-negative number of seconds`);
  }
  return value;
}

/** Execution reads of one session; the run handles share it. */
export class Executions {
  constructor(private readonly context: Context) {}

  /** The execution's detail; `QDashNotFoundError` before it exists. */
  get(executionId: string): Promise<ExecutionResponseDetail> {
    return read(this.context.reads, (options) =>
      this.context.api.execution.getExecution({ execution_id: executionId }, options),
    );
  }

  /**
   * Poll until the whole run reaches a terminal status and return its detail. An execution the
   * server does not list yet (404) is polled again; a failed or cancelled run is returned, not
   * thrown; `QDashTimeoutError` leaves the run going. Other errors reject.
   */
  async wait(executionId: string, options: WaitOptions = {}): Promise<ExecutionResponseDetail> {
    const timeoutSeconds = checkedSeconds("timeoutSeconds", options.timeoutSeconds ?? 3600);
    const pollIntervalSeconds = checkedSeconds("pollIntervalSeconds", options.pollIntervalSeconds ?? 5);
    const deadline = this.context.now() + timeoutSeconds * 1_000;
    let attempted = false;
    while (true) {
      if (attempted && this.context.now() >= deadline) {
        throw new QDashTimeoutError(
          `Execution '${executionId}' did not reach a terminal state within ${timeoutSeconds} seconds`,
        );
      }
      attempted = true;
      let detail: ExecutionResponseDetail | undefined;
      try {
        detail = await this.get(executionId);
      } catch (error) {
        if (!(error instanceof QDashNotFoundError)) throw error;
      }
      if (detail && TERMINAL_STATUSES.has(runStatus(detail).toLowerCase())) return detail;
      const remaining = deadline - this.context.now();
      if (remaining <= 0) {
        throw new QDashTimeoutError(
          `Execution '${executionId}' did not reach a terminal state within ${timeoutSeconds} seconds`,
        );
      }
      // Never sleep past the deadline or start another read once the budget runs out.
      await this.context.sleep(Math.min(pollIntervalSeconds * 1_000, remaining));
    }
  }
}

/** A dispatched run, followed by its execution ID; `qdash.run(id)` reattaches to one. */
export class Run {
  constructor(
    protected readonly executions: Executions,
    readonly executionId: string,
  ) {}

  /** The run's current state; `QDashNotFoundError` before it exists. */
  async get(): Promise<RunResult> {
    return runResult(this.executionId, await this.executions.get(this.executionId));
  }

  /**
   * Poll until the whole run ends and return its result. A failed or cancelled run is
   * returned, not thrown; check `result.status`. `QDashTimeoutError` leaves the run going.
   */
  async wait(options: WaitOptions = {}): Promise<RunResult> {
    return runResult(this.executionId, await this.executions.wait(this.executionId, options));
  }
}
