import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import { Type } from "typebox";

import { toTextToolResult } from "../lib/results.js";

/**
 * Declarative calibration pipelines.
 *
 * The agent writes a CalibrationPipelineSpec (targets, ordered steps, run
 * parameters); QDash validates it against the chip, backend, and task catalog,
 * then runs it as one execution. The spec cannot reference code, only the
 * Step classes and task names QDash exposes, so QDash owns the validation and
 * these tools only relay it. The spec schema is deliberately not restated
 * here: `qdash_get_pipeline_catalog` returns QDash's own JSON schema.
 */

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

export type PipelineProblem = { path: string; message: string };

export type ResolvedPipelineStep = {
  index: number;
  type: string;
  name: string;
  kind: string;
  tasks: string[];
};

export type PipelineValidation = {
  valid: boolean;
  problems?: PipelineProblem[];
  backend_name: string;
  spec?: Record<string, unknown> | null;
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
    default_tasks: string[];
  }>;
  one_qubit_modes: string[];
  tasks: Record<string, string[]>;
  spec_schema: Record<string, unknown>;
  example?: Record<string, unknown>;
};

type PipelineRequest = { chip_id: string; spec: Record<string, unknown>; backend_name?: string };

/** The slice of QDashClient these tools use; tests pass a stub. */
export type PipelineClient = {
  api: {
    getCalibrationPipelineCatalog(params?: { backend_name?: string }): Promise<unknown>;
    validateCalibrationPipeline(request: PipelineRequest): Promise<unknown>;
    executeCalibrationPipeline(request: PipelineRequest): Promise<unknown>;
  };
};

