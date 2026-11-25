/**
 * `qdash_get_task_result_evidence`: the pi adapter of the SDK's
 * `qdash.taskResults.evidence(taskId, { cooldownId })`, which joins one task
 * result with its execution, the stored state of its target, and a named
 * cooldown, reporting every missing or failed part instead of filling it in.
 *
 * The SDK owns the reads and their semantics. This adapter only bounds the
 * values for a model, adds the QDash web links, and writes a short summary;
 * redaction is the shared `redact`.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashConnection } from "../lib/qdash-connection.js";
import type { TaskResultContext, TaskResultEvidence } from "@oqtopus-team/qdash-sdk";
import { Type } from "typebox";

import { qdashObjectLinks, qdashWebBaseUrl } from "../lib/links.js";
import { redact, toTextToolResult } from "../lib/results.js";
import { sdkSession, type SdkSessionFactory } from "../lib/sdk-session.js";
import { CONFIG_PATH_DESCRIPTION, PROFILE_DESCRIPTION } from "../lib/connection.js";

export const TASK_RESULT_EVIDENCE_TOOL = "qdash_get_task_result_evidence";

type EvidenceParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  taskId: string;
  cooldownId?: string;
};

export type TaskResultEvidenceDependencies = {
  makeClient(params: EvidenceParams): Promise<QDashConnection>;
  /** The SDK session for a resolved client; defaults to one with the client's settings. */
  sdk?: SdkSessionFactory;
};

type Json = Record<string, unknown>;

