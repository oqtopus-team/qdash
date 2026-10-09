import type { Context, JsonValue } from "@earendil-works/chord";
import type {
  ModelRuntime,
  ToolDefinition as CodingAgentTool,
} from "@earendil-works/pi-coding-agent";
import { ModelRegistry } from "@earendil-works/pi-coding-agent";
import {
  defineExtension,
  defineTool,
  type Extension,
  type ToolExecutionApi,
  type ToolRegistration,
} from "@earendil-works/pi-durable";
import type { TSchema } from "typebox";

import {
  ALLOWED_TOOL_NAMES,
  EXPERIMENTAL_WRITE_TOOL_NAMES,
  isExperimentalWriteTool,
} from "./allowed-tools.ts";
import type { QDashConnection } from "./auth.ts";
import { withParameterOverrides } from "./tool-schemas.ts";

/** Convert a value returned by an extension into durable's strict JSON shape. */
function asJson(value: unknown): JsonValue | undefined {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}

/** A write call waiting for the user, as stored in the tool result and shown in the UI. */
export interface ApprovalRequest {
  /** The tool call id; the user's decision names it. */
  id: string;
  tool: string;
  label: string;
  args: Record<string, unknown>;
}

// pi-qdash connection plumbing; meaningless to the person approving the call.
const HIDDEN_ARGS = new Set(["confirmWrite", "profile", "configPath", "useEnv"]);

function approvalArgs(args: unknown): Record<string, unknown> {
  if (typeof args !== "object" || args === null) return {};
  return Object.fromEntries(Object.entries(args).filter(([key]) => !HIDDEN_ARGS.has(key)));
}

/** Connection settings and write confirmation belong exclusively to the runtime. */
function withoutRuntimeArguments(parameters: TSchema): TSchema {
  const { properties, required } = parameters as {
    properties?: Record<string, TSchema>;
    required?: string[];
  };
  if (!properties) return parameters;
  return {
    ...parameters,
    properties: Object.fromEntries(
      Object.entries(properties).filter(([key]) => !HIDDEN_ARGS.has(key)),
    ),
    ...(Array.isArray(required)
      ? { required: required.filter((key: string) => !HIDDEN_ARGS.has(key)) }
      : {}),
  };
}

/** Run a pi-coding-agent tool with the non-interactive context this runtime provides. */
async function runCodingAgentTool(
  tool: CodingAgentTool,
  callId: string,
  args: unknown,
  signal: AbortSignal | undefined,
  modelRuntime: ModelRuntime,
  cwd: string,
  connection: QDashConnection,
) {
  const extensionContext = {
    cwd,
    mode: "json",
    hasUI: false,
    signal,
    modelRegistry: new ModelRegistry(modelRuntime),
    isIdle: () => false,
    isProjectTrusted: () => true,
    hasPendingMessages: () => false,
  };
  return tool.execute(
    callId,
    {
      ...approvalArgs(args),
      ...connection.toolArgs,
      ...(isExperimentalWriteTool(tool.name) ? { confirmWrite: true } : {}),
    } as never,
    signal,
    undefined,
    extensionContext as never,
  );
}

/**
 * Adapt one pi-coding-agent tool to pi-durable's execution contract.
 *
 * Read-only calls may be replayed after interruption. Experimental writes
 * never run from the model's call: the call ends the turn with an approval
 * request, and the runtime runs it only after the user approves it in the UI
 * (see `QDashWriteTools.runApproved`).
 */
