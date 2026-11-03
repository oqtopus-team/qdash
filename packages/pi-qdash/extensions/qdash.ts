import { randomUUID } from "node:crypto";
import { dirname, join } from "node:path";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";

import type { ExtensionAPI, Theme } from "@earendil-works/pi-coding-agent";
import {
  QDashClient,
  defaultConfigPath,
  type CooldownResponse,
  type DownloadedFile,
  type TaskResultFigureOptions,
} from "@oqtopus-team/qdash-client";
import { Text, truncateToWidth } from "@earendil-works/pi-tui";
import { Type } from "typebox";

import { analyzePlotlyFigure, figureAnalysisText } from "./lib/figure-analysis.js";
import { fetchFigureDetails, figureComponent, figureResultText, mediaTypeForPath, type FigureDetails } from "./lib/figures.js";
import { forumImageReplyContent, forumImageReplyPreview, loadLocalForumImages, type LocalForumImage } from "./lib/forum-images.js";
import { forumDetailComponent, forumDetailLines, forumListLines, forumPostTitle, forumPostsFromPayload } from "./lib/forum-render.js";
import { investigationContextSummary, validateInvestigationContext, type TimeseriesInvestigationContext } from "./lib/investigation-context.js";
import { executionPagePath, forumPostPagePath, qdashObjectLinks, qdashWebBaseUrl, qdashWebUrl, safeConfig, withQDashLinks } from "./lib/links.js";
import { arrayFromPayload, compactItems, firstNumber, firstString, formatItem, payloadTotal, statusIcon } from "./lib/payload.js";
import { toFigureToolResult, toTextToolResult, toToolResult } from "./lib/results.js";
import { ansi, boxLinesToWidth, boxed, formatNumber, textComponent } from "./lib/render.js";
import { plotSeriesLines, timeseriesPlotComponent, timeseriesPoints } from "./lib/timeseries-plot.js";
import { installQDashWriteGate } from "./lib/write-gate.js";
import { withAbort } from "./lib/abort.js";
import { qcalContextText, recordedParameters, sweepsOf, type RecordedParameter, type Sweep } from "./lib/qcal-evidence.js";
import { registerCalibrationPipelineTools } from "./tools/calibration-pipeline.js";
import { registerFlowAuthoringTools } from "./tools/flow-authoring.js";
import { registerTaskKnowledgeTool } from "./tools/task-knowledge.js";
import { registerTimeseriesComparisonTool } from "./tools/timeseries.js";
import { analyzeWiringMarkdown, wiringInsightLines, type WiringInsights } from "./lib/wiring-analysis.js";

type QDashQueryParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  action:
    | "chips"
    | "default_chip"
    | "metrics_config"
    | "chip_metrics"
    | "chip_qubits"
    | "chip_qubit"
    | "chip_couplings"
    | "chip_coupling"
    | "cryostats"
    | "cryostat"
    | "cooldowns"
    | "cooldown"
    | "cooldown_wiring_events"
    | "timeseries"
    | "task_results"
    | "task_result"
    | "task_note"
    | "qubit_latest"
    | "qubit_history"
    | "coupling_latest"
    | "coupling_history"
    | "tasks"
    | "task_knowledge"
    | "task_knowledge_markdown"
    | "projects"
    | "project"
    | "files_tree"
    | "file_content"
    | "git_status"
    | "flows"
    | "flow"
    | "flow_templates"
    | "flow_template"
    | "flow_helper_files"
    | "flow_helper_file"
    | "executions"
    | "execution"
    | "forum_posts"
    | "provenance_stats"
    | "provenance_history"
    | "provenance_changes"
    | "provenance_lineage"
    | "provenance_impact";
  chipId?: string;
  qid?: string;
  couplingId?: string;
  cryoId?: string;
  cooldownId?: string;
  taskId?: string;
  taskName?: string;
  task?: string;
  projectId?: string;
  path?: string;
  flowName?: string;
  templateId?: string;
  filename?: string;
  executionId?: string;
  entityId?: string;
  parameter?: string;
  parameterName?: string;
  tag?: string;
  date?: string;
  backend?: string;
  status?: string;
  username?: string;
  messageContains?: string;
  startAt?: string;
  endAt?: string;
  startFrom?: string;
  startTo?: string;
  withinHours?: number;
  limit?: number;
  skip?: number;
  offset?: number;
};

type RawGetParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  path: string;
  query?: Record<string, string | number | boolean | null | undefined>;
};

type ConfirmableParams = {
  confirmWrite?: boolean;
};

type QDashContextState = {
  profile?: string;
  chipId?: string;
  agentSessionId?: string;
  qid?: string;
  couplingId?: string;
  taskName?: string;
  lastExecutionId?: string;
  lastTaskId?: string;
  investigation?: TimeseriesInvestigationContext;
};

const CONTEXT_ENTRY_TYPE = "qdash-context";
const GLOBAL_CONTEXT_PATH = join(homedir(), ".pi", "agent", "qdash-context.json");
let currentContext: QDashContextState = {};

function applyQDashContext<T extends { profile?: string; chipId?: string; sessionId?: string }>(params: T): T {
  return {
    ...params,
    profile: params.profile ?? currentContext.profile,
    chipId: params.chipId ?? currentContext.chipId,
    sessionId: params.sessionId ?? currentContext.agentSessionId,
  };
}

function contextSummary(): string {
  const profile = currentContext.profile ?? "env/default";
  const chip = currentContext.chipId ?? "auto-chip";
  const session = currentContext.agentSessionId ? ` session:${shortId(currentContext.agentSessionId)}` : "";
  const target = currentContext.qid ? ` q${currentContext.qid}` : currentContext.couplingId ? ` c${currentContext.couplingId}` : "";
  const investigation = currentContext.investigation?.name ? ` investigation:${currentContext.investigation.name}` : "";
  return `qdash ${profile} ${chip}${target}${session}${investigation}`;
}

function contextStatusLine(theme?: Theme): string {
  const accent = (value: string) => theme ? theme.fg("accent", value) : value;
  const dim = (value: string) => theme ? theme.fg("dim", value) : value;
  const success = (value: string) => theme ? theme.fg("success", value) : value;
  const warn = (value: string) => theme ? theme.fg("warning", value) : value;
  const profile = currentContext.profile ?? (shouldUseEnv({}) ? "env" : "default");
  const chip = currentContext.chipId ?? "auto";
  const session = currentContext.agentSessionId ? shortId(currentContext.agentSessionId, 8) : "none";
  const target = currentContext.qid ? `q${currentContext.qid}` : currentContext.couplingId ? `c${currentContext.couplingId}` : "none";
  const profileText = `${dim("profile")} ${success(profile)}`;
  const chipText = `${dim("chip")} ${currentContext.chipId ? success(chip) : warn(chip)}`;
  const targetText = `${dim("target")} ${currentContext.qid || currentContext.couplingId ? success(target) : dim(target)}`;
  const sessionText = `${dim("agent")} ${currentContext.agentSessionId ? success(session) : dim(session)}`;
  return [
    `${accent("◆")} ${accent("QDash")}`,
    `👤 ${profileText}`,
    `${accent("▣")} ${chipText}`,
    `🎯 ${targetText}`,
    `🤖 ${sessionText}`,
  ].join(dim("  │  "));
}

function isQDashContextState(value: unknown): value is QDashContextState {
  if (!value || typeof value !== "object") return false;
  const context = value as QDashContextState;
  const stringsValid = [context.profile, context.chipId, context.agentSessionId, context.qid, context.couplingId, context.taskName, context.lastExecutionId, context.lastTaskId]
    .every((item) => item === undefined || typeof item === "string");
  if (!stringsValid) return false;
  if (context.investigation === undefined) return true;
  try {
    validateInvestigationContext(context.investigation);
    return true;
  } catch {
    return false;
  }
}

function loadGlobalContext(): QDashContextState {
  try {
    if (!existsSync(GLOBAL_CONTEXT_PATH)) return {};
    const data = JSON.parse(readFileSync(GLOBAL_CONTEXT_PATH, "utf8"));
    return isQDashContextState(data) ? data : {};
  } catch {
    return {};
  }
}

function saveGlobalContext(context: QDashContextState): void {
  const { investigation: _investigation, ...globalContext } = context;
  mkdirSync(dirname(GLOBAL_CONTEXT_PATH), { recursive: true });
  writeFileSync(GLOBAL_CONTEXT_PATH, `${JSON.stringify(globalContext, null, 2)}\n`, "utf8");
}

function adoptContextFromToolInput(input: unknown): boolean {
  if (!input || typeof input !== "object") return false;
  const params = input as { profile?: unknown; chipId?: unknown; sessionId?: unknown; qid?: unknown; couplingId?: unknown; taskName?: unknown; taskId?: unknown; executionId?: unknown; useEnv?: unknown };
  let changed = false;

  if (typeof params.profile === "string" && params.profile.trim()) {
    const profile = params.profile.trim();
    if (currentContext.profile !== profile) {
      const { chipId: _chipId, ...rest } = currentContext;
      currentContext = { ...rest, profile };
      changed = true;
    }
  } else if (params.useEnv === true && currentContext.profile !== undefined) {
    const { profile: _profile, chipId: _chipId, ...rest } = currentContext;
    currentContext = rest;
    changed = true;
  }

  if (typeof params.chipId === "string" && params.chipId.trim() && currentContext.chipId !== params.chipId.trim()) {
    currentContext = { ...currentContext, chipId: params.chipId.trim() };
    changed = true;
  }

  if (typeof params.sessionId === "string" && params.sessionId.trim() && currentContext.agentSessionId !== params.sessionId.trim()) {
    currentContext = { ...currentContext, agentSessionId: params.sessionId.trim() };
    changed = true;
  }

  if (typeof params.qid === "string" && params.qid.trim() && currentContext.qid !== params.qid.trim()) {
    const { couplingId: _couplingId, ...rest } = currentContext;
    currentContext = { ...rest, qid: params.qid.trim() };
    changed = true;
  }

  if (typeof params.couplingId === "string" && params.couplingId.trim() && currentContext.couplingId !== params.couplingId.trim()) {
    const { qid: _qid, ...rest } = currentContext;
    currentContext = { ...rest, couplingId: params.couplingId.trim() };
    changed = true;
  }

  if (typeof params.taskName === "string" && params.taskName.trim() && currentContext.taskName !== params.taskName.trim()) {
    currentContext = { ...currentContext, taskName: params.taskName.trim() };
    changed = true;
  }

  if (typeof params.taskId === "string" && params.taskId.trim() && currentContext.lastTaskId !== params.taskId.trim()) {
    currentContext = { ...currentContext, lastTaskId: params.taskId.trim() };
    changed = true;
  }

  if (typeof params.executionId === "string" && params.executionId.trim() && currentContext.lastExecutionId !== params.executionId.trim()) {
    currentContext = { ...currentContext, lastExecutionId: params.executionId.trim() };
    changed = true;
  }

  return changed;
}

function shortId(value: string, length = 10): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

const QueryAction = Type.Union([
  Type.Literal("chips"),
  Type.Literal("default_chip"),
  Type.Literal("metrics_config"),
  Type.Literal("chip_metrics"),
  Type.Literal("chip_qubits"),
  Type.Literal("chip_qubit"),
  Type.Literal("chip_couplings"),
  Type.Literal("chip_coupling"),
  Type.Literal("cryostats"),
  Type.Literal("cryostat"),
  Type.Literal("cooldowns"),
  Type.Literal("cooldown"),
  Type.Literal("cooldown_wiring_events"),
  Type.Literal("timeseries"),
  Type.Literal("task_results"),
  Type.Literal("task_result"),
  Type.Literal("task_note"),
  Type.Literal("qubit_latest"),
  Type.Literal("qubit_history"),
  Type.Literal("coupling_latest"),
  Type.Literal("coupling_history"),
  Type.Literal("tasks"),
  Type.Literal("task_knowledge"),
  Type.Literal("task_knowledge_markdown"),
  Type.Literal("projects"),
  Type.Literal("project"),
  Type.Literal("files_tree"),
  Type.Literal("file_content"),
  Type.Literal("git_status"),
  Type.Literal("flows"),
  Type.Literal("flow"),
  Type.Literal("flow_templates"),
  Type.Literal("flow_template"),
  Type.Literal("flow_helper_files"),
  Type.Literal("flow_helper_file"),
  Type.Literal("executions"),
  Type.Literal("execution"),
  Type.Literal("forum_posts"),
  Type.Literal("provenance_stats"),
  Type.Literal("provenance_history"),
  Type.Literal("provenance_changes"),
  Type.Literal("provenance_lineage"),
  Type.Literal("provenance_impact"),
]);

const connectionParams = {
  profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
  configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

const paginationParams = {
  limit: Type.Optional(Type.Number()),
  skip: Type.Optional(Type.Number()),
  offset: Type.Optional(Type.Number()),
};

const chipScopedParams = {
  chipId: Type.Optional(Type.String({ description: "Chip ID. Defaults to the active/default chip when omitted." })),
};

const querySchema = Type.Object({
  ...connectionParams,
  action: QueryAction,
  chipId: Type.Optional(Type.String({ description: "Chip ID. Defaults to the active/default chip for chip-scoped actions when omitted." })),
  qid: Type.Optional(Type.String()),
  couplingId: Type.Optional(Type.String()),
  cryoId: Type.Optional(Type.String()),
  cooldownId: Type.Optional(Type.String()),
  taskId: Type.Optional(Type.String()),
  taskName: Type.Optional(Type.String()),
  task: Type.Optional(Type.String({ description: "Task parameter used by latest/history endpoints." })),
  projectId: Type.Optional(Type.String()),
  path: Type.Optional(Type.String({ description: "Project file path for file_content." })),
  flowName: Type.Optional(Type.String()),
  templateId: Type.Optional(Type.String()),
  filename: Type.Optional(Type.String()),
  executionId: Type.Optional(Type.String()),
  entityId: Type.Optional(Type.String()),
  parameter: Type.Optional(Type.String({ description: "Metric/parameter name for timeseries." })),
  parameterName: Type.Optional(Type.String()),
  tag: Type.Optional(Type.String()),
  date: Type.Optional(Type.String({ description: "History date, usually YYYYMMDD." })),
  backend: Type.Optional(Type.String()),
  status: Type.Optional(Type.String()),
  username: Type.Optional(Type.String()),
  messageContains: Type.Optional(Type.String()),
  startAt: Type.Optional(Type.String()),
  endAt: Type.Optional(Type.String()),
  startFrom: Type.Optional(Type.String()),
  startTo: Type.Optional(Type.String()),
  withinHours: Type.Optional(Type.Number()),
  limit: Type.Optional(Type.Number()),
  skip: Type.Optional(Type.Number()),
  offset: Type.Optional(Type.Number()),
});

function shouldUseEnv(params: { useEnv?: boolean; profile?: string; configPath?: string }): boolean {
  if (params.useEnv !== undefined) return params.useEnv;
  return !params.profile && !params.configPath && Boolean(process.env.QDASH_BASE_URL);
}

async function makeClient(params: { useEnv?: boolean; profile?: string; configPath?: string }): Promise<QDashClient> {
  params = applyQDashContext(params);
  if (shouldUseEnv(params)) return QDashClient.fromEnv();
  return QDashClient.fromProfile(params.profile ?? "default", params.configPath);
}

async function defaultChipId(client: QDashClient, chipId?: string): Promise<string> {
  return chipId ?? currentContext.chipId ?? client.getDefaultChipId();
}

// Keep arbitrary GET access isolated for qdash_raw_get and legacy filters that are
// not represented in the generated OpenAPI surface. Normal operations should use
// QDashClient's high-level methods or client.api so upgrades remain type-checked.
async function rawGet<T>(client: QDashClient, path: string, query?: Record<string, unknown>): Promise<T> {
  return (client as unknown as { get<T>(path: string, query?: Record<string, unknown>): Promise<T> }).get(path, cleanQuery(query));
}

type TaskResultFigureFile = DownloadedFile & {
  path: string;
  figurePaths: string[];
  jsonFigurePaths: string[];
};

type CalibrationEvidence = {
  id?: string;
  source: string;
  target?: Record<string, unknown>;
  task?: Record<string, unknown>;
  metrics?: Record<string, number | string | boolean | null>;
  parameters?: Record<string, number | string | boolean | null>;
  /** The run parameters as recorded, with units and value types. */
  runParameters?: Record<string, RecordedParameter>;
  /** The calibration inputs as recorded (previous values), with units. */
  inputParameters?: Record<string, RecordedParameter>;
  /** The output parameters as recorded (fitted results), with units. */
  metricRecords?: Record<string, RecordedParameter>;
  /** The swept parameters among them: the axes the plot was taken along. */
  sweeps?: Sweep[];
  resultJson?: unknown;
  figures?: Array<Record<string, unknown>>;
  logs?: string[];
  notes?: string;
  history?: Array<Record<string, unknown>>;
};

function parameterValueRecord(value: unknown): Record<string, number | string | boolean | null> {
  const output: Record<string, number | string | boolean | null> = {};
  const input = value && typeof value === "object" ? value as Record<string, unknown> : {};
  for (const [key, raw] of Object.entries(input)) {
    const object = raw && typeof raw === "object" ? raw as Record<string, unknown> : undefined;
    const candidate = object && "value" in object ? object.value : raw;
    if (typeof candidate === "number" || typeof candidate === "string" || typeof candidate === "boolean" || candidate === null) output[key] = candidate;
  }
  return output;
}

function firstStringField(object: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = object[key];
    if (typeof value === "string" && value) return value;
  }
  return undefined;
}

/**
 * The evidence text, used as the context of `qcal_evaluate`: the task, the
 * target, the sweep and the run settings. Fitted results and calibration
 * inputs are left out unless asked for, since the evaluation model is meant
 * to read them off the plot.
 */
function qcalEvidenceText(evidence: CalibrationEvidence, include: { inputs?: boolean; metrics?: boolean } = {}): string {
  return qcalContextText({
    taskName: typeof evidence.task?.name === "string" ? evidence.task.name : undefined,
    status: typeof evidence.task?.status === "string" ? evidence.task.status : undefined,
    targetKind: typeof evidence.target?.kind === "string" ? evidence.target.kind : undefined,
    targetId: typeof evidence.target?.id === "string" ? evidence.target.id : undefined,
    chipId: typeof evidence.target?.chipId === "string" ? evidence.target.chipId : undefined,
    runParameters: evidence.runParameters ?? {},
    ...(include.inputs ? { inputParameters: recordedParameters(evidence.inputParameters) } : {}),
    ...(include.metrics ? { metrics: recordedParameters(evidence.metricRecords) } : {}),
    message: typeof evidence.task?.message === "string" ? evidence.task.message : undefined,
  });
}

function cleanQuery(values: Record<string, unknown> = {}): Record<string, unknown> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== null));
}

function pathPart(value: string): string {
  return encodeURIComponent(value);
}

function requireValue(value: string | undefined, name: string): string {
  if (!value) throw new Error(`${name} is required for this QDash action`);
  return value;
}

type CooldownWiringParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  chipId?: string;
  cryoId?: string;
  cooldownId?: string;
  includeBlocks?: boolean;
  includeHistory?: boolean;
  historyLimit?: number;
  includeInsights?: boolean;
};

type WiringInsightParams = CooldownWiringParams & {
  color?: boolean;
};

function newestCooldown(cooldowns: CooldownResponse[]): CooldownResponse | undefined {
  return [...cooldowns].sort((a, b) => {
    const activeDifference = Number(a.ended_at != null) - Number(b.ended_at != null);
    if (activeDifference !== 0) return activeDifference;
    return Date.parse(b.started_at || "") - Date.parse(a.started_at || "");
  })[0];
}

