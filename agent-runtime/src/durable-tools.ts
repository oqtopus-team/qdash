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

import {
  ALLOWED_TOOL_NAMES,
  EXPERIMENTAL_WRITE_TOOL_NAMES,
  isExperimentalWriteTool,
} from "./allowed-tools.ts";

/** Convert a value returned by an extension into durable's strict JSON shape. */
function asJson(value: unknown): JsonValue | undefined {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}

/**
 * Adapt one pi-coding-agent tool to pi-durable's execution contract.
 *
 * Read-only calls may be replayed after interruption. Experimental writes are
 * adapted as unsafe and retain pi-qdash's non-interactive confirmation field.
 * Raw-path access and unreviewed tools are removed before adaptation.
 */
export function adaptCodingAgentTool(
  tool: CodingAgentTool,
  modelRuntime: ModelRuntime,
  cwd: string,
): ToolRegistration {
  const writesQDash = isExperimentalWriteTool(tool.name);
  return defineTool({
    name: tool.name,
    description: tool.description,
    parameters: tool.parameters,
    // A repeated read is harmless. A write interrupted after reaching QDash
    // must instead surface as interrupted and be reconciled by the operator.
    replay: writesQDash ? "unsafe" : "safe",
    ...(tool.prepareArguments ? { prepareArguments: tool.prepareArguments } : {}),
    ...(tool.executionMode ? { executionMode: tool.executionMode } : {}),
    execute: async (args, api: ToolExecutionApi, context: Context) => {
      if (
        writesQDash &&
        (!(typeof args === "object" && args !== null && "confirmWrite" in args) ||
          (args as { confirmWrite?: unknown }).confirmWrite !== true)
      ) {
        throw new Error(`${tool.name} requires confirmWrite: true`);
      }
      const extensionContext = {
        cwd,
        mode: "json",
        hasUI: false,
        signal: context.abortSignal,
        modelRegistry: new ModelRegistry(modelRuntime),
        isIdle: () => false,
        isProjectTrusted: () => true,
        hasPendingMessages: () => false,
      };
      const result = await tool.execute(
        api.callId,
        args,
        context.abortSignal,
        undefined,
        extensionContext as never,
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

/** Build the durable extension containing all permitted pi-qdash tools. */
export function buildQDashExtension(
  extensions: ReadonlyArray<{ tools?: Map<string, { definition: CodingAgentTool }> }>,
  modelRuntime: ModelRuntime,
  cwd: string,
  enableExperimentalWriteTools = false,
): Extension {
  const allowed = new Set<string>([
    ...ALLOWED_TOOL_NAMES,
    ...(enableExperimentalWriteTools ? EXPERIMENTAL_WRITE_TOOL_NAMES : []),
  ]);
  const tools = new Map<string, ToolRegistration>();
  for (const extension of extensions) {
    for (const [name, registered] of extension.tools ?? []) {
      if (allowed.has(name)) {
        tools.set(name, adaptCodingAgentTool(registered.definition, modelRuntime, cwd));
      }
    }
  }
  return defineExtension({ name: "qdash", tools: [...tools.values()] });
}
