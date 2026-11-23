/**
 * The waiting tools `qdash_wait_execution`, `qdash_wait_agent_action`, and
 * `qdash_wait_agent_intervention`, split into one poll and its result so two
 * hosts can run them:
 *
 * - The pi CLI runs the client's own polling loop (`client.waitForExecution`
 *   and friends) and builds its result with `result`; a wait the client has
 *   no loop for runs `pollUntilSettled`.
 * - The QDash Agent Runtime polls once per durable wake with `check` and
 *   parks between polls, so a wait holds no process, keeps its deadline across
 *   restarts, and ends at once when the user stops it (see
 *   `agent-runtime/src/durable-waits.ts`).
 *
 * `check` decides "done" exactly as the client's loop does (the client keeps
 * its rule private); `tests/waits.test.mjs` pins the two together.
 *
 * Both hosts bound each poll with `boundedCheck`: a read that hangs ends the
 * wait at its deadline (with the tool's timeout error) or at once when the
 * user cancels, and its late answer or failure is dropped. The client's
 * requests take no `AbortSignal`, so the abandoned HTTP read itself still runs
 * until the client's request timeout; it only reads, and a check stops before
 * its next request once the signal aborted.
 */

import {
  QDashClient,
  QDashTimeoutError,
  type AgentActionResponse,
  type ExecutionResponseDetail,
} from "@oqtopus-team/qdash-client";

import {
  buildAgentLoopContext,
  DEFAULT_INTERVENTION_POLL_SECONDS,
  DEFAULT_INTERVENTION_WAIT_SECONDS,
  FAILED_RUN_HINT,
  formatAgentLoopContext,
  MAX_INTERVENTION_WAIT_SECONDS,
  MIN_INTERVENTION_POLL_SECONDS,
  UNANSWERED_INTERVENTION_STATUSES,
  type AgentLoopContext,
} from "./agent-loop.js";
import { qdashWebBaseUrl, qdashWebUrl, withQDashLinks } from "./links.js";
import { toTextToolResult, toToolResult } from "./results.js";

/** Statuses at which `client.waitForExecution` stops. */
export const EXECUTION_TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "cancelled",
  "canceled",
  "crashed",
]);

export interface WaitExecutionParams {
  executionId: string;
  timeoutSeconds?: number;
  pollIntervalSeconds?: number;
}

export interface WaitAgentActionParams {
  sessionId: string;
  actionId: string;
  waitForExecution?: boolean;
  timeoutSeconds?: number;
  pollIntervalSeconds?: number;
}

/** A waiting tool's timeout and poll interval, with the client's defaults applied and checked. */
export interface WaitTiming {
  timeoutSeconds: number;
  pollIntervalSeconds: number;
}

/** pi-qdash's tool result shape. */
export type WaitToolResult = ReturnType<typeof toToolResult>;

/** One waiting tool, as one poll and its result. */
export interface WaitSpec<P, T> {
  /** Timeout and interval the client's loop would use; throws its RangeError for a negative one. */
  timing(params: P): WaitTiming;
  /**
   * Poll once: the value the client's loop would return now, or undefined to poll again.
   * A check that makes several requests stops before the next one once `signal` aborted.
   */
  check(client: QDashClient, params: P, signal?: AbortSignal): Promise<T | undefined>;
  /** The tool result for the value the wait ended with. */
  result(client: QDashClient, params: P, value: T): WaitToolResult;
  /** The error the client's loop throws once the deadline passed with no value. */
  timeoutError(params: P, timing: WaitTiming): Error;
}

function timing(timeoutSeconds: number, pollIntervalSeconds: number): WaitTiming {
  // Same check and message as the client's validatePollOptions.
  if (timeoutSeconds < 0 || pollIntervalSeconds < 0) {
    throw new RangeError("Polling timeout and interval must be non-negative");
  }
  return { timeoutSeconds, pollIntervalSeconds };
}

/** Whether `client.waitForExecution` (whole pipeline, the default) returns this execution. */
export function executionSettled(execution: ExecutionResponseDetail): boolean {
  // A pipeline step's own execution completes long before the run does.
  const status = execution.pipeline ? execution.pipeline.status : execution.status;
  return EXECUTION_TERMINAL_STATUSES.has(String(status).toLowerCase());
}

