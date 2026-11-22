/**
 * Host-neutral tool policy for the pi-qdash tools, shared by the standalone
 * pi CLI (script-policy.ts) and the QDash Agent Runtime
 * (agent-runtime/src/allowed-tools.ts and codemode.ts).
 *
 * The policy says three things about each tool:
 *
 * - whether it writes to QDash, so every call needs the user's approval;
 * - whether a code mode script may call it: only audited read-only tools,
 *   which read the QDash API as the user and return data, not images;
 * - whether it is deferred: not offered to the model until it is loaded with
 *   `tool_search`, because it covers a narrower workflow.
 *
 * How each host enforces the policy differs (pi's `tool_call` hooks and
 * exposure, pi-durable's callers and hooks), so only the lists, bounds, and
 * messages live here. The module has no runtime dependencies so either host
 * can import it.
 */

/**
 * pi-qdash tools that create or modify QDash data. Every call needs the
 * user's approval; none may run from a script, where no approval exists.
 */
export const REVIEWED_WRITE_TOOL_NAMES = [
  "qdash_create_agent_session",
  "qdash_submit_agent_action",
  "qdash_end_agent_session",
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
  "qdash_save_metric_script",
  "qdash_save_dashboard",
] as const;

/**
 * pi-qdash tools that write to QDash without a per-call approval, because the
 * user already approved the bounded agent session they act in.
 *
 * A session created with `autonomy: "auto"` records that a person approved its
 * qubits, tasks, override bounds, action budget, and expiry once (creating it
 * is a reviewed write). These tools act only inside such a session: each call
 * re-reads it from QDash and refuses when it is not active, not `auto`, out
 * of budget, busy, or the step leaves its scope, and QDash checks the scope
 * again.
 *
 * `qdash_commit_agent_session_update` commits (and, when granted, applies) a
 * candidate only in a session whose approval also granted
 * `policy.parameter_updates`: the parameters, the tasks that may supply them,
 * and whether backend apply is included. It records the agent's pass
 * assessment first and sends the write as `autonomous`, so QDash checks the
 * grant, the creator, the assessment, the gates, and the current state itself.
 * Without that grant, and for every other session, commits and applies stay
 * the reviewed writes above; no flag a model sets turns one into the other.
 * Like reviewed writes, no code mode script may call them; each call's
 * idempotency key derives from its tool call id, so a replayed call reuses
 * what it created instead of measuring again.
 *
 * `qdash_record_agent_decision` only appends the agent's own reading of a
 * result to the audit of a session the signed-in user created; it changes no
 * session state, so it needs neither autonomy `auto` nor an active session.
 */
export const SESSION_GRANTED_WRITE_TOOL_NAMES = [
  "qdash_run_agent_session_step",
  "qdash_request_agent_human",
  "qdash_record_agent_decision",
  "qdash_commit_agent_session_update",
] as const;

/**
 * Read-only pi-qdash tools that code mode scripts may call.
 *
 * Each was audited to only read the QDash API as the signed-in user
 * (`qdash_current_time` reads only the host clock): no write, no local files,
 * no long polling, and no image output (a script receives JSON, so a figure
 * would be lost). Every other tool, including
 * write tools, figure tools, raw API access, and another extension's tool
 * that reuses one of these names, can only be called by the model directly,
 * where approval and the host's own rendering apply.
 */
export const NESTED_READ_TOOL_NAMES = [
  "qdash_analyze_figure_json",
  "qdash_compare_calibration",
  "qdash_compare_executions",
  "qdash_current_time",
  "qdash_dashboard",
  "qdash_dashboard_insights",
  "qdash_degradation_report",
  "qdash_get_agent_action",
  "qdash_get_agent_candidate_commit",
  "qdash_get_agent_session",
  "qdash_get_agent_session_audit",
  "qdash_get_agent_session_context",
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
  "qdash_list_agent_interventions",
  "qdash_list_agent_sessions",
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
] as const;