async function resolveCooldownWiring(params: CooldownWiringParams) {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  let selection: string;
  let cooldown: CooldownResponse;
  let resolvedChipId = params.chipId ?? currentContext.chipId;

  if (params.cooldownId) {
    cooldown = await client.api.getCooldown(params.cooldownId);
    selection = "explicit cooldownId";
  } else {
    resolvedChipId = params.chipId ?? (params.cryoId ? undefined : await defaultChipId(client));
    const response = await client.api.listCooldowns({
      cryo_id: params.cryoId,
      chip_id: resolvedChipId,
    });
    const selected = newestCooldown(response.cooldowns ?? []);
    if (!selected) {
      const scope = params.cryoId ? `cryo ${params.cryoId}` : `chip ${resolvedChipId}`;
      throw new Error(`No cooldown containing wiring information was found for ${scope}`);
    }
    cooldown = await client.api.getCooldown(selected.cooldown_id);
    selection = params.cryoId ? "active/newest cooldown for cryo" : "active/newest cooldown for chip";
  }

  const blocks = Array.isArray(cooldown.wiring_blocks) ? cooldown.wiring_blocks : [];
  const wiringInfo = typeof cooldown.wiring_info === "string" ? cooldown.wiring_info.trim() : "";
  const includeBlocks = params.includeBlocks === true || !wiringInfo;
  const history = params.includeHistory
    ? await client.api.listCooldownWiringEvents(cooldown.cooldown_id, {
        limit: params.historyLimit ?? 20,
        skip: 0,
      })
    : undefined;
  let cryostat: unknown;
  try {
    cryostat = await client.api.getCryostat(cooldown.cryo_id);
  } catch {
    // Wiring remains useful on servers where cryostat detail is not accessible.
  }

  const insights = params.includeInsights === true ? analyzeWiringMarkdown(wiringInfo || undefined) : undefined;

  return {
    selection: {
      strategy: selection,
      requested_chip_id: resolvedChipId,
      requested_cryo_id: params.cryoId,
      resolved_cooldown_id: cooldown.cooldown_id,
    },
    cryostat,
    cooldown: {
      cooldown_id: cooldown.cooldown_id,
      cryo_id: cooldown.cryo_id,
      description: cooldown.description,
      started_at: cooldown.started_at,
      ended_at: cooldown.ended_at,
      chip_ids: cooldown.chip_ids ?? [],
    },
    wiring: {
      markdown: wiringInfo || undefined,
      block_count: blocks.length,
      blocks: includeBlocks ? blocks : undefined,
      blocks_omitted: !includeBlocks && blocks.length > 0,
    },
    insights,
    history,
  };
}

function configProfiles(configPath = defaultConfigPath()): { path: string; exists: boolean; profiles: string[] } {
  if (!existsSync(configPath)) return { path: configPath, exists: false, profiles: [] };
  const contents = readFileSync(configPath, "utf8");
  const profiles = [...contents.matchAll(/^\s*\[([^\]]+)]\s*$/gm)].map((m) => m[1]);
  return { path: configPath, exists: true, profiles };
}

async function buildDashboard(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number }) {
  params = applyQDashContext(params);
  const limit = params.limit ?? 5;
  const client = await makeClient(params);
  const chipId = await defaultChipId(client, params.chipId);
  const [chips, openThreads, recentExecutions, failedTaskResults, provenanceStats] = await Promise.allSettled([
    client.listChips(),
    client.listForumPosts({ chipId, status: "open", limit }),
    client.api.listExecutions({ chip_id: chipId, limit }),
    client.api.listTaskResults({ chip_id: chipId, status: "failed", limit }),
    client.getProvenanceStats(),
  ]);
  const value = <T>(result: PromiseSettledResult<T>): T | { error: string } => result.status === "fulfilled" ? result.value : { error: result.reason instanceof Error ? result.reason.message : String(result.reason) };
  const threadsPayload = value(openThreads);
  const executionsPayload = value(recentExecutions);
  const failedTasksPayload = value(failedTaskResults);
  return {
    context: { ...currentContext, profile: params.profile ?? currentContext.profile, chipId },
    chips: value(chips),
    openThreads: {
      count: payloadTotal(threadsPayload),
      shown: arrayFromPayload(threadsPayload).length,
      items: compactItems(threadsPayload, ["number", "title", "category", "target_type", "target_id", "created_at"], limit),
      raw: threadsPayload,
    },
    recentExecutions: {
      count: payloadTotal(executionsPayload),
      shown: arrayFromPayload(executionsPayload).length,
      items: compactItems(executionsPayload, ["execution_id", "flow_run_id", "flow_name", "status", "created_at", "started_at", "finished_at"], limit),
      raw: executionsPayload,
    },
    failedTaskResults: {
      count: payloadTotal(failedTasksPayload),
      shown: arrayFromPayload(failedTasksPayload).length,
      items: compactItems(failedTasksPayload, ["task_id", "task_name", "status", "qid", "coupling_id", "start_at", "created_at"], limit),
      raw: failedTasksPayload,
    },
    provenanceStats: value(provenanceStats),
  };
}

function dashboardLines(dashboard: Awaited<ReturnType<typeof buildDashboard>>, color = false): string[] {
  const chips = arrayFromPayload(dashboard.chips);
  const profile = dashboard.context.profile ?? "env/default";
  const session = dashboard.context.agentSessionId ? shortId(dashboard.context.agentSessionId) : "none";
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const dim = (text: string) => color ? ansi("2", text) : text;
  const success = (text: string) => color ? ansi("32", text) : text;
  const warning = (text: string) => color ? ansi("33", text) : text;
  const error = (text: string) => color ? ansi("31", text) : text;
  const threadCount = dashboard.openThreads.count > 0 ? warning(String(dashboard.openThreads.count)) : success(String(dashboard.openThreads.count));
  const failedCount = dashboard.failedTaskResults.count > 0 ? error(`${dashboard.failedTaskResults.shown}/${dashboard.failedTaskResults.count}`) : success(`${dashboard.failedTaskResults.shown}/${dashboard.failedTaskResults.count}`);
  return boxed("QDash Harness", [
    `${muted("profile")} ${accent(profile)}   ${muted("chip")} ${accent(dashboard.context.chipId)}   ${muted("session")} ${dim(session)}`,
    `${muted("chips")} ${success(String(chips.length))}   ${muted("open threads")} ${threadCount}   ${muted("executions")} ${accent(`${dashboard.recentExecutions.shown}/${dashboard.recentExecutions.count}`)}   ${muted("failed tasks")} ${failedCount}`,
    "",
    accent("Open Forum threads"),
    ...(dashboard.openThreads.items.length > 0 ? dashboard.openThreads.items.map((item, index) => `  ${warning(formatItem(item, `thread-${index + 1}`))}`) : [`  ${dim("none")}`]),
    "",
    accent("Recent executions"),
    ...(dashboard.recentExecutions.items.length > 0 ? dashboard.recentExecutions.items.map((item, index) => `  ${muted(formatItem(item, `exec-${index + 1}`))}`) : [`  ${dim("none")}`]),
    "",
    accent("Failed task results"),
    ...(dashboard.failedTaskResults.items.length > 0 ? dashboard.failedTaskResults.items.map((item, index) => `  ${error(formatItem(item, `task-${index + 1}`))}`) : [`  ${dim("none")}`]),
  ], color);
}

function styledDashboardLines(dashboard: Awaited<ReturnType<typeof buildDashboard>>, theme: Theme): string[] {
  const chips = arrayFromPayload(dashboard.chips);
  const profile = dashboard.context.profile ?? "env/default";
  const session = dashboard.context.agentSessionId ? shortId(dashboard.context.agentSessionId) : "none";
  const threadColor = dashboard.openThreads.count > 0 ? "warning" : "success";
  const failedColor = dashboard.failedTaskResults.count > 0 ? "error" : "success";
  return [
    theme.fg("accent", theme.bold("QDash Harness")),
    `${theme.fg("muted", "profile")} ${theme.fg("accent", profile)}  ${theme.fg("muted", "chip")} ${theme.fg("accent", dashboard.context.chipId)}  ${theme.fg("muted", "session")} ${theme.fg("dim", session)}`,
    "",
    [
      `${theme.fg("muted", "chips")} ${theme.fg("success", String(chips.length))}`,
      `${theme.fg("muted", "open threads")} ${theme.fg(threadColor, String(dashboard.openThreads.count))}`,
      `${theme.fg("muted", "executions")} ${theme.fg("accent", `${dashboard.recentExecutions.shown}/${dashboard.recentExecutions.count}`)}`,
      `${theme.fg("muted", "failed tasks")} ${theme.fg(failedColor, `${dashboard.failedTaskResults.shown}/${dashboard.failedTaskResults.count}`)}`,
    ].join("   "),
    "",
    theme.fg("borderAccent", "Open Forum threads"),
    ...(dashboard.openThreads.items.length > 0
      ? dashboard.openThreads.items.map((item, index) => `  ${theme.fg("warning", formatItem(item, `thread-${index + 1}`))}`)
      : [`  ${theme.fg("dim", "none")}`]),
    "",
    theme.fg("borderAccent", "Recent executions"),
    ...(dashboard.recentExecutions.items.length > 0
      ? dashboard.recentExecutions.items.map((item, index) => `  ${theme.fg("muted", formatItem(item, `exec-${index + 1}`))}`)
      : [`  ${theme.fg("dim", "none")}`]),
    "",
    theme.fg("borderAccent", "Failed task results"),
    ...(dashboard.failedTaskResults.items.length > 0
      ? dashboard.failedTaskResults.items.map((item, index) => `  ${theme.fg("error", formatItem(item, `task-${index + 1}`))}`)
      : [`  ${theme.fg("dim", "none")}`]),
  ];
}

function dashboardComponent(dashboard: Awaited<ReturnType<typeof buildDashboard>>, theme: Theme) {
  return {
    render(width: number) {
      const border = theme.fg("borderMuted", "─".repeat(Math.max(0, Math.min(width, 80))));
      return [border, ...styledDashboardLines(dashboard, theme), border].map((line) => truncateToWidth(line, width));
    },
    invalidate() {},
  };
}

type RecentCalibrationSummary = {
  context: { profile?: string; chipId: string; webBaseUrl: string };
  items: Record<string, unknown>[];
  groups: Array<{ target: string; status: string; summary: string; latest: Record<string, unknown>; links: Record<string, string> }>;
};

function calibrationTarget(item: Record<string, unknown>): string {
  const qid = firstString(item, ["qid"]);
  if (qid) return `q${qid}`;
  const coupling = firstString(item, ["coupling_id", "couplingId"]);
  if (coupling) return `c${coupling}`;
  return "global";
}

function calibrationSummaryForTarget(items: Record<string, unknown>[]): { status: string; summary: string; latest: Record<string, unknown> } {
  const latest = items[0] ?? {};
  const latestTask = firstString(latest, ["task_name", "name"]) ?? "task";
  const latestStatus = firstString(latest, ["status"]) ?? "unknown";
  const latestMessage = firstString(latest, ["message"]);
  const hadFailedRabi = items.some((item) => firstString(item, ["task_name", "name"]) === "CheckRabi" && firstString(item, ["status"]) === "failed");
  const hasConfigure = items.some((item) => firstString(item, ["task_name", "name"]) === "Configure" && firstString(item, ["status"]) === "completed");
  const latestIsSuccessfulRabi = latestTask === "CheckRabi" && latestStatus === "completed";
  if (latestIsSuccessfulRabi && (hadFailedRabi || hasConfigure)) {
    return { status: "recovered", summary: "CheckRabi completed after recovery sequence", latest };
  }
  if (latestStatus === "failed" && ["CheckChevron", "CheckQubitSpectroscopy"].includes(latestTask)) {
    return { status: "blocked", summary: latestMessage ?? `${latestTask} failed; stop and review figures/settings`, latest };
  }
  if (latestStatus === "failed") return { status: "failed", summary: latestMessage ?? `${latestTask} failed`, latest };
  if (latestStatus === "completed") return { status: "ok", summary: `${latestTask} completed`, latest };
  return { status: latestStatus, summary: `${latestTask} ${latestStatus}`, latest };
}

async function buildRecentCalibrationSummary(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number; withinHours?: number }): Promise<RecentCalibrationSummary> {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  const chipId = await defaultChipId(client, params.chipId);
  const end = new Date();
  const start = new Date(end.getTime() - (params.withinHours ?? 24) * 3600_000);
  const payload = await client.api.listTaskResults({ chip_id: chipId, start_from: start.toISOString(), start_to: end.toISOString(), limit: params.limit ?? 30 });
  const items = arrayFromPayload(payload).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  const byTarget = new Map<string, Record<string, unknown>[]>();
  for (const item of items) {
    const target = calibrationTarget(item);
    byTarget.set(target, [...(byTarget.get(target) ?? []), item]);
  }
  const groups = [...byTarget.entries()].map(([target, targetItems]) => {
    const result = calibrationSummaryForTarget(targetItems);
    return { target, ...result, links: qdashObjectLinks(client, result.latest) };
  });
  return { context: { profile: params.profile ?? currentContext.profile, chipId, webBaseUrl: qdashWebBaseUrl(client) }, items, groups };
}

function recentCalibrationSummaryLines(summary: RecentCalibrationSummary, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const statusMark = (status: string) => status === "recovered" || status === "ok" ? "✓" : status === "blocked" || status === "failed" ? "✗" : "•";
  const body = [
    `${muted("profile")} ${accent(summary.context.profile ?? "env/default")}  ${muted("chip")} ${accent(summary.context.chipId)}`,
    `${muted("url")} ${summary.context.webBaseUrl}`,
    "",
    ...(summary.groups.length > 0 ? summary.groups.map((group) => {
      const task = firstString(group.latest, ["task_name", "name"]);
      const exec = firstString(group.latest, ["execution_id"]);
      const taskUrl = group.links.task_result;
      const execUrl = group.links.execution;
      return [
        `${statusMark(group.status)} ${accent(group.target)} ${muted(`[${group.status}]`)} ${task ? `${task}: ` : ""}${group.summary}`,
        taskUrl ? `    ${muted("task")} ${taskUrl}` : undefined,
        execUrl ? `    ${muted("exec")} ${execUrl}` : exec ? `    ${muted("exec")} ${exec}` : undefined,
      ].filter(Boolean).join("\n");
    }) : [muted("no recent calibration task results")]),
  ];
  return boxed("QDash Recent Calibration", body.flatMap((line) => line.split("\n")), color);
}

function recentCalibrationSummaryComponent(summary: RecentCalibrationSummary, theme: Theme) {
  return {
    render(width: number) {
      return recentCalibrationSummaryLines(summary).map((line) => truncateToWidth(line, width));
    },
    invalidate() {},
  };
}

type CalibrationComparison = {
  context: { profile?: string; chipId: string; webBaseUrl: string };
  target: { kind: "qubit" | "coupling"; id: string; label: string };
  compared: Array<{ task: string; before: Record<string, unknown>; after: Record<string, unknown>; changes: Record<string, { before: unknown; after: unknown }> }>;
};

async function buildCalibrationComparison(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number }): Promise<CalibrationComparison> {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  const chipId = await defaultChipId(client, params.chipId);
  const qid = params.qid ?? (params.couplingId ? undefined : currentContext.qid);
  const couplingId = params.couplingId ?? (params.qid ? undefined : currentContext.couplingId);
  if (!qid && !couplingId) throw new Error("qid or couplingId is required (or select one with /qdash-use-target)");
  const kind = qid ? "qubit" : "coupling";
  const id = (qid ?? couplingId) as string;
  const results = await client.listTaskResults({ chipId, qid, couplingId, limit: Math.max(2, Math.min(100, params.limit ?? 20)) });
  const items = arrayFromPayload(results).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  const groups = new Map<string, Record<string, unknown>[]>();
  for (const item of items) {
    const task = firstString(item, ["task_name", "name"]) ?? "task";
    groups.set(task, [...(groups.get(task) ?? []), item]);
  }
  const compared = [...groups.entries()].flatMap(([task, entries]) => {
    if (entries.length < 2) return [];
    const after = entries[0];
    const before = entries[1];
    const beforeParams = (before.output_parameters ?? {}) as Record<string, unknown>;
    const afterParams = (after.output_parameters ?? {}) as Record<string, unknown>;
    const changes: Record<string, { before: unknown; after: unknown }> = {};
    for (const name of new Set([...Object.keys(beforeParams), ...Object.keys(afterParams)])) {
      const beforeValue = parameterValue(beforeParams[name]);
      const afterValue = parameterValue(afterParams[name]);
      if (JSON.stringify(beforeValue) !== JSON.stringify(afterValue)) changes[name] = { before: beforeValue, after: afterValue };
    }
    return [{ task, before, after, changes }];
  });
  return { context: { profile: params.profile ?? currentContext.profile, chipId, webBaseUrl: qdashWebBaseUrl(client) }, target: { kind, id, label: kind === "qubit" ? `q${id}` : `c${id}` }, compared };
}

function parameterValue(value: unknown): unknown {
  if (value && typeof value === "object" && "value" in value) return (value as { value?: unknown }).value;
  return value;
}

function calibrationComparisonLines(comparison: CalibrationComparison, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const lines = [`profile ${comparison.context.profile ?? "env/default"}  chip ${comparison.context.chipId}`, `target ${comparison.target.label}`, ""];
  if (comparison.compared.length === 0) lines.push(muted("Not enough repeated task results to compare."));
  for (const item of comparison.compared) {
    lines.push(accent(item.task));
    const beforeId = firstString(item.before, ["task_id", "id"]) ?? "before";
    const afterId = firstString(item.after, ["task_id", "id"]) ?? "after";
    lines.push(`  before ${shortId(beforeId, 18)}  after ${shortId(afterId, 18)}`);
    const changes = Object.entries(item.changes);
    if (changes.length === 0) lines.push(`  ${muted("no output-parameter changes")}`);
    else for (const [name, change] of changes) lines.push(`  ${name}: ${JSON.stringify(change.before)} → ${JSON.stringify(change.after)}`);
  }
  return boxed("QDash Calibration Comparison", lines, color);
}

type InvestigationReport = {
  context: { profile?: string; chipId: string; webBaseUrl: string };
  recent: RecentCalibrationSummary;
  target?: TargetOperationsReport;
  insights?: DashboardInsightsResult;
};

async function buildInvestigationReport(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number }): Promise<InvestigationReport> {
  params = applyQDashContext(params);
  const recent = await buildRecentCalibrationSummary(params);
  const qid = params.qid ?? currentContext.qid;
  const couplingId = params.couplingId ?? currentContext.couplingId;
  if (qid || couplingId) {
    const target = await buildTargetOperationsReport({ ...params, qid, couplingId });
    return { context: recent.context, recent, target };
  }
  const insights = await buildDashboardInsights(params);
  return { context: recent.context, recent, insights };
}

function investigationLines(report: InvestigationReport, color = false): string[] {
  const sections = boxed("QDash Investigation", [
    `profile ${report.context.profile ?? "env/default"}  chip ${report.context.chipId}`,
    "",
    "Recent calibration",
    ...recentCalibrationSummaryLines(report.recent, color).slice(2, -1),
    ...(report.target ? ["", ...targetOperationsReportLines(report.target, color).slice(2, -1)] : []),
    ...(report.insights ? ["", ...dashboardInsightLines(report.insights, color).slice(2, -1)] : []),
    "",
    "read-only investigation; no task execution or parameter changes",
  ], color);
  return sections;
}

type TargetOperationsReport = {
  context: { profile?: string; chipId: string; webBaseUrl: string };
  target: { kind: "qubit" | "coupling"; id: string; label: string };
  latestTarget: unknown;
  recentResults: Record<string, unknown>[];
  failures: Record<string, unknown>[];
  forumPosts: Record<string, unknown>[];
  recommendation: RecommendedNextAction | null;
};

type RecommendedNextAction = {
  target: string;
  recommendation: string;
  reason: string;
  status: string;
  links: Record<string, string>;
  latest?: Record<string, unknown>;
};

