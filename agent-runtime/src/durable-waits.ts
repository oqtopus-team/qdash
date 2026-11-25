import type { Context } from "@earendil-works/chord/context";
import type { ToolExecutionApi, ToolPark } from "@earendil-works/pi-durable";
import {
  boundedCheck,
  connectionClient,
  MIN_CHECK_MS,
  type WaitSpec,
  type WaitToolResult,
} from "@oqtopus-team/pi-qdash/extensions/lib/waits.ts";

import type { QDashConnection } from "./auth.ts";

/** What a parked wait keeps between polls. */
export interface WaitCheckpoint {
  /** Harness-clock time after which the wait fails with the tool's timeout error. */
  deadline: number;
}

/** Memo of the deadline a fresh call fixed, for a rerun cut off before its first park. */
const DEADLINE_MEMO = "qdash.wait.deadline";

/**
 * One run of a pi-qdash waiting tool (`qdash_wait_execution`,
 * `qdash_wait_agent_action`) as a durable tool that parks between polls.
 *
 * Each run polls QDash once with `spec.check`. A value ends the call with the
 * same result the pi CLI builds; otherwise the call fails with the tool's
 * timeout error once the deadline passed, or parks (`{ kind: "sleep", until }`)
 * for one poll interval. While parked the call holds no process and no
 * pending request, and its slot shows `sleeping`.
 *
 * - **Deadline:** fixed once, from the Harness clock, when the call first
 *   runs: memoized, so a rerun cut off before its first park keeps it, and
 *   carried in every park's checkpoint, so a restart or a reopened chat store
 *   resumes against the original deadline and a wait never outlives its
 *   timeout. A wake that comes late (the runtime was down) polls once and then
 *   reports the result or the timeout.
 * - **Stop:** aborting a parked call ends it at once; an abort during a poll
 *   drops the poll (the caller passes a `check` that settles on abort).
 * - **Hung read:** a poll is bounded by the time left to the deadline (at
 *   least `MIN_CHECK_MS`), as in the pi CLI's `pollUntilSettled`; one that is
 *   still running then ends the call with the tool's timeout error, and its
 *   late answer or failure is dropped.
 *   Neither touches the execution or action: waiting only reads, so there is
 *   no `cancel` work.
 * - **Replay:** the tool is replay-safe and every run only reads QDash, so a
 *   repeated poll has no side effect.
 * - **Auth:** each run builds its client from the chat's connection (the
 *   requesting user's token and project); the checkpoint holds no credential.
 */
export async function parkingWait<P extends object, T>(
  spec: WaitSpec<P, T>,
  params: P,
  api: Pick<ToolExecutionApi, "checkpoint" | "memo" | "now">,
  context: Context,
  connection: Pick<QDashConnection, "toolArgs">,
): Promise<WaitToolResult | ToolPark<{ deadline: number }>> {
  // A negative timeout or interval fails as the client's loop fails.
  const timing = spec.timing(params);
  const parked = api.checkpoint as Partial<WaitCheckpoint> | undefined;
  const deadline =
    typeof parked?.deadline === "number"
      ? parked.deadline
      : await api.memo(DEADLINE_MEMO, api.now() + timing.timeoutSeconds * 1_000, context);
  const client = await connectionClient(connection.toolArgs);
  const outcome = await boundedCheck(spec, client, params, {
    timeoutMs: Math.max(MIN_CHECK_MS, deadline - api.now()),
  });
  if (outcome.kind === "timeout") throw spec.timeoutError(params, timing);
  const value = outcome.value;
  if (value !== undefined) return spec.result(client, params, value);
  const now = api.now();
  if (now >= deadline) throw spec.timeoutError(params, timing);
  return { kind: "sleep", checkpoint: { deadline }, until: now + timing.pollIntervalSeconds * 1_000 };
}
