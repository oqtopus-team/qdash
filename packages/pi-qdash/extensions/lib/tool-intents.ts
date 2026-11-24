/**
 * Which kind of request each pi-qdash tool serves, shared by the pi CLI and
 * the QDash Agent Runtime. It classifies tools, never the user's words.
 *
 * Both hosts already find deferred tools with pi's `tool_search`, a BM25
 * ranker over each tool's description and parameter text (pi-coding-agent's
 * `extensions/tool-search` and pi-durable's `tool-search`), and code mode
 * scripts with `searchTools()` over the same text. pi-qdash does not add its
 * own search or selection: it adds the request-type words below to the
 * description of each deferred tool (applyToolPolicy, script-policy.ts), so a
 * search phrased as a request type ranks that type's tools first, and gives
 * the model a short guide naming the tools per request type.
 *
 * Nothing here limits access. Every tool stays loadable by name or by any
 * other query, tools loaded earlier stay loaded on the branch (pi records
 * them), and a conversation can move between request types at any turn.
 * Approval and code mode policy stay in tool-policy.ts.
 *
 * The module has no runtime dependencies so either host can import it.
 */

import { DEFERRED_MARK } from "./qdash-guidance.js";

export type ToolIntent = "stored_values" | "diagnosis" | "measurement_preparation" | "write";

export interface ToolIntentSpec {
  intent: ToolIntent;
  /** Heading in the guide. */
  label: string;
  /** When it applies, in the guide. */
  when: string;
  /** Words a search for this request type may use; added to each deferred tool's search text. */
  searchTerms: string;
  /** Tools for it, most useful first. */
  tools: readonly string[];
}

export const QDASH_TOOL_INTENTS: readonly ToolIntentSpec[] = [
  {
    intent: "stored_values",
    label: "Stored values",
    when: "what a value or status is now, or was: read stored results, no measurement",
    searchTerms: "stored values: current saved latest value, status, parameter, history, trend",
    tools: [
      "qdash_get_chip_metrics",
      "qdash_list_chip_qubits",
      "qdash_list_chip_couplings",
      "qdash_list_task_results",
      "qdash_get_task_result",
      "qdash_get_timeseries",
      "qdash_recent_calibration_summary",
      "qdash_list_executions",
      "qdash_get_execution",
      "qdash_get_provenance_stats",
      "qdash_list_cooldowns",
    ],
  },
  {
    intent: "diagnosis",
    label: "Diagnosis",
    when: "why a result failed, drifted, or looks wrong: gather evidence before concluding",
    searchTerms: "diagnosis: diagnose why failed, failure cause, evidence, investigate, troubleshoot, drift, compare",
    tools: [
      "qdash_get_task_result_evidence",
      "qdash_get_task_knowledge",
      "qdash_get_task_figures",
      "qdash_get_figure",
      "qdash_analyze_figure_json",
      "qdash_investigate",
      "qdash_target_report",
      "qdash_triage_overview",
      "qdash_degradation_report",
      "qdash_compare_executions",
      "qdash_compare_calibration",
      "qdash_compare_timeseries",
      "qdash_get_cooldown_wiring",
      "qdash_wiring_insights",
      "qdash_list_cooldown_wiring_events",
    ],
  },
  {
    intent: "measurement_preparation",
    label: "Measurement preparation",
    when: "plan a remeasurement or calibration; these read and check, they run and save nothing",
    searchTerms: "measurement preparation: plan, prepare, remeasure, calibrate, recommend next, pipeline catalog, validate before running",
    tools: [
      "qdash_recommend_next_action",
      "qdash_plan_calibration",
      "qdash_get_pipeline_catalog",
      "qdash_plan_pipeline",
      "qdash_list_flows",
      "qdash_get_flow",
      "qdash_validate_calibration",
      "qdash_list_calibration_sessions",
      "qdash_get_calibration_session",
      "qdash_list_agent_sessions",
      "qdash_get_agent_session_context",
    ],
  },
  {
    intent: "write",
    label: "Writes",
    when: "run, save, commit, or apply only when the user asks; each keeps its approval or session grant",
    searchTerms: "write: run, execute, start, save, commit, apply, create, post; needs approval",
    tools: [
      "qdash_run_pipeline",
      "qdash_execute_flow",
      "qdash_create_calibration_session",
      "qdash_create_agent_session",
      "qdash_run_agent_session_step",
      "qdash_commit_agent_candidate",
      "qdash_apply_agent_candidate_commit",
      "qdash_commit_agent_session_update",
      "qdash_end_agent_session",
      "qdash_save_flow",
      "qdash_save_metric_script",
      "qdash_save_dashboard",
      "qdash_create_forum_post",
    ],
  },
];

const INTENTS_BY_TOOL = new Map<string, ToolIntent[]>();
for (const spec of QDASH_TOOL_INTENTS) {
  for (const tool of spec.tools) INTENTS_BY_TOOL.set(tool, [...(INTENTS_BY_TOOL.get(tool) ?? []), spec.intent]);
}

/** The request types a tool serves; empty for a tool not classified. */
export function toolIntents(name: string): ToolIntent[] {
  return INTENTS_BY_TOOL.get(name) ?? [];
}

/** Line added to a tool's description so `tool_search` ranks it for its request types, or null. */
export function intentSearchLine(name: string): string | null {
  const intents = toolIntents(name);
  if (intents.length === 0) return null;
  const terms = QDASH_TOOL_INTENTS.filter((spec) => intents.includes(spec.intent)).map((spec) => spec.searchTerms);
  return `Request type: ${terms.join("; ")}.`;
}

/**
 * `description` with the request-type line on its own line after it, so
 * search results that show a description's first line stay unchanged.
 * Unclassified tools, and descriptions that already carry the line, are
 * returned as they are.
 */
export function withIntentSearchText(name: string, description: string): string {
  const line = intentSearchLine(name);
  if (!line || description.includes(line)) return description;
  return `${description.trimEnd()}\n${line}`;
}

/** Most tools the guide names per request type. */
const GUIDE_TOOLS_PER_INTENT = 6;

/**
 * The guide that maps request types to tools, limited to `availableTools`
 * and with `deferredTools` marked, or null when no request type has a tool.
 */
export function intentRoutingGuide(availableTools: Iterable<string>, deferredTools: Iterable<string> = []): string | null {
  const available = new Set(availableTools);
  const deferred = new Set(deferredTools);
  const lines = QDASH_TOOL_INTENTS.flatMap((spec) => {
    const tools = spec.tools.filter((name) => available.has(name)).slice(0, GUIDE_TOOLS_PER_INTENT);
    if (tools.length === 0) return [];
    const names = tools.map((name) => `\`${name}\`${deferred.has(name) ? DEFERRED_MARK : ""}`).join(", ");
    return [`- ${spec.label} (${spec.when}): ${names}`];
  });
  if (lines.length === 0) return null;
  const loading = [...deferred].some((name) => available.has(name) && toolIntents(name).length > 0)
    ? [`To load a request type's deferred tools, search with its words, for example \`tool_search\` "diagnosis task result evidence".`]
    : [];
  return [
    "Choose tools by what the current request asks. A conversation can move between these at any turn, or combine them: choose again for each request, and keep using tools already loaded. A tool not listed here is still available when it fits better.",
    ...lines,
    ...loading,
  ].join("\n");
}