function recommendFromCalibrationSummary(summary: RecentCalibrationSummary, requestedTarget?: string): RecommendedNextAction[] {
  const groups = requestedTarget ? summary.groups.filter((group) => group.target === requestedTarget || group.target === `q${requestedTarget}` || group.target === `c${requestedTarget}`) : summary.groups;
  return groups.map((group) => {
    const task = firstString(group.latest, ["task_name", "name"]);
    const message = firstString(group.latest, ["message"]) ?? group.summary;
    if (group.status === "recovered") {
      return { target: group.target, status: "done", recommendation: "Inspect candidates; commit/apply only after explicit confirmation if this result should become authoritative.", reason: group.summary, links: group.links, latest: group.latest };
    }
    if (task === "CheckRabi" && group.status === "failed" && /non-finite|nan|R²|R2/i.test(message)) {
      return { target: group.target, status: "next", recommendation: "Run CheckChevron. If it succeeds, run Configure, then validate with CheckRabi.", reason: message, links: group.links, latest: group.latest };
    }
    if (task === "CheckChevron" && group.status === "blocked") {
      return { target: group.target, status: "stop", recommendation: "Stop automatic recovery; inspect figures and run/inspect CheckQubitSpectroscopy before Configure or Rabi retry.", reason: message, links: group.links, latest: group.latest };
    }
    if (task === "CheckQubitSpectroscopy" && group.status === "blocked") {
      return { target: group.target, status: "human", recommendation: "Request human review; frequency detection is outside operating range and candidates are unsafe.", reason: message, links: group.links, latest: group.latest };
    }
    if (group.status === "blocked" || group.status === "failed") {
      return { target: group.target, status: "review", recommendation: "Inspect task figures and recent history before another operational action.", reason: message, links: group.links, latest: group.latest };
    }
    return { target: group.target, status: "ok", recommendation: "No immediate recovery action suggested.", reason: group.summary, links: group.links, latest: group.latest };
  });
}

async function buildTargetOperationsReport(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number }): Promise<TargetOperationsReport> {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  const chipId = await defaultChipId(client, params.chipId);
  const qid = params.qid ?? (params.couplingId ? undefined : currentContext.qid);
  const couplingId = params.couplingId ?? (params.qid ? undefined : currentContext.couplingId);
  if (!qid && !couplingId) throw new Error("qid or couplingId is required (or select one with /qdash-use-target)");
  const kind = qid ? "qubit" : "coupling";
  const id = qid ?? couplingId as string;
  const label = kind === "qubit" ? `q${id}` : `c${id}`;
  const end = new Date();
  const start = new Date(end.getTime() - (params.withinHours ?? 168) * 3600_000);
  const limit = Math.max(1, Math.min(100, params.limit ?? 10));
  const [latestTarget, results, forumPosts] = await Promise.all([
    kind === "qubit" ? client.getChipQubit(chipId, id) : client.getChipCoupling(chipId, id),
    client.listTaskResults({ chipId, qid, couplingId, startAt: start.toISOString(), endAt: end.toISOString(), limit }),
    client.listForumPosts({ chipId, status: "open", targetType: kind, targetId: id, limit }),
  ]);
  const recentResults = arrayFromPayload(results).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  const summary: RecentCalibrationSummary = { context: { profile: params.profile ?? currentContext.profile, chipId, webBaseUrl: qdashWebBaseUrl(client) }, items: recentResults, groups: [] };
  const groups = new Map<string, Record<string, unknown>[]>();
  groups.set(label, recentResults);
  summary.groups = [...groups.entries()].map(([target, items]) => ({ target, ...calibrationSummaryForTarget(items), links: qdashObjectLinks(client, items[0] ?? {}) }));
  const recommendation = recommendFromCalibrationSummary(summary, label)[0] ?? null;
  return {
    context: summary.context,
    target: { kind, id, label },
    latestTarget,
    recentResults,
    failures: recentResults.filter((item) => firstString(item, ["status"])?.toLowerCase() === "failed"),
    forumPosts: forumPostsFromPayload(forumPosts),
    recommendation,
  };
}

function targetOperationsReportLines(report: TargetOperationsReport, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const warn = (text: string) => color ? ansi("33", text) : text;
  const error = (text: string) => color ? ansi("31", text) : text;
  const resultLine = (item: Record<string, unknown>) => {
    const task = firstString(item, ["task_name", "name"]) ?? "task";
    const status = firstString(item, ["status"]) ?? "unknown";
    const id = firstString(item, ["task_id", "taskId"]) ?? "";
    return `${statusIcon(status)} ${task} [${status}]${id ? ` ${shortId(id, 16)}` : ""}`;
  };
  return boxed(`QDash Target Report ${report.target.label}`, [
    `${muted("profile")} ${accent(report.context.profile ?? "env/default")}  ${muted("chip")} ${accent(report.context.chipId)}`,
    `${muted("results")} ${report.recentResults.length}  ${muted("failures")} ${report.failures.length ? error(String(report.failures.length)) : "0"}  ${muted("forum")} ${report.forumPosts.length ? warn(String(report.forumPosts.length)) : "0"}`,
    "",
    accent("Recent results"),
    ...(report.recentResults.length ? report.recentResults.slice(0, 10).map(resultLine) : [`  ${muted("none")}`]),
    "",
    accent("Recommendation"),
    ...(report.recommendation ? [`  ${report.recommendation.recommendation}`, `  ${muted("reason")} ${report.recommendation.reason}`] : [`  ${muted("no immediate action suggested")}`]),
  ], color);
}

type CalibrationPlanStep = {
  order: number;
  action: string;
  mode: "inspect" | "diagnostic" | "validate" | "stop";
  requiresConfirmation: boolean;
  reason: string;
};

type CalibrationPlan = {
  context: TargetOperationsReport["context"];
  target: TargetOperationsReport["target"];
  basis: string;
  steps: CalibrationPlanStep[];
  safety: string[];
};

function buildCalibrationPlan(report: TargetOperationsReport): CalibrationPlan {
  const latest = report.recentResults[0] ?? {};
  const task = firstString(latest, ["task_name", "name"]) ?? "";
  const message = firstString(latest, ["message"]) ?? "";
  const failed = report.failures.length > 0;
  const steps: CalibrationPlanStep[] = [{ order: 1, action: `Inspect ${report.target.label} report, figures, history, and forum context`, mode: "inspect", requiresConfirmation: false, reason: "Establish evidence before any operational action." }];

  if (report.target.kind === "qubit" && task === "CheckRabi" && failed && /non-finite|nan|r²|r2/i.test(message)) {
    steps.push(
      { order: 2, action: "CheckChevron", mode: "diagnostic", requiresConfirmation: true, reason: "Recover a non-finite Rabi fit using a same-target diagnostic." },
      { order: 3, action: "Configure", mode: "validate", requiresConfirmation: true, reason: "Only if CheckChevron succeeds with plausible estimates." },
      { order: 4, action: "CheckRabi", mode: "validate", requiresConfirmation: true, reason: "Validate the Chevron-derived operating point without committing candidates." },
    );
  } else if (report.target.kind === "coupling" && failed && /randomized|bell|zx90|cross.?resonance/i.test(`${task} ${message}`)) {
    for (const [index, action] of ["CheckCrossResonance", "CreateZX90", "CheckZX90", "CheckBellState", "CheckBellStateTomography", "ZX90InterleavedRandomizedBenchmarking"].entries()) {
      steps.push({ order: index + 2, action, mode: index === 0 ? "diagnostic" : "validate", requiresConfirmation: true, reason: "Walk back through two-qubit prerequisites before RB validation." });
    }
  } else if (report.recommendation?.status === "stop" || report.recommendation?.status === "human") {
    steps.push({ order: 2, action: "Request human review", mode: "stop", requiresConfirmation: false, reason: report.recommendation.reason });
  } else {
    steps.push({ order: 2, action: "Run the task recommended by the target report", mode: "validate", requiresConfirmation: true, reason: report.recommendation?.reason ?? "No automatic recovery recipe matched; review the evidence first." });
  }

  return {
    context: report.context,
    target: report.target,
    basis: failed ? `Latest failure: ${task || "unknown task"}${message ? ` — ${message}` : ""}` : "No recent failed result matched a recovery recipe.",
    steps,
    safety: [
      "This is a dry-run plan; no task is executed and no parameter is changed.",
      "Confirm each operational step separately.",
      "Do not commit or apply candidates until a validation task succeeds and the user explicitly approves it.",
    ],
  };
}

function calibrationPlanLines(plan: CalibrationPlan, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const mark = (mode: CalibrationPlanStep["mode"]) => mode === "stop" ? "✗" : mode === "inspect" ? "·" : mode === "diagnostic" ? "→" : "✓";
  return boxed(`QDash Dry-run Plan ${plan.target.label}`, [
    `${muted("profile")} ${accent(plan.context.profile ?? "env/default")}  ${muted("chip")} ${accent(plan.context.chipId)}`,
    `${muted("basis")} ${plan.basis}`,
    "",
    ...plan.steps.map((step) => `${mark(step.mode)} ${step.order}. ${step.action} [${step.mode}]${step.requiresConfirmation ? " [confirmation]" : ""}\n    ${muted(step.reason)}`),
    "",
    accent("Safety gates"),
    ...plan.safety.map((item) => `  - ${item}`),
  ], color);
}

type DegradationReport = {
  context: { profile?: string; chipId: string; webBaseUrl: string };
  lock: unknown;
  changes: unknown;
  trends: unknown;
  recommendations?: unknown;
};

async function buildDegradationReport(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; withinHours?: number; minStreak?: number; limit?: number; entityId?: string }): Promise<DegradationReport> {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  const chipId = await defaultChipId(client, params.chipId);
  const [lock, changes, trends, recommendations] = await Promise.all([
    client.getExecutionLockStatus(),
    client.getRecentChanges({ withinHours: params.withinHours ?? 24, limit: params.limit ?? 20 }),
    client.getDegradationTrends({ minStreak: params.minStreak ?? 3, limit: params.limit ?? 20 }),
    params.entityId ? client.getRecalibrationRecommendations(params.entityId) : Promise.resolve(undefined),
  ]);
  return { context: { profile: params.profile ?? currentContext.profile, chipId, webBaseUrl: qdashWebBaseUrl(client) }, lock, changes, trends, recommendations };
}

function degradationReportLines(report: DegradationReport, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const objectArray = (value: unknown, keys: string[]): Record<string, unknown>[] => {
    const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
    for (const key of keys) if (Array.isArray(payload[key])) return payload[key].filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
    return [];
  };
  const changes = objectArray(report.changes, ["changes", "items"]);
  const trends = objectArray(report.trends, ["trends", "items"]);
  const recommendations = objectArray(report.recommendations, ["recommended_tasks", "tasks"]);
  const locked = Boolean(report.lock && typeof report.lock === "object" && (report.lock as Record<string, unknown>).lock);
  return boxed("QDash Degradation Report", [
    `${muted("profile")} ${accent(report.context.profile ?? "env/default")}  ${muted("chip")} ${accent(report.context.chipId)}  ${muted("execution lock")} ${locked ? "LOCKED" : "available"}`,
    `${muted("recent changes")} ${changes.length}  ${muted("degradation trends")} ${trends.length}${report.recommendations ? `  ${muted("recommendations")} ${recommendations.length}` : ""}`,
    "",
    accent("Degradation trends"),
    ...(trends.length ? trends.slice(0, 10).map((item) => `! ${firstString(item, ["parameter_name", "parameter", "name"]) ?? "parameter"} ${firstString(item, ["qid", "target"]) ?? ""} ${firstString(item, ["streak", "severity"]) ?? ""}`) : [`  ${muted("none detected")}`]),
    "",
    accent("Recent changes"),
    ...(changes.length ? changes.slice(0, 10).map((item) => `• ${firstString(item, ["parameter_name", "parameter", "name"]) ?? "parameter"} ${firstString(item, ["qid", "target"]) ?? ""} Δ${firstString(item, ["delta", "delta_percent"]) ?? "?"}`) : [`  ${muted("none")}`]),
    ...(report.recommendations ? ["", accent("Recommended downstream tasks"), ...(recommendations.length ? recommendations.slice(0, 8).map((item) => `→ ${firstString(item, ["task_name", "task", "name"]) ?? JSON.stringify(item)}`) : [`  ${muted("none")}`])] : []),
    "",
    `${accent("safety")} ${locked ? "An execution is active; do not start another calibration action." : "No active execution lock reported. This report is read-only."}`,
  ], color);
}

type CalibrationValidation = {
  context: { profile?: string; chipId?: string; webBaseUrl: string };
  taskId: string;
  task: Record<string, unknown>;
  status: "passed" | "failed" | "needs_review" | "unknown";
  gates: Array<{ name: string; passed: boolean; detail: string }>;
  figurePaths: string[];
  comparison?: unknown;
  next: string;
  links: Record<string, string>;
};

async function buildCalibrationValidation(params: { profile?: string; configPath?: string; useEnv?: boolean; taskId: string; beforeExecutionId?: string }): Promise<CalibrationValidation> {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  const task = await client.getTaskResult(params.taskId) as unknown as Record<string, unknown>;
  const status = firstString(task, ["status"])?.toLowerCase() ?? "unknown";
  const figurePaths = taskFigurePaths(task, 20);
  const afterExecutionId = firstString(task, ["execution_id", "executionId"]);
  const comparison = params.beforeExecutionId && afterExecutionId
    ? await client.compareExecutions(params.beforeExecutionId, afterExecutionId).catch(() => undefined)
    : undefined;
  const comparisonRecord = comparison as unknown as Record<string, unknown> | undefined;
  const changedParameters = comparisonRecord ? firstNumber(comparisonRecord, ["changed_count"]) ?? (Array.isArray(comparisonRecord.changed_parameters) ? (comparisonRecord.changed_parameters as unknown[]).length : undefined) : undefined;
  const gates = [
    { name: "task completed", passed: ["completed", "success", "succeeded"].includes(status), detail: status },
    { name: "figures available", passed: figurePaths.length > 0, detail: figurePaths.length ? `${figurePaths.length} figure(s)` : "no figures attached" },
    ...(params.beforeExecutionId ? [{ name: "execution comparison", passed: comparison !== undefined, detail: comparison === undefined ? "comparison unavailable" : `${changedParameters ?? 0} changed parameter(s)` }] : []),
  ];
  const figuresGate = gates.find((gate) => gate.name === "figures available");
  const comparisonGate = gates.find((gate) => gate.name === "execution comparison");
  const validationStatus: CalibrationValidation["status"] = !gates[0].passed ? "failed" : figuresGate?.passed === false || comparisonGate?.passed === false ? "needs_review" : "passed";
  const next = validationStatus === "passed"
    ? "Inspect candidates and ask for explicit confirmation before commit/apply. Preserve evidence in the target Forum thread when appropriate."
    : validationStatus === "failed"
      ? "Stop the recovery sequence; inspect the task message and figures before another operational action."
      : "Review the figures and execution comparison before treating this result as authoritative.";
  return {
    context: { profile: params.profile ?? currentContext.profile, chipId: firstString(task, ["chip_id", "chipId"]) ?? currentContext.chipId, webBaseUrl: qdashWebBaseUrl(client) },
    taskId: params.taskId,
    task,
    status: validationStatus,
    gates,
    figurePaths,
    comparison,
    next,
    links: qdashObjectLinks(client, task),
  };
}

function calibrationValidationLines(validation: CalibrationValidation, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const statusColor = validation.status === "passed" ? "32" : validation.status === "failed" ? "31" : "33";
  const statusText = color ? ansi(statusColor, validation.status) : validation.status;
  return boxed(`QDash Calibration Validation ${shortId(validation.taskId, 16)}`, [
    `${muted("status")} ${statusText}`,
    `${muted("task")} ${firstString(validation.task, ["task_name", "name"]) ?? "unknown"}`,
    "",
    accent("Gates"),
    ...validation.gates.map((gate) => `${gate.passed ? "✓" : "✗"} ${gate.name}: ${gate.detail}`),
    "",
    `${accent("next")} ${validation.next}`,
    ...(validation.figurePaths.length ? ["", `${muted("figures")} ${validation.figurePaths.length} (use qdash_get_task_figures)`] : []),
    ...(validation.comparison ? [`${muted("comparison")} ${firstNumber(validation.comparison as Record<string, unknown>, ["unchanged_count"]) ?? 0} unchanged parameter(s)`] : []),
    ...(validation.links.task_result ? [`${muted("task url")} ${validation.links.task_result}`] : []),
  ], color);
}

function recommendationLines(recommendations: RecommendedNextAction[], color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const mark = (status: string) => ["done", "ok"].includes(status) ? "✓" : ["stop", "human", "review"].includes(status) ? "✗" : "→";
  return boxed("QDash Next Action", recommendations.length > 0 ? recommendations.flatMap((item) => [
    `${mark(item.status)} ${accent(item.target)} ${muted(`[${item.status}]`)} ${item.recommendation}`,
    `    ${muted("reason")} ${item.reason}`,
    ...(item.links.task_result ? [`    ${muted("task")} ${item.links.task_result}`] : []),
    ...(item.links.execution ? [`    ${muted("exec")} ${item.links.execution}`] : []),
  ]) : [muted("no recent calibration target found")], color);
}

type DashboardInsight = {
  target: string;
  severity: "critical" | "warning" | "info";
  title: string;
  evidence: string[];
  suggestion: string;
  links: Record<string, string[]>;
};

type DashboardInsightsResult = {
  context: { profile?: string; chipId: string; webBaseUrl: string };
  insights: DashboardInsight[];
};

function targetFromText(text: string): string | undefined {
  const coupling = text.match(/Q?0*(\d{1,3})\s*[-–]\s*Q?0*(\d{1,3})/i);
  if (coupling) return `c${Number(coupling[1])}-${Number(coupling[2])}`;
  const qubit = text.match(/\bQ0*(\d{1,3})\b/i);
  return qubit ? `q${Number(qubit[1])}` : undefined;
}

function addEvidence(map: Map<string, DashboardInsight>, target: string, severity: DashboardInsight["severity"], title: string, evidence: string, suggestion: string, links: Record<string, string> = {}) {
  const existing = map.get(target);
  const rank = { info: 0, warning: 1, critical: 2 } as const;
  if (!existing) {
    map.set(target, { target, severity, title, evidence: [evidence], suggestion, links: Object.fromEntries(Object.entries(links).map(([key, value]) => [key, [value]])) });
    return;
  }
  if (rank[severity] > rank[existing.severity]) existing.severity = severity;
  if (!existing.evidence.includes(evidence)) existing.evidence.push(evidence);
  for (const [key, value] of Object.entries(links)) existing.links[key] = [...(existing.links[key] ?? []), value];
}

function addMetricInsights(map: Map<string, DashboardInsight>, metrics: unknown, client: QDashClient) {
  if (!metrics || typeof metrics !== "object") return;
  const qubitMetrics = (metrics as Record<string, unknown>).qubit_metrics;
  if (!qubitMetrics || typeof qubitMetrics !== "object") return;
  const metricObject = qubitMetrics as Record<string, unknown>;
  const checks: Array<{ name: string; threshold: number; direction: "below"; label: string }> = [
    { name: "t1", threshold: 5, direction: "below", label: "low T1" },
    { name: "t2_echo", threshold: 2, direction: "below", label: "low T2 echo" },
    { name: "average_readout_fidelity", threshold: 0.8, direction: "below", label: "low readout fidelity" },
    { name: "average_gate_fidelity", threshold: 0.98, direction: "below", label: "low 1Q gate fidelity" },
  ];
  for (const check of checks) {
    const values = metricObject[check.name];
    if (!values || typeof values !== "object") continue;
    for (const [qid, item] of Object.entries(values as Record<string, unknown>)) {
      if (!item || typeof item !== "object") continue;
      const value = (item as Record<string, unknown>).value;
      if (typeof value !== "number" || !Number.isFinite(value) || value >= check.threshold) continue;
      const links = qdashObjectLinks(client, item as Record<string, unknown>);
      addEvidence(map, `q${qid}`, check.name === "t1" || check.name === "t2_echo" ? "warning" : "info", `${check.label} on q${qid}`, `${check.name}=${formatNumber(value)} below ${check.threshold}`, `Inspect ${check.name} history and related failed tasks/forum notes.`, links);
    }
  }
}

