import type { QDashClient } from "@oqtopus-team/qdash-client";
import type { ExecutionResponseDetail } from "@oqtopus-team/qdash-client/models";

/** How long `wait()` polls `GET /executions/{id}`; the run is never cancelled. */
export interface WaitOptions {
  /** Give up after this many seconds with `QDashTimeoutError` (default 3600). */
  timeoutSeconds?: number;
  /** Seconds between reads (default 5). */
  pollIntervalSeconds?: number;
}

/**
 * The state of a run when it was read.
 *
 * `status` is the whole run's: `detail.pipeline.status`, which stays `running`
 * until the last step ends even when the first step's execution has completed.
 * A run without pipeline progress keeps `detail.status`. `detail` is the
 * execution detail as the API returned it.
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

/**
 * Poll until the whole run ends. An execution not listed yet (404) is read again;
 * a failed or cancelled run is returned; `QDashTimeoutError` leaves the run going.
 */
export function waitForRun(
  client: QDashClient,
  executionId: string,
  options: WaitOptions,
): Promise<ExecutionResponseDetail> {
  return client.waitForExecution(executionId, {
    timeoutSeconds: options.timeoutSeconds ?? 3600,
    pollIntervalSeconds: options.pollIntervalSeconds ?? 5,
    wholePipeline: true,
    notFoundAsPending: true,
  });
}