/**
 * pi-qdash tools the model is not offered until it loads them with
 * `tool_search`. The common chip, result, execution, figure, and overview
 * tools stay offered directly; these cover narrower workflows. Scripts may
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
  "qdash_end_agent_session",
  "qdash_execute_agent_action",
  "qdash_get_agent_action",
  "qdash_list_agent_actions",
  "qdash_list_agent_interventions",
  "qdash_list_agent_sessions",
  "qdash_get_agent_session_context",
  "qdash_run_agent_session_step",
  "qdash_request_agent_human",
  "qdash_record_agent_decision",
  "qdash_commit_agent_session_update",
  "qdash_get_agent_session_audit",
  "qdash_wait_agent_intervention",
  "qdash_wait_agent_action",
  "qdash_list_agent_action_candidates",
  "qdash_commit_agent_candidate",
  "qdash_commit_agent_candidate_set",
  "qdash_get_agent_candidate_commit",
  "qdash_apply_agent_candidate_commit",
  "qdash_wait_agent_candidate_apply",
  // Metric scripts and dashboards: validation and previews run code on the server.
  "qdash_validate_metric_script",
  "qdash_preview_metric_script",
  "qdash_save_metric_script",
  "qdash_save_dashboard",
  // QDash and qubex source code, client configuration.
  "qdash_list_source_roots",
  "qdash_search_source",
  "qdash_read_source",
  "qdash_config_info",
] as const;

/** Evaluation tools (pi-qcaleval) whose figures and reference the host fills. */
export const EVALUATION_TOOL_NAMES = ["qcal_evaluate"] as const;

const WRITE_TOOLS = new Set<string>(REVIEWED_WRITE_TOOL_NAMES);
const SESSION_GRANTED_WRITE_TOOLS = new Set<string>(SESSION_GRANTED_WRITE_TOOL_NAMES);
const NESTED_READ_TOOLS = new Set<string>(NESTED_READ_TOOL_NAMES);
const DEFERRED_TOOLS = new Set<string>(DEFERRED_TOOL_NAMES);
const EVALUATION_TOOLS = new Set<string>(EVALUATION_TOOL_NAMES);

export function isReviewedWriteTool(name: string): boolean {
  return WRITE_TOOLS.has(name);
}

export function isSessionGrantedWriteTool(name: string): boolean {
  return SESSION_GRANTED_WRITE_TOOLS.has(name);
}

export function isNestedReadTool(name: string): boolean {
  return NESTED_READ_TOOLS.has(name);
}

export function isDeferredTool(name: string): boolean {
  return DEFERRED_TOOLS.has(name);
}

export function isEvaluationTool(name: string): boolean {
  return EVALUATION_TOOLS.has(name);
}

/**
 * Largest value one nested call hands a script, as serialized JSON. A larger
 * response fails the call with advice to narrow it, so one call cannot fill a
 * script's memory or the session's record of nested results.
 */
export const MAX_NESTED_DATA_BYTES = 512 * 1024;

/** What the model reads when a script tried a tool it may not call. */
export function nestedBlockMessage(name: string): string {
  return `${name} cannot be called from a code mode script: scripts may only call QDash's read-only tools. Call ${name} directly instead; write tools then ask the user for approval.`;
}

/**
 * The code mode namespace of the pi-qdash tools, the same in both hosts: the
 * QDash Agent Runtime declares it on its `qdash` durable extension, and the pi
 * CLI on each tool pi-qdash registers. Code mode lists `description` once
 * above the tools scripts may call; a script reads `instructions` with
 * `describeNamespace("qdash")`, and `searchTools()` searches both. It names
 * no tools: which tools a script may call stays the policy above.
 */
export const QDASH_TOOL_NAMESPACE = {
  name: "qdash",
  description:
    "QDash calibration data read as the signed-in user: chips, qubits, couplings, executions, task results, metrics, time series, flows, forum posts, and source. Each tool resolves to its redacted response data as JSON.",
  instructions: [
    "Scripts can call only QDash's audited read-only tools. Write tools, figures, charts, and evaluation tools are called directly, outside a script; write tools then ask the user for approval.",
    "A tool resolves to the response data its text answer summarizes, as JSON and not truncated; print a small sample first when you do not know its shape.",
    `One call may hand a script at most ${MAX_NESTED_DATA_BYTES} bytes of JSON; a larger response fails the call. Narrow it with a chip, qubit, task, time range, or limit, or split it into several calls.`,
    "Deferred read tools can be called from a script without loading them with tool_search first.",
  ].join("\n"),
} as const;