async function buildDashboardInsights(params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number; withinHours?: number }): Promise<DashboardInsightsResult> {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  const chipId = await defaultChipId(client, params.chipId);
  const limit = params.limit ?? 30;
  const end = new Date();
  const start = new Date(end.getTime() - (params.withinHours ?? 168) * 3600_000);
  const [forums, failed, metrics] = await Promise.allSettled([
    client.listForumPosts({ chipId, status: "open", limit }),
    client.api.listTaskResults({ chip_id: chipId, status: "failed", start_from: start.toISOString(), start_to: end.toISOString(), limit }),
    client.getChipMetrics(chipId),
  ]);
  const value = <T>(result: PromiseSettledResult<T>): T | undefined => result.status === "fulfilled" ? result.value : undefined;
  const insightMap = new Map<string, DashboardInsight>();

  for (const post of forumPostsFromPayload(value(forums))) {
    const targetType = firstString(post, ["target_type"]);
    const targetId = firstString(post, ["target_id", "qid"]);
    const title = forumPostTitle(post);
    const target = targetId ? (targetType === "coupling" ? `c${targetId}` : `q${targetId}`) : targetFromText(title);
    if (!target) continue;
    const lower = title.toLowerCase();
    const severity: DashboardInsight["severity"] = /tls|死|衝突|leak|リーク|不安定|見えない/.test(lower) ? "warning" : "info";
    addEvidence(insightMap, target, severity, title, `forum: ${title}`, "Open forum context should be reviewed before calibration changes.", qdashObjectLinks(client, post));
  }

  for (const task of arrayFromPayload(value(failed)).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")) {
    const target = calibrationTarget(task);
    const taskName = firstString(task, ["task_name", "name"]) ?? "task";
    const message = firstString(task, ["message"]) ?? "failed";
    addEvidence(insightMap, target, "warning", `${taskName} failed on ${target}`, `failed ${taskName}: ${message}`, "Inspect the failed task figures and recent history before continuing calibration.", qdashObjectLinks(client, task));
  }

  addMetricInsights(insightMap, value(metrics), client);

  const insights = [...insightMap.values()].sort((a, b) => {
    const rank = { critical: 2, warning: 1, info: 0 } as const;
    return rank[b.severity] - rank[a.severity] || b.evidence.length - a.evidence.length;
  }).slice(0, limit);
  return { context: { profile: params.profile ?? currentContext.profile, chipId, webBaseUrl: qdashWebBaseUrl(client) }, insights };
}

function dashboardInsightLines(result: DashboardInsightsResult, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const sev = (severity: string) => severity === "critical" ? "‼" : severity === "warning" ? "!" : "i";
  const body = [
    `${muted("profile")} ${accent(result.context.profile ?? "env/default")}  ${muted("chip")} ${accent(result.context.chipId)}`,
    `${muted("url")} ${result.context.webBaseUrl}`,
    "",
    ...(result.insights.length > 0 ? result.insights.flatMap((insight) => [
      `${sev(insight.severity)} ${accent(insight.target)} ${muted(`[${insight.severity}]`)} ${insight.title}`,
      ...insight.evidence.slice(0, 4).map((line) => `    - ${line}`),
      `    ${muted("suggest")} ${insight.suggestion}`,
      ...Object.entries(insight.links).flatMap(([kind, urls]) => urls.slice(0, 2).map((url) => `    ${muted(kind)} ${url}`)),
    ]) : [muted("no insights from current dashboard/forum/metrics data")]),
  ];
  return boxed("QDash Dashboard Insights", body, color);
}

type ForumEvidenceReplyParams = {
  parentPostId: string;
  taskId: string;
  interpretation: string;
  title?: string;
  includeFigures?: boolean;
  maxFigures?: number;
  includeHistory?: boolean;
  historyLimit?: number;
};

function filenameFromFigurePath(path: string): string {
  return path.split("/").filter(Boolean).pop() ?? "figure.png";
}

function figureApiUrl(path: string): string {
  return `/api/executions/figure?path=${encodeURIComponent(path)}`;
}

function taskFigurePaths(task: Record<string, unknown>, maxFigures: number): string[] {
  const paths = task.figure_path;
  return Array.isArray(paths) ? paths.filter((item): item is string => typeof item === "string").slice(0, maxFigures) : [];
}

type ForumImageReplyParams = {
  parentPostId: string;
  imagePaths: string[];
  interpretation: string;
  title?: string;
};

type PreparedForumImageReply = {
  parent: Record<string, unknown>;
  images: LocalForumImage[];
  title: string;
  preview: string;
};

async function prepareForumImageReply(client: QDashClient, params: ForumImageReplyParams): Promise<PreparedForumImageReply> {
  const parent = await client.getForumPost(params.parentPostId) as unknown as Record<string, unknown>;
  const images = loadLocalForumImages(params.imagePaths);
  const title = params.title ?? `${new Date().toISOString().slice(0, 10)} 追加分析画像`;
  const preview = forumImageReplyPreview(title, images, params.interpretation);
  return { parent, images, title, preview };
}

async function createForumImageReply(client: QDashClient, params: ForumImageReplyParams, prepared: PreparedForumImageReply) {
  const uploaded = [];
  for (const image of prepared.images) {
    const result = await client.uploadForumImage(image.blob, image.filename);
    uploaded.push({ ...image, url: result.url });
  }
  const content = forumImageReplyContent(prepared.title, uploaded, params.interpretation);
  const parent = prepared.parent;
  const request = {
    category: firstString(parent, ["category"]) ?? "other",
    title: null,
    content,
    content_blocks: [],
    parent_id: params.parentPostId,
    chip_id: firstString(parent, ["chip_id", "chipId"]),
    target_type: firstString(parent, ["target_type", "targetType"]),
    target_id: firstString(parent, ["target_id", "targetId"]),
    cooldown_id: firstString(parent, ["cooldown_id", "cooldownId"]),
    status: firstString(parent, ["status"]) ?? "open",
  };
  const reply = await client.createForumPost(request as never);
  return {
    reply,
    content,
    images: uploaded.map(({ blob: _blob, ...image }) => image),
  };
}

async function buildForumEvidenceReply(client: QDashClient, params: ForumEvidenceReplyParams) {
  const [parent, task] = await Promise.all([
    client.getForumPost(params.parentPostId) as unknown as Promise<Record<string, unknown>>,
    client.getTaskResult(params.taskId) as unknown as Promise<Record<string, unknown>>,
  ]);
  const taskName = firstString(task, ["task_name", "taskName"]) ?? "task";
  const qid = firstString(task, ["qid"]);
  const couplingId = firstString(task, ["coupling_id", "couplingId"]);
  const target = couplingId ? `coupling ${couplingId}` : qid ? `Q${qid}` : "target";
  const executionId = firstString(task, ["execution_id", "executionId"]);
  const message = firstString(task, ["message"]) ?? "";
  const chipId = firstString(task, ["chip_id", "chipId"]) ?? firstString(parent, ["chip_id", "chipId"]);
  const category = firstString(parent, ["category"]) ?? (couplingId ? "coupling" : "qubit");
  const targetType = firstString(parent, ["target_type", "targetType"]) ?? (couplingId ? "coupling" : qid ? "qubit" : undefined);
  const targetId = firstString(parent, ["target_id", "targetId"]) ?? couplingId ?? qid;
  const title = params.title ?? `${new Date().toISOString().slice(0, 10)} 追加観測: ${target} ${taskName}`;
  const taskUrl = qdashWebUrl(client, `/task-results/${encodeURIComponent(params.taskId)}`);
  const executionUrl = executionId ? qdashWebUrl(client, executionPagePath(executionId, chipId)) : undefined;
  const figures = params.includeFigures === false ? [] : taskFigurePaths(task, params.maxFigures ?? 2);
  const figureMarkdown = figures.map((path) => `![${filenameFromFigurePath(path)}](${figureApiUrl(path)})`).join("\n\n");
  const history = params.includeHistory === false ? [] : arrayFromPayload(await client.listTaskResults({
    chipId,
    taskName,
    qid,
    couplingId,
    limit: params.historyLimit ?? 5,
  })).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  const historyLines = history
    .filter((item) => firstString(item, ["task_id", "taskId"]) !== params.taskId)
    .slice(0, Math.max(0, (params.historyLimit ?? 5) - 1))
    .map((item) => {
      const historyTaskId = firstString(item, ["task_id", "taskId"]);
      const status = firstString(item, ["status"]) ?? "unknown";
      const start = firstString(item, ["start_at", "startAt"])?.slice(0, 16) ?? "time unknown";
      const msg = firstString(item, ["message"]);
      return historyTaskId ? `- ${start} ${status}: [${historyTaskId}](${qdashWebUrl(client, `/task-results/${encodeURIComponent(historyTaskId)}`)})${msg ? ` — ${msg}` : ""}` : undefined;
    }).filter((line): line is string => Boolean(line));
  const content = [
    `## ${title}`,
    "",
    `${target} の \`${taskName}\` から evidence を追加します。`,
    "",
    `- [task](${taskUrl})`,
    ...(executionUrl ? [`- [execution](${executionUrl})`] : []),
    ...(message ? [`- message: \`${message}\``] : []),
    ...(figures.length > 0 ? ["", figureMarkdown] : []),
    ...(historyLines.length > 0 ? ["", `### Recent ${taskName} history`, "", ...historyLines] : []),
    "",
    params.interpretation,
    "",
    "— 🤖 by pi-qdash",
  ].join("\n");
  // Keep content_blocks empty so QDash renders the markdown `content` directly.
  // The current forum UI reliably renders markdown links and images, while BlockNote
  // link inline objects can appear blank in some deployed versions.
  const request = {
    category,
    title: null,
    content,
    content_blocks: [],
    parent_id: params.parentPostId,
    chip_id: chipId,
    target_type: targetType,
    target_id: targetId,
    status: firstString(parent, ["status"]) ?? "open",
  };
  return { request, preview: content, parent, task, figures };
}

async function executeQuery(params: QDashQueryParams) {
  params = applyQDashContext(params);
  const client = await makeClient(params);
  switch (params.action) {
    case "chips": return client.listChips();
    case "default_chip": return client.getDefaultChip();
    case "metrics_config": return client.getMetricsConfig();
    case "chip_metrics": return client.getChipMetrics(await defaultChipId(client, params.chipId));
    case "chip_qubits": return client.listChipQubits(await defaultChipId(client, params.chipId), { limit: params.limit, offset: params.offset });
    case "chip_qubit": return client.getChipQubit(await defaultChipId(client, params.chipId), requireValue(params.qid, "qid"));
    case "chip_couplings": return client.listChipCouplings(await defaultChipId(client, params.chipId), { limit: params.limit, offset: params.offset });
    case "chip_coupling": return client.getChipCoupling(await defaultChipId(client, params.chipId), requireValue(params.couplingId, "couplingId"));
    case "cryostats": return client.api.listCryostats();
    case "cryostat": return client.api.getCryostat(requireValue(params.cryoId, "cryoId"));
    case "cooldowns": return client.api.listCooldowns({ cryo_id: params.cryoId, chip_id: params.chipId });
    case "cooldown": return client.api.getCooldown(requireValue(params.cooldownId, "cooldownId"));
    case "cooldown_wiring_events": return client.api.listCooldownWiringEvents(requireValue(params.cooldownId, "cooldownId"), { limit: params.limit, skip: params.skip });
    case "timeseries": return client.getTaskResultsTimeseries({ chipId: await defaultChipId(client, params.chipId), parameter: requireValue(params.parameter, "parameter"), tag: params.tag, qid: params.qid, startAt: requireValue(params.startAt, "startAt"), endAt: requireValue(params.endAt, "endAt") });
    case "task_results": return rawGet(client, "/task-results", { chip_id: params.chipId, task_name: params.taskName, qid: params.qid, coupling_id: params.couplingId, execution_id: params.executionId, username: params.username, status: params.status, start_from: params.startFrom ?? params.startAt, start_to: params.startTo ?? params.endAt, message_contains: params.messageContains, limit: params.limit, skip: params.skip });
    case "task_result": return client.getTaskResult(requireValue(params.taskId, "taskId"));
    case "task_note": return client.api.getTaskNote(requireValue(params.taskId, "taskId"));
    case "qubit_latest": return client.api.getLatestQubitTaskResults({ chip_id: await defaultChipId(client, params.chipId), task: requireValue(params.task ?? params.taskName, "task") });
    case "qubit_history": return rawGet(client, `/task-results/qubits/${pathPart(requireValue(params.qid, "qid"))}/history`, { chip_id: await defaultChipId(client, params.chipId), task: requireValue(params.task ?? params.taskName, "task"), date: requireValue(params.date, "date") });
    case "coupling_latest": return client.api.getLatestCouplingTaskResults({ chip_id: await defaultChipId(client, params.chipId), task: requireValue(params.task ?? params.taskName, "task") });
    case "coupling_history": return rawGet(client, `/task-results/couplings/${pathPart(requireValue(params.couplingId, "couplingId"))}/history`, { chip_id: await defaultChipId(client, params.chipId), task: requireValue(params.task ?? params.taskName, "task"), date: requireValue(params.date, "date") });
    case "tasks": return client.listTasks(params.backend);
    case "task_knowledge": return params.taskName ? client.getTaskKnowledge(params.taskName) : client.listTaskKnowledge();
    case "task_knowledge_markdown": return client.getTaskKnowledgeMarkdown(requireValue(params.taskName, "taskName"));
    case "projects": return client.listProjects();
    case "project": return client.getProject(requireValue(params.projectId, "projectId"));
    case "files_tree": return client.getFilesTree();
    case "file_content": return client.getFileContent(requireValue(params.path, "path"));
    case "git_status": return client.getGitStatus();
    case "flows": return client.listFlows();
    case "flow": return client.getFlow(requireValue(params.flowName, "flowName"));
    case "flow_templates": return client.listFlowTemplates();
    case "flow_template": return client.getFlowTemplate(requireValue(params.templateId, "templateId"));
    case "flow_helper_files": return client.api.listFlowHelperFiles();
    case "flow_helper_file": return client.api.getFlowHelperFile(requireValue(params.filename, "filename"));
    case "executions": return rawGet(client, "/executions", { chip_id: params.chipId, flow_name: params.flowName, status: params.status, skip: params.skip, limit: params.limit });
    case "execution": return client.getExecution(requireValue(params.executionId, "executionId"));
    case "forum_posts": return client.listForumPosts({ status: params.status, chipId: params.chipId, limit: params.limit, skip: params.skip });
    case "provenance_stats": return client.getProvenanceStats();
    case "provenance_history": return client.api.getParameterHistory({ parameter_name: requireValue(params.parameterName ?? params.parameter, "parameterName"), qid: requireValue(params.qid, "qid"), limit: params.limit });
    case "provenance_changes": {
      const parameterName = params.parameterName ?? params.parameter;
      return client.getRecentChanges({ parameterNames: parameterName ? [parameterName] : undefined, withinHours: params.withinHours, limit: params.limit });
    }
    case "provenance_lineage": return client.getProvenanceLineage(requireValue(params.entityId, "entityId"));
    case "provenance_impact": return client.getProvenanceImpact(requireValue(params.entityId, "entityId"));
  }
}

