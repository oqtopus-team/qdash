/**
 * pi-qdash tools the chat agent must not see.
 *
 * See .agent/sessions/2026-09-18-copilot-pi-agent-runtime/adr/0003-*.md
 */

/**
 * Tools that create or modify QDash data.
 *
 * Removed from the tool list entirely rather than relying on pi-qdash's own
 * write gate, which cannot prompt for approval when embedded via the SDK
 * (`ctx.hasUI` is always false).
 *
 * Kept in sync with pi-qdash `extensions/lib/write-gate.ts`.
 */
const WRITE_TOOL_NAMES = [
  "qdash_create_agent_session",
  "qdash_submit_agent_action",
  "qdash_commit_agent_candidate",
  "qdash_execute_agent_action",
  "qdash_commit_agent_campaign_candidates",
  "qdash_apply_agent_candidate_commit",
  "qdash_create_forum_post",
  "qdash_update_forum_post",
  "qdash_create_forum_evidence_reply",
  "qdash_create_forum_image_reply",
];

/**
 * Tools that can reach arbitrary API paths.
 *
 * The runtime authenticates as the QDash administrator, so an unrestricted GET
 * would expose `/admin/*` (the user roster, every project) to the chat. The
 * typed `qdash_*` tools cover the calibration data the chat needs.
 */
const RAW_ACCESS_TOOL_NAMES = ["qdash_raw_get"];

export const EXCLUDED_TOOL_NAMES = [...WRITE_TOOL_NAMES, ...RAW_ACCESS_TOOL_NAMES];
