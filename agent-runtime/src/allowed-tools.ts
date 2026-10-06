/**
 * Positive allowlist for the pinned pi-qdash package.
 *
 * The runtime authenticates to QDash with a service credential. A newly added
 * extension tool must therefore be reviewed here before the model can see it;
 * relying only on a denylist would silently expand that credential's surface.
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
  "qdash_list_ai_reviews",
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
  "qdash_list_issues",
  "qdash_list_task_results",
  "qdash_plan_calibration",
  "qdash_plan_pipeline",
  "qdash_plot_timeseries",
  "qdash_preview_forum_evidence_reply",
  "qdash_preview_forum_image_reply",
  "qdash_query",
  "qdash_recent_calibration_figure",
  "qdash_recent_calibration_summary",
  "qdash_recommend_next_action",
  "qdash_target_report",
  "qdash_triage_overview",
  "qdash_validate_calibration",
  "qdash_wait_agent_action",
  "qdash_wait_agent_candidate_apply",
  "qdash_wait_execution",
  "qdash_wiring_insights",
] as const;

/**
 * Reviewed write-capable tools from the pinned pi-qdash package.
 *
 * These stay separate from the normal allowlist so an operator must opt in to
 * the whole experimental surface explicitly. Raw path access remains excluded.
 */
export const EXPERIMENTAL_WRITE_TOOL_NAMES = [
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
  "qdash_run_pipeline",
] as const;

const EXPERIMENTAL_WRITE_TOOLS = new Set<string>(EXPERIMENTAL_WRITE_TOOL_NAMES);

export function isExperimentalWriteTool(name: string): boolean {
  return EXPERIMENTAL_WRITE_TOOLS.has(name);
}
