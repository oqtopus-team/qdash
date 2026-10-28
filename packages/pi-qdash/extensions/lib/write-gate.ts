import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const WRITE_TOOL_NAMES = new Set([
  "qdash_create_agent_session",
  "qdash_submit_agent_action",
  "qdash_commit_agent_candidate",
  "qdash_execute_agent_action",
  "qdash_commit_agent_candidate_set",
  "qdash_apply_agent_candidate_commit",
  "qdash_create_forum_post",
  "qdash_update_forum_post",
  "qdash_create_forum_evidence_reply",
  "qdash_create_forum_image_reply",
  "qdash_run_pipeline",
  "qdash_save_flow",
  "qdash_execute_flow",
]);

export function installQDashWriteGate(pi: ExtensionAPI): void {
  pi.on("tool_call", async (event, ctx) => {
    if (!WRITE_TOOL_NAMES.has(event.toolName)) return;
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
