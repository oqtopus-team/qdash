import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { isReviewedWriteTool, nestedBlockMessage } from "./tool-policy.js";

export function installQDashWriteGate(pi: ExtensionAPI): void {
  pi.on("tool_call", async (event, ctx) => {
    if (!isReviewedWriteTool(event.toolName)) return;
    // Another tool (a code mode script) made this call: `confirmWrite` it set
    // must not skip the user's confirmation, and no confirmation is asked for
    // a call the model did not make. script-policy.ts blocks it too.
    if (event.parentToolCallId !== undefined) {
      return { block: true, reason: nestedBlockMessage(event.toolName) };
    }
    const input = event.input as { confirmWrite?: boolean };
    if (input.confirmWrite === true) return;

    if (!ctx.hasUI) {
      return {
        block: true,
        reason: `${event.toolName} is a QDash write operation and requires confirmWrite: true in non-interactive mode.`,
      };
    }

    const ok = await ctx.ui.confirm(
      "Approve QDash write operation?",
      `${event.toolName} will create or modify data in QDash. Continue?`,
    );
    if (!ok) return { block: true, reason: "QDash write operation rejected by user" };
    input.confirmWrite = true;
  });
}
