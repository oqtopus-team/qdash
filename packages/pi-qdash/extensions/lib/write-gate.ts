import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { agentSessionApprovalText } from "./agent-loop.js";
import { isReviewedWriteTool, nestedBlockMessage } from "./tool-policy.js";
import {
  cancelledApprovalMessage,
  canonicalArgs,
  changedArgsMessage,
  approvalReviewText,
  forgetGateApproval,
  noApprovalMessage,
  recordGateApproval,
  unserializableArgsMessage,
} from "./write-approval.js";
import { reviewWrite } from "./write-review.js";

/** What the gate's review shows about a call, built from the snapshot it approves. */
export function gateDialogMessage(toolName: string, approvedArgs: string): string {
  const args = JSON.parse(approvedArgs) as Record<string, unknown>;
  const lines = [`${toolName} will create or modify data in QDash.`];
  // A session's grant is what the user approves once for many later steps: show it plainly.
  if (toolName === "qdash_create_agent_session") {
    const chipId = typeof args.chipId === "string" ? args.chipId : "(the user's default chip)";
    const expires = typeof args.expiresInSeconds === "number" ? args.expiresInSeconds : undefined;
    lines.push("", agentSessionApprovalText(chipId, args.policy, expires));
  }
  return approvalReviewText(lines.join("\n"), approvedArgs);
}

/**
 * pi CLI confirmation of every reviewed QDash write the model calls.
 *
 * Lifecycle of one approval, keyed by tool call id (write-approval.ts):
 *
 * 1. `tool_call`: any earlier approval for the id is dropped. A nested call,
 *    a session without a UI, an aborted turn, or arguments that are not plain
 *    JSON data are blocked without a dialog. Otherwise the gate snapshots the
 *    canonical arguments, shows all of them in a review the user can scroll
 *    to the end (write-review.ts), and waits for the user with pi's abort
 *    signal. It records the snapshot, bound to the tool name, only when the
 *    user accepted, the turn was not aborted meanwhile, and the arguments
 *    still equal the snapshot.
 * 2. The tool's `execute` consumes the approval once and runs only when its
 *    arguments still equal the snapshot (a later `tool_call` hook may have
 *    changed them in place).
 * 3. `tool_execution_end` fires for every call, including one a later hook
 *    blocked or an abort skipped: its approval is forgotten. `turn_end`,
 *    `agent_end`, and `session_shutdown` forget every approval this gate
 *    recorded, so none outlives its turn.
 *
 * No argument skips the dialog, so a model cannot approve its own write.
 */
export function installQDashWriteGate(pi: ExtensionAPI): void {
  const recorded = new Set<string>();
  const forget = (toolCallId: string) => {
    forgetGateApproval(toolCallId);
    recorded.delete(toolCallId);
  };
  const forgetAll = () => {
    for (const toolCallId of recorded) forgetGateApproval(toolCallId);
    recorded.clear();
  };

  pi.on("tool_call", async (event, ctx) => {
    if (!isReviewedWriteTool(event.toolName)) return;
    // A new call with this id voids whatever an earlier one was granted.
    forget(event.toolCallId);
    // Another tool (a code mode script) made this call: no confirmation is
    // asked for a call the model did not make. script-policy.ts blocks it too.
    if (event.parentToolCallId !== undefined) {
      return { block: true, reason: nestedBlockMessage(event.toolName) };
    }
    if (!ctx.hasUI) return { block: true, reason: noApprovalMessage(event.toolName) };
    const signal = ctx.signal;
    if (signal?.aborted) return { block: true, reason: cancelledApprovalMessage(event.toolName) };
    const approved = canonicalArgs(event.input);
    if (approved === undefined) return { block: true, reason: unserializableArgsMessage(event.toolName) };

    // The whole review text is fixed here from the snapshot (write-review.ts).
    const ok = await reviewWrite(ctx, "Approve QDash write operation?", gateDialogMessage(event.toolName, approved), signal);
    if (signal?.aborted) return { block: true, reason: cancelledApprovalMessage(event.toolName) };
    if (!ok) return { block: true, reason: "QDash write operation rejected by user" };
    if (canonicalArgs(event.input) !== approved) {
      return { block: true, reason: changedArgsMessage(event.toolName) };
    }
    recordGateApproval(event.toolCallId, event.toolName, approved);
    recorded.add(event.toolCallId);
    return undefined;
  });
  pi.on("tool_execution_end", (event) => {
    forget(event.toolCallId);
  });
  pi.on("turn_end", () => {
    forgetAll();
  });
  pi.on("agent_end", () => {
    forgetAll();
  });
  pi.on("session_shutdown", () => {
    forgetAll();
  });
}
