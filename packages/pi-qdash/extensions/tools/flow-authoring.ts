import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashConnection } from "../lib/qdash-connection.js";
import { Type } from "typebox";

import { pausedSessionConflict } from "../lib/agent-loop.js";
import { toTextToolResult } from "../lib/results.js";
import { requireWriteApproval } from "../lib/write-approval.js";
import { isResultUnknown, resultUnknownToolError, sdkSession, type SdkSessionFactory } from "../lib/sdk-session.js";
import { CONFIG_PATH_DESCRIPTION, PROFILE_DESCRIPTION } from "../lib/connection.js";

/**
 * Flow authoring: saving a calibration flow the agent wrote.
 *
 * A flow is Python that runs on the QDash workflow worker with hardware and
 * database access, so saving one is a confirmation-gated write, and running one
 * (`qdash_execute_flow`) is another. A flow is decorated with
 * `@calibration_flow(session_name=...)` from `qdash.workflow` (or Prefect's `@flow` in older
 * flows) and runs its calibrations with
 * `CalibrationSession.from_context(resolve_calib_context(...)).run(targets=..., steps=...)`,
 * using the targets and steps of `qdash.calibration`. QDash owns the
 * real validation (`POST /flows`: the decorated function must exist, the file is
 * formatted with ruff, and a Prefect deployment is registered); these checks
 * only catch what would certainly be rejected, so the user is not asked to
 * approve a save that cannot succeed. Templates and helpers are read through
 * `qdash_query` (`flow_templates`, `flow_template`, `flow_helper_files`,
 * `flow_helper_file`), existing flows through `qdash_get_flow`. Running goes
 * through the SDK's `qdash.workflows.run`, which checks the name before any
 * request; the project is the profile's, or the server's default when none is
 * set. Confirmation stays here, and the tool returns the execution ID without
 * waiting.
 */

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

export type SaveFlowRequest = {
  name: string;
  description: string;
  code: string;
  flow_function_name: string;
  chip_id: string;
  default_parameters: Record<string, unknown>;
  default_run_parameters: Record<string, unknown>;
  tags: string[];
};

export type SaveFlowResult = { name: string; file_path: string; message: string };

export type FlowExecution = {
  execution_id: string;
  flow_run_id: string;
  flow_run_url: string;
  qdash_ui_url: string;
  message: string;
  calibration_session_id?: string | null;
  calibration_run_id?: string | null;
  replayed?: boolean;
};

/**
 * The idempotency key of a saved-flow run: one per tool call, so a replayed or retried call
 * returns the run it started instead of starting another. The call id comes from the host,
 * never from the model's arguments.
 */
export function flowRunKey(toolCallId: string): string {
  const key = `qdash_execute_flow:${toolCallId}`;
  return key.length <= 128 ? key : `qdash_execute_flow:${toolCallId.slice(-100)}`;
}

/** The client these tools use; tests pass a stub with `saveFlow`, `executeFlow` and `config`. */
export type FlowClient = QDashConnection;

export type FlowAuthoringDependencies = {
  makeClient(params: ConnectionParams): Promise<FlowClient>;
  /** The chip the flow is for: the explicit id, else the session/default chip. */
  resolveChipId(client: FlowClient, chipId?: string): Promise<string>;
  /** The QDash web page of a flow, when the web URL is known. */
  flowPageUrl?(client: FlowClient, name: string): string | undefined;
  /** The SDK session for a resolved client; defaults to one with the client's settings. */
  sdk?: SdkSessionFactory;
};

const FLOW_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Why a save would certainly be rejected, before anyone is asked to approve it. */
export function flowCodeProblems(name: string, code: string, functionName: string): string[] {
  const problems: string[] = [];
  if (!FLOW_NAME.test(name)) problems.push(`name '${name}' must be letters, digits and underscores, not starting with a digit`);
  if (!FLOW_NAME.test(functionName)) problems.push(`flowFunctionName '${functionName}' is not a Python identifier`);
  const calibrationFlow = /^\s*@calibration_flow\b/m.test(code);
  if (!calibrationFlow && !/^\s*@flow\b/m.test(code)) {
    problems.push("the code has no `@calibration_flow` decorator (import it with `from qdash.workflow import calibration_flow`) or `@flow`");
  }
  if (!new RegExp(`^\\s*(?:async\\s+)?def\\s+${functionName}\\s*\\(`, "m").test(code)) {
    problems.push(`the code defines no function named '${functionName}'`);
  }
  if (calibrationFlow) {
    if (!/^\s*from\s+qdash\.workflow\s+import\s+[^\n]*\bcalibration_flow\b/m.test(code) && !/^\s*from\s+qdash\.workflow\s+import\s+\([^)]*\bcalibration_flow\b/m.test(code)) {
      problems.push("the code uses `@calibration_flow` but does not import it from qdash.workflow");
    }
  } else if (!/^\s*(?:from|import)\s+prefect\b/m.test(code)) {
    problems.push("the code does not import prefect");
  }
  return problems;
}

