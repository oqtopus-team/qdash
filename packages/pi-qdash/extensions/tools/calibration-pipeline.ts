import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashConnection } from "../lib/qdash-connection.js";
import { Type } from "typebox";

import { pausedSessionConflict } from "../lib/agent-loop.js";
import {
  planBindingProblem,
  resolvePipelinePlanPreview,
  runPipelineArgumentProblem,
  type PipelinePlanApprovalPreview,
} from "../lib/pipeline-plan-preview.js";
import { toTextToolResult } from "../lib/results.js";
import { requireWriteApproval } from "../lib/write-approval.js";
import { isResultUnknown, resultUnknownToolError, sdkSession, unknownLaunchGuidance, type SdkSessionFactory } from "../lib/sdk-session.js";
import { CONFIG_PATH_DESCRIPTION, PROFILE_DESCRIPTION } from "../lib/connection.js";
import { errorText, statusCodeOrStatus } from "../lib/errors.js";

/**
 * Declarative calibration pipelines.
 *
 * The agent writes a CalibrationPipelineSpec (targets, ordered steps, run
 * parameters); QDash validates it against the chip, backend, and task catalog,
 * then records an execution for each step reached. The spec cannot reference code, only the
 * Step classes and task names QDash exposes, so QDash owns the validation and
 * these tools only relay it. The spec schema is deliberately not restated
 * here: `qdash_get_pipeline_catalog` returns QDash's own JSON schema.
 *
 * The routes are reached through the SDK's `qdash.pipelines`, which owns the
 * request shape; the project is the profile's, or the server's default when
 * none is set. Confirmation, the structured result and the 422/503 handling
 * stay here. A run returns its execution ID at once; following it is
 * qdash_wait_execution's job.
 */

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

/** The qubits a spec names, or undefined when it targets MUXes or names none. */
export function specQids(spec: Record<string, unknown>): string[] | undefined {
  const targets = spec.targets as { qids?: unknown; mux_ids?: unknown } | undefined;
  if (!targets || targets.mux_ids != null) return undefined;
  const qids = targets.qids;
  return Array.isArray(qids) && qids.length > 0 && qids.every((qid) => typeof qid === "string") ? (qids as string[]) : undefined;
}

export type PipelineProblem = { path: string; message: string };

/** One call as QDash will run it: identity, failure policy, effective settings. */
export type ResolvedTaskCall = {
  call_id: string;
  name: string;
  on_failure: string;
  settings: Record<string, unknown>;
};

export type ResolvedPipelineStep = {
  index: number;
  type: string;
  name: string;
  step_id?: string | null;
  kind: string;
  /** Task names in call order, with repeats. */
  tasks: string[];
  calls?: ResolvedTaskCall[];
  reference?: { step?: string | null; call_id?: string | null } | null;
};

export type PipelineValidation = {
  valid: boolean;
  problems?: PipelineProblem[];
  warnings?: PipelineProblem[];
  backend_name: string;
  spec_version?: number | null;
  spec?: Record<string, unknown> | null;
  migrated_spec?: Record<string, unknown> | null;
  plan_digest?: string | null;
  targets?: { qids?: string[]; mux_ids?: number[]; exclude_qids?: string[] } | null;
  steps?: ResolvedPipelineStep[];
  task_run_count?: number;
};

export type PipelineExecution = {
  execution_id: string;
  flow_run_id: string;
  flow_run_url: string;
  qdash_ui_url: string;
  message: string;
  steps?: ResolvedPipelineStep[];
  targets?: PipelineValidation["targets"];
  /** Set when the run was recorded in a calibration session. */
  calibration_session_id?: string | null;
  pipeline_run_id?: string | null;
  /** A retry of the same call returned the run the first attempt started. */
  replayed?: boolean;
};

/**
 * The idempotency key of a pipeline run: one per tool call, so a replayed or retried call
 * returns the run it started instead of starting another, whether it is recorded in a named
 * calibration session or in the automatic one QDash creates. The call id comes from the host, never from the model's arguments.
 */
export function pipelineRunKey(toolCallId: string): string {
  const key = `qdash_run_pipeline:${toolCallId}`;
  return key.length <= 128 ? key : `qdash_run_pipeline:${toolCallId.slice(-100)}`;
}

/**
 * The idempotency key of a plan creation: one per tool call, so a replayed call (for example
 * a nested call a durable script repeats) returns the plan it stored instead of storing
 * another. The call id comes from the host, never from the model's arguments.
 */
export function pipelinePlanKey(toolCallId: string): string {
  const key = `qdash_create_pipeline_plan:${toolCallId}`;
  return key.length <= 128 ? key : `qdash_create_pipeline_plan:${toolCallId.slice(-90)}`;
}