export default function qdashExtension(pi: ExtensionAPI) {
  installQDashWriteGate(pi);
  registerTaskKnowledgeTool(pi, { makeClient });
  registerCalibrationPipelineTools(pi, {
    makeClient,
    resolveChipId: (client, chipId) => defaultChipId(client as QDashClient, chipId),
  });
  registerFlowAuthoringTools(pi, {
    makeClient,
    resolveChipId: (client, chipId) => defaultChipId(client as QDashClient, chipId),
    flowPageUrl: (client, name) => qdashWebUrl(client as QDashClient, `/workflow/${encodeURIComponent(name)}`),
  });

  pi.registerTool({
    name: "qdash_config_info",
    label: "QDash Config Info",
    description: "Show non-secret QDash client configuration and available local profiles.",
    promptSnippet: "Inspect QDash profile availability and non-secret connection settings",
    promptGuidelines: ["Use qdash_config_info before QDash queries when profile or configuration is unclear. Never expose QDash secrets."],
    parameters: Type.Object(connectionParams),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean }) {
      const profiles = configProfiles(params.configPath);
      try {
        const client = await makeClient(params);
        return toToolResult({ profiles, active: safeConfig(client, shouldUseEnv(params) ? "env" : `profile:${params.profile ?? "default"}`) });
      } catch (error) {
        return toToolResult({ profiles, error: error instanceof Error ? error.message : String(error) });
      }
    },
  });

  pi.registerTool({
    name: "qdash_query",
    label: "QDash Query",
    description: "Run common read-only QDash queries via @oqtopus-team/qdash-client.",
    promptSnippet: "Query QDash chips, cryostats, cooldown wiring, metrics, tasks, files, flows, executions, projects, forum posts, and provenance",
    promptGuidelines: [
      "Prefer dedicated QDash tools such as qdash_list_chips, qdash_get_chip_metrics, qdash_list_task_results, qdash_list_forum_posts, qdash_list_flows, and qdash_list_executions when they match the task.",
      "Use qdash_query for read-only QDash data access not covered by a dedicated tool, instead of curl or scraping the UI.",
      "Ask for confirmation before using operational or write APIs; qdash_query intentionally exposes read-only operations only.",
      "Never expose QDash tokens, passwords, or Cloudflare Access secrets.",
    ],
    parameters: querySchema,
    async execute(_toolCallId, params: QDashQueryParams) {
      const data = await executeQuery(params);
      const client = await makeClient(params);
      return toToolResult(withQDashLinks(client, data), { action: params.action, webBaseUrl: qdashWebBaseUrl(client) });
    },
  });

  const registerQueryTool = (tool: {
    name: string;
    label: string;
    description: string;
    promptSnippet: string;
    action: QDashQueryParams["action"];
    parameters: ReturnType<typeof Type.Object>;
  }) => {
    pi.registerTool({
      name: tool.name,
      label: tool.label,
      description: tool.description,
      promptSnippet: tool.promptSnippet,
      promptGuidelines: [
        `Prefer ${tool.name} for this specific read-only QDash operation instead of qdash_query or qdash_raw_get.`,
        "Never expose QDash tokens, passwords, or Cloudflare Access secrets.",
      ],
      parameters: tool.parameters,
      async execute(_toolCallId, params: Omit<QDashQueryParams, "action">) {
        const data = await executeQuery({ ...params, action: tool.action });
        const client = await makeClient(params);
        return toToolResult(withQDashLinks(client, data), { action: tool.action, tool: tool.name, webBaseUrl: qdashWebBaseUrl(client) });
      },
    });
  };

  registerQueryTool({
    name: "qdash_list_chips",
    label: "QDash List Chips",
    description: "List QDash chips through qdash-client.",
    promptSnippet: "List QDash chips and their status",
    action: "chips",
    parameters: Type.Object(connectionParams),
  });

  registerQueryTool({
    name: "qdash_get_default_chip",
    label: "QDash Default Chip",
    description: "Get the active/default QDash chip.",
    promptSnippet: "Get the default active QDash chip",
    action: "default_chip",
    parameters: Type.Object(connectionParams),
  });

  registerQueryTool({
    name: "qdash_get_chip_metrics",
    label: "QDash Chip Metrics",
    description: "Get metrics for a chip. If chipId is omitted, the default chip is used.",
    promptSnippet: "Get QDash chip metrics for the default or specified chip",
    action: "chip_metrics",
    parameters: Type.Object({ ...connectionParams, ...chipScopedParams }),
  });

  registerQueryTool({
    name: "qdash_list_chip_qubits",
    label: "QDash List Chip Qubits",
    description: "List qubits for a chip. If chipId is omitted, the default chip is used.",
    promptSnippet: "List qubits for a QDash chip",
    action: "chip_qubits",
    parameters: Type.Object({ ...connectionParams, ...chipScopedParams, ...paginationParams }),
  });

  registerQueryTool({
    name: "qdash_list_chip_couplings",
    label: "QDash List Chip Couplings",
    description: "List couplings for a chip. If chipId is omitted, the default chip is used.",
    promptSnippet: "List couplings for a QDash chip",
    action: "chip_couplings",
    parameters: Type.Object({ ...connectionParams, ...chipScopedParams, ...paginationParams }),
  });

  registerQueryTool({
    name: "qdash_list_cryostats",
    label: "QDash List Cryostats",
    description: "List cryostats available in QDash.",
    promptSnippet: "List QDash cryostats before inspecting cooldowns or wiring",
    action: "cryostats",
    parameters: Type.Object(connectionParams),
  });

  registerQueryTool({
    name: "qdash_list_cooldowns",
    label: "QDash List Cooldowns",
    description: "List QDash cooldowns, optionally filtered by cryostat or chip.",
    promptSnippet: "List cryostat cooldowns and identify the active or latest wiring context",
    action: "cooldowns",
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      cryoId: Type.Optional(Type.String()),
    }),
  });

  pi.registerTool({
    name: "qdash_get_cooldown_wiring",
    label: "QDash Cooldown Wiring",
    description: "Get cryostat/cooldown wiring. A cooldown can be selected explicitly, or the active/newest cooldown is resolved automatically from cryoId or the active/default chip.",
    promptSnippet: "Resolve the relevant cryostat cooldown and retrieve its human-readable wiring information",
    promptGuidelines: [
      "Prefer qdash_get_cooldown_wiring whenever the user asks about cryo, cryostat, cooldown, cabling, or wiring.",
      "Omit cooldownId to automatically select the active cooldown, falling back to the newest cooldown for the cryostat or chip.",
      "The markdown field is the compact human-readable wiring document. Request includeBlocks only when raw BlockNote structure or embedded content is needed.",
      "Use includeHistory when investigating when or why wiring changed.",
      "Set includeInsights when you want to naturally point out unusual attenuation totals and the affected qubits/MUXes; otherwise prefer qdash_wiring_insights for a focused summary.",
      "Never expose QDash tokens, passwords, or Cloudflare Access secrets.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Chip used to resolve its active/newest cooldown. Defaults to the current/default chip." })),
      cryoId: Type.Optional(Type.String({ description: "Cryostat used to resolve its active/newest cooldown." })),
      cooldownId: Type.Optional(Type.String({ description: "Explicit cooldown ID; takes precedence over chipId and cryoId." })),
      includeBlocks: Type.Optional(Type.Boolean({ description: "Include raw BlockNote wiring blocks. Defaults to false unless markdown is unavailable." })),
      includeHistory: Type.Optional(Type.Boolean({ description: "Include wiring checkpoint history." })),
      historyLimit: Type.Optional(Type.Number({ description: "Maximum wiring history entries; defaults to 20." })),
      includeInsights: Type.Optional(Type.Boolean({ description: "Analyze attenuation totals and highlight unusual control/readout ports. Defaults to false; use qdash_wiring_insights for a focused summary." })),
    }),
    async execute(_toolCallId, params: CooldownWiringParams) {
      const data = await resolveCooldownWiring(params);
      const client = await makeClient(params);
      return toToolResult(withQDashLinks(client, data), {
        tool: "qdash_get_cooldown_wiring",
        webBaseUrl: qdashWebBaseUrl(client),
      });
    },
  });

  pi.registerTool({
    name: "qdash_wiring_insights",
    label: "QDash Wiring Insights",
    description: "Analyze cooldown wiring markdown and summarize attenuation totals, unusual ports, and affected qubits/MUXes.",
    promptSnippet: "Highlight unusual QDash wiring attenuation totals and affected qubits/MUXes",
    promptGuidelines: [
      "Use qdash_wiring_insights when the user asks what is characteristic, unusual, different, or noteworthy in wiring attenuation.",
      "Report totals concisely, and translate control-port anomalies to qids when the MUX×4 mapping is available.",
      "This tool is read-only and does not change QDash wiring or calibration parameters.",
      "Never expose QDash tokens, passwords, or Cloudflare Access secrets.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Chip used to resolve its active/newest cooldown. Defaults to the current/default chip." })),
      cryoId: Type.Optional(Type.String({ description: "Cryostat used to resolve its active/newest cooldown." })),
      cooldownId: Type.Optional(Type.String({ description: "Explicit cooldown ID; takes precedence over chipId and cryoId." })),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: WiringInsightParams) {
      const data = await resolveCooldownWiring({ ...params, includeBlocks: false, includeHistory: false, includeInsights: true });
      const insights = data.insights;
      const client = await makeClient(params);
      if (!insights) return toToolResult(withQDashLinks(client, data), { tool: "qdash_wiring_insights", webBaseUrl: qdashWebBaseUrl(client) });
      return toTextToolResult(wiringInsightLines(insights, params.color).join("\n"), withQDashLinks(client, data), {
        tool: "qdash_wiring_insights",
        webBaseUrl: qdashWebBaseUrl(client),
      });
    },
  });

  registerQueryTool({
    name: "qdash_list_cooldown_wiring_events",
    label: "QDash Cooldown Wiring History",
    description: "List wiring change checkpoints for a cooldown.",
    promptSnippet: "Inspect QDash cooldown wiring change history and snapshots",
    action: "cooldown_wiring_events",
    parameters: Type.Object({
      ...connectionParams,
      cooldownId: Type.String(),
      limit: Type.Optional(Type.Number()),
      skip: Type.Optional(Type.Number()),
    }),
  });

  registerQueryTool({
    name: "qdash_get_timeseries",
    label: "QDash Timeseries",
    description: "Get task-result timeseries for a parameter and time range.",
    promptSnippet: "Get QDash task-result timeseries for a parameter over a time range",
    action: "timeseries",
    parameters: Type.Object({
      ...connectionParams,
      ...chipScopedParams,
      parameter: Type.String(),
      startAt: Type.String({ description: "Start timestamp, preferably UTC ISO with Z." }),
      endAt: Type.String({ description: "End timestamp, preferably UTC ISO with Z." }),
      qid: Type.Optional(Type.String()),
      tag: Type.Optional(Type.String()),
    }),
  });

  pi.registerTool({
    name: "qdash_plot_timeseries",
    label: "QDash Plot Timeseries",
    description: "Render a compact TUI sparkline/plot for a task-result parameter timeseries.",
    promptSnippet: "Plot QDash task-result timeseries in the TUI",
    promptGuidelines: ["Use qdash_plot_timeseries when the user wants to visualize history, drift, trends, or analysis timeseries in the TUI."],
    parameters: Type.Object({
      ...connectionParams,
      ...chipScopedParams,
      parameter: Type.String(),
      startAt: Type.Optional(Type.String({ description: "Start timestamp, preferably UTC ISO with Z. Defaults to withinHours ago." })),
      endAt: Type.Optional(Type.String({ description: "End timestamp, preferably UTC ISO with Z. Defaults to now." })),
      withinHours: Type.Optional(Type.Number({ description: "Lookback window when startAt is omitted. Defaults to 168 hours." })),
      qid: Type.Optional(Type.String()),
      tag: Type.Optional(Type.String()),
      height: Type.Optional(Type.Number()),
      width: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; parameter: string; startAt?: string; endAt?: string; withinHours?: number; qid?: string; tag?: string; height?: number; width?: number; color?: boolean }) {
      const client = await makeClient(params);
      const endAt = params.endAt ?? new Date().toISOString();
      const startAt = params.startAt ?? new Date(Date.parse(endAt) - (params.withinHours ?? 168) * 3600_000).toISOString();
      const chipId = await defaultChipId(client, params.chipId);
      const data = await client.getTaskResultsTimeseries({ chipId, parameter: params.parameter, tag: params.tag, qid: params.qid, startAt, endAt });
      const title = `QDash Timeseries: ${params.parameter}${params.qid ? ` q${params.qid}` : ""}`;
      const text = plotSeriesLines(timeseriesPoints(data), { title, height: params.height, width: params.width, color: params.color }).join("\n");
      return toTextToolResult(text, data, { tool: "qdash_plot_timeseries", parameter: params.parameter, qid: params.qid, chipId, startAt, endAt });
    },
    renderResult(result, _options, theme) {
      const details = result.details as { data?: unknown; parameter?: string; qid?: string } | undefined;
      const title = `QDash Timeseries: ${details?.parameter ?? "parameter"}${details?.qid ? ` q${details.qid}` : ""}`;
      return timeseriesPlotComponent(details?.data, title, theme);
    },
  });

  registerTimeseriesComparisonTool(pi, {
    makeClient,
    defaultChipId,
    investigationContext: () => currentContext.investigation,
  });

  registerQueryTool({
    name: "qdash_list_task_results",
    label: "QDash List Task Results",
    description: "List task results with common filters.",
    promptSnippet: "List QDash task results with filters such as chip, task, status, qubit, coupling, or time range",
    action: "task_results",
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      taskName: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String()),
      couplingId: Type.Optional(Type.String()),
      executionId: Type.Optional(Type.String()),
      username: Type.Optional(Type.String()),
      status: Type.Optional(Type.String()),
      startAt: Type.Optional(Type.String()),
      endAt: Type.Optional(Type.String()),
      startFrom: Type.Optional(Type.String()),
      startTo: Type.Optional(Type.String()),
      messageContains: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      skip: Type.Optional(Type.Number()),
    }),
  });

  registerQueryTool({
    name: "qdash_get_task_result",
    label: "QDash Task Result",
    description: "Get a single task result by taskId.",
    promptSnippet: "Get a QDash task result by task ID",
    action: "task_result",
    parameters: Type.Object({ ...connectionParams, taskId: Type.String() }),
  });

  registerQueryTool({
    name: "qdash_list_flows",
    label: "QDash List Flows",
    description: "List QDash flows.",
    promptSnippet: "List QDash flows",
    action: "flows",
    parameters: Type.Object(connectionParams),
  });

  registerQueryTool({
    name: "qdash_get_flow",
    label: "QDash Get Flow",
    description: "Get a QDash flow by name.",
    promptSnippet: "Get a QDash flow definition by name",
    action: "flow",
    parameters: Type.Object({ ...connectionParams, flowName: Type.String() }),
  });

  registerQueryTool({
    name: "qdash_list_executions",
    label: "QDash List Executions",
    description: "List QDash executions with optional chip, flow, status, and pagination filters.",
    promptSnippet: "List QDash executions",
    action: "executions",
    parameters: Type.Object({ ...connectionParams, chipId: Type.Optional(Type.String()), flowName: Type.Optional(Type.String()), status: Type.Optional(Type.String()), limit: Type.Optional(Type.Number()), skip: Type.Optional(Type.Number()) }),
  });

  pi.registerTool({
    name: "qdash_wait_execution",
    label: "QDash Wait Execution",
    description: "Poll a QDash execution until it reaches a terminal state. This is read-only and does not start, cancel, or modify execution.",
    promptSnippet: "Wait for a QDash calibration execution to finish and inspect its final state",
    promptGuidelines: [
      "Use qdash_wait_execution after a confirmed calibration action when the user wants completion polling.",
      "After completion, use qdash_validate_calibration before committing or applying any candidates.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      executionId: Type.String(),
      timeoutSeconds: Type.Optional(Type.Number()),
      pollIntervalSeconds: Type.Optional(Type.Number()),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; executionId: string; timeoutSeconds?: number; pollIntervalSeconds?: number }, signal) {
      const client = await makeClient(params);
      const data = await withAbort(
        client.waitForExecution(params.executionId, { timeoutSeconds: params.timeoutSeconds, pollIntervalSeconds: params.pollIntervalSeconds }),
        signal,
        `Waiting for execution ${params.executionId}`,
      );
      return toToolResult(withQDashLinks(client, data), { tool: "qdash_wait_execution", executionId: params.executionId, webBaseUrl: qdashWebBaseUrl(client) });
    },
  });

  pi.registerTool({
    name: "qdash_compare_executions",
    label: "QDash Compare Executions",
    description: "Compare calibration parameter values between two QDash executions. Read-only.",
    promptSnippet: "Compare QDash calibration parameters before and after an execution",
    promptGuidelines: [
      "Use qdash_compare_executions when validating the effect of a calibration execution.",
      "A parameter difference is evidence only; require explicit review before commit or apply.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      executionIdBefore: Type.String(),
      executionIdAfter: Type.String(),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; executionIdBefore: string; executionIdAfter: string; color?: boolean }) {
      const client = await makeClient(params);
      const data = await client.compareExecutions(params.executionIdBefore, params.executionIdAfter);
      const record = data as unknown as Record<string, unknown>;
      const changed = Array.isArray(record.changed_parameters) ? record.changed_parameters.length : 0;
      const added = Array.isArray(record.added_parameters) ? record.added_parameters.length : 0;
      const removed = Array.isArray(record.removed_parameters) ? record.removed_parameters.length : 0;
      const text = boxed("QDash Execution Comparison", [
        `before ${params.executionIdBefore}`,
        `after  ${params.executionIdAfter}`,
        "",
        `changed ${changed}  added ${added}  removed ${removed}`,
        `unchanged ${firstNumber(record, ["unchanged_count"]) ?? 0}`,
        "",
        "Read-only comparison. Review changed parameters and validation figures before committing or applying candidates.",
      ], params.color).join("\\n");
      return toTextToolResult(text, data, { tool: "qdash_compare_executions", webBaseUrl: qdashWebBaseUrl(client) });
    },
  });

  registerQueryTool({
    name: "qdash_get_execution",
    label: "QDash Get Execution",
    description: "Get a QDash execution by executionId.",
    promptSnippet: "Get QDash execution details by execution ID",
    action: "execution",
    parameters: Type.Object({ ...connectionParams, executionId: Type.String() }),
  });

  pi.registerTool({
    name: "qdash_create_agent_session",
    label: "QDash Create Agent Session",
    description: "Create a QDash agent calibration session. This is a write operation and requires confirmation.",
    promptSnippet: "Create a QDash agent calibration session after explicit user confirmation",
    promptGuidelines: [
      "Use qdash_create_agent_session only after the user explicitly asks to start an agent calibration workflow.",
      "qdash_create_agent_session is a write operation; set confirmWrite only after user confirmation.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      ...chipScopedParams,
      policy: Type.Any({ description: "Agent session policy object accepted by QDash." }),
      expiresInSeconds: Type.Optional(Type.Number()),
      skillName: Type.Optional(Type.String()),
      skillVersion: Type.Optional(Type.String()),
      skillHash: Type.Optional(Type.String()),
      modelName: Type.Optional(Type.String()),
      confirmWrite: Type.Optional(Type.Boolean({ description: "Required for non-interactive execution. Set true only after explicit user confirmation." })),
    }),
    async execute(_toolCallId, params: ConfirmableParams & {
      profile?: string;
      configPath?: string;
      useEnv?: boolean;
      chipId?: string;
      policy: unknown;
      expiresInSeconds?: number;
      skillName?: string;
      skillVersion?: string;
      skillHash?: string;
      modelName?: string;
    }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Create QDash agent session?", "This will create an agent session in QDash."))) {
          throw new Error("qdash_create_agent_session requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      const chipId = await defaultChipId(client, params.chipId);
      const data = await client.createAgentSession({
        chipId,
        policy: params.policy as never,
        expiresInSeconds: params.expiresInSeconds,
        skillName: params.skillName ?? "pi-qdash",
        skillVersion: params.skillVersion,
        skillHash: params.skillHash,
        modelName: params.modelName,
      });
      return toToolResult(data, { tool: "qdash_create_agent_session", chipId });
    },
  });

  pi.registerTool({
    name: "qdash_get_agent_session",
    label: "QDash Get Agent Session",
    description: "Get a QDash agent calibration session by sessionId.",
    promptSnippet: "Get QDash agent calibration session details",
    promptGuidelines: ["Use qdash_get_agent_session to inspect QDash agent session state."],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String() }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string }) {
      const client = await makeClient(params);
      return toToolResult(await client.getAgentSession(params.sessionId), { tool: "qdash_get_agent_session" });
    },
  });

  pi.registerTool({
    name: "qdash_submit_agent_action",
    label: "QDash Submit Agent Action",
    description: "Submit an action to a QDash agent session. This is a write operation and requires confirmation.",
    promptSnippet: "Submit an action to a QDash agent session after explicit user confirmation",
    promptGuidelines: [
      "Use qdash_submit_agent_action only after the user confirms the exact agent action.",
      "Set confirmWrite only after explicit user confirmation.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      idempotencyKey: Type.Optional(Type.String()),
      expectedStateVersion: Type.Number(),
      actionType: Type.String(),
      taskName: Type.Optional(Type.String()),
      qids: Type.Optional(Type.Array(Type.String())),
      parameterOverrides: Type.Optional(Type.Record(Type.String(), Type.Number())),
      diagnosis: Type.Optional(Type.String()),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & {
      profile?: string;
      configPath?: string;
      useEnv?: boolean;
      sessionId: string;
      idempotencyKey?: string;
      expectedStateVersion: number;
      actionType: string;
      taskName?: string;
      qids?: string[];
      parameterOverrides?: Record<string, number>;
      diagnosis?: string;
    }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Submit QDash agent action?", `Submit action '${params.actionType}' to session '${params.sessionId}'?`))) {
          throw new Error("qdash_submit_agent_action requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      const data = await client.submitAgentAction(params.sessionId, {
        idempotencyKey: params.idempotencyKey ?? randomUUID(),
        expectedStateVersion: params.expectedStateVersion,
        actionType: params.actionType as never,
        taskName: params.taskName,
        qids: params.qids,
        parameterOverrides: params.parameterOverrides,
        diagnosis: params.diagnosis,
      });
      return toToolResult(data, { tool: "qdash_submit_agent_action" });
    },
  });

  pi.registerTool({
    name: "qdash_get_agent_action",
    label: "QDash Get Agent Action",
    description: "Get one QDash agent action by sessionId and actionId.",
    promptSnippet: "Get QDash agent action details",
    promptGuidelines: ["Use qdash_get_agent_action to inspect a submitted QDash agent action."],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String(), actionId: Type.String() }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; actionId: string }) {
      const client = await makeClient(params);
      return toToolResult(await client.getAgentAction(params.sessionId, params.actionId), { tool: "qdash_get_agent_action" });
    },
  });

  pi.registerTool({
    name: "qdash_list_agent_actions",
    label: "QDash List Agent Actions",
    description: "List QDash agent actions for a session.",
    promptSnippet: "List QDash agent actions for an agent session",
    promptGuidelines: ["Use qdash_list_agent_actions to inspect actions in a QDash agent session."],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String() }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string }) {
      const client = await makeClient(params);
      return toToolResult(await client.listAgentActions(params.sessionId), { tool: "qdash_list_agent_actions" });
    },
  });

  pi.registerTool({
    name: "qdash_wait_agent_action",
    label: "QDash Wait Agent Action",
    description: "Wait for a QDash agent action to be dispatched or linked to an execution.",
    promptSnippet: "Poll QDash until an agent action is dispatched or linked to execution",
    promptGuidelines: ["Use qdash_wait_agent_action after submitting an agent action when the user wants polling."],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      actionId: Type.String(),
      waitForExecution: Type.Optional(Type.Boolean({ description: "If true, wait for execution_id; otherwise wait for operation_id." })),
      timeoutSeconds: Type.Optional(Type.Number()),
      pollIntervalSeconds: Type.Optional(Type.Number()),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; actionId: string; waitForExecution?: boolean; timeoutSeconds?: number; pollIntervalSeconds?: number }, signal) {
      const client = await makeClient(params);
      const options = { timeoutSeconds: params.timeoutSeconds, pollIntervalSeconds: params.pollIntervalSeconds };
      const data = await withAbort(
        params.waitForExecution
          ? client.waitForAgentActionExecution(params.sessionId, params.actionId, options)
          : client.waitForAgentAction(params.sessionId, params.actionId, options),
        signal,
        `Waiting for agent action ${params.actionId}`,
      );
      return toToolResult(data, { tool: "qdash_wait_agent_action" });
    },
  });

  pi.registerTool({
    name: "qdash_list_agent_action_candidates",
    label: "QDash List Agent Action Candidates",
    description: "List candidate parameter updates produced by a QDash agent action.",
    promptSnippet: "List QDash agent action candidates",
    promptGuidelines: ["Use qdash_list_agent_action_candidates before committing or applying candidates."],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String(), actionId: Type.String() }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; actionId: string }) {
      const client = await makeClient(params);
      return toToolResult(await client.listAgentActionCandidates(params.sessionId, params.actionId), { tool: "qdash_list_agent_action_candidates" });
    },
  });

  pi.registerTool({
    name: "qdash_execute_agent_action",
    label: "QDash Execute Agent Action",
    description: "Run an authorized QDash agent action's task the way the Task Workbench runs it: inputs from the current calibration state, outputs staged for the candidate gate. This is a write operation and requires confirmation.",
    promptSnippet: "Run a QDash agent action's task after explicit user confirmation",
    promptGuidelines: [
      "Use qdash_execute_agent_action only after the user confirms the action, its task, target, and overrides.",
      "The task runs on the current calibration state; pass sourceExecutionId only to record which execution the action was decided from.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      actionId: Type.String(),
      sourceExecutionId: Type.Optional(Type.String({ description: "Execution the action was decided from, recorded for provenance. The run does not restore it." })),
      updateParams: Type.Optional(Type.Boolean()),
      reconfigure: Type.Optional(Type.Boolean()),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; actionId: string; sourceExecutionId?: string; updateParams?: boolean; reconfigure?: boolean }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Execute QDash agent action?", `Run action '${params.actionId}' on the current calibration state? Outputs stay staged until a candidate is committed.`))) {
          throw new Error("qdash_execute_agent_action requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      return toToolResult(await client.executeAgentAction(params.sessionId, params.actionId, {
        sourceExecutionId: params.sourceExecutionId,
        updateParams: params.updateParams,
        reconfigure: params.reconfigure,
      }), { tool: "qdash_execute_agent_action" });
    },
  });

  pi.registerTool({
    name: "qdash_commit_agent_candidate",
    label: "QDash Commit Agent Candidate",
    description: "Commit a QDash agent action candidate. This is a write operation and requires confirmation.",
    promptSnippet: "Commit a QDash agent candidate after explicit user confirmation",
    promptGuidelines: ["Use qdash_commit_agent_candidate only after showing the candidate and receiving explicit confirmation."],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      actionId: Type.String(),
      parameterName: Type.String(),
      taskId: Type.String(),
      idempotencyKey: Type.Optional(Type.String()),
      expectedStateVersion: Type.Number(),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; actionId: string; parameterName: string; taskId: string; idempotencyKey?: string; expectedStateVersion: number }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Commit QDash agent candidate?", `Commit candidate '${params.parameterName}' for task '${params.taskId}'?`))) {
          throw new Error("qdash_commit_agent_candidate requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      const data = await client.commitAgentActionCandidate(params.sessionId, params.actionId, params.parameterName, {
        idempotencyKey: params.idempotencyKey ?? randomUUID(),
        expectedStateVersion: params.expectedStateVersion,
        taskId: params.taskId,
      });
      return toToolResult(data, { tool: "qdash_commit_agent_candidate" });
    },
  });

  pi.registerTool({
    name: "qdash_list_forum_posts",
    label: "QDash List Forum Posts",
    description: "List QDash forum posts with optional category/status/chip/target filters.",
    promptSnippet: "List QDash forum posts",
    promptGuidelines: ["Use qdash_list_forum_posts instead of qdash_query when the user asks for QDash forum posts."],
    parameters: Type.Object({
      ...connectionParams,
      category: Type.Optional(Type.String()),
      status: Type.Optional(Type.String()),
      chipId: Type.Optional(Type.String()),
      targetType: Type.Optional(Type.String()),
      targetId: Type.Optional(Type.String()),
      skip: Type.Optional(Type.Number()),
      limit: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; category?: string; status?: string; chipId?: string; targetType?: string; targetId?: string; skip?: number; limit?: number; color?: boolean }) {
      const client = await makeClient(params);
      const data = await client.listForumPosts({
        category: params.category,
        status: params.status,
        chipId: params.chipId ?? currentContext.chipId,
        targetType: params.targetType,
        targetId: params.targetId,
        skip: params.skip,
        limit: params.limit,
      });
      return toTextToolResult(forumListLines(data, "QDash Forum", params.color).join("\n"), data, { tool: "qdash_list_forum_posts" });
    },
    renderResult(result, _options, theme) {
      const data = (result.details as { data?: unknown } | undefined)?.data;
      return textComponent(forumListLines(data, "QDash Forum"), theme);
    },
  });

  pi.registerTool({
    name: "qdash_get_forum_post",
    label: "QDash Get Forum Post",
    description: "Get a QDash forum post by postId.",
    promptSnippet: "Get QDash forum post details",
    promptGuidelines: ["Use qdash_get_forum_post to inspect one QDash forum post."],
    parameters: Type.Object({ ...connectionParams, postId: Type.String(), color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })) }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; postId: string; color?: boolean }) {
      const client = await makeClient(params);
      const data = await client.getForumPost(params.postId);
      const url = qdashWebUrl(client, forumPostPagePath(params.postId));
      return toTextToolResult(`${forumDetailLines(data, "QDash Forum Post", params.color).join("\n")}\nurl ${url}`, withQDashLinks(client, data), { tool: "qdash_get_forum_post", url });
    },
    renderResult(result, _options, theme) {
      const data = (result.details as { data?: unknown } | undefined)?.data;
      return forumDetailComponent(data, theme);
    },
  });

  pi.registerTool({
    name: "qdash_list_forum_replies",
    label: "QDash List Forum Replies",
    description: "List replies for a QDash forum post by postId.",
    promptSnippet: "List replies for a QDash forum post",
    promptGuidelines: ["Use qdash_list_forum_replies to inspect replies on a QDash forum post."],
    parameters: Type.Object({ ...connectionParams, postId: Type.String(), color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })) }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; postId: string; color?: boolean }) {
      const client = await makeClient(params);
      const data = await client.getForumPostReplies(params.postId);
      const url = qdashWebUrl(client, forumPostPagePath(params.postId));
      return toTextToolResult(`${forumListLines(data, "QDash Forum Replies", params.color).join("\n")}\nurl ${url}`, data, { tool: "qdash_list_forum_replies", url });
    },
    renderResult(result, _options, theme) {
      const data = (result.details as { data?: unknown } | undefined)?.data;
      return textComponent(forumListLines(data, "QDash Forum Replies"), theme, true);
    },
  });

  pi.registerTool({
    name: "qdash_create_forum_post",
    label: "QDash Create Forum Post",
    description: "Create a QDash forum post. This is a write operation and requires confirmation.",
    promptSnippet: "Create a QDash forum post after explicit user confirmation",
    promptGuidelines: ["Use qdash_create_forum_post only after the user confirms the exact post contents."],
    parameters: Type.Object({
      ...connectionParams,
      request: Type.Any({ description: "ForumPostCreate request body accepted by QDash." }),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; request: unknown }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Create QDash forum post?", "This will create a forum post in QDash."))) {
          throw new Error("qdash_create_forum_post requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      return toToolResult(await client.createForumPost(params.request as never), { tool: "qdash_create_forum_post" });
    },
  });

  pi.registerTool({
    name: "qdash_preview_forum_evidence_reply",
    label: "QDash Preview Forum Evidence Reply",
    description: "Preview a QDash forum evidence reply generated from a task result. Read-only; no forum post is created.",
    promptSnippet: "Prepare and review QDash evidence reply content before publishing it",
    promptGuidelines: [
      "Use qdash_preview_forum_evidence_reply before publishing investigated calibration evidence.",
      "After the user approves the preview, use qdash_create_forum_evidence_reply to write it.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      parentPostId: Type.String(),
      taskId: Type.String(),
      interpretation: Type.String({ description: "Human-readable interpretation or hypothesis to append after the task links and figures." }),
      title: Type.Optional(Type.String()),
      includeFigures: Type.Optional(Type.Boolean()),
      maxFigures: Type.Optional(Type.Number()),
      includeHistory: Type.Optional(Type.Boolean()),
      historyLimit: Type.Optional(Type.Number()),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; parentPostId: string; taskId: string; interpretation: string; title?: string; includeFigures?: boolean; maxFigures?: number; includeHistory?: boolean; historyLimit?: number }) {
      const client = await makeClient(params);
      const built = await buildForumEvidenceReply(client, params);
      return toTextToolResult(built.preview, { preview: built.preview, parent: built.parent, task: built.task, figures: built.figures }, { tool: "qdash_preview_forum_evidence_reply" });
    },
  });

  pi.registerTool({
    name: "qdash_preview_forum_image_reply",
    label: "QDash Preview Forum Image Reply",
    description: "Preview a QDash forum reply that will upload and embed locally generated analysis images. Read-only; no image or post is created.",
    promptSnippet: "Preview local analysis images and forum reply content before uploading",
    promptGuidelines: [
      "Use qdash_preview_forum_image_reply before uploading locally generated analysis images to a forum thread.",
      "Show the image paths and reply content, then require explicit confirmation before publishing.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      parentPostId: Type.String(),
      imagePaths: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }),
      interpretation: Type.String({ description: "Human-readable interpretation or context shown after the images." }),
      title: Type.Optional(Type.String()),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; parentPostId: string; imagePaths: string[]; interpretation: string; title?: string }) {
      const client = await makeClient(params);
      const prepared = await prepareForumImageReply(client, params);
      return toTextToolResult(prepared.preview, {
        preview: prepared.preview,
        parent: prepared.parent,
        images: prepared.images.map(({ blob: _blob, ...image }) => image),
      }, { tool: "qdash_preview_forum_image_reply" });
    },
  });

  pi.registerTool({
    name: "qdash_create_forum_image_reply",
    label: "QDash Create Forum Image Reply",
    description: "Upload locally generated analysis images and create a QDash forum reply embedding them. This is a write operation and requires confirmation.",
    promptSnippet: "Upload local analysis images and create a forum reply after explicit confirmation",
    promptGuidelines: [
      "Use qdash_create_forum_image_reply only after previewing the exact image paths and reply content with qdash_preview_forum_image_reply.",
      "Require explicit confirmation before uploading images or creating the reply.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      parentPostId: Type.String(),
      imagePaths: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }),
      interpretation: Type.String({ description: "Human-readable interpretation or context shown after the images." }),
      title: Type.Optional(Type.String()),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; parentPostId: string; imagePaths: string[]; interpretation: string; title?: string }, _signal, _onUpdate, ctx) {
      const client = await makeClient(params);
      const prepared = await prepareForumImageReply(client, params);
      if (!params.confirmWrite) {
        const confirmed = ctx.hasUI && await ctx.ui.confirm("Upload images and create QDash forum reply?", prepared.preview.slice(0, 1800));
        if (!confirmed) throw new Error("qdash_create_forum_image_reply requires explicit confirmation");
      }
      const created = await createForumImageReply(client, params, prepared);
      const postId = firstString(created.reply as unknown as Record<string, unknown>, ["id"]);
      const parentUrl = qdashWebUrl(client, `/forum/posts/${encodeURIComponent(params.parentPostId)}`);
      const text = [`created forum image reply${postId ? ` ${postId}` : ""}`, `parent ${parentUrl}`, "", created.content].join("\n");
      return toTextToolResult(text, created, { tool: "qdash_create_forum_image_reply", url: parentUrl });
    },
  });

  pi.registerTool({
    name: "qdash_create_forum_evidence_reply",
    label: "QDash Create Forum Evidence Reply",
    description: "Create a QDash forum reply from a task result, embedding task figures as visible QDash UI image blocks. This is a write operation and requires confirmation.",
    promptSnippet: "Create a QDash forum evidence reply with visible task figures after explicit confirmation",
    promptGuidelines: ["Use qdash_create_forum_evidence_reply when adding investigated task evidence to an existing forum thread; show the generated content and require confirmation before writing."],
    parameters: Type.Object({
      ...connectionParams,
      parentPostId: Type.String(),
      taskId: Type.String(),
      interpretation: Type.String({ description: "Human-readable interpretation or hypothesis to append after the task links and figures." }),
      title: Type.Optional(Type.String()),
      includeFigures: Type.Optional(Type.Boolean()),
      maxFigures: Type.Optional(Type.Number()),
      includeHistory: Type.Optional(Type.Boolean()),
      historyLimit: Type.Optional(Type.Number()),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; parentPostId: string; taskId: string; interpretation: string; title?: string; includeFigures?: boolean; maxFigures?: number; includeHistory?: boolean; historyLimit?: number }, _signal, _onUpdate, ctx) {
      const client = await makeClient(params);
      const built = await buildForumEvidenceReply(client, params);
      if (!params.confirmWrite) {
        const confirmed = ctx.hasUI && await ctx.ui.confirm("Create QDash forum evidence reply?", built.preview.slice(0, 1800));
        if (!confirmed) throw new Error("qdash_create_forum_evidence_reply requires explicit confirmation");
      }
      const data = await client.createForumPost(built.request as never);
      const postId = firstString(data as unknown as Record<string, unknown>, ["id"]);
      const parentUrl = qdashWebUrl(client, `/forum/posts/${encodeURIComponent(params.parentPostId)}`);
      const text = [`created forum evidence reply${postId ? ` ${postId}` : ""}`, `parent ${parentUrl}`, "", built.preview].join("\n");
      return toTextToolResult(text, { reply: data, preview: built.preview, figures: built.figures }, { tool: "qdash_create_forum_evidence_reply", url: parentUrl });
    },
  });

  pi.registerTool({
    name: "qdash_update_forum_post",
    label: "QDash Update Forum Post",
    description: "Update a QDash forum post. This is a write operation and requires confirmation.",
    promptSnippet: "Update a QDash forum post after explicit user confirmation",
    promptGuidelines: ["Use qdash_update_forum_post only after the user confirms the exact post update."],
    parameters: Type.Object({
      ...connectionParams,
      postId: Type.String(),
      request: Type.Any({ description: "ForumPostUpdate request body accepted by QDash." }),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; postId: string; request: unknown }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Update QDash forum post?", `Update forum post '${params.postId}'?`))) {
          throw new Error("qdash_update_forum_post requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      return toToolResult(await client.updateForumPost(params.postId, params.request as never), { tool: "qdash_update_forum_post" });
    },
  });

  pi.registerTool({
    name: "qdash_commit_agent_candidate_set",
    label: "QDash Commit Agent Candidate Set",
    description: "Commit a reviewed QDash agent candidate set (several candidates at once). This is a write operation and requires confirmation.",
    promptSnippet: "Commit a QDash agent candidate set after explicit user confirmation",
    promptGuidelines: ["Use qdash_commit_agent_candidate_set only after showing the candidate set and receiving explicit confirmation."],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      candidates: Type.Array(Type.Any({ description: "Agent plan candidate references accepted by QDash." })),
      idempotencyKey: Type.Optional(Type.String()),
      expectedStateVersion: Type.Number(),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; candidates: unknown[]; idempotencyKey?: string; expectedStateVersion: number }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Commit QDash agent candidate set?", `Commit ${params.candidates.length} candidate(s)?`))) {
          throw new Error("qdash_commit_agent_candidate_set requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      return toToolResult(await client.commitAgentCandidateSet(params.sessionId, params.candidates as never, {
        idempotencyKey: params.idempotencyKey ?? randomUUID(),
        expectedStateVersion: params.expectedStateVersion,
      }), { tool: "qdash_commit_agent_candidate_set" });
    },
  });

  pi.registerTool({
    name: "qdash_get_agent_candidate_commit",
    label: "QDash Get Agent Candidate Commit",
    description: "Get a QDash agent candidate commit by commitId.",
    promptSnippet: "Get QDash agent candidate commit status",
    promptGuidelines: ["Use qdash_get_agent_candidate_commit to inspect a candidate commit before applying it."],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String(), commitId: Type.String() }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; commitId: string }) {
      const client = await makeClient(params);
      return toToolResult(await client.getAgentCandidateCommit(params.sessionId, params.commitId), { tool: "qdash_get_agent_candidate_commit" });
    },
  });

  pi.registerTool({
    name: "qdash_apply_agent_candidate_commit",
    label: "QDash Apply Agent Candidate Commit",
    description: "Apply a QDash agent candidate commit to backend configuration. This is a write operation and requires confirmation.",
    promptSnippet: "Apply a QDash agent candidate commit after explicit user confirmation",
    promptGuidelines: ["Use qdash_apply_agent_candidate_commit only after showing the commit and receiving explicit confirmation."],
    parameters: Type.Object({
      ...connectionParams,
      sessionId: Type.String(),
      commitId: Type.String(),
      idempotencyKey: Type.Optional(Type.String()),
      expectedStateVersion: Type.Number(),
      pushToGithub: Type.Optional(Type.Boolean()),
      confirmWrite: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params: ConfirmableParams & { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; commitId: string; idempotencyKey?: string; expectedStateVersion: number; pushToGithub?: boolean }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Apply QDash agent candidate commit?", `Apply commit '${params.commitId}' to backend configuration?`))) {
          throw new Error("qdash_apply_agent_candidate_commit requires explicit confirmation");
        }
      }
      const client = await makeClient(params);
      return toToolResult(await client.applyAgentCandidateCommit(params.sessionId, params.commitId, {
        idempotencyKey: params.idempotencyKey ?? randomUUID(),
        expectedStateVersion: params.expectedStateVersion,
        pushToGithub: params.pushToGithub,
      }), { tool: "qdash_apply_agent_candidate_commit" });
    },
  });

  pi.registerTool({
    name: "qdash_wait_agent_candidate_apply",
    label: "QDash Wait Agent Candidate Apply",
    description: "Wait for a QDash agent candidate commit apply operation to finish.",
    promptSnippet: "Poll QDash until a candidate apply operation finishes",
    promptGuidelines: ["Use qdash_wait_agent_candidate_apply after applying a candidate commit when the user wants polling."],
    parameters: Type.Object({ ...connectionParams, sessionId: Type.String(), commitId: Type.String(), timeoutSeconds: Type.Optional(Type.Number()), pollIntervalSeconds: Type.Optional(Type.Number()) }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; sessionId: string; commitId: string; timeoutSeconds?: number; pollIntervalSeconds?: number }, signal) {
      const client = await makeClient(params);
      return toToolResult(
        await withAbort(
          client.waitForAgentCandidateApply(params.sessionId, params.commitId, { timeoutSeconds: params.timeoutSeconds, pollIntervalSeconds: params.pollIntervalSeconds }),
          signal,
          `Waiting for candidate commit ${params.commitId}`,
        ),
        { tool: "qdash_wait_agent_candidate_apply" },
      );
    },
  });

  pi.registerTool({
    name: "qdash_recent_calibration_figure",
    label: "QDash Recent Calibration Figure",
    description: "Fetch and render a figure from a recent calibration result without requiring a task ID.",
    promptSnippet: "Show a recent QDash calibration experiment image",
    promptGuidelines: ["Use qdash_recent_calibration_figure when the user asks to see recent calibration images and has not provided a task ID."],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      taskIndex: Type.Optional(Type.Number({ description: "Recent task index, newest first. Defaults to 0." })),
      figureIndex: Type.Optional(Type.Number({ description: "Figure index within the selected task. Defaults to 0." })),
      withinHours: Type.Optional(Type.Number()),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; taskIndex?: number; figureIndex?: number; withinHours?: number }) {
      const client = await makeClient(params);
      const chipId = await defaultChipId(client, params.chipId);
      const end = new Date();
      const start = new Date(end.getTime() - (params.withinHours ?? 168) * 3600_000);
      const payload = await client.listTaskResults({ chipId, startAt: start.toISOString(), endAt: end.toISOString(), limit: 50 });
      const tasks = arrayFromPayload(payload).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
      const task = tasks[params.taskIndex ?? 0];
      const taskId = task && firstString(task, ["task_id", "taskId"]);
      if (!taskId) throw new Error("No recent calibration task result with a task ID was found");
      const file: TaskResultFigureFile = await client.getTaskResultFigure(taskId, { index: params.figureIndex ?? 0 });
      const bytes = Buffer.from(file.data);
      const mediaType = file.mediaType || mediaTypeForPath(file.path ?? "");
      const details: FigureDetails = { tool: "qdash_recent_calibration_figure", taskId, path: file.path ?? "", mediaType, sizeBytes: bytes.byteLength, figurePaths: file.figurePaths ?? [], jsonFigurePaths: file.jsonFigurePaths ?? [] };
      if (mediaType.startsWith("image/")) details.base64 = bytes.toString("base64");
      else details.text = bytes.toString("utf8");
      return toFigureToolResult(figureResultText(details), details, { task, selectedPath: details.path }, details);
    },
    renderResult(result, _options, theme) {
      return figureComponent(result.details as unknown as FigureDetails, theme);
    },
  });

  pi.registerTool({
    name: "qdash_get_figure",
    label: "QDash Get Figure",
    description: "Fetch a QDash calibration figure by absolute figure path and render images in interactive TUI.",
    promptSnippet: "Fetch and render a QDash calibration figure image or JSON figure by path",
    promptGuidelines: ["Use qdash_get_figure when the user asks to inspect a calibration figure path from a task result or execution."],
    parameters: Type.Object({
      ...connectionParams,
      path: Type.String({ description: "Absolute figure path, e.g. /app/calib_data/.../fig/Figure.png" }),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; path: string }) {
      const client = await makeClient(params);
      const details = await fetchFigureDetails(client, params.path);
      return toFigureToolResult(figureResultText(details), details, { path: params.path }, details);
    },
    renderResult(result, _options, theme) {
      return figureComponent(result.details as unknown as FigureDetails, theme);
    },
  });

  pi.registerTool({
    name: "qdash_get_task_figures",
    label: "QDash Get Task Figures",
    description: "Fetch figure paths from a QDash task result and render one selected figure in interactive TUI.",
    promptSnippet: "Fetch and render calibration figures associated with a QDash task result",
    promptGuidelines: ["Use qdash_get_task_figures after inspecting a task result with figure_path/json_figure_path."],
    parameters: Type.Object({
      ...connectionParams,
      taskId: Type.String(),
      index: Type.Optional(Type.Number({ description: "Figure index to fetch. Defaults to 0." })),
      preferJson: Type.Optional(Type.Boolean({ description: "Fetch json_figure_path instead of figure_path when available." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; taskId: string; index?: number; preferJson?: boolean }) {
      const client = await makeClient(params);
      try {
        const options: TaskResultFigureOptions = { index: params.index, preferJson: params.preferJson };
        const file: TaskResultFigureFile = await client.getTaskResultFigure(params.taskId, options);
        const bytes = Buffer.from(file.data);
        const mediaType = file.mediaType || mediaTypeForPath(file.path ?? "");
        const details: FigureDetails = {
          tool: "qdash_get_task_figures",
          taskId: params.taskId,
          path: file.path ?? "",
          mediaType,
          sizeBytes: bytes.byteLength,
          figurePaths: file.figurePaths ?? [],
          jsonFigurePaths: file.jsonFigurePaths ?? [],
        };
        if (mediaType.startsWith("image/")) details.base64 = bytes.toString("base64");
        else details.text = bytes.toString("utf8");
        return toFigureToolResult(figureResultText(details), details, { taskId: params.taskId, figurePaths: details.figurePaths, jsonFigurePaths: details.jsonFigurePaths, selectedPath: details.path }, details);
      } catch (error) {
        return toTextToolResult(boxed("QDash Task Figures", [
          `task ${params.taskId}`,
          "",
          error instanceof Error ? error.message : String(error),
        ]).join("\n"), { taskId: params.taskId, error: error instanceof Error ? error.message : String(error) }, { tool: "qdash_get_task_figures", taskId: params.taskId, path: "", mediaType: "", sizeBytes: 0 } satisfies FigureDetails);
      }
    },
    renderResult(result, _options, theme) {
      return figureComponent(result.details as unknown as FigureDetails, theme);
    },
  });

  pi.registerTool({
    name: "qdash_analyze_figure_json",
    label: "QDash Analyze Figure JSON",
    description: "Read-only helper that fetches a Plotly JSON calibration figure and summarizes numeric traces for agentic diagnosis.",
    promptSnippet: "Analyze QDash calibration figure JSON traces without changing parameters",
    promptGuidelines: [
      "Use qdash_analyze_figure_json when a calibration figure has json_figure_path and you need numeric evidence from scatter or heatmap traces.",
      "Treat the output as evidence for a skill/runbook decision; do not commit/apply parameters from this analysis alone.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      path: Type.Optional(Type.String({ description: "Absolute JSON figure path. If omitted, taskId is required." })),
      taskId: Type.Optional(Type.String({ description: "Task result ID used to select json_figure_path." })),
      index: Type.Optional(Type.Number({ description: "JSON figure index for taskId selection. Defaults to 0." })),
      includeData: Type.Optional(Type.Boolean({ description: "Include parsed Plotly JSON in structured data. Defaults to false." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; path?: string; taskId?: string; index?: number; includeData?: boolean }) {
      const client = await makeClient(params);
      let path = params.path;
      let text = "";
      if (path) {
        const details = await fetchFigureDetails(client, path);
        text = details.text ?? "";
      } else {
        const taskId = requireValue(params.taskId, "taskId");
        const file: TaskResultFigureFile = await client.getTaskResultFigure(taskId, { index: params.index, preferJson: true });
        path = file.path;
        text = Buffer.from(file.data).toString("utf8");
      }
      const figure = JSON.parse(text) as unknown;
      const analysis = analyzePlotlyFigure(path ?? "", figure, params.taskId);
      return toTextToolResult(figureAnalysisText(analysis), { analysis, figure: params.includeData ? figure : undefined }, { tool: "qdash_analyze_figure_json", path, data: analysis });
    },
  });

  pi.registerTool({
    name: "qdash_build_qcal_evidence",
    label: "QDash Build QCal Evidence",
    description: "Summarize a QDash task result (target, sweep and run settings) as evidence for pi-qcaleval's qcal_evaluate, returning the task figure as image content. Fitted results are left out unless includeMetrics is set.",
    promptSnippet: "Summarize a QDash calibration task result as evidence for qcal_evaluate",
    promptGuidelines: [
      "Use qdash_build_qcal_evidence before qcal_evaluate when the user asks to evaluate a QDash calibration task with pi-qcaleval; pass the returned summary as the context of qcal_evaluate.",
      "qdash_build_qcal_evidence is read-only and only converts QDash data into a generic evidence bundle; it does not evaluate, execute, commit, or apply calibration parameters.",
      "The task figure comes back as image content, so qcal_evaluate can follow directly without fetching the figure again; treat the evaluation as advisory evidence.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      taskId: Type.String(),
      includeFigures: Type.Optional(Type.Boolean({ description: "Embed task image figures as data URLs. Defaults to true." })),
      includeFigureAnalysis: Type.Optional(Type.Boolean({ description: "Analyze Plotly JSON figures and include summaries/warnings in notes. Defaults to true." })),
      maxFigures: Type.Optional(Type.Number({ description: "Maximum image figures to embed. Defaults to 1." })),
      includeRawTaskResult: Type.Optional(Type.Boolean({ description: "Include the full raw task result in resultJson. Defaults to false." })),
      includeInputs: Type.Optional(Type.Boolean({ description: "Add the calibration inputs (previous values) to the evidence text. Defaults to false: the evaluation model reads the plot." })),
      includeMetrics: Type.Optional(Type.Boolean({ description: "Add the fitted output parameters to the evidence text. Defaults to false: the evaluation model reads the plot." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; taskId: string; includeFigures?: boolean; includeFigureAnalysis?: boolean; maxFigures?: number; includeRawTaskResult?: boolean; includeInputs?: boolean; includeMetrics?: boolean }) {
      const client = await makeClient(params);
      const task = await client.getTaskResult(params.taskId) as unknown as Record<string, unknown>;
      const figures: Array<Record<string, unknown>> = [];
      const images: Array<{ type: "image"; data: string; mimeType: string }> = [];
      const notes: string[] = [];
      const figurePaths = Array.isArray(task.figure_path) ? task.figure_path.filter((item): item is string => typeof item === "string") : [];
      const jsonFigurePaths = Array.isArray(task.json_figure_path) ? task.json_figure_path.filter((item): item is string => typeof item === "string") : [];

      if (params.includeFigureAnalysis !== false) {
        const limit = Math.min(jsonFigurePaths.length, params.maxFigures ?? 1);
        for (let index = 0; index < limit; index += 1) {
          try {
            const file: TaskResultFigureFile = await client.getTaskResultFigure(params.taskId, { index, preferJson: true });
            const figure = JSON.parse(Buffer.from(file.data).toString("utf8")) as unknown;
            const analysis = analyzePlotlyFigure(file.path ?? jsonFigurePaths[index] ?? "", figure, params.taskId);
            notes.push(`Figure JSON analysis #${index + 1}:`, ...analysis.summaries.map((line) => `- ${line}`));
            if (analysis.warnings.length) notes.push("Warnings:", ...analysis.warnings.map((line) => `- ${line}`));
            figures.push({ path: file.path ?? jsonFigurePaths[index], role: "plotly", data: figure });
          } catch (error) {
            notes.push(`Figure JSON analysis #${index + 1} failed: ${error instanceof Error ? error.message : String(error)}`);
          }
        }
      }

      if (params.includeFigures !== false) {
        const limit = Math.min(figurePaths.length, params.maxFigures ?? 1);
        for (let index = 0; index < limit; index += 1) {
          try {
            const file: TaskResultFigureFile = await client.getTaskResultFigure(params.taskId, { index, preferJson: false });
            const bytes = Buffer.from(file.data);
            const mediaType = file.mediaType || mediaTypeForPath(file.path ?? figurePaths[index] ?? "");
            if (mediaType.startsWith("image/")) {
              const base64 = bytes.toString("base64");
              figures.push({ path: file.path ?? figurePaths[index], url: `data:${mediaType};base64,${base64}`, mimeType: mediaType, role: "plot" });
              images.push({ type: "image", data: base64, mimeType: mediaType });
            }
          } catch (error) {
            notes.push(`Figure image #${index + 1} embedding failed: ${error instanceof Error ? error.message : String(error)}`);
          }
        }
      }

      const couplingId = firstStringField(task, ["coupling_id", "couplingId", "qid"]);
      const qid = firstStringField(task, ["qid"]);
      const runParameters = recordedParameters(task.run_parameters);
      const evidence: CalibrationEvidence = {
        id: params.taskId,
        source: "external",
        target: {
          kind: couplingId && couplingId.includes("-") ? "coupling" : qid ? "qubit" : "system",
          id: couplingId ?? qid,
          couplingId: couplingId && couplingId.includes("-") ? couplingId : undefined,
          qids: qid && !qid.includes("-") ? [qid] : undefined,
          chipId: firstStringField(task, ["chip_id", "chipId"]),
        },
        task: {
          name: firstStringField(task, ["task_name", "taskName", "name"]),
          objective: `Evaluate QDash calibration task ${firstStringField(task, ["task_name", "taskName", "name"]) ?? params.taskId}`,
          backend: firstStringField(task, ["backend", "chip_id", "chipId"]),
          startedAt: firstStringField(task, ["start_at", "startAt"]),
          completedAt: firstStringField(task, ["end_at", "endAt"]),
          status: firstStringField(task, ["status"]),
          message: typeof task.message === "string" && task.message.trim() ? task.message.trim() : undefined,
        },
        metrics: parameterValueRecord(task.output_parameters),
        parameters: { ...parameterValueRecord(task.input_parameters), ...parameterValueRecord(task.run_parameters) },
        runParameters,
        sweeps: sweepsOf(runParameters),
        inputParameters: recordedParameters(task.input_parameters),
        metricRecords: recordedParameters(task.output_parameters),
        figures: figures.length ? figures : undefined,
        notes: [
          typeof task.message === "string" ? `Task message: ${task.message}` : undefined,
          notes.length ? notes.join("\n") : undefined,
        ].filter(Boolean).join("\n\n") || undefined,
        resultJson: params.includeRawTaskResult ? task : {
          task_id: task.task_id,
          execution_id: task.execution_id,
          flow_name: task.flow_name,
          figure_path: figurePaths,
          json_figure_path: jsonFigurePaths,
          links: task._links,
        },
      };

      const result = toTextToolResult(
        qcalEvidenceText(evidence, { inputs: params.includeInputs === true, metrics: params.includeMetrics === true }),
        { evidence },
        { tool: "qdash_build_qcal_evidence", taskId: params.taskId, evidence },
      );
      return { ...result, content: [...result.content, ...images] };
    },
  });

  registerQueryTool({
    name: "qdash_get_provenance_stats",
    label: "QDash Provenance Stats",
    description: "Get QDash provenance statistics.",
    promptSnippet: "Get QDash provenance stats",
    action: "provenance_stats",
    parameters: Type.Object(connectionParams),
  });

  pi.registerTool({
    name: "qdash_degradation_report",
    label: "QDash Degradation Report",
    description: "Show read-only provenance degradation trends, recent parameter changes, execution lock state, and optional downstream recalibration recommendations.",
    promptSnippet: "Inspect QDash degradation trends and recalibration impact before changing parameters",
    promptGuidelines: [
      "Use qdash_degradation_report before planning calibration changes or when investigating drift.",
      "The execution lock is a safety signal, not permission to bypass confirmation or start work.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      withinHours: Type.Optional(Type.Number()),
      minStreak: Type.Optional(Type.Number()),
      limit: Type.Optional(Type.Number()),
      entityId: Type.Optional(Type.String({ description: "Optional provenance entity ID for downstream recalibration recommendations." })),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; withinHours?: number; minStreak?: number; limit?: number; entityId?: string; color?: boolean }) {
      const report = await buildDegradationReport(params);
      return toTextToolResult(degradationReportLines(report, params.color).join("\\n"), report, { tool: "qdash_degradation_report", webBaseUrl: report.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const report = (result.details as { data?: DegradationReport } | undefined)?.data;
      return report ? textComponent(degradationReportLines(report).join("\\n").split("\\n"), theme) : textComponent(["No degradation report"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_validate_calibration",
    label: "QDash Validate Calibration",
    description: "Validate a calibration task result with explicit gates for status and figures. Read-only; does not commit or apply candidates.",
    promptSnippet: "Validate a QDash calibration result before continuing or committing parameters",
    promptGuidelines: [
      "Use qdash_validate_calibration after an operational task completes or fails.",
      "A passed validation is not approval to commit or apply parameters; require explicit confirmation for those writes.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      taskId: Type.String(),
      beforeExecutionId: Type.Optional(Type.String({ description: "Optional earlier execution ID to compare against the task's execution." })),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; taskId: string; beforeExecutionId?: string; color?: boolean }) {
      const validation = await buildCalibrationValidation(params);
      return toTextToolResult(calibrationValidationLines(validation, params.color).join("\\n"), validation, { tool: "qdash_validate_calibration", webBaseUrl: validation.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const validation = (result.details as { data?: CalibrationValidation } | undefined)?.data;
      return validation ? textComponent(calibrationValidationLines(validation).join("\\n").split("\\n"), theme) : textComponent(["No calibration validation"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_plan_calibration",
    label: "QDash Plan Calibration",
    description: "Create a read-only dry-run calibration plan for one qubit or coupling. It never executes tasks or changes parameters.",
    promptSnippet: "Plan a safe QDash calibration workflow without executing it",
    promptGuidelines: [
      "Use qdash_plan_calibration after inspecting a target and before any operational calibration action.",
      "Present the plan and require explicit confirmation for each write or task-execution step.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String()),
      couplingId: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      withinHours: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number; color?: boolean }) {
      const report = await buildTargetOperationsReport(params);
      const plan = buildCalibrationPlan(report);
      return toTextToolResult(calibrationPlanLines(plan, params.color).join("\\n"), plan, { tool: "qdash_plan_calibration" });
    },
    renderResult(result, _options, theme) {
      const plan = (result.details as { data?: CalibrationPlan } | undefined)?.data;
      return plan ? textComponent(calibrationPlanLines(plan).join("\\n").split("\\n"), theme) : textComponent(["No calibration plan"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_target_report",
    label: "QDash Target Report",
    description: "Build a read-only operational report for one qubit or coupling, correlating recent results, failures, Forum context, and a safe next-action recommendation.",
    promptSnippet: "Inspect one QDash qubit or coupling as an operational incident report",
    promptGuidelines: [
      "Use qdash_target_report before calibration changes when a specific qubit or coupling is under investigation.",
      "This is read-only; do not treat the recommendation as approval to execute or commit a calibration action.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String({ description: "Qubit ID. Defaults to the selected QDash target." })),
      couplingId: Type.Optional(Type.String({ description: "Coupling ID. Defaults to the selected QDash target." })),
      limit: Type.Optional(Type.Number()),
      withinHours: Type.Optional(Type.Number({ description: "Lookback window. Defaults to 168 hours." })),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number; color?: boolean }) {
      const report = await buildTargetOperationsReport(params);
      return toTextToolResult(targetOperationsReportLines(report, params.color).join("\\n"), report, { tool: "qdash_target_report", webBaseUrl: report.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const report = (result.details as { data?: TargetOperationsReport } | undefined)?.data;
      return report ? textComponent(targetOperationsReportLines(report).join("\\n").split("\\n"), theme) : textComponent(["No target report"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_dashboard",
    label: "QDash Dashboard",
    description: "Build a compact read-only QDash dashboard for the current profile/chip context.",
    promptSnippet: "Show QDash harness dashboard: chips, open Forum threads, recent executions, failed task results, and provenance stats",
    promptGuidelines: [
      "Use qdash_dashboard when the user asks for QDash status, overview, triage, or a dashboard.",
      "Summarize dashboard data instead of dumping large raw payloads.",
    ],
    parameters: Type.Object({ ...connectionParams, ...chipScopedParams, limit: Type.Optional(Type.Number()), color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })) }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number; color?: boolean }) {
      const dashboard = await buildDashboard(params);
      return toTextToolResult(dashboardLines(dashboard, params.color).join("\n"), dashboard, { tool: "qdash_dashboard", lines: dashboardLines(dashboard) });
    },
    renderCall(args, theme) {
      const profile = args.profile ?? currentContext.profile ?? "context";
      return new Text(theme.fg("toolTitle", theme.bold("qdash_dashboard ")) + theme.fg("muted", profile), 0, 0);
    },
    renderResult(result, _options, theme) {
      const details = result.details as { data?: Awaited<ReturnType<typeof buildDashboard>> } | undefined;
      if (details?.data) return dashboardComponent(details.data, theme);
      return new Text(theme.fg("dim", "QDash dashboard unavailable"), 0, 0);
    },
  });

  pi.registerTool({
    name: "qdash_dashboard_insights",
    label: "QDash Dashboard Insights",
    description: "Correlate dashboard metrics, open Forum posts, and failed tasks into target-level insights with links.",
    promptSnippet: "Generate QDash target insights from dashboard metrics, forum links, notes, and failed tasks",
    promptGuidelines: ["Use qdash_dashboard_insights when the user asks for insights across dashboard metrics, target summaries, Forum posts, or anomalous targets."],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      withinHours: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number; withinHours?: number; color?: boolean }) {
      const result = await buildDashboardInsights(params);
      return toTextToolResult(dashboardInsightLines(result, params.color).join("\n"), result, { tool: "qdash_dashboard_insights", webBaseUrl: result.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const data = (result.details as { data?: DashboardInsightsResult } | undefined)?.data;
      return data ? textComponent(dashboardInsightLines(data).join("\n").split("\n"), theme) : textComponent(["No dashboard insights"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_compare_calibration",
    label: "QDash Compare Calibration",
    description: "Compare repeated calibration results for one qubit or coupling without changing parameters.",
    promptSnippet: "Compare the latest QDash calibration with the previous one",
    promptGuidelines: ["Use qdash_compare_calibration when the user asks what changed between recent calibration experiments."],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String()),
      couplingId: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; color?: boolean }) {
      const comparison = await buildCalibrationComparison(params);
      return toTextToolResult(calibrationComparisonLines(comparison, params.color).join("\\n"), comparison, { tool: "qdash_compare_calibration", webBaseUrl: comparison.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const comparison = (result.details as { data?: CalibrationComparison } | undefined)?.data;
      return comparison ? textComponent(calibrationComparisonLines(comparison).join("\\n").split("\\n"), theme) : textComponent(["No calibration comparison"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_investigate",
    label: "QDash Investigate",
    description: "Run a read-only natural-language-friendly QDash investigation combining recent calibration results, target history, failures, Forum context, and safe recommendations.",
    promptSnippet: "Investigate a QDash target or recent calibration by correlating results, figures, and Forum context",
    promptGuidelines: [
      "Use qdash_investigate when the user asks to investigate, compare, or understand a QDash target or recent calibration in natural language.",
      "This tool is read-only; do not execute tasks or change parameters based on its recommendation without explicit confirmation.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String()),
      couplingId: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      withinHours: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number; color?: boolean }) {
      const report = await buildInvestigationReport(params);
      return toTextToolResult(investigationLines(report, params.color).join("\\n"), report, { tool: "qdash_investigate", webBaseUrl: report.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const report = (result.details as { data?: InvestigationReport } | undefined)?.data;
      return report ? textComponent(investigationLines(report).join("\\n").split("\\n"), theme) : textComponent(["No QDash investigation"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_recent_calibration_summary",
    label: "QDash Recent Calibration Summary",
    description: "Summarize recent calibration task outcomes with QDash Web UI links.",
    promptSnippet: "Summarize recent QDash calibration results and return task/execution URLs",
    promptGuidelines: ["Use qdash_recent_calibration_summary when the user asks for recent calibration results, what happened, or quick links to details."],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      withinHours: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number; withinHours?: number; color?: boolean }) {
      const summary = await buildRecentCalibrationSummary(params);
      return toTextToolResult(recentCalibrationSummaryLines(summary, params.color).join("\n"), summary, { tool: "qdash_recent_calibration_summary", webBaseUrl: summary.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const summary = (result.details as { data?: RecentCalibrationSummary } | undefined)?.data;
      return summary ? recentCalibrationSummaryComponent(summary, theme) : textComponent(["No calibration summary"], theme);
    },
  });

  pi.registerTool({
    name: "qdash_recommend_next_action",
    label: "QDash Recommend Next Action",
    description: "Recommend the next safe calibration action from recent task outcomes and current target context.",
    promptSnippet: "Recommend the next QDash calibration action",
    promptGuidelines: ["Use qdash_recommend_next_action before continuing autonomous calibration after a failed or completed calibration task."],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String()),
      qid: Type.Optional(Type.String()),
      couplingId: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number()),
      withinHours: Type.Optional(Type.Number()),
      color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })),
    }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; qid?: string; couplingId?: string; limit?: number; withinHours?: number; color?: boolean }) {
      const summary = await buildRecentCalibrationSummary(params);
      const target = params.qid ?? currentContext.qid ?? params.couplingId ?? currentContext.couplingId;
      const recommendations = recommendFromCalibrationSummary(summary, target);
      return toTextToolResult(recommendationLines(recommendations, params.color).join("\n"), { recommendations, summary }, { tool: "qdash_recommend_next_action", webBaseUrl: summary.context.webBaseUrl });
    },
    renderResult(result, _options, theme) {
      const recommendations = ((result.details as { data?: { recommendations?: RecommendedNextAction[] } } | undefined)?.data?.recommendations) ?? [];
      return textComponent(recommendationLines(recommendations).join("\n").split("\n"), theme);
    },
  });

  pi.registerTool({
    name: "qdash_triage_overview",
    label: "QDash Triage Overview",
    description: "Create a read-only triage overview from open Forum threads and failed task results for the current QDash context.",
    promptSnippet: "Summarize QDash open Forum threads and failed task results for triage",
    promptGuidelines: ["Use qdash_triage_overview when the user asks what to investigate next in QDash."],
    parameters: Type.Object({ ...connectionParams, ...chipScopedParams, limit: Type.Optional(Type.Number()), color: Type.Optional(Type.Boolean({ description: "Emit ANSI colors in text output for terminal display." })) }),
    async execute(_toolCallId, params: { profile?: string; configPath?: string; useEnv?: boolean; chipId?: string; limit?: number; color?: boolean }) {
      const dashboard = await buildDashboard(params);
      const triage = {
        context: dashboard.context,
        openThreads: dashboard.openThreads,
        failedTaskResults: dashboard.failedTaskResults,
        suggestedFocus: [
          dashboard.failedTaskResults.count > 0 ? "Review failed task results first." : undefined,
          dashboard.openThreads.count > 0 ? "Review open Forum threads and correlate with recent executions." : undefined,
        ].filter(Boolean),
      };
      const accent = (text: string) => params.color ? ansi("1;36", text) : text;
      const dim = (text: string) => params.color ? ansi("2", text) : text;
      const success = (text: string) => params.color ? ansi("32", text) : text;
      const error = (text: string) => params.color ? ansi("31", text) : text;
      const lines = boxed("QDash Triage", [
        `open threads ${triage.openThreads.count > 0 ? ansi("33", String(triage.openThreads.count)) : success(String(triage.openThreads.count))}`,
        `failed tasks ${triage.failedTaskResults.count > 0 ? error(`${triage.failedTaskResults.shown}/${triage.failedTaskResults.count}`) : success(`${triage.failedTaskResults.shown}/${triage.failedTaskResults.count}`)}`,
        "",
        accent("Suggested focus"),
        ...(triage.suggestedFocus.length > 0 ? triage.suggestedFocus.map((item) => `  - ${params.color ? ansi("33", item ?? "") : item}`) : [`  ${dim("none")}`]),
        "",
        accent("Failed task results"),
        ...(dashboard.failedTaskResults.items.length > 0 ? dashboard.failedTaskResults.items.map((item, index) => `  ${params.color ? error(formatItem(item, `task-${index + 1}`)) : formatItem(item, `task-${index + 1}`)}`) : [`  ${dim("none")}`]),
      ], params.color);
      return toTextToolResult(lines.join("\n"), triage, { tool: "qdash_triage_overview" });
    },
    renderResult(result, _options, theme) {
      const data = (result.details as { data?: { openThreads?: { count?: number }; failedTaskResults?: { count?: number }; suggestedFocus?: string[] } } | undefined)?.data;
      if (!data) return new Text(theme.fg("dim", "QDash triage unavailable"), 0, 0);
      const lines = [
        theme.fg("accent", theme.bold("QDash Triage")),
        `${theme.fg("muted", "open threads")} ${theme.fg((data.openThreads?.count ?? 0) > 0 ? "warning" : "success", String(data.openThreads?.count ?? 0))}`,
        `${theme.fg("muted", "failed tasks")} ${theme.fg((data.failedTaskResults?.count ?? 0) > 0 ? "error" : "success", String(data.failedTaskResults?.count ?? 0))}`,
        "",
        theme.fg("borderAccent", "Suggested focus"),
        ...(data.suggestedFocus?.length ? data.suggestedFocus.map((item) => `  ${theme.fg("warning", item)}`) : [`  ${theme.fg("dim", "none")}`]),
      ];
      return new Text(lines.join("\n"), 0, 0);
    },
  });

  pi.registerTool({
    name: "qdash_raw_get",
    label: "QDash Raw GET",
    description: "Run a read-only raw GET request through qdash-client transport for endpoints not covered by qdash_query.",
    promptSnippet: "Call a read-only QDash GET endpoint through qdash-client",
    promptGuidelines: ["Use qdash_raw_get only for read-only QDash endpoints not covered by qdash_query. Do not use it for operationally sensitive endpoints without user confirmation."],
    parameters: Type.Object({
      ...connectionParams,
      path: Type.String({ description: "API path, e.g. /task-results/timeseries" }),
      query: Type.Optional(Type.Record(Type.String(), Type.Any())),
    }),
    async execute(_toolCallId, params: RawGetParams) {
      if (!params.path.startsWith("/")) throw new Error("path must start with '/'");
      if (/\/files\/git\/(pull|push)|\/flows\/[^/]+\/execute|\/executions\/[^/]+\/re-execute|\/admin\b|\/auth\b/i.test(params.path)) {
        throw new Error("This endpoint is operationally sensitive; ask the user for explicit confirmation and use an appropriate dedicated workflow.");
      }
      const client = await makeClient(params);
      const data = await (client as unknown as { get<T>(path: string, query?: unknown): Promise<T> }).get(params.path, params.query ?? {});
      return toToolResult(data, { path: params.path });
    },
  });

  const persistContext = () => {
    const context = { ...currentContext };
    pi.appendEntry(CONTEXT_ENTRY_TYPE, context);
    saveGlobalContext(context);
  };

  const refreshContextUi = (ctx: { ui: { theme?: Theme; setStatus: (key: string, value: string) => void; setWidget?: (key: string, lines: string[]) => void } }) => {
    ctx.ui.setStatus("qdash", contextStatusLine(ctx.ui.theme));
  };

  const ensureActiveChip = async () => {
    if (currentContext.chipId) return false;
    const client = await makeClient({ profile: currentContext.profile });
    currentContext = { ...currentContext, chipId: await client.getDefaultChipId() };
    return true;
  };

  pi.on("tool_result", async (event, ctx) => {
    if (event.isError || !event.toolName.startsWith("qdash_")) return;
    if (!adoptContextFromToolInput(event.input)) return;
    try {
      await ensureActiveChip();
    } catch {
      // Keep the selected profile visible even if QDash cannot resolve chips right now.
    }
    persistContext();
    if (ctx.hasUI) refreshContextUi(ctx);
  });

  pi.registerCommand("qdash-setup", {
    description: "Quickly configure QDash context; usage: /qdash-setup [profile] [chip_id]",
    handler: async (args, ctx) => {
      const [profileArg, chipArg] = args.trim().split(/\s+/).filter(Boolean);
      const profile = profileArg ?? currentContext.profile ?? "default";
      try {
        const client = await makeClient({ profile });
        const chipId = chipArg ?? currentContext.chipId ?? await client.getDefaultChipId();
        currentContext = { ...currentContext, profile, chipId };
        persistContext();
        refreshContextUi(ctx);
        const dashboard = await buildDashboard({ profile, chipId, limit: 5 });
        ctx.ui.setWidget("qdash", (_tui, theme) => dashboardComponent(dashboard, theme));
        ctx.ui.notify(`QDash setup complete: profile ${profile}, chip ${chipId}`, "info");
      } catch (error) {
        ctx.ui.notify(`QDash setup failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("qdash-use-profile", {
    description: "Set the current QDash profile for this pi session",
    handler: async (args, ctx) => {
      const profile = args.trim();
      if (!profile) {
        ctx.ui.notify("Usage: /qdash-use-profile <profile>", "warning");
        return;
      }
      const client = await makeClient({ profile });
      currentContext = { ...currentContext, profile, chipId: await client.getDefaultChipId() };
      persistContext();
      refreshContextUi(ctx);
      ctx.ui.notify(`QDash profile set to ${profile}, chip ${currentContext.chipId}`, "info");
    },
  });

  pi.registerCommand("qdash-use-chip", {
    description: "Set the current QDash chip ID for this pi session; omit the argument to use the default chip",
    handler: async (args, ctx) => {
      const requested = args.trim() || undefined;
      const client = await makeClient({});
      const chipId = requested ?? await client.getDefaultChipId();
      currentContext = { ...currentContext, chipId };
      persistContext();
      refreshContextUi(ctx);
      ctx.ui.notify(`QDash chip set to ${chipId}`, "info");
    },
  });

  pi.registerCommand("qdash-use-target", {
    description: "Set the current QDash calibration target; usage: /qdash-use-target qid <qid> | coupling <coupling_id>",
    handler: async (args, ctx) => {
      const [kind, value] = args.trim().split(/\s+/).filter(Boolean);
      if (!kind || !value || !["qid", "q", "qubit", "coupling", "c"].includes(kind)) {
        ctx.ui.notify("Usage: /qdash-use-target qid <qid> | coupling <coupling_id>", "warning");
        return;
      }
      if (["qid", "q", "qubit"].includes(kind)) {
        const { couplingId: _couplingId, ...rest } = currentContext;
        currentContext = { ...rest, qid: value };
      } else {
        const { qid: _qid, ...rest } = currentContext;
        currentContext = { ...rest, couplingId: value };
      }
      persistContext();
      refreshContextUi(ctx);
      ctx.ui.notify(`QDash target set to ${currentContext.qid ? `q${currentContext.qid}` : `c${currentContext.couplingId}`}`, "info");
    },
  });

  pi.registerCommand("qdash-use-agent-session", {
    description: "Set the current QDash agent session ID for this pi session",
    handler: async (args, ctx) => {
      const agentSessionId = args.trim();
      if (!agentSessionId) {
        ctx.ui.notify("Usage: /qdash-use-agent-session <session_id>", "warning");
        return;
      }
      currentContext = { ...currentContext, agentSessionId };
      persistContext();
      refreshContextUi(ctx);
      ctx.ui.notify(`QDash agent session set to ${agentSessionId}`, "info");
    },
  });

  pi.registerCommand("qdash-investigation-setup", {
    description: "Create or edit a reusable generic timeseries investigation context; accepts optional JSON",
    handler: async (args, ctx) => {
      const template: TimeseriesInvestigationContext = currentContext.investigation ?? {
        name: "timeseries-investigation",
        timezoneOffsetMinutes: 540,
        qdashSeries: currentContext.qid ? [
          { parameter: "metric_a", qid: currentContext.qid },
          { parameter: "metric_b", qid: currentContext.qid },
        ] : [
          { parameter: "metric_a" },
          { parameter: "metric_b" },
        ],
        analysis: { resampleMinutes: 1, detrend: "none", normalize: "none" },
      };
      const source = args.trim() || await ctx.ui.editor("QDash investigation context (JSON)", JSON.stringify(template, null, 2));
      if (!source) return;
      try {
        const investigation = validateInvestigationContext(JSON.parse(source));
        currentContext = { ...currentContext, investigation };
        persistContext();
        refreshContextUi(ctx);
        ctx.ui.setWidget("qdash", ["QDash Investigation", investigationContextSummary(investigation)]);
        ctx.ui.notify(`Investigation context saved: ${investigationContextSummary(investigation)}`, "info");
      } catch (error) {
        ctx.ui.notify(`Invalid investigation context: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("qdash-clear-investigation", {
    description: "Clear the reusable timeseries investigation context without changing profile/chip context",
    handler: async (_args, ctx) => {
      const { investigation: _investigation, ...rest } = currentContext;
      currentContext = rest;
      persistContext();
      refreshContextUi(ctx);
      ctx.ui.notify("QDash investigation context cleared", "info");
    },
  });

  pi.registerCommand("qdash-clear-context", {
    description: "Clear the current QDash profile/chip/agent-session/investigation context",
    handler: async (_args, ctx) => {
      currentContext = {};
      persistContext();
      refreshContextUi(ctx);
      ctx.ui.setWidget("qdash", ["QDash context cleared", "profile env/default", "chip auto-chip", "session none"]);
      ctx.ui.notify("QDash context cleared", "info");
    },
  });

  pi.registerCommand("qdash-degradation-report", {
    description: "Show read-only QDash degradation trends and execution lock state",
    handler: async (_args, ctx) => {
      try {
        const report = await buildDegradationReport({});
        refreshContextUi(ctx);
        ctx.ui.setWidget("qdash", (_tui, theme) => textComponent(degradationReportLines(report).slice(1, -1), theme, true));
        ctx.ui.notify(`QDash degradation report updated: ${report.context.chipId}`, "info");
      } catch (error) {
        ctx.ui.notify(`QDash degradation report failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("qdash-plan-calibration", {
    description: "Show a read-only dry-run calibration plan for the selected target",
    handler: async (_args, ctx) => {
      try {
        const report = await buildTargetOperationsReport({});
        const plan = buildCalibrationPlan(report);
        refreshContextUi(ctx);
        ctx.ui.setWidget("qdash", (_tui, theme) => textComponent(calibrationPlanLines(plan).slice(1, -1), theme, true));
        ctx.ui.notify(`QDash dry-run plan prepared: ${plan.target.label}`, "info");
      } catch (error) {
        ctx.ui.notify(`QDash plan failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("qdash-target-report", {
    description: "Show a read-only operational report; usage: /qdash-target-report qid <qid> | coupling <coupling_id>",
    handler: async (args, ctx) => {
      const [kind, value] = args.trim().split(/\\s+/).filter(Boolean);
      const params = kind && value && ["qid", "q", "qubit", "coupling", "c"].includes(kind)
        ? ["qid", "q", "qubit"].includes(kind) ? { qid: value } : { couplingId: value }
        : {};
      try {
        const report = await buildTargetOperationsReport(params);
        refreshContextUi(ctx);
        ctx.ui.setWidget("qdash", (_tui, theme) => textComponent(targetOperationsReportLines(report).slice(1, -1), theme, true));
        ctx.ui.notify(`QDash target report updated: ${report.target.label}`, "info");
      } catch (error) {
        ctx.ui.notify(`QDash target report failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("qdash-wiring-insights", {
    description: "Show wiring attenuation insights for the active/newest cooldown",
    handler: async (_args, ctx) => {
      try {
        const data = await resolveCooldownWiring({ includeBlocks: false, includeHistory: false, includeInsights: true });
        refreshContextUi(ctx);
        const insights = data.insights;
        if (insights) {
          ctx.ui.setWidget("qdash", (_tui, theme) => textComponent(wiringInsightLines(insights).slice(1, -1), theme, true));
          ctx.ui.notify(`QDash wiring insights updated: ${data.selection.resolved_cooldown_id}`, "info");
        } else {
          ctx.ui.setWidget("qdash", ["QDash Wiring Insights", "No markdown wiring table found"]);
          ctx.ui.notify("QDash wiring insights unavailable: no markdown table", "warning");
        }
      } catch (error) {
        ctx.ui.notify(`QDash wiring insights failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("qdash-dashboard", {
    description: "Show a compact QDash dashboard for the current context",
    handler: async (args, ctx) => {
      const limit = args.trim() ? Number(args.trim()) : undefined;
      const dashboard = await buildDashboard({ limit: Number.isFinite(limit) ? limit : undefined });
      refreshContextUi(ctx);
      ctx.ui.setWidget("qdash", (_tui, theme) => dashboardComponent(dashboard, theme));
      ctx.ui.notify(`QDash dashboard updated: ${dashboard.openThreads.count} open Forum threads, ${dashboard.failedTaskResults.count} failed tasks`, "info");
    },
  });

  pi.registerCommand("qdash-refresh", {
    description: "Refresh the QDash dashboard widget for the current context",
    handler: async (args, ctx) => {
      const limit = args.trim() ? Number(args.trim()) : undefined;
      const dashboard = await buildDashboard({ limit: Number.isFinite(limit) ? limit : undefined });
      refreshContextUi(ctx);
      ctx.ui.setWidget("qdash", (_tui, theme) => dashboardComponent(dashboard, theme));
      ctx.ui.notify("QDash widget refreshed", "info");
    },
  });

  pi.registerCommand("qdash-context", {
    description: "Show the current QDash context",
    handler: async (_args, ctx) => {
      refreshContextUi(ctx);
      ctx.ui.setWidget("qdash", [
        "QDash Context",
        `profile ${currentContext.profile ?? "env/default"}`,
        `chip ${currentContext.chipId ?? "auto-chip"}`,
        `target ${currentContext.qid ? `q${currentContext.qid}` : currentContext.couplingId ? `c${currentContext.couplingId}` : "none"}`,
        `task ${currentContext.taskName ?? "none"}`,
        `last execution ${currentContext.lastExecutionId ?? "none"}`,
        `last task ${currentContext.lastTaskId ?? "none"}`,
        `agent session ${currentContext.agentSessionId ?? "none"}`,
        `investigation ${currentContext.investigation ? investigationContextSummary(currentContext.investigation) : "none"}`,
      ]);
      ctx.ui.notify(contextSummary(), "info");
    },
  });

  pi.registerCommand("qdash-config", {
    description: "Show non-secret QDash config/profile information",
    handler: async (args, ctx) => {
      const profile = args.trim() || undefined;
      const profiles = configProfiles();
      try {
        const client = await makeClient({ profile });
        ctx.ui.setWidget("qdash", JSON.stringify({ profiles, active: safeConfig(client, profile ? `profile:${profile}` : shouldUseEnv({}) ? "env" : "profile:default") }, null, 2).split("\n"));
        ctx.ui.notify("QDash config shown in widget", "info");
      } catch (error) {
        ctx.ui.notify(`QDash config error: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    currentContext = loadGlobalContext();
    for (const entry of ctx.sessionManager.getEntries() as Array<{ type?: string; customType?: string; data?: unknown }>) {
      if (entry.type === "custom" && entry.customType === CONTEXT_ENTRY_TYPE && isQDashContextState(entry.data)) {
        currentContext = { ...entry.data };
      }
    }
    try {
      if (await ensureActiveChip()) persistContext();
    } catch {
      // Leave chip as auto when no QDash connection/profile is available at startup.
    }
    refreshContextUi(ctx);
  });
}