export const WAIT_EXECUTION: WaitSpec<WaitExecutionParams, ExecutionResponseDetail> = {
  timing: (params) => timing(params.timeoutSeconds ?? 600, params.pollIntervalSeconds ?? 0.5),
  async check(client, params) {
    const execution = await client.getExecution(params.executionId);
    return executionSettled(execution) ? execution : undefined;
  },
  result: (client, params, execution) =>
    toToolResult(withQDashLinks(client, execution), {
      tool: "qdash_wait_execution",
      executionId: params.executionId,
      webBaseUrl: qdashWebBaseUrl(client),
    }),
  timeoutError: (params, { timeoutSeconds }) =>
    new QDashTimeoutError(
      `Execution '${params.executionId}' did not reach a terminal state within ${timeoutSeconds} seconds`,
    ),
};

/** The action field `qdash_wait_agent_action` waits for. */
function actionField(params: WaitAgentActionParams): "operation_id" | "execution_id" {
  return params.waitForExecution ? "execution_id" : "operation_id";
}

export const WAIT_AGENT_ACTION: WaitSpec<WaitAgentActionParams, AgentActionResponse> = {
  // waitForAgentActionExecution waits 600 s by default, waitForAgentAction 120 s.
  timing: (params) =>
    timing(params.timeoutSeconds ?? (params.waitForExecution ? 600 : 120), params.pollIntervalSeconds ?? 0.5),
  async check(client, params) {
    const action = await client.getAgentAction(params.sessionId, params.actionId);
    return action.execution_status === "failed" || action[actionField(params)] != null ? action : undefined;
  },
  result: (_client, _params, action) => {
    const result = toToolResult(action, { tool: "qdash_wait_agent_action" });
    // A failed run gets the same mechanical next step the session context gives it.
    if (action.action_type !== "run_task" || String(action.execution_status).toLowerCase() !== "failed") return result;
    return { ...result, content: [...result.content, { type: "text" as const, text: `Next: ${FAILED_RUN_HINT([action.action_id])}` }] };
  },
  timeoutError: (params, { timeoutSeconds }) =>
    new Error(
      `Agent action '${params.actionId}' did not produce ${actionField(params)} within ${timeoutSeconds} seconds`,
    ),
};

export interface WaitAgentInterventionParams {
  sessionId: string;
  timeoutSeconds?: number;
  pollIntervalSeconds?: number;
}

/**
 * Wait, bounded, for an expert to answer the intervention a session is paused
 * on. It ends when the session is no longer `waiting_for_human` (the expert
 * reactivated or stopped it, or it expired) or its intervention left `open`
 * and `responding` (for a plan, `resume_authorized`). The result is the same
 * loop context `qdash_get_agent_session_context` returns, so the model reads
 * the answer with the original question, the attempts, and the session state.
 *
 * The timeout is capped at an hour and the poll interval is at least five
 * seconds: this is a wait inside one live turn, not a background watcher.
 * Waiting only reads; it never answers or reactivates anything.
 */
export const WAIT_AGENT_INTERVENTION: WaitSpec<WaitAgentInterventionParams, AgentLoopContext> = {
  timing: (params) => {
    const checked = timing(
      params.timeoutSeconds ?? DEFAULT_INTERVENTION_WAIT_SECONDS,
      params.pollIntervalSeconds ?? DEFAULT_INTERVENTION_POLL_SECONDS,
    );
    return {
      timeoutSeconds: Math.min(checked.timeoutSeconds, MAX_INTERVENTION_WAIT_SECONDS),
      pollIntervalSeconds: Math.max(checked.pollIntervalSeconds, MIN_INTERVENTION_POLL_SECONDS),
    };
  },
  async check(client, params, signal) {
    const session = await client.getAgentSession(params.sessionId);
    throwIfAborted(signal);
    if (session.status === "waiting_for_human" && session.active_intervention_id) {
      const active = await client.getAgentIntervention(params.sessionId, session.active_intervention_id);
      if (UNANSWERED_INTERVENTION_STATUSES.has(active.status)) return undefined;
      throwIfAborted(signal);
    }
    const [actions, interventions] = await Promise.all([
      client.listAgentActions(params.sessionId),
      client.listAgentInterventions(params.sessionId),
    ]);
    return buildAgentLoopContext({ session, actions, interventions });
  },
  result: (client, params, context) =>
    toTextToolResult(
      formatAgentLoopContext(context, {
        sessionUrl: qdashWebUrl(client, `/agent-sessions/${encodeURIComponent(params.sessionId)}`),
        interventionUrl: context.intervention ? qdashWebUrl(client, context.intervention.page_path) : undefined,
      }),
      context,
      { tool: "qdash_wait_agent_intervention", sessionId: params.sessionId, state: context.state },
    ),
  timeoutError: (params, { timeoutSeconds }) =>
    new QDashTimeoutError(
      `No expert answered the intervention of agent session '${params.sessionId}' within ${timeoutSeconds} seconds. The session stays paused: start no measurement, commit, apply, flow, or pipeline for it. Tell the user it is waiting for an expert in QDash; when they say the expert answered, read qdash_get_agent_session_context and continue from there.`,
    ),
};

