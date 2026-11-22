/**
 * pi extension the validation harness loads before pi-qdash.
 *
 * It keeps a validation run inside its bounds without changing pi-qdash:
 *
 * - A QDash tool must use the validation connection (`QDASH_*` from the
 *   harness), never a `profile` or `configPath` that could name another
 *   deployment.
 * - The run makes at most `QDASH_VALIDATION_MAX_TOOL_CALLS` tool calls.
 *
 * The approval of reviewed writes is not the guard's job: pi-qdash itself asks
 * the user in the dialog for every reviewed write and ignores any argument a
 * model sets (write-approval.ts), so the validation run exercises production
 * behavior.
 *
 * Without `QDASH_VALIDATION_GUARD=1` it does nothing, so loading it by accident
 * changes no ordinary pi session.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const GUARD_ENV = "QDASH_VALIDATION_GUARD";
export const MAX_TOOL_CALLS_ENV = "QDASH_VALIDATION_MAX_TOOL_CALLS";
export const DEFAULT_MAX_TOOL_CALLS = 40;

export const GUARD_MESSAGES = {
  connection: "The validation harness allows only the configured QDash connection; omit profile, configPath, and useEnv.",
  budget: "The validation run reached its tool-call budget; stop and report what you found.",
} as const;

export interface GuardDecision {
  block: true;
  reason: string;
}

/** The guard's decision for one tool call, given how many calls came before it. */
export function guardToolCall(
  toolName: string,
  input: Record<string, unknown>,
  previousCalls: number,
  maxCalls: number,
): GuardDecision | undefined {
  if (previousCalls >= maxCalls) return { block: true, reason: GUARD_MESSAGES.budget };
  if (toolName.startsWith("qdash_") && (input.profile !== undefined || input.configPath !== undefined || input.useEnv === false)) {
    return { block: true, reason: GUARD_MESSAGES.connection };
  }
  return undefined;
}

function maxCallsFrom(env: NodeJS.ProcessEnv): number {
  const value = Number(env[MAX_TOOL_CALLS_ENV]);
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_MAX_TOOL_CALLS;
}

export default function validationGuard(pi: ExtensionAPI): void {
  if (process.env[GUARD_ENV] !== "1") return;
  const maxCalls = maxCallsFrom(process.env);
  let calls = 0;
  pi.on("tool_call", async (event) => {
    const decision = guardToolCall(event.toolName, (event.input ?? {}) as Record<string, unknown>, calls, maxCalls);
    calls += 1;
    return decision;
  });
}
