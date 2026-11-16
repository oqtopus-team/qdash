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
  "qdash_plot_timeseries",
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
 * Reviewed write-capable tools from the bundled pi-qdash package.
 *
 * These stay separate from read tools so every call requires user approval.
 * Raw path access remains excluded.
 */
export const REVIEWED_WRITE_TOOL_NAMES = [
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
] as const;

const REVIEWED_WRITE_TOOLS = new Set<string>(REVIEWED_WRITE_TOOL_NAMES);

export function isReviewedWriteTool(name: string): boolean {
  return REVIEWED_WRITE_TOOLS.has(name);
}

/**
 * Read-only pi-qdash tools that Code Mode scripts may call as nested tools.
 *
 * Each was audited to only read the QDash API as the signed-in user: no
 * write, no local files of the runtime container, no long polling, and no
 * image output (a script receives JSON, so a figure would be lost). Every
 * other tool, including write tools, trusted extension tools, and tools of a
 * local checkout that replaces one of these names, can only be called by the
 * model directly, where approval and the chat's own rendering apply.
 */
export const NESTED_READ_TOOL_NAMES = [
  "qdash_analyze_figure_json",
  "qdash_compare_calibration",
  "qdash_compare_executions",
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
  "qdash_get_flow",
  "qdash_get_forum_post",
  "qdash_get_pipeline_catalog",
  "qdash_get_provenance_stats",
  "qdash_get_task_knowledge",
  "qdash_get_task_result",
  "qdash_get_timeseries",
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
  "qdash_list_task_results",
  "qdash_plan_calibration",
  "qdash_plan_pipeline",
  "qdash_query",
  "qdash_recent_calibration_summary",
  "qdash_recommend_next_action",
  "qdash_target_report",
  "qdash_triage_overview",
  "qdash_validate_calibration",
  "qdash_wiring_insights",
] as const satisfies ReadonlyArray<(typeof ALLOWED_TOOL_NAMES)[number]>;

const NESTED_READ_TOOLS = new Set<string>(NESTED_READ_TOOL_NAMES);

export function isNestedReadTool(name: string): boolean {
  return NESTED_READ_TOOLS.has(name);
}

/**
 * pi-qdash tools the model is not offered until it loads them with
 * `tool_search` (or calls one by name, which loads it for the next request).
 * The common chip, result, execution, figure, and overview tools stay
 * offered directly; these cover narrower workflows. Code Mode scripts may
 * call the read-only ones without loading them.
 */
export const DEFERRED_TOOL_NAMES = [
  // Cryostat, cooldown, and wiring context.
  "qdash_list_cryostats",
  "qdash_list_cooldowns",
  "qdash_get_cooldown_wiring",
  "qdash_wiring_insights",
  "qdash_list_cooldown_wiring_events",
  // CSV and multi-series timeseries analysis.
  "qdash_inspect_timeseries_csv",
  "qdash_compare_timeseries",
  // Pipelines, execution comparison and waiting, provenance.
  "qdash_get_pipeline_catalog",
  "qdash_plan_pipeline",
  "qdash_run_pipeline",
  "qdash_wait_execution",
  "qdash_compare_executions",
  "qdash_get_provenance_stats",
  // Forum.
  "qdash_list_forum_posts",
  "qdash_get_forum_post",
  "qdash_list_forum_replies",
  "qdash_preview_forum_evidence_reply",
  "qdash_preview_forum_image_reply",
  "qdash_create_forum_post",
  "qdash_update_forum_post",
  "qdash_create_forum_evidence_reply",
  "qdash_create_forum_image_reply",
  // Figure evidence packaging and numeric figure analysis.
  "qdash_analyze_figure_json",
  "qdash_build_qcal_evidence",
  // Calibration planning and validation.
  "qdash_compare_calibration",
  "qdash_recommend_next_action",
  "qdash_degradation_report",
  "qdash_plan_calibration",
  "qdash_validate_calibration",
  // Scoped agent workflow state and actions.
  "qdash_create_agent_session",
  "qdash_get_agent_session",
  "qdash_submit_agent_action",
  "qdash_execute_agent_action",
  "qdash_get_agent_action",
  "qdash_list_agent_actions",
  "qdash_wait_agent_action",
  "qdash_list_agent_action_candidates",
  "qdash_commit_agent_candidate",
  "qdash_commit_agent_candidate_set",
  "qdash_get_agent_candidate_commit",
  "qdash_apply_agent_candidate_commit",
  "qdash_wait_agent_candidate_apply",
  // QDash and qubex source code, client configuration.
  "qdash_list_source_roots",
  "qdash_search_source",
  "qdash_read_source",
  "qdash_config_info",
] as const satisfies ReadonlyArray<
  (typeof ALLOWED_TOOL_NAMES)[number] | (typeof REVIEWED_WRITE_TOOL_NAMES)[number]
>;

const DEFERRED_TOOLS = new Set<string>(DEFERRED_TOOL_NAMES);

export function isDeferredTool(name: string): boolean {
  return DEFERRED_TOOLS.has(name);
}

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
