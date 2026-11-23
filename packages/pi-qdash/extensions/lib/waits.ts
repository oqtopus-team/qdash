/**
 * The waiting tools `qdash_wait_execution` and `qdash_wait_agent_action`,
 * split into one poll and its result so two hosts can run them:
 *
 * - The pi CLI runs the client's own polling loop (`client.waitForExecution`
 *   and friends) and builds its result with `result`.
 * - The QDash Agent Runtime polls once per durable wake with `check` and
 *   parks between polls, so a wait holds no process, keeps its deadline across
 *   restarts, and ends at once when the user stops it (see
 *   `agent-runtime/src/durable-waits.ts`).
 *
 * `check` decides "done" exactly as the client's loop does (the client keeps
 * its rule private); `tests/waits.test.mjs` pins the two together.
 */

import {
  QDashClient,
  QDashTimeoutError,
  type AgentActionResponse,
  type ExecutionResponseDetail,
} from "@oqtopus-team/qdash-client";

import { qdashWebBaseUrl, withQDashLinks } from "./links.js";
import { toToolResult } from "./results.js";

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
  /** Poll once: the value the client's loop would return now, or undefined to poll again. */
  check(client: QDashClient, params: P): Promise<T | undefined>;
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
  result: (_client, _params, action) => toToolResult(action, { tool: "qdash_wait_agent_action" }),
  timeoutError: (params, { timeoutSeconds }) =>
    new Error(
      `Agent action '${params.actionId}' did not produce ${actionField(params)} within ${timeoutSeconds} seconds`,
    ),
};

/** The waiting tools a host may run poll by poll, by tool name. */
export const WAIT_SPECS = {
  qdash_wait_execution: WAIT_EXECUTION,
  qdash_wait_agent_action: WAIT_AGENT_ACTION,
} as const;

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
