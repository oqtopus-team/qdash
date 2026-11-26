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
  "qdash_current_time",
  "qdash_dashboard",
  "qdash_dashboard_insights",
  "qdash_degradation_report",
  "qdash_get_agent_action",
  "qdash_get_agent_candidate_commit",
  "qdash_get_agent_session",
  "qdash_get_agent_session_audit",
  "qdash_get_agent_session_context",
  "qdash_get_calibration_session",
  "qdash_get_calibration_session_audit",
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
  "qdash_get_task_result_evidence",
  "qdash_get_timeseries",
  "qdash_inspect_timeseries_csv",
  "qdash_investigate",
  "qdash_list_agent_action_candidates",
  "qdash_list_agent_actions",
  "qdash_list_agent_interventions",
  "qdash_list_agent_sessions",
  "qdash_list_calibration_sessions",
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
  "qdash_create_pipeline_plan",
  "qdash_preview_metric_script",
  "qdash_preview_forum_evidence_reply",
  "qdash_preview_forum_image_reply",
  "qdash_query",
  "qdash_read_source",
  "qdash_recent_calibration_figure",
  "qdash_recent_calibration_summary",
  "qdash_recommend_next_action",
  "qdash_search_source",
  "qdash_summarize_task_results",
  "qdash_target_report",
  "qdash_triage_overview",
  "qdash_validate_calibration",
  "qdash_validate_metric_script",
  "qdash_wait_agent_action",
  "qdash_wait_agent_candidate_apply",
  "qdash_wait_agent_intervention",
  "qdash_wait_execution",
  "qdash_wiring_insights",
] as const;

/**
 * Reviewed write tools, session-granted write tools, the reads Code Mode
 * scripts may call, and the deferred tools come from pi-qdash's host-neutral
 * policy (extensions/lib/tool-policy.ts), which the pi CLI enforces too.
 * Reviewed writes stay separate from read tools so every call requires user
 * approval; session-granted writes run without one only inside an agent
 * session the user approved with `autonomy: "auto"`, which the tools check
 * themselves. Raw path access remains excluded.
 */
export {
  DEFERRED_TOOL_NAMES,
  NESTED_PROPOSAL_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
  SESSION_GRANTED_WRITE_TOOL_NAMES,
  isDeferredTool,
  isNestedProposalTool,
  isNestedReadTool,
  isReviewedWriteTool,
  isScriptCallableTool,
  isSessionGrantedWriteTool,
} from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";

import {
  DEFERRED_TOOL_NAMES as SHARED_DEFERRED,
  NESTED_PROPOSAL_TOOL_NAMES as SHARED_PROPOSALS,
  NESTED_READ_TOOL_NAMES as SHARED_NESTED,
  REVIEWED_WRITE_TOOL_NAMES as SHARED_WRITES,
  SESSION_GRANTED_WRITE_TOOL_NAMES as SHARED_SESSION_WRITES,
} from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";

// Compile-time checks: scripts reach only allowlisted reads, and every
// deferred tool is an allowlisted read or a reviewed or session-granted write.
const _nestedAreAllowed: ReadonlyArray<(typeof ALLOWED_TOOL_NAMES)[number]> = SHARED_NESTED;
// The proposal tools scripts may call are allowlisted too; they are neither reads nor reviewed writes.
const _proposalsAreAllowed: ReadonlyArray<(typeof ALLOWED_TOOL_NAMES)[number]> = SHARED_PROPOSALS;
const _deferredAreReviewed: ReadonlyArray<
  | (typeof ALLOWED_TOOL_NAMES)[number]
  | (typeof SHARED_WRITES)[number]
  | (typeof SHARED_SESSION_WRITES)[number]
> = SHARED_DEFERRED;
void _nestedAreAllowed;
void _proposalsAreAllowed;
void _deferredAreReviewed;

/**
 * Bundled packages whose tools go through the per-name allowlist above. Every
 * other bundled package (pi-qcaleval) is trusted as a whole by its root: each
 * tool it defines is offered, and reviewed write names still require user
 * approval (see bundled-extensions.ts).
 */
export const ALLOWLISTED_PACKAGES = ["@oqtopus-team/pi-qdash"] as const;