/** A stored plan as `POST /calibration-pipelines/plans` returns it. */
export type PipelinePlan = {
  plan_id: string;
  chip_id: string;
  backend_name: string;
  expires_at: string;
  expired?: boolean;
  review_digest: string;
  spec?: Record<string, unknown>;
  targets?: PipelineValidation["targets"];
  target_qids?: string[];
  steps?: ResolvedPipelineStep[];
  warnings?: PipelineProblem[];
  task_run_count?: number;
  replayed?: boolean;
};

/** Text shown for a stored plan: its ID, digest, expiry, starting qubits, and resolved steps. */
export function formatPipelinePlanCreated(plan: PipelinePlan): string {
  const name = typeof plan.spec?.name === "string" ? ` '${plan.spec.name}'` : "";
  const warnings = problemLines(plan.warnings);
  return [
    `${plan.replayed ? "Already stored" : "Stored"} pipeline plan ${plan.plan_id}${name} on chip ${plan.chip_id} (backend ${plan.backend_name}).`,
    `Review digest ${plan.review_digest}; expires ${plan.expires_at}. It runs nothing and approves nothing.`,
    `Starting qubits: ${(plan.target_qids ?? []).join(", ") || "none"}. ${plan.task_run_count ?? 0} task calls per target.`,
    ...(warnings.length ? ["", "Warnings (the plan is still valid):", ...warnings] : []),
    "",
    "Steps:",
    ...stepLines(plan.steps),
    "",
    `To run it, call qdash_run_pipeline({ chipId: "${plan.chip_id}", planId: "${plan.plan_id}" }) directly (not from a script); the user approves the plan QDash shows them.`,
  ].join("\n");
}

