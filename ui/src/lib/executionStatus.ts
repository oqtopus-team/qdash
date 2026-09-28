const CANCELLABLE_STATUSES = new Set(["scheduled", "pending", "running"]);
const IN_PROGRESS_STATUSES = new Set([...CANCELLABLE_STATUSES, "cancelling"]);
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

/**
 * Whether the execution is still in flight.
 *
 * A cancellation has been requested but not yet confirmed by Prefect while the
 * status is "cancelling", so the execution still holds the project lock and
 * still needs to be polled.
 */
export function isExecutionInProgress(status?: string | null): boolean {
  return status != null && IN_PROGRESS_STATUSES.has(status);
}

/**
 * Whether a cancellation can still be requested for the execution.
 *
 * Deliberately excludes "cancelling" so a second request cannot be sent while
 * the first one is being applied.
 */
export function isExecutionCancellable(status?: string | null): boolean {
  return status != null && CANCELLABLE_STATUSES.has(status);
}

/** Whether the execution has reached a status that will not change again. */
export function isExecutionTerminal(status?: string | null): boolean {
  return status != null && TERMINAL_STATUSES.has(status);
}
