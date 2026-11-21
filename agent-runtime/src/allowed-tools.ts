/**
 * Positive allowlist for the bundled pi-qdash package.
 *
 * The runtime authenticates as the user who submitted the turn. Newly added
 * extension tools still require review before they are exposed to the model.
 */
export const ALLOWED_TOOL_NAMES = [
  "qdash_analyze_figure_json",
  "qdash_build_qcal_evidence",
  "qdash_compare_calibration",
  "qdash_compare_executions",
  "qdash_compare_timeseries",
  "qdash_config_info",
  "qdash_dashboard",
  "qdash_dashboard_insights",
  "qdash_degradation_report",
  "qdash_get_agent_action",
  "qdash_get_agent_candidate_commit",
  "qdash_get_agent_session",
  "qdash_get_chip_metrics",
  "qdash_get_cooldown_wiring",
  "qdash_get_default_chip",
  "qdash_get_execution",
  "qdash_get_figure",
  "qdash_get_flow",
  "qdash_get_forum_post",
  "qdash_get_pipeline_catalog",
  "qdash_get_provenance_stats",
  "qdash_get_task_figures",
  "qdash_get_task_knowledge",
  "qdash_get_task_result",
  "qdash_get_timeseries",
  "qdash_inspect_timeseries_csv",
  "qdash_investigate",
  "qdash_list_agent_action_candidates",
  "qdash_list_agent_actions",
  "qdash_list_chip_couplings",
  "qdash_list_chip_qubits",
  "qdash_list_chips",
  "qdash_list_cooldown_wiring_events",
  "qdash_list_cooldowns",
  "qdash_list_cryostats",
  "qdash_list_executions",
  "qdash_list_flows",
  "qdash_list_forum_posts",
  "qdash_list_forum_replies",
  "qdash_list_source_roots",
  "qdash_list_task_results",
  "qdash_plan_calibration",
  "qdash_plan_pipeline",
  "qdash_preview_forum_evidence_reply",
  "qdash_preview_forum_image_reply",
  "qdash_query",
  "qdash_read_source",
  "qdash_recent_calibration_figure",
  "qdash_recent_calibration_summary",
  "qdash_recommend_next_action",
  "qdash_search_source",
  "qdash_target_report",
  "qdash_triage_overview",
  "qdash_validate_calibration",
  "qdash_wait_agent_action",
  "qdash_wait_agent_candidate_apply",
  "qdash_wait_execution",
  "qdash_wiring_insights",
] as const;

/**
 * Reviewed write tools, the reads Code Mode scripts may call, and the
 * deferred tools come from pi-qdash's host-neutral policy
 * (extensions/lib/tool-policy.ts), which the pi CLI enforces too. Write
 * tools stay separate from read tools so every call requires user approval;
 * raw path access remains excluded.
 */
export {
  DEFERRED_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
  isDeferredTool,
  isNestedReadTool,
  isReviewedWriteTool,
} from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";

import {
  DEFERRED_TOOL_NAMES as SHARED_DEFERRED,
  NESTED_READ_TOOL_NAMES as SHARED_NESTED,
  REVIEWED_WRITE_TOOL_NAMES as SHARED_WRITES,
} from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";

// Compile-time checks: scripts reach only allowlisted reads, and every
// deferred tool is an allowlisted read or a reviewed write.
const _nestedAreAllowed: ReadonlyArray<(typeof ALLOWED_TOOL_NAMES)[number]> = SHARED_NESTED;
const _deferredAreReviewed: ReadonlyArray<
  (typeof ALLOWED_TOOL_NAMES)[number] | (typeof SHARED_WRITES)[number]
> = SHARED_DEFERRED;
void _nestedAreAllowed;
void _deferredAreReviewed;

/**
 * Installed pi packages trusted as a whole, like a local checkout: every tool
 * they define is offered without a per-name entry above (reviewed write names
 * still require user approval). Reviewed per package; the bundled source is reviewed with QDash.
 */
export const TRUSTED_EXTENSION_PACKAGES = ["@oqtopus-team/pi-qcaleval"] as const;

/**
 * Packages whose tools go through the per-name allowlist above even when a
 * local checkout of them is mounted for development: the checkout replaces
 * the bundled copy, but does not widen what the model may call.
 */
export const ALLOWLISTED_PACKAGES = ["@oqtopus-team/pi-qdash"] as const;