export function adaptCodingAgentTool(
  tool: CodingAgentTool,
  modelRuntime: ModelRuntime,
  cwd: string,
  connection: QDashConnection,
): ToolRegistration {
  const writesQDash = isExperimentalWriteTool(tool.name);
  const parameters = withParameterOverrides(tool.name, tool.parameters);
  return defineTool({
    name: tool.name,
    description: writesQDash
      ? `${tool.description} The user is shown the exact arguments and must approve before it runs.`
      : tool.description,
    parameters: withoutRuntimeArguments(parameters),
    // A repeated read is harmless. A write never runs inside the harness, so
    // replaying the call only re-issues the approval request.
    replay: "safe",
    ...(tool.prepareArguments ? { prepareArguments: tool.prepareArguments } : {}),
    ...(tool.executionMode ? { executionMode: tool.executionMode } : {}),
    execute: async (args, api: ToolExecutionApi, context: Context) => {
      if (writesQDash) {
        const approval: ApprovalRequest = {
          id: api.callId,
          tool: tool.name,
          label: tool.label || tool.name,
          args: approvalArgs(args),
        };
        return {
          content: [
            {
              type: "text",
              text: "Approval requested: the user now sees this operation with its arguments and Approve/Decline buttons. Stop here. Their decision arrives as the next message.",
            },
          ],
          details: asJson({ approval }),
          control: { terminate: true as const },
        };
      }
      const result = await runCodingAgentTool(
        tool,
        api.callId,
        args,
        context.abortSignal,
        modelRuntime,
        cwd,
        connection,
      );
      return {
        content: result.content,
        ...(result.details === undefined ? {} : { details: asJson(result.details) }),
        ...(result.isError === undefined ? {} : { isError: result.isError }),
        ...(result.usage === undefined ? {} : { usage: result.usage }),
        ...(result.terminate ? { control: { terminate: true as const } } : {}),
      };
    },
  });
}

const MAX_RESULT_CHARS = 8_000;

/** What the model is told after the user decided on a write call. */
export function decisionMessage(
  approval: ApprovalRequest,
  outcome:
    | { approved: false }
    | { approved: true; result: string }
    | { approved: true; error: string },
): string {
  const what = `${approval.label} (${approval.tool})`;
  if (!outcome.approved) {
    return `[QDash runtime] The user declined ${what}. It was not run. Do not call it again unless the user asks; suggest another way forward if there is one.`;
  }
  if ("error" in outcome) {
    return `[QDash runtime] The user approved ${what}, but running it failed:\n${outcome.error}\nExplain the failure and what the user can do next.`;
  }
  const result =
    outcome.result.length > MAX_RESULT_CHARS
      ? `${outcome.result.slice(0, MAX_RESULT_CHARS)}\n… (truncated)`
      : outcome.result;
  return `[QDash runtime] The user approved ${what} and it ran with the arguments they saw. Result:\n${result || "(no output)"}\nContinue the task from here.`;
}

/** The original write tools, run by the runtime once the user has approved a call. */
export class QDashWriteTools {
  constructor(
    private readonly tools: ReadonlyMap<string, CodingAgentTool>,
    private readonly modelRuntime: ModelRuntime,
    private readonly cwd: string,
    private readonly connection: QDashConnection,
  ) {}

  /** Run an approved call with the exact arguments the user saw; returns its text. */
  async runApproved(approval: ApprovalRequest, signal?: AbortSignal): Promise<string> {
    const tool = this.tools.get(approval.tool);
    if (!tool) throw new Error(`write tool ${approval.tool} is not enabled`);
    const result = await runCodingAgentTool(
      tool,
      approval.id,
      { ...approval.args, confirmWrite: true },
      signal,
      this.modelRuntime,
      this.cwd,
      this.connection,
    );
    const text = result.content
      .map((block) => (block.type === "text" ? block.text : ""))
      .join("\n")
      .trim();
    if (result.isError) throw new Error(text || `${approval.tool} failed`);
    return text;
  }
}

/** Build the durable extension containing all permitted pi-qdash tools. */
export function buildQDashExtension(
  extensions: ReadonlyArray<{
    tools?: Map<string, { definition: CodingAgentTool }>;
  }>,
  modelRuntime: ModelRuntime,
  cwd: string,
  connection: QDashConnection,
  enableExperimentalWriteTools = false,
): { extension: Extension; writeTools: QDashWriteTools } {
  const allowed = new Set<string>([
    ...ALLOWED_TOOL_NAMES,
    ...(enableExperimentalWriteTools ? EXPERIMENTAL_WRITE_TOOL_NAMES : []),
  ]);
  const tools = new Map<string, ToolRegistration>();
  const writes = new Map<string, CodingAgentTool>();
  for (const extension of extensions) {
    for (const [name, registered] of extension.tools ?? []) {
      if (!allowed.has(name)) continue;
      tools.set(name, adaptCodingAgentTool(registered.definition, modelRuntime, cwd, connection));
      if (isExperimentalWriteTool(name)) writes.set(name, registered.definition);
    }
  }
  return {
    extension: defineExtension({ name: "qdash", tools: [...tools.values()] }),
    writeTools: new QDashWriteTools(writes, modelRuntime, cwd, connection),
  };
}