export type CalibrationPipelineDependencies = {
  makeClient(params: ConnectionParams): Promise<PipelineClient>;
  /** The chip to run on: the explicit id, else the session/default chip. */
  resolveChipId(client: PipelineClient, chipId?: string): Promise<string>;
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

function taskList(tasks: string[]): string {
  if (tasks.length === 0) return "no tasks (transform)";
  const shown = tasks.slice(0, TASK_PREVIEW).join(", ");
  const rest = tasks.length - TASK_PREVIEW;
  return rest > 0 ? `${tasks.length} tasks: ${shown}, +${rest} more` : `${tasks.length} task${tasks.length === 1 ? "" : "s"}: ${shown}`;
}

export function stepLines(steps: ResolvedPipelineStep[] | undefined): string[] {
  if (!steps?.length) return ["- (no steps resolved)"];
  return steps.map((step) => {
    const label = step.name === step.type ? step.type : `${step.name} (${step.type})`;
    return `${step.index}. ${label} — ${taskList(step.tasks)}`;
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
    lines.push(`Valid. ${result.task_run_count ?? 0} task runs per target.`);
  } else {
    lines.push(`Not valid: ${problems.length} problem${problems.length === 1 ? "" : "s"}. Fix the spec and validate again.`, ...problems);
  }
  if (result.steps?.length) lines.push("", "Steps:", ...stepLines(result.steps));
  return lines.join("\n");
}

export function formatPipelineExecution(result: PipelineExecution, chipId: string): string {
  const stepCount = result.steps?.length ?? 0;
  const taskRuns = (result.steps ?? []).reduce((count, step) => count + step.tasks.length, 0);
  return [
    `Started: ${result.message}`,
    `execution_id ${result.execution_id}`,
    `chip ${chipId}, ${describeTargets(result.targets)}, ${stepCount} step${stepCount === 1 ? "" : "s"}, ${taskRuns} task runs per target`,
    `qdash ${result.qdash_ui_url}`,
    `prefect ${result.flow_run_url}`,
    "",
    "Use qdash_wait_execution with this execution_id to follow it to completion.",
  ].join("\n");
}

export function formatPipelineCatalog(catalog: PipelineCatalog): string {
  const lines = [`Calibration pipeline catalog (backend ${catalog.backend_name})`, "", "Step types:"];
  for (const step of catalog.step_types) {
    const needs = step.requires.length ? ` needs ${step.requires.join(" or ")};` : "";
    const scope = step.task_scope ? ` ${step.task_scope} tasks` : "";
    const defaults = step.default_tasks.length ? `; default ${step.default_tasks.length} tasks` : "";
    lines.push(`- ${step.type} [${step.kind}${scope}]: ${step.description}${needs}${defaults}`);
  }
  lines.push("", `One-qubit modes: ${catalog.one_qubit_modes.join(", ")}`, "", "Tasks by type:");
  for (const [taskType, names] of Object.entries(catalog.tasks)) {
    lines.push(`- ${taskType} (${names.length}): ${names.join(", ")}`);
  }
  lines.push(
    "",
    "Targets are either {qids: [...]} or {mux_ids: [...], exclude_qids?: [...]}.",
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

function statusOf(error: unknown): number | undefined {
  if (!error || typeof error !== "object") return undefined;
  const value = error as { statusCode?: unknown; status?: unknown };
  return typeof value.statusCode === "number" ? value.statusCode : typeof value.status === "number" ? value.status : undefined;
}

const connectionParams = {
  profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
  configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

// Loose on purpose: QDash validates the spec and reports problems with paths,
// and a union-heavy schema here would be ignored by vLLM guided decoding anyway.
const specParam = Type.Object({}, {
  additionalProperties: true,
  description: "CalibrationPipelineSpec: {name?, targets: {qids} | {mux_ids, exclude_qids?}, steps: [{type, ...}], task_run_parameters?, default_run_parameters?, tags?}. Get step types and tasks from qdash_get_pipeline_catalog.",
});

export function registerCalibrationPipelineTools(pi: Pick<ExtensionAPI, "registerTool">, deps: CalibrationPipelineDependencies): void {
  pi.registerTool({
    name: "qdash_get_pipeline_catalog",
    label: "QDash Pipeline Catalog",
    description: "List the step types, task names, and spec schema for composing a calibration pipeline. Read-only. Call this before writing a pipeline spec.",
    promptSnippet: "Look up the step types and tasks available for a QDash calibration pipeline",
    promptGuidelines: [
      "Use qdash_get_pipeline_catalog before composing a pipeline spec; use only the step types and task names it lists.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      backendName: Type.Optional(Type.String({ description: "Backend to list tasks for. Defaults to the configured backend." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { backendName?: string }) {
      const client = await deps.makeClient(params);
      const catalog = (await client.api.getCalibrationPipelineCatalog(
        params.backendName ? { backend_name: params.backendName } : undefined,
      )) as PipelineCatalog;
      return toTextToolResult(formatPipelineCatalog(catalog), catalog, { tool: "qdash_get_pipeline_catalog", backendName: catalog.backend_name });
    },
  });

  pi.registerTool({
    name: "qdash_plan_pipeline",
    label: "QDash Plan Pipeline",
    description: "Check a calibration pipeline spec against QDash without running it: returns problems with paths into the spec and the exact tasks each step will run. Read-only. Call this before qdash_run_pipeline.",
    promptSnippet: "Validate a QDash calibration pipeline spec and preview the tasks it will run",
    promptGuidelines: [
      "Use qdash_plan_pipeline after composing a spec and after every edit; a spec with problems is not an error, fix it and plan again.",
      "Show the user the resolved steps and task counts before running.",
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
      const result = (await client.api.validateCalibrationPipeline({
        chip_id: chipId,
        spec: params.spec,
        ...(params.backendName ? { backend_name: params.backendName } : {}),
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
    name: "qdash_run_pipeline",
    label: "QDash Run Pipeline",
    description: "Run a calibration pipeline spec as one QDash execution. Completed tasks write their calibrated parameters to QDash directly, without an agent candidate gate. Confirmation-gated write operation. Validate with qdash_plan_pipeline first; the spec runs exactly as validated.",
    promptSnippet: "Run a validated QDash calibration pipeline spec",
    promptGuidelines: [
      "Use qdash_run_pipeline only for a spec that qdash_plan_pipeline reported valid.",
      "Tell the user before running that completed tasks update calibrated parameters in QDash directly.",
      "Do not use qdash_run_pipeline to run a task an agent session action failed to run; that skips the session's candidate gate. Report the failure instead.",
      "After it starts, follow the execution with qdash_wait_execution and summarize failed targets.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      chipId: Type.String({ description: "Chip to run on." }),
      spec: specParam,
      backendName: Type.Optional(Type.String({ description: "Defaults to the configured backend." })),
      confirmWrite: Type.Optional(Type.Boolean({ description: "Required for non-interactive execution. Set true only after explicit user confirmation." })),
    }),
    async execute(_toolCallId, params: ConnectionParams & { chipId: string; spec: Record<string, unknown>; backendName?: string; confirmWrite?: boolean }, _signal, _onUpdate, ctx) {
      if (!params.confirmWrite) {
        if (!ctx.hasUI || !(await ctx.ui.confirm("Run QDash calibration pipeline?", `This starts a calibration execution on chip ${params.chipId}. Completed tasks update calibrated parameters in QDash directly.`))) {
          throw new Error("qdash_run_pipeline requires explicit confirmation");
        }
      }
      const client = await deps.makeClient(params);
      try {
        const result = (await client.api.executeCalibrationPipeline({
          chip_id: params.chipId,
          spec: params.spec,
          ...(params.backendName ? { backend_name: params.backendName } : {}),
        })) as PipelineExecution;
        return toTextToolResult(formatPipelineExecution(result, params.chipId), result, {
          tool: "qdash_run_pipeline",
          chipId: params.chipId,
          executionId: result.execution_id,
          started: true,
        });
      } catch (error) {
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
        if (statusOf(error) === 503) {
          throw new Error("QDash cannot run pipelines right now: the worker has not registered the calibration-pipeline deployment. Ask an operator to restart the worker, then try again.");
        }
        throw error;
      }
    },
  });
}