function detailOf(error: unknown): string | undefined {
  if (!error || typeof error !== "object") return undefined;
  const payload = (error as { payload?: unknown }).payload;
  const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string") return detail;
  const message = (error as { message?: unknown }).message;
  return typeof message === "string" ? message : undefined;
}

export function formatSavedFlow(result: SaveFlowResult, chipId: string, url: string | undefined): string {
  return [
    `${result.message} (chip ${chipId}).`,
    `File: ${result.file_path}`,
    ...(url ? [`Page: ${url}`] : []),
    "The flow is registered as a Prefect deployment. Saving did not run it; qdash_execute_flow runs it when the user asks.",
  ].join("\n");
}

export function formatFlowExecution(result: FlowExecution, name: string): string {
  const recorded = result.calibration_session_id
    ? [`Recorded in calibration session ${result.calibration_session_id} as run ${result.calibration_run_id ?? "(unknown)"}${result.replayed ? " (this call had already started it; nothing new was started)" : ""}; every step execution of the run belongs to it.`]
    : [];
  return [
    `${result.replayed ? "Already started" : result.message || `Flow '${name}' started.`}`,
    `Execution: ${result.execution_id}`,
    ...recorded,
    `QDash: ${result.qdash_ui_url}`,
    `Prefect: ${result.flow_run_url}`,
    "Follow it with qdash_wait_execution; completed tasks write their calibrated parameters to QDash directly.",
  ].join("\n");
}