/** The waiting tools a host may run poll by poll, by tool name. */
export const WAIT_SPECS = {
  qdash_wait_execution: WAIT_EXECUTION,
  qdash_wait_agent_action: WAIT_AGENT_ACTION,
  qdash_wait_agent_intervention: WAIT_AGENT_INTERVENTION,
} as const;

/**
 * Least time one poll may take, even when the wait's deadline is nearer (or
 * already passed, as for a zero timeout): every wait reads QDash at least once.
 */
export const MIN_CHECK_MS = 1_000;

/** How one bounded poll ended. */
export type BoundedCheck<T> = { kind: "value"; value: T | undefined } | { kind: "timeout" };

/**
 * One poll of `spec`, bounded by `timeoutMs` and `signal`.
 *
 * Resolves with the poll's value, with `timeout` once `timeoutMs` passed
 * first, and rejects with an AbortError once `signal` aborts first; the timer
 * and the abort listener are removed in every case. A poll that answers or
 * fails after that is dropped: its result is never used and its rejection is
 * handled, so nothing surfaces later as an unhandled rejection.
 */
export function boundedCheck<P, T>(
  spec: Pick<WaitSpec<P, T>, "check">,
  client: QDashClient,
  params: P,
  options: { timeoutMs: number; signal?: AbortSignal },
): Promise<BoundedCheck<T>> {
  const { signal } = options;
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise<BoundedCheck<T>>((resolve, reject) => {
    let done = false;
    const finish = (settle: () => void) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      settle();
    };
    const onAbort = () => finish(() => reject(abortError()));
    const timer = setTimeout(() => finish(() => resolve({ kind: "timeout" })), Math.max(0, options.timeoutMs));
    signal?.addEventListener("abort", onAbort, { once: true });
    let poll: Promise<T | undefined>;
    try {
      poll = spec.check(client, params, signal);
    } catch (error) {
      poll = Promise.reject(error);
    }
    poll.then(
      (value) => finish(() => resolve({ kind: "value", value })),
      (error) => finish(() => reject(error)),
    );
  });
}

/**
 * Run a wait spec's polls in this process until it settles, times out, or
 * `signal` aborts: the pi CLI's loop for a wait the client has no loop for.
 * Each poll is bounded by the deadline (at least `MIN_CHECK_MS`) and by the
 * signal, so a hung read neither outlives the wait nor delays a cancel.
 */
export async function pollUntilSettled<P, T>(
  spec: WaitSpec<P, T>,
  client: QDashClient,
  params: P,
  signal?: AbortSignal,
  sleep: (ms: number, signal?: AbortSignal) => Promise<void> = abortableSleep,
): Promise<WaitToolResult> {
  const timing = spec.timing(params);
  const deadline = Date.now() + timing.timeoutSeconds * 1_000;
  for (;;) {
    if (signal?.aborted) throw abortError();
    const outcome = await boundedCheck(spec, client, params, {
      timeoutMs: Math.max(MIN_CHECK_MS, deadline - Date.now()),
      signal,
    });
    if (outcome.kind === "timeout") throw spec.timeoutError(params, timing);
    if (outcome.value !== undefined) return spec.result(client, params, outcome.value);
    if (Date.now() >= deadline) throw spec.timeoutError(params, timing);
    await sleep(Math.min(timing.pollIntervalSeconds * 1_000, Math.max(0, deadline - Date.now())), signal);
  }
}

function abortError(): Error {
  const error = new Error("The wait was cancelled; nothing in QDash changed.");
  error.name = "AbortError";
  return error;
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (signal?.aborted) throw abortError();
}

function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export type WaitToolName = keyof typeof WAIT_SPECS;

export function isWaitToolName(name: string): name is WaitToolName {
  return Object.hasOwn(WAIT_SPECS, name);
}

/**
 * The client a host-owned connection names: always its explicit profile and
 * config file, never the environment or pi-qdash's selected profile.
 */
export function connectionClient(args: { profile: string; configPath: string }): Promise<QDashClient> {
  return QDashClient.fromProfile(args.profile, args.configPath);
}