/** What a script reads when a nested call returned more data than it may receive. */
export function nestedDataTooLargeMessage(name: string, bytes: number): string {
  return `${name} returned ${bytes} bytes of data, more than the ${MAX_NESTED_DATA_BYTES} bytes a script may receive from one call. Narrow the request (a chip, qubit, task, time range, or limit) or split it into several calls.`;
}

/** Size of a value as UTF-8 JSON, without a Buffer so either host can run it. */
export function jsonByteLength(value: unknown): number {
  const text = JSON.stringify(value) ?? "";
  let bytes = 0;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff) {
      bytes += 4;
      index += 1;
    } else bytes += 3;
  }
  return bytes;
}

/** The value a script may receive from `name`, or the error it reads instead. */
export function boundScriptData(
  name: string,
  value: unknown,
): { ok: true; value: unknown; bytes: number } | { ok: false; message: string; bytes: number } {
  const bytes = jsonByteLength(value);
  if (bytes <= MAX_NESTED_DATA_BYTES) return { ok: true, value, bytes };
  return { ok: false, message: nestedDataTooLargeMessage(name, bytes), bytes };
}

/**
 * What a script gets for a nested QDash call: pi-qdash's redacted
 * `details.data`, else the text answer parsed as JSON, else the text itself.
 * The data is the one the text summarizes, not truncated.
 */
export function scriptDataOf(result: {
  content?: ReadonlyArray<{ type: string; text?: string }>;
  details?: unknown;
}): unknown {
  const data = (result.details as { data?: unknown } | undefined)?.data;
  if (data !== undefined) return JSON.parse(JSON.stringify(data)) as unknown;
  const text = (result.content ?? [])
    .map((block) => (block.type === "text" && typeof block.text === "string" ? block.text : ""))
    .join("\n");
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/** First-line prefix of a code mode script's options (pi-codemode's `CODEMODE_OPTIONS_PREFIX`). */
export const SCRIPT_OPTIONS_PREFIX = "// @options:";
/** Deadline of a script that sets none. */
export const DEFAULT_SCRIPT_TIMEOUT_MS = 120_000;
/** Longest deadline a script may set. */
export const MAX_SCRIPT_TIMEOUT_MS = 300_000;
/** Largest `timeout_ms` code mode accepts (`setTimeout`'s limit); a larger one is its error to report. */
const SCRIPT_TIMEOUT_LIMIT_MS = 2_147_483_647;

/**
 * The script source with a bounded deadline: a script without one gets the
 * default, and a longer one is cut to the maximum. A malformed options line,
 * or a `timeout_ms` code mode would reject, is left for code mode to report.
 */
export function withScriptDeadline(source: string, prefix: string = SCRIPT_OPTIONS_PREFIX): string {
  const newline = source.indexOf("\n");
  const first = (newline === -1 ? source : source.slice(0, newline)).replace(/\r$/, "");
  const trimmed = first.trimStart();
  if (!trimmed.startsWith(prefix)) {
    return `${prefix} ${JSON.stringify({ timeout_ms: DEFAULT_SCRIPT_TIMEOUT_MS })}\n${source}`;
  }
  let options: unknown;
  try {
    options = JSON.parse(trimmed.slice(prefix.length).trim());
  } catch {
    return source;
  }
  if (typeof options !== "object" || options === null || Array.isArray(options)) return source;
  let timeout: number;
  if (!Object.hasOwn(options, "timeout_ms")) {
    timeout = DEFAULT_SCRIPT_TIMEOUT_MS;
  } else {
    const requested = (options as { timeout_ms: unknown }).timeout_ms;
    // Code mode rejects any other value with its own message.
    const valid =
      typeof requested === "number" &&
      Number.isSafeInteger(requested) &&
      requested > 0 &&
      requested <= SCRIPT_TIMEOUT_LIMIT_MS;
    if (!valid) return source;
    timeout = Math.min(requested, MAX_SCRIPT_TIMEOUT_MS);
  }
  const rest = newline === -1 ? "" : source.slice(newline);
  return `${prefix} ${JSON.stringify({ ...options, timeout_ms: timeout })}${rest}`;
}