/** What `qdash_run_pipeline` reports as its origin; QDash stores it as client reported. */
export const PIPELINE_TOOL_ORIGIN = { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" } as const;

export type TaskDocumentation = {
  description: string;
  when_to_use?: string;
  /** Explanatory only: QDash enforces inputs from task metadata, not from this list. */
  prerequisites?: string[];
};

export type PipelineCatalog = {
  backend_name: string;
  step_types: Array<{
    type: string;
    kind: string;
    description: string;
    requires: string[];
    provides: string[];
    task_scope?: string | null;
    default_step_id?: string | null;
    default_tasks: Array<{ name: string; call_id?: string | null }>;
    step_metrics?: string[];
  }>;
  one_qubit_execution_modes: string[];
  two_qubit_execution_modes?: string[];
  tasks: Record<string, string[]>;
  /** Guidance declared by task classes, keyed by task name; undocumented tasks are absent. */
  task_documentation?: Record<string, TaskDocumentation>;
  spec_version?: number;
  spec_schema: Record<string, unknown>;
  example?: Record<string, unknown>;
};

/** The client these tools use; tests pass a stub with the same `api` methods and `config`. */
export type PipelineClient = QDashConnection;

export type CalibrationPipelineDependencies = {
  makeClient(params: ConnectionParams): Promise<PipelineClient>;
  /** The chip to run on: the explicit id, else the session/default chip. */
  resolveChipId(client: PipelineClient, chipId?: string): Promise<string>;
  /** The SDK session for a resolved client; defaults to one with the client's settings. */
  sdk?: SdkSessionFactory;
};

const TASK_PREVIEW = 8;

function describeTargets(targets: PipelineValidation["targets"]): string {
  if (!targets) return "targets unknown";
  if (targets.qids?.length) return `qubits ${targets.qids.join(", ")}`;
  if (targets.mux_ids?.length) {
    const base = `MUX ${targets.mux_ids.join(", ")}`;
    return targets.exclude_qids?.length ? `${base} (excluding ${targets.exclude_qids.join(", ")})` : base;
  }
  return "targets unknown";
}

/** A call's label: the task name, plus its call_id when the two differ. */
function callLabel(call: { name: string; call_id: string }): string {
  return call.call_id === call.name ? call.name : `${call.call_id}=${call.name}`;
}

function callList(step: ResolvedPipelineStep): string {
  const labels = step.calls?.length ? step.calls.map(callLabel) : step.tasks;
  if (labels.length === 0) {
    if (!step.reference?.step) return "no tasks (transform)";
    const source = step.reference.call_id ? `${step.reference.step}.${step.reference.call_id}` : step.reference.step;
    return `reads ${source}`;
  }
  const shown = labels.slice(0, TASK_PREVIEW).join(", ");
  const rest = labels.length - TASK_PREVIEW;
  const noun = labels.length === 1 ? "call" : "calls";
  return rest > 0 ? `${labels.length} calls: ${shown}, +${rest} more` : `${labels.length} ${noun}: ${shown}`;
}

export function stepLines(steps: ResolvedPipelineStep[] | undefined): string[] {
  if (!steps?.length) return ["- (no steps resolved)"];
  return steps.map((step) => {
    const id = step.step_id && step.step_id !== step.name ? ` [${step.step_id}]` : "";
    const label = step.name === step.type ? step.type : `${step.name} (${step.type})`;
    return `${step.index}. ${label}${id} — ${callList(step)}`;
  });
}

export function problemLines(problems: PipelineProblem[] | undefined): string[] {
  if (!problems?.length) return [];
  return problems.map((problem) => `- ${problem.path}: ${problem.message}`);
}

/** Text shown for a validated (or rejected) plan. */
export function formatPipelinePlan(result: PipelineValidation, chipId: string): string {
  const name = typeof result.spec?.name === "string" ? result.spec.name : undefined;
  const header = `Pipeline${name ? ` '${name}'` : ""} on chip ${chipId} (backend ${result.backend_name})`;
  const problems = problemLines(result.problems);
  const lines = [header, `Targets: ${describeTargets(result.targets)}`, ""];
  if (result.valid) {
    lines.push(`Valid. ${result.task_run_count ?? 0} task calls per target.`);
  } else {
    lines.push(`Not valid: ${problems.length} problem${problems.length === 1 ? "" : "s"}. Fix the spec and validate again.`, ...problems);
  }
  if (result.migrated_spec) {
    lines.push(
      "",
      `This is a version ${result.spec_version ?? 1} spec. details.data.migrated_spec holds the same pipeline as spec_version 2; review it (rename generated call_ids if useful) and plan it instead.`,
    );
  }
  const warnings = problemLines(result.warnings);
  if (warnings.length) lines.push("", "Warnings (the spec is still valid):", ...warnings);
  if (result.steps?.length) lines.push("", "Steps:", ...stepLines(result.steps));
  return lines.join("\n");
}

export function formatPipelineExecution(result: PipelineExecution, chipId: string): string {
  const stepCount = result.steps?.length ?? 0;
  const taskRuns = (result.steps ?? []).reduce((count, step) => count + (step.calls?.length ?? step.tasks.length), 0);
  const recorded = result.calibration_session_id
    ? [`Recorded in calibration session ${result.calibration_session_id} as pipeline run ${result.pipeline_run_id ?? "(unknown)"}${result.replayed ? " (this call had already started it; nothing new was started)" : ""}.`]
    : [];
  return [
    `${result.replayed ? "Already started" : "Started"}: ${result.message}`,
    `execution_id ${result.execution_id}`,
    `chip ${chipId}, ${describeTargets(result.targets)}, ${stepCount} step${stepCount === 1 ? "" : "s"}, ${taskRuns} task calls per target`,
    ...recorded,
    `qdash ${result.qdash_ui_url}`,
    `prefect ${result.flow_run_url}`,
    "",
    "Use qdash_wait_execution with this execution_id to follow it to completion.",
  ].join("\n");
}

/** The detail string of an HTTP error, if it carries one. */
function errorDetail(error: unknown): string | undefined {
  if (!error || typeof error !== "object") return undefined;
  const payload = (error as { payload?: unknown }).payload;
  const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : undefined;
  return typeof detail === "string" ? detail : undefined;
}

/** The first sentence of a task description, which keeps the unexpanded listing short. */
export function firstSentence(text: string): string {
  const match = /^.*?[.!?](?=\s+[A-Z(]|$)/s.exec(text.trim());
  return match ? match[0] : text.trim();
}

/**
 * Declared task guidance: the first sentence of each documented task's description,
 * plus the full description, when-to-use, and prerequisites for the tasks named
 * in `expand`.
 */
function formatTaskDocumentation(documentation: Record<string, TaskDocumentation>, expand: string[]): string[] {
  const names = Object.keys(documentation).sort();
  const expanded = new Set(expand);
  const lines: string[] = [];
  if (names.length) {
    lines.push("", `Task documentation (${names.length} documented; pass taskNames for the full description, when to use, and prerequisites):`);
    for (const name of names) {
      const doc = documentation[name];
      if (!expanded.has(name)) {
        lines.push(`- ${name}: ${firstSentence(doc.description)}`);
        continue;
      }
      lines.push(`- ${name}: ${doc.description}`);
      if (doc.when_to_use) lines.push(`  When to use: ${doc.when_to_use}`);
      if (doc.prerequisites?.length) {
        lines.push("  Prerequisites (explanatory; validation reports what is actually missing):");
        for (const item of doc.prerequisites) lines.push(`  - ${item}`);
      }
    }
  }
  const undocumented = [...expanded].filter((name) => !(name in documentation));
  if (undocumented.length) {
    lines.push("", `No declared documentation for: ${undocumented.join(", ")}`);
  }
  return lines;
}

/** The declared parameters of one task, as `GET /tasks` lists them. */
export type TaskParameters = {
  name: string;
  input_parameters?: Record<string, { unit?: string }>;
  output_parameters?: Record<string, { unit?: string }>;
};

function parameterList(parameters: Record<string, { unit?: string }> | undefined): string {
  const names = Object.keys(parameters ?? {}).sort();
  return names.length ? names.map((name) => (parameters?.[name]?.unit ? `${name} (${parameters[name].unit})` : name)).join(", ") : "none";
}

/**
 * The declared inputs and outputs of the requested tasks, with their units, or
 * why they could not be listed. Output names are what a session's
 * allowed_overrides must name for a result to become a committable candidate.
 */
export function formatTaskParameters(tasks: readonly TaskParameters[] | string, names: readonly string[]): string[] {
  if (!names.length) return [];
  if (typeof tasks === "string") return ["", `Declared task parameters unavailable: ${tasks}`];
  const lines = ["", "Declared task parameters (names and units as QDash stores them):"];
  for (const name of names) {
    const task = tasks.find((item) => item.name === name);
    if (!task) {
      lines.push(`- ${name}: not in this backend's task list`);
      continue;
    }
    lines.push(`- ${name}`, `  Inputs: ${parameterList(task.input_parameters)}`, `  Outputs: ${parameterList(task.output_parameters)}`);
  }
  return lines;
}

export function formatPipelineCatalog(catalog: PipelineCatalog, expandTasks: string[] = []): string {
  const lines = [`Calibration pipeline catalog (backend ${catalog.backend_name})`, "", "Step types:"];
  for (const step of catalog.step_types) {
    const needs = step.requires.length ? ` needs ${step.requires.join(" or ")};` : "";
    const scope = step.task_scope ? ` ${step.task_scope} tasks` : "";
    const defaults = step.default_tasks.length ? `; default ${step.default_tasks.length} calls` : "";
    lines.push(`- ${step.type} [${step.kind}${scope}]: ${step.description}${needs}${defaults}`);
  }
  lines.push("", `One-qubit execution_mode values: ${catalog.one_qubit_execution_modes.join(", ")}`);
  if (catalog.two_qubit_execution_modes?.length) {
    lines.push(`Two-qubit execution_mode values: ${catalog.two_qubit_execution_modes.join(", ")}`);
  }
  if ([...catalog.one_qubit_execution_modes, ...(catalog.two_qubit_execution_modes ?? [])].includes("manual")) {
    lines.push(
      'execution_mode "manual" requires rounds and runs them exactly as written: [["0", "8"], ["1", "9"]] for qubits, [[["0", "1"], ["4", "5"]], [["8", "9"]]] for directed pairs. Validate the spec to check rounds against the chip.',
    );
  }
  lines.push("", "Tasks by type:");
  for (const [taskType, names] of Object.entries(catalog.tasks)) {
    lines.push(`- ${taskType} (${names.length}): ${names.join(", ")}`);
  }
  lines.push(...formatTaskDocumentation(catalog.task_documentation ?? {}, expandTasks));
  lines.push(
    "",
    `Specs need spec_version: ${catalog.spec_version ?? 2}. Targets are either {qids: [...]} or {mux_ids: [...], exclude_qids?: [...]}.`,
    'A step\'s tasks are calls: {"name": "CheckRamsey", "call_id"?, "run"?, "input"?, "update_calibration_parameters"?, "on_failure"?}. A task may run more than once in one step when every occurrence has its own call_id.',
    "Filters read the latest OneQubitCheck/OneQubitFineTune unless they set step (a step_id) and optionally call_id.",
    "The full spec JSON schema is in details.data.spec_schema; validate with qdash_plan_pipeline.",
  );
  return lines.join("\n");
}

/** Problems carried by a 422 from /calibration-pipelines/execute, if that is what `error` is. */
export function problemsFromError(error: unknown): PipelineProblem[] | null {
  if (!error || typeof error !== "object") return null;
  const payload = (error as { payload?: unknown }).payload;
  const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : undefined;
  const problems = detail && typeof detail === "object" ? (detail as { problems?: unknown }).problems : undefined;
  if (!Array.isArray(problems)) return null;
  return problems
    .filter((item): item is PipelineProblem => Boolean(item) && typeof item === "object" && typeof (item as PipelineProblem).path === "string")
    .map((item) => ({ path: item.path, message: String(item.message ?? "") }));
}

const connectionParams = {
  profile: Type.Optional(Type.String({ description: PROFILE_DESCRIPTION })),
  configPath: Type.Optional(Type.String({ description: CONFIG_PATH_DESCRIPTION })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

// Loose on purpose: QDash validates the spec and reports problems with paths,
// and a union-heavy schema here would be ignored by vLLM guided decoding anyway.
const specParam = Type.Object({}, {
  additionalProperties: true,
  description: "CalibrationPipelineSpec: {spec_version: 2, name?, targets: {qids} | {mux_ids, exclude_qids?}, steps: [{type, step_id?, tasks?: [{name, call_id?, run?, input?, update_calibration_parameters?, on_failure?}], ...}], default_run_parameters?, tags?}. Put per-call settings on each task call; task_parameters (per-task defaults) is deprecated and only kept so existing specs still run. Get step types and tasks from qdash_get_pipeline_catalog.",
});

export function registerCalibrationPipelineTools(pi: Pick<ExtensionAPI, "registerTool">, deps: CalibrationPipelineDependencies): void {
  pi.registerTool({
    name: "qdash_get_pipeline_catalog",
    label: "QDash Pipeline Catalog",
    description: "List the step types, task names, declared task documentation, and spec schema for composing a calibration pipeline. Read-only. Call this before writing a pipeline spec, or with taskNames to read what a task does, when to use it, its prerequisites, and its declared input and output parameters with units.",
    promptSnippet: "Look up the step types, tasks, and task documentation available for a QDash calibration pipeline",
    promptGuidelines: [
      "Use qdash_get_pipeline_catalog before composing a pipeline spec; use only the step types and task names it lists.",
      "Pass taskNames to qdash_get_pipeline_catalog to read a task's purpose, when to use it, and prerequisites before choosing it; documented prerequisites explain, while qdash_plan_pipeline reports what is actually missing.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      backendName: Type.Optional(Type.String({ description: "Backend to list tasks for. Defaults to the configured backend." })),
      taskNames: Type.Optional(Type.Array(Type.String(), { description: "Task names whose full documentation (when to use, prerequisites) to include." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { backendName?: string; taskNames?: string[] }) {
      const client = await deps.makeClient(params);
      const qdash = (deps.sdk ?? sdkSession)(client);
      const catalog = (await qdash.pipelines.catalog({ backendName: params.backendName })) as PipelineCatalog;
      const taskNames = params.taskNames ?? [];
      let declared: TaskParameters[] | string = [];
      if (taskNames.length) {
        try {
          declared = ((await client.listTasks(catalog.backend_name)) as { tasks?: TaskParameters[] }).tasks ?? [];
        } catch (error) {
          declared = errorText(error);
        }
      }
      const text = [formatPipelineCatalog(catalog, taskNames), ...formatTaskParameters(declared, taskNames)].join("\n");
      return toTextToolResult(text, catalog, { tool: "qdash_get_pipeline_catalog", backendName: catalog.backend_name });
    },
  });

  pi.registerTool({
    name: "qdash_plan_pipeline",
    label: "QDash Plan Pipeline",
    description: "Check a calibration pipeline spec against QDash without running it: returns problems with paths into the spec and the exact tasks each step will run. Read-only. Call this before qdash_run_pipeline.",
    promptSnippet: "Validate a QDash calibration pipeline spec and preview the tasks it will run",
    promptGuidelines: [
      "Use qdash_plan_pipeline after composing a spec and after every edit; a spec with problems is not an error, fix it and plan again.",
      "When the plan returns migrated_spec, the spec was version 1; plan the migrated spec instead of editing the old shape.",
      "Show the user the resolved steps, their call ids and settings, and any warnings before running.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Chip to run on. Defaults to the session or default chip." })),
      spec: specParam,
      backendName: Type.Optional(Type.String({ description: "Defaults to the configured backend." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { chipId?: string; spec: Record<string, unknown>; backendName?: string }) {
      const client = await deps.makeClient(params);
      const chipId = await deps.resolveChipId(client, params.chipId);
      const result = (await (deps.sdk ?? sdkSession)(client).pipelines.validate(params.spec, {
        chipId,
        backendName: params.backendName,
      })) as PipelineValidation;
      return toTextToolResult(formatPipelinePlan(result, chipId), result, {
        tool: "qdash_plan_pipeline",
        chipId,
        valid: result.valid,
        problemCount: result.problems?.length ?? 0,
      });
    },
  });

  pi.registerTool({
    name: "qdash_create_pipeline_plan",
    label: "QDash Create Pipeline Plan",
    description: "Validate a calibration pipeline spec and store it in QDash as a plan: an immutable proposal with its resolved calls, the qubits its targets resolve to, and a review digest, which expires after 24 hours. It writes only that record: it runs nothing, reserves no hardware, joins no calibration session, and approves nothing. Returns the plan with its plan_id; pass that planId to qdash_run_pipeline instead of the spec. Code mode scripts may call it.",
    promptSnippet: "Store a validated QDash calibration pipeline spec as a plan to run by reference",
    promptGuidelines: [
      "Use qdash_create_pipeline_plan after building a spec in a codemode script (with qdash.calibration) and checking it with qdash_plan_pipeline; return the plan's plan_id from the script and call qdash_run_pipeline with planId directly, so the spec is never copied by hand.",
      "qdash_create_pipeline_plan only stores a proposal; it is not an approval. Running the plan is still a qdash_run_pipeline call the user approves after the host shows them the stored plan.",
      "A plan expires after 24 hours and is never renewed; after that build the spec again and store a new plan.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.Optional(Type.String({ description: "Chip to run on. Defaults to the session or default chip." })),
      spec: specParam,
      backendName: Type.Optional(Type.String({ description: "Defaults to the configured backend." })),
    }),
    async execute(toolCallId, params: ConnectionParams & { chipId?: string; spec: Record<string, unknown>; backendName?: string }) {
      const client = await deps.makeClient(params);
      const chipId = await deps.resolveChipId(client, params.chipId);
      let plan: PipelinePlan;
      try {
        plan = (await (deps.sdk ?? sdkSession)(client).pipelines.createPlan(
          params.spec,
          { chipId, backendName: params.backendName },
          { idempotencyKey: pipelinePlanKey(toolCallId) },
        )) as PipelinePlan;
      } catch (error) {
        const problems = problemsFromError(error);
        if (!problems) throw error;
        const text = [
          `QDash did not store the plan: the spec has ${problems.length} problem${problems.length === 1 ? "" : "s"}. Nothing was stored or started.`,
          ...problemLines(problems),
        ].join("\n");
        return toTextToolResult(text, { valid: false, problems }, { tool: "qdash_create_pipeline_plan", chipId, stored: false, problemCount: problems.length });
      }
      return toTextToolResult(formatPipelinePlanCreated(plan), plan, {
        tool: "qdash_create_pipeline_plan",
        chipId: plan.chip_id,
        planId: plan.plan_id,
        stored: true,
        ...(plan.replayed ? { replayed: true } : {}),
      });
    },
  });

  pi.registerTool({
    name: "qdash_run_pipeline",
    label: "QDash Run Pipeline",
    description: "Run a calibration pipeline as one QDash execution, from exactly one of a spec or the planId of a plan stored with qdash_create_pipeline_plan. Completed tasks write their calibrated parameters to QDash directly, without an agent candidate gate. Confirmation-gated write operation: with planId, the user approves the stored plan the host fetches from QDash, and it runs only with that plan's review digest. Validate a spec with qdash_plan_pipeline first; it runs exactly as validated.",
    promptSnippet: "Run a validated QDash calibration pipeline spec or stored plan",
    promptGuidelines: [
      "Use qdash_run_pipeline only for a spec that qdash_plan_pipeline reported valid, or for the planId qdash_create_pipeline_plan returned; pass exactly one of spec and planId.",
      "When a codemode script built the spec, store it with qdash_create_pipeline_plan in the script and pass only its planId here; do not copy the spec into this call.",
      "When the run serves a calibration objective, pass that objective's calibrationSessionId (from qdash_create_calibration_session or the user) so QDash records the run, with all its step executions, in it. Without it the run joins an automatic session of its own. It grants nothing: the user still approves this exact run.",
      "When the run carries out an experiment you recorded with qdash_record_calibration_decision, pass that decision's decisionId too, so the session's audit links your intent to this run. Record the decision first; never pass a decision of another session.",
      "If QDash reports that a run's launch outcome is unknown, do not start it again: check the reported execution ID with qdash_get_execution, or without one page through qdash_list_executions for the run's chipId, and tell the user.",
      "Tell the user before running that completed tasks update calibrated parameters in QDash directly.",
      "Do not use qdash_run_pipeline to run a task an agent session action failed to run; that skips the session's candidate gate. Report the failure instead.",
      "After it starts, follow the execution with qdash_wait_execution and summarize failed targets.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.String({ description: "Chip to run on; with planId, the plan's chip." }),
      spec: Type.Optional(specParam),
      planId: Type.Optional(Type.String({ description: "A plan stored with qdash_create_pipeline_plan, instead of spec. The user approves the stored plan QDash returns." })),
      backendName: Type.Optional(Type.String({ description: "Defaults to the configured backend (with planId: the plan's)." })),
      calibrationSessionId: Type.Optional(Type.String({ description: "Record the run in this calibration session (open, on this chip, created by the user). Grants nothing." })),
      decisionId: Type.Optional(Type.String({ description: "With calibrationSessionId: the decision of that session (qdash_record_calibration_decision with an experiment) this run carries out." })),
    }),
    async execute(toolCallId, params: ConnectionParams & { chipId: string; spec?: Record<string, unknown>; planId?: string; backendName?: string; calibrationSessionId?: string; decisionId?: string }, _signal, _onUpdate, ctx) {
      const argumentProblem = runPipelineArgumentProblem(params);
      if (argumentProblem) throw new Error(argumentProblem);
      if (params.decisionId && !params.calibrationSessionId) {
        throw new Error("decisionId needs calibrationSessionId: a decision belongs to one calibration session.");
      }
      const recordedIn = params.calibrationSessionId
        ? ` It is recorded in calibration session ${params.calibrationSessionId}${params.decisionId ? ` as carrying out decision ${params.decisionId}` : ""}, which groups it and grants nothing.`
        : "";
      const dialog = { title: "Run QDash calibration pipeline?", message: `This starts a calibration execution on chip ${params.chipId}. Completed tasks update calibrated parameters in QDash directly.${recordedIn}` };
      if (params.planId !== undefined) {
        return runStoredPlan(deps, toolCallId, { ...params, planId: params.planId }, ctx, dialog);
      }
      const spec = params.spec as Record<string, unknown>;
      await requireWriteApproval("qdash_run_pipeline", toolCallId, params, ctx, dialog);
      const client = await deps.makeClient(params);
      // A paused agent session's targets must not be measured around its pause.
      const conflict = await pausedSessionConflict(client, params.chipId, specQids(spec));
      if (conflict) {
        return toTextToolResult(conflict, { blocked: true }, { tool: "qdash_run_pipeline", chipId: params.chipId, started: false, blockedByPausedSession: true });
      }
      const qdash = (deps.sdk ?? sdkSession)(client);
      try {
        // Dispatch only: the run handle's wait() is deliberately not called here.
        // Every run is recorded before it starts, in the named calibration session if any.
        // The key ties this tool call to that one run.
        const recording = {
          idempotencyKey: pipelineRunKey(toolCallId),
          ...(params.calibrationSessionId ? { calibrationSessionId: params.calibrationSessionId } : {}),
          ...(params.decisionId ? { decisionId: params.decisionId } : {}),
        };
        // The origin is this tool's own constant, never the model's arguments: QDash shows it as
        // reported, so a run started here is told apart from one the user started directly.
        const run = await qdash.pipelines.execute(spec, { chipId: params.chipId, backendName: params.backendName }, recording, { reportedOrigin: PIPELINE_TOOL_ORIGIN });
        const result = run.response as PipelineExecution;
        return toTextToolResult(formatPipelineExecution(result, params.chipId), result, {
          tool: "qdash_run_pipeline",
          chipId: params.chipId,
          executionId: result.execution_id,
          started: true,
          ...(result.calibration_session_id ? { calibrationSessionId: result.calibration_session_id, pipelineRunId: result.pipeline_run_id ?? undefined } : {}),
          ...(params.decisionId ? { decisionId: params.decisionId } : {}),
          ...(result.replayed ? { replayed: true } : {}),
        });
      } catch (error) {
        // Answered, but without the recording asked for: the run may be going.
        if (isResultUnknown(error)) throw resultUnknownToolError(error, { chipId: params.chipId });
        const problems = problemsFromError(error);
        if (problems) {
          const text = [
            `QDash rejected the pipeline spec (${problems.length} problem${problems.length === 1 ? "" : "s"}). Nothing was started.`,
            ...problemLines(problems),
            "",
            "Fix the spec, confirm it with qdash_plan_pipeline, then run again.",
          ].join("\n");
          return toTextToolResult(text, { problems }, { tool: "qdash_run_pipeline", chipId: params.chipId, started: false, problemCount: problems.length });
        }
        if (statusCodeOrStatus(error) === 503) {
          throw new Error("QDash cannot run pipelines right now: the worker has not registered the calibration-pipeline deployment. Ask an operator to restart the worker, then try again.");
        }
        const detail = errorDetail(error);
        if (detail && /unknown|may have started|being dispatched/i.test(detail)) {
          // Never retried with a new call: the first launch may be running.
          throw new Error(`${detail} ${unknownLaunchGuidance(undefined, { chipId: params.chipId })}`);
        }
        throw error;
      }
    },
  });
}

type RunPlanParams = ConnectionParams & { chipId: string; planId: string; backendName?: string; calibrationSessionId?: string; decisionId?: string };

/**
 * `qdash_run_pipeline` with `planId`: approve the plan the host fetched, then run it with the
 * review digest of that preview. The model's arguments name the plan only; the digest, the
 * starting qubits for the paused-session check, and what the user saw come from the preview.
 */
async function runStoredPlan(
  deps: CalibrationPipelineDependencies,
  toolCallId: string,
  params: RunPlanParams,
  ctx: Parameters<typeof requireWriteApproval>[3],
  dialog: { title: string; message: string },
) {
  const client = await deps.makeClient(params);
  const qdash = (deps.sdk ?? sdkSession)(client);
  const preview = (await requireWriteApproval("qdash_run_pipeline", toolCallId, params, ctx, {
    ...dialog,
    preview: () => resolvePipelinePlanPreview(qdash.pipelines, params),
  })) as PipelinePlanApprovalPreview | undefined;
  const binding = planBindingProblem(preview, params);
  if (binding || !preview) throw new Error(binding ?? "qdash_run_pipeline was not run: no approved plan.");
  // A paused agent session's qubits must not be measured around its pause: the plan's own
  // starting qubits, MUXes expanded, are what the check compares.
  const conflict = await pausedSessionConflict(client, params.chipId, preview.targetQids.length ? preview.targetQids : undefined);
  if (conflict) {
    return toTextToolResult(conflict, { blocked: true }, { tool: "qdash_run_pipeline", chipId: params.chipId, planId: params.planId, started: false, blockedByPausedSession: true });
  }
  try {
    const recording = {
      idempotencyKey: pipelineRunKey(toolCallId),
      ...(params.calibrationSessionId ? { calibrationSessionId: params.calibrationSessionId } : {}),
      ...(params.decisionId ? { decisionId: params.decisionId } : {}),
    };
    const run = await qdash.pipelines.executePlan(
      params.planId,
      {
        chipId: params.chipId,
        expectedReviewDigest: preview.reviewDigest,
        ...(params.backendName ? { backendName: params.backendName } : {}),
      },
      recording,
      { reportedOrigin: PIPELINE_TOOL_ORIGIN },
    );
    const result = run.response as PipelineExecution;
    return toTextToolResult(
      [`Plan ${params.planId} (review digest ${preview.reviewDigest}).`, formatPipelineExecution(result, params.chipId)].join("\n"),
      result,
      {
        tool: "qdash_run_pipeline",
        chipId: params.chipId,
        planId: params.planId,
        reviewDigest: preview.reviewDigest,
        executionId: result.execution_id,
        started: true,
        ...(result.calibration_session_id ? { calibrationSessionId: result.calibration_session_id, pipelineRunId: result.pipeline_run_id ?? undefined } : {}),
        ...(params.decisionId ? { decisionId: params.decisionId } : {}),
        ...(result.replayed ? { replayed: true } : {}),
      },
    );
  } catch (error) {
    if (isResultUnknown(error)) throw resultUnknownToolError(error, { chipId: params.chipId });
    const problems = problemsFromError(error);
    if (problems) {
      const text = [
        `QDash no longer accepts plan ${params.planId} (${problems.length} problem${problems.length === 1 ? "" : "s"}). Nothing was started.`,
        ...problemLines(problems),
        "",
        "Fix the spec, store a new plan with qdash_create_pipeline_plan, and run that plan.",
      ].join("\n");
      return toTextToolResult(text, { problems }, { tool: "qdash_run_pipeline", chipId: params.chipId, planId: params.planId, started: false, problemCount: problems.length });
    }
    if (statusCodeOrStatus(error) === 503) {
      throw new Error("QDash cannot run pipelines right now: the worker has not registered the calibration-pipeline deployment. Ask an operator to restart the worker, then try again.");
    }
    const detail = errorDetail(error);
    if (detail && /unknown|may have started|being dispatched/i.test(detail)) {
      throw new Error(`${detail} ${unknownLaunchGuidance(undefined, { chipId: params.chipId })}`);
    }
    if (detail) throw new Error(`QDash did not run plan ${params.planId}: ${detail}`);
    throw error;
  }
}