/** Bounds applied to every value the tool returns. */
export const EVIDENCE_BOUNDS = {
  maxDepth: 4,
  maxKeys: 40,
  maxArray: 20,
  maxString: 500,
  /** Stored outputs of the target that are shown. */
  maxOutputs: 30,
  /** Largest serialized evidence; larger parameter blocks are dropped first. */
  maxBytes: 24_000,
} as const;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  if (typeof value === "string" && value.length > 0) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return undefined;
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max)}… (+${text.length - max} chars)`;
}

/** `value` with long strings, arrays, objects, and deep nesting cut to the bounds. */
export function boundValue(value: unknown, depth = 0): unknown {
  if (typeof value === "string") return truncate(value, EVIDENCE_BOUNDS.maxString);
  if (Array.isArray(value)) {
    if (depth >= EVIDENCE_BOUNDS.maxDepth) return `[array of ${value.length}]`;
    const kept = value.slice(0, EVIDENCE_BOUNDS.maxArray).map((item) => boundValue(item, depth + 1));
    return value.length > kept.length ? [...kept, `… (+${value.length - kept.length} more)`] : kept;
  }
  if (isObject(value)) {
    const entries = Object.entries(value);
    if (depth >= EVIDENCE_BOUNDS.maxDepth) return `[object with ${entries.length} keys]`;
    const out = Object.fromEntries(
      entries.slice(0, EVIDENCE_BOUNDS.maxKeys).map(([key, item]) => [key, boundValue(item, depth + 1)]),
    ) as Json;
    if (entries.length > EVIDENCE_BOUNDS.maxKeys) out["…"] = `+${entries.length - EVIDENCE_BOUNDS.maxKeys} more keys`;
    return out;
  }
  return value;
}

function pick(object: unknown, keys: readonly string[]): Json {
  if (!isObject(object)) return {};
  return Object.fromEntries(keys.filter((key) => object[key] !== undefined).map((key) => [key, boundValue(object[key])]));
}

function countBy(items: unknown[], key: string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const value = isObject(item) ? str(item[key]) ?? "unknown" : "unknown";
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

/** A context part with its value reduced by `present`; absent parts are kept as the SDK reports them. */
function presentPart<T>(part: TaskResultContext<T>, present: (value: T) => Json): Json {
  // The part's own status comes last, so a value's `status` field cannot replace it.
  return part.status === "ok" ? { ...present(part.value), status: "ok" } : { ...part };
}

function presentResult(result: Json): Json {
  const count = (key: string) => (Array.isArray(result[key]) ? (result[key] as unknown[]).length : 0);
  const stack = str(result.stack_trace);
  return {
    ...pick(result, [
      "task_name", "status", "flow_name", "username",
      "start_at", "end_at", "elapsed_time", "message", "tags",
      "output_parameter_names", "output_parameters", "input_parameters", "run_parameters", "invocation",
    ]),
    // Identifiers must stay whole. The final budget pass can omit them, but
    // string truncation would manufacture a different identifier.
    ...Object.fromEntries(
      ["task_id", "qid", "chip_id", "execution_id", "source_task_id"]
        .filter((key) => result[key] !== undefined)
        .map((key) => [key, result[key]]),
    ),
    re_execution_count: count("re_executions"),
    re_executions: boundValue(result.re_executions ?? []),
    stack_trace: stack ? { present: true, tail: stack.length > 1500 ? `…${stack.slice(-1500)}` : stack } : { present: false },
    figures: {
      figure_count: count("figure_path"),
      json_figure_count: count("json_figure_path"),
      raw_data_count: count("raw_data_path"),
      read_with: "qdash_get_task_figures or qdash_get_figure with this taskId",
    },
  };
}

/** The SDK evidence bounded for a model, with links and identifiers. */
export function presentEvidence(evidence: TaskResultEvidence, links: Record<string, string>): Json {
  const result = evidence.result as unknown as Json;
  const presented: Json = {
    task_id: evidence.taskId,
    result: presentResult(result),
    execution: presentPart(evidence.execution, ({ execution, task, chipMatches }) => {
      const tasks = Array.isArray(execution.task) ? execution.task : [];
      return {
        execution_id: str(result.execution_id),
        execution_status: typeof execution.status === "string" ? execution.status : undefined,
        ...pick(execution, [
          "name", "flow_name", "chip_id", "username", "start_at", "end_at", "elapsed_time", "message", "tags",
          "pipeline", "agent_session", "calibration_session",
        ]),
        task_count: tasks.length,
        task_status_counts: countBy(tasks, "status"),
        this_task: task ? pick(task, ["task_id", "name", "task_type", "qid", "status", "message", "upstream_id", "start_at", "end_at"]) : null,
        ...(task ? {} : { this_task_note: "The execution does not list this task result." }),
        chip_matches_result: chipMatches,
      };
    }),
    target: presentPart(evidence.target, (target) => {
      const names = Object.keys(target.outputs);
      const shown = names.slice(0, EVIDENCE_BOUNDS.maxOutputs);
      const state = target.state as unknown as Json;
      return {
        kind: target.kind,
        id: target.id,
        kind_source: target.kindSource,
        chip_id: str(state.chip_id),
        state_status: str(state.status),
        stored_parameter_count: isObject(state.data) ? Object.keys(state.data).length : 0,
        stored_values_for_outputs: Object.fromEntries(
          shown.map((name) => [name, { stored: boundValue(target.outputs[name]!.stored), from_this_result: target.outputs[name]!.fromThisResult }]),
        ),
        outputs_not_stored: boundValue(target.outputsNotStored),
        ...(names.length > shown.length ? { outputs_omitted: names.length - shown.length } : {}),
        note: "Current stored values; they may come from a later result. from_this_result is null when the stored entry names no task.",
      };
    }),
    cooldown: presentPart(evidence.cooldown, ({ cooldown, checks }) => ({
      ...pick(cooldown, ["cooldown_id", "cryo_id", "started_at", "ended_at", "chip_ids", "description"]),
      association: "named by the caller",
      checks: { chip_listed_in_cooldown: checks.chipListed, result_start_within_cooldown: checks.resultStartWithin },
      note: "The checks say whether the named cooldown is consistent with the result; QDash does not report that the result was recorded in it.",
    })),
    links,
    identifiers: {
      task_id: evidence.taskId,
      execution_id: str(result.execution_id) ?? null,
      chip_id: str(result.chip_id) ?? null,
      qid: str(result.qid) ?? null,
      cooldown_id: evidence.cooldown.status === "ok" ? str((evidence.cooldown.value.cooldown as unknown as Json).cooldown_id) ?? null : null,
    },
  };
  return fitToBound(redact(presented) as Json);
}

function byteLength(value: unknown): number {
  return new TextEncoder().encode(JSON.stringify(value) ?? "").length;
}

/** Drop the largest optional blocks until the evidence fits the byte bound, saying what was dropped. */
function fitToBound(evidence: Json): Json {
  if (byteLength(evidence) <= EVIDENCE_BOUNDS.maxBytes) return evidence;
  const result = { ...(evidence.result as Json) };
  const fitted: Json = { ...evidence, result };
  const omitted: string[] = [];
  for (const key of ["run_parameters", "input_parameters", "invocation", "re_executions", "output_parameters"]) {
    if (!(key in result)) continue;
    delete result[key];
    omitted.push(key);
    if (byteLength(fitted) <= EVIDENCE_BOUNDS.maxBytes) break;
  }
  result.omitted_for_size = omitted;
  const target = fitted.target as Json;
  if (byteLength(fitted) > EVIDENCE_BOUNDS.maxBytes && target.status === "ok") {
    fitted.target = { ...target, stored_values_for_outputs: "omitted for size; read with qdash_list_chip_qubits or qdash_list_chip_couplings" };
  }
  if (byteLength(fitted) <= EVIDENCE_BOUNDS.maxBytes) return fitted;

  // Context errors, object keys, links, and execution metadata can exceed
  // the budget too. Keep only whole, small fields in an explicit fallback;
  // never truncate an identifier or URL into a different one.
  const compact: Json = {
    omitted_for_size: "Detailed evidence omitted to fit the byte budget. Read individual records for details.",
    result: {},
    links: {},
    identifiers: {},
  };
  for (const name of ["execution", "target", "cooldown"]) {
    const part = evidence[name] as Json;
    compact[name] = {
      status: part.status,
      omitted_for_size: true,
    };
  }
  const retain = (object: Json, key: string, value: unknown) => {
    if (value === undefined || byteLength(value) > 2048) return;
    object[key] = value;
    if (byteLength(compact) > EVIDENCE_BOUNDS.maxBytes) delete object[key];
  };
  retain(compact, "task_id", evidence.task_id);
  for (const key of ["task_id", "task_name", "status", "execution_id", "chip_id", "qid"]) {
    retain(compact.result as Json, key, (evidence.result as Json)[key]);
  }
  for (const key of ["task_id", "execution_id", "chip_id", "qid", "cooldown_id"]) {
    retain(compact.identifiers as Json, key, (evidence.identifiers as Json)[key]);
  }
  for (const key of ["task_result", "execution"]) {
    retain(compact.links as Json, key, (evidence.links as Json)[key]);
  }
  for (const name of ["execution", "target", "cooldown"]) {
    for (const key of ["error", "reason", "statusCode"]) {
      retain(compact[name] as Json, key, (evidence[name] as Json)[key]);
    }
  }
  return compact;
}

function partLine(label: string, part: Json, ok: (data: Json) => string): string {
  if (part.omitted_for_size) return `${label}: ${part.status}; details omitted for size.`;
  if (part.status === "ok") return `${label}: ${ok(part)}`;
  if (part.status === "failed") return `${label}: read failed (${truncate(String(part.error), 300)}); no other data is substituted.`;
  return `${label}: ${part.status === "not_associated" ? "not associated" : "not applicable"} — ${part.reason}`;
}

function formatValue(value: unknown): string {
  if (isObject(value) && "value" in value) {
    const unit = str(value.unit);
    return `${JSON.stringify(value.value)}${unit ? ` ${unit}` : ""}`;
  }
  return truncate(JSON.stringify(value) ?? "null", 80);
}

/** The presented evidence as a short summary followed by its JSON. */
export function evidenceText(evidence: Json): string {
  const result = evidence.result as Json;
  const outputs = isObject(result.output_parameters) ? Object.entries(result.output_parameters).slice(0, 10) : [];
  const message = str(result.message);
  const links = isObject(evidence.links) ? Object.entries(evidence.links) : [];
  const target = str(result.qid) ? ` on ${str(result.qid)}` : "";
  const chip = str(result.chip_id) ? ` (chip ${str(result.chip_id)})` : "";
  return [
    `Task result ${str(result.task_id) ?? evidence.task_id} ${str(result.task_name) ?? ""}${target}${chip}: status ${str(result.status) ?? "unknown"}`,
    ...(message ? [`message: ${truncate(message, 300)}`] : []),
    ...(outputs.length ? [`outputs: ${outputs.map(([name, value]) => `${name}=${formatValue(value)}`).join(", ")}`] : []),
    partLine("execution", evidence.execution as Json, (data) =>
      `${str(data.execution_id) ?? ""} status ${str(data.execution_status) ?? "unknown"}, flow ${str(data.flow_name) ?? "-"}, ${data.task_count} tasks${data.this_task ? "" : "; this result is not listed in it"}`),
    partLine("target", evidence.target as Json, (data) =>
      `${data.kind} ${data.id} status ${str(data.state_status) ?? "unknown"}, ${Object.keys(isObject(data.stored_values_for_outputs) ? data.stored_values_for_outputs : {}).length} output parameters stored`),
    partLine("cooldown", evidence.cooldown as Json, (data) => {
      const checks = isObject(data.checks) ? data.checks : {};
      return `${str(data.cooldown_id)} named by the caller; chip listed: ${checks.chip_listed_in_cooldown}, result start within: ${checks.result_start_within_cooldown}`;
    }),
    ...(links.length ? [`links: ${links.map(([name, url]) => `${name} ${url}`).join("  ")}`] : []),
    "",
    JSON.stringify(evidence, null, 2),
  ].join("\n");
}

export function registerTaskResultEvidenceTool(pi: Pick<ExtensionAPI, "registerTool">, deps: TaskResultEvidenceDependencies): void {
  pi.registerTool({
    name: TASK_RESULT_EVIDENCE_TOOL,
    label: "QDash Task Result Evidence",
    description:
      "Read one task result together with the context to diagnose it: its execution and this task's entry there, the current stored values of its qubit or coupling for the parameters it outputs, and a cooldown you name, checked against the result. Read-only and bounded. Each context part reports ok, failed, or why it does not apply; nothing is inferred or substituted, and the cooldown is never guessed.",
    promptSnippet: "Read a QDash task result with its execution, target, and cooldown context for diagnosis",
    promptGuidelines: [
      `Use ${TASK_RESULT_EVIDENCE_TOOL} when diagnosing or explaining one task result: why it failed, whether its values were stored, and what ran around it.`,
      "Report a context part that failed or does not apply as missing; do not fill it in from other results.",
      "The cooldown is reported only for a cooldownId you pass; QDash's task result does not say which cooldown it ran in.",
    ],
    parameters: Type.Object({
      profile: Type.Optional(Type.String({ description: PROFILE_DESCRIPTION })),
      configPath: Type.Optional(Type.String({ description: CONFIG_PATH_DESCRIPTION })),
      useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
      taskId: Type.String({ description: "Task result ID, as in qdash_list_task_results." }),
      cooldownId: Type.Optional(Type.String({ description: "A cooldown to check against the result, from qdash_list_cooldowns. Never inferred when omitted." })),
    }),
    async execute(_toolCallId, params: EvidenceParams) {
      const client = await deps.makeClient(params);
      const evidence = await (deps.sdk ?? sdkSession)(client).taskResults.evidence(params.taskId, params.cooldownId ? { cooldownId: params.cooldownId } : {});
      const result = evidence.result as unknown as Json;
      const executionId = str(result.execution_id);
      const chipId = str(result.chip_id);
      const links = qdashObjectLinks(client, {
        task_id: evidence.taskId,
        ...(executionId ? { execution_id: executionId } : {}),
        ...(chipId ? { chip_id: chipId } : {}),
      });
      const presented = presentEvidence(evidence, links);
      return toTextToolResult(evidenceText(presented), presented, { tool: TASK_RESULT_EVIDENCE_TOOL, webBaseUrl: qdashWebBaseUrl(client) });
    },
  });
}