const connectionParams = {
  profile: Type.Optional(Type.String({ description: PROFILE_DESCRIPTION })),
  configPath: Type.Optional(Type.String({ description: CONFIG_PATH_DESCRIPTION })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

export function registerFlowAuthoringTools(pi: Pick<ExtensionAPI, "registerTool">, deps: FlowAuthoringDependencies): void {
  pi.registerTool({
    name: "qdash_save_flow",
    label: "QDash Save Flow",
    description:
      "Save a calibration flow (Python, decorated with @calibration_flow) as a QDash workflow: writes the file, formats it, registers its Prefect deployment, and records it in the project. Saving an existing name replaces that flow. Confirmation-gated write operation: the flow runs later on the workflow worker with hardware access. Start from a template (qdash_query flow_templates / flow_template) or an existing flow (qdash_get_flow).",
    promptSnippet: "Save a calibration flow the user asked you to write as a QDash workflow",
    promptGuidelines: [
      "Before qdash_save_flow, read a template or the existing flow and keep its structure: the @calibration_flow function (with a literal session_name), the explicit resolve_calib_context and CalibrationSession.from_context, and session.run(targets=..., steps=...) with qdash.calibration targets and steps. Do not write CalibService in new flows.",
      "Show the user the whole code and say which chip it is for; the save is confirmation-gated and replaces a flow of the same name.",
      "Saving does not run the flow. Do not run it unless the user asks.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      name: Type.String({ description: "Flow name: letters, digits and underscores. Also the file name and, by default, the decorated flow function name." }),
      code: Type.String({ description: "The complete Python source of the flow module." }),
      description: Type.Optional(Type.String({ description: "One line shown on the Workflow page." })),
      chipId: Type.Optional(Type.String({ description: "Chip the flow is for. Defaults to the session/default chip." })),
      flowFunctionName: Type.Optional(Type.String({ description: "The decorated flow function to deploy when it is not named like the flow." })),
      defaultParameters: Type.Optional(Type.Object({}, { additionalProperties: true, description: "Default values of the flow function's parameters." })),
      defaultRunParameters: Type.Optional(Type.Object({}, { additionalProperties: true, description: "Run parameters applied to every task, such as shots or interval." })),
      tags: Type.Optional(Type.Array(Type.String())),
    }),
    async execute(
      toolCallId,
      params: ConnectionParams & {
        name: string;
        code: string;
        description?: string;
        chipId?: string;
        flowFunctionName?: string;
        defaultParameters?: Record<string, unknown>;
        defaultRunParameters?: Record<string, unknown>;
        tags?: string[];
      },
      _signal,
      _onUpdate,
      ctx,
    ) {
      const functionName = params.flowFunctionName ?? params.name;
      const problems = flowCodeProblems(params.name, params.code, functionName);
      if (problems.length > 0) {
        const text = [
          `The flow cannot be saved as it is (${problems.length} problem${problems.length === 1 ? "" : "s"}). Nothing was written.`,
          ...problems.map((problem) => `- ${problem}`),
        ].join("\n");
        return toTextToolResult(text, { problems }, { tool: "qdash_save_flow", saved: false, problemCount: problems.length });
      }
      await requireWriteApproval("qdash_save_flow", toolCallId, params, ctx, { title: "Save QDash flow?", message: `This writes flow '${params.name}' to the project and registers its deployment.` });
      const client = await deps.makeClient(params);
      const chipId = await deps.resolveChipId(client, params.chipId);
      try {
        const result = (await client.saveFlow({
          name: params.name,
          description: params.description ?? "",
          code: params.code,
          flow_function_name: functionName,
          chip_id: chipId,
          default_parameters: params.defaultParameters ?? {},
          default_run_parameters: params.defaultRunParameters ?? {},
          tags: params.tags ?? [],
        })) as SaveFlowResult;
        const url = deps.flowPageUrl?.(client, result.name);
        return toTextToolResult(formatSavedFlow(result, chipId, url), { ...result, chip_id: chipId, url }, {
          tool: "qdash_save_flow",
          saved: true,
          flowName: result.name,
          chipId,
        });
      } catch (error) {
        const detail = detailOf(error);
        if (!detail) throw error;
        return toTextToolResult(
          `QDash rejected the flow: ${detail}\nNothing was saved. Fix the code and save again.`,
          { detail },
          { tool: "qdash_save_flow", saved: false },
        );
      }
    },
  });

  pi.registerTool({
    name: "qdash_execute_flow",
    label: "QDash Execute Flow",
    description:
      "Run a saved QDash flow as one execution, with parameters that override its defaults. Confirmation-gated write operation: the flow runs on the workflow worker with hardware access, takes the project execution lock, and completed tasks write their calibrated parameters to QDash directly.",
    promptSnippet: "Run a saved QDash flow after explicit user confirmation",
    promptGuidelines: [
      "Use qdash_execute_flow only when the user asks to run a flow; saving one with qdash_save_flow is not a request to run it.",
      "Check qdash_list_executions for a running execution first; a flow takes the project execution lock.",
      "After it starts, follow the execution with qdash_wait_execution and summarize failed targets.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      // The names a flow can be saved under; pi rejects others before confirmation.
      name: Type.String({ pattern: "^[A-Za-z0-9_]+$", description: "The saved flow's name: letters, digits and underscores." }),
      parameters: Type.Optional(Type.Object({}, { additionalProperties: true, description: "Flow function parameters; override the flow's default_parameters." })),
      calibrationSessionId: Type.Optional(Type.String({ description: "Record the run in this calibration session (open, on the flow's chip, created by the user). Without it the run joins an automatic session of its own. Grants nothing." })),
    }),
    async execute(toolCallId, params: ConnectionParams & { name: string; parameters?: Record<string, unknown>; calibrationSessionId?: string }, _signal, _onUpdate, ctx) {
      const recordedIn = params.calibrationSessionId ? ` It is recorded in calibration session ${params.calibrationSessionId}, which groups it and grants nothing.` : "";
      await requireWriteApproval("qdash_execute_flow", toolCallId, params, ctx, { title: "Run QDash flow?", message: `This starts flow '${params.name}' on the workflow worker. Completed tasks update calibrated parameters in QDash directly.${recordedIn}` });
      const client = await deps.makeClient(params);
      // A paused agent session's targets must not be measured around its pause.
      const flowChip = typeof params.parameters?.chip_id === "string" ? params.parameters.chip_id : undefined;
      const flowQids = Array.isArray(params.parameters?.qids) && params.parameters.qids.length > 0 && params.parameters.qids.every((qid) => typeof qid === "string")
        ? (params.parameters.qids as string[])
        : undefined;
      const conflict = await pausedSessionConflict(client, flowChip, flowQids);
      if (conflict) {
        return toTextToolResult(conflict, { blocked: true }, { tool: "qdash_execute_flow", flowName: params.name, started: false, blockedByPausedSession: true });
      }
      const qdash = (deps.sdk ?? sdkSession)(client);
      // Recorded under this call's key: a replayed call returns the run it started.
      const run = await qdash.workflows
        .run(params.name, {
          parameters: params.parameters,
          idempotencyKey: flowRunKey(toolCallId),
          ...(params.calibrationSessionId ? { calibrationSessionId: params.calibrationSessionId } : {}),
        })
        .catch((error: unknown) => {
          // Answered, but without the recording asked for: the run may be going.
          throw isResultUnknown(error)
            ? resultUnknownToolError(error, flowChip ? { chipId: flowChip } : { chipHint: `the chip_id that qdash_get_flow shows for flow ${params.name}` })
            : error;
        });
      const result = run.response as FlowExecution;
      return toTextToolResult(formatFlowExecution(result, params.name), result, {
        tool: "qdash_execute_flow",
        flowName: params.name,
        executionId: result.execution_id,
        started: true,
        ...(result.calibration_session_id ? { calibrationSessionId: result.calibration_session_id, calibrationRunId: result.calibration_run_id ?? undefined } : {}),
        ...(result.replayed ? { replayed: true } : {}),
      });
    },
  });
}
