import type { Context, JsonValue } from "@earendil-works/chord";
import type { Api, Model } from "@earendil-works/pi-ai";
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
  TRUSTED_EXTENSION_PACKAGES,
  isExperimentalWriteTool,
} from "./allowed-tools.ts";
import type { QDashConnection } from "./auth.ts";
import {
  acceptsImages,
  hasImages,
  latestFigures,
  requestedImageCount,
  withImages,
} from "./figure-context.ts";
import { hostRecord } from "./evaluate.ts";
import {
  acceptsCriteria,
  acceptsKnowledge,
  fetchTaskExamples,
  fetchTaskKnowledge,
  hasExamples,
  hasKnowledge,
  referenceOf,
  requestedTaskName,
  wantsExamples,
  withExamples,
  withKnowledge,
} from "./knowledge-context.ts";
import type { LabeledExample, Reference } from "./knowledge-context.ts";
import { isTrustedExtension } from "./local-extensions.ts";
import { withParameterOverrides } from "./tool-schemas.ts";

/** Newest transcript entries searched for a figure when a tool asks for one. */
const FIGURE_SCAN_LIMIT = 50;

/** Whether an extension is a mounted development checkout or a trusted installed package. */
function isTrusted(
  extension: { path?: string },
  roots: readonly string[],
  packages: readonly string[],
): boolean {
  return extension.path !== undefined && isTrustedExtension(extension.path, roots, packages);
}

/** The model the conversation runs on, resolved from the durable agent record. */
async function conversationModel(
  api: Pick<ToolExecutionApi, "agent">,
  context: Context,
  modelRuntime: ModelRuntime,
): Promise<Model<Api> | undefined> {
  if (typeof api.agent !== "function") return undefined;
  const ref = (await api.agent(context)).model;
  return ref ? (modelRuntime.getModel(ref.provider, ref.modelId) ?? undefined) : undefined;
}

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
export async function runCodingAgentTool(
  tool: CodingAgentTool,
  callId: string,
  args: unknown,
  signal: AbortSignal | undefined,
  modelRuntime: ModelRuntime,
  cwd: string,
  connection: QDashConnection,
  /** The conversation's model, so a tool can fall back to it (pi-qcaleval does). */
  model?: Model<Api>,
) {
  const extensionContext = {
    cwd,
    mode: "json",
    hasUI: false,
    signal,
    model,
    modelRegistry: new ModelRegistry(modelRuntime),
    isIdle: () => false,
    isProjectTrusted: () => true,
    hasPendingMessages: () => false,
  };
  const run = tool.execute(
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
  return untilAborted(run, signal, tool.name);
}

/** Thrown when a tool call is cancelled while the tool itself is still running. */
export class ToolCancelled extends Error {
  override readonly name = "AbortError";
  constructor(toolName: string) {
    super(`${toolName} was cancelled; whatever it waited on keeps running in QDash.`);
  }
}

/**
 * Settle a tool call as soon as the turn is cancelled. A pi-qdash tool that
 * polls (waiting on an execution) may not watch the signal; letting it run on
 * would keep the conversation busy, and the chat would refuse the user's next
 * message. The tool's own promise is left to finish or time out on its own.
 */
export function untilAborted<T>(run: Promise<T>, signal: AbortSignal | undefined, toolName: string): Promise<T> {
  if (!signal) return run;
  if (signal.aborted) {
    // The call already started; its later rejection must not go unhandled.
    run.catch(() => undefined);
    return Promise.reject(new ToolCancelled(toolName));
  }
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => {
      console.warn(`[agent-runtime] ${toolName} cancelled while running; its result is dropped`);
      reject(new ToolCancelled(toolName));
      run.catch(() => undefined);
    };
    signal.addEventListener("abort", onAbort, { once: true });
    run.then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
  });
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
  options: {
    replay?: "safe" | "unsafe";
    /** Fill an omitted `images` argument from the newest figure in the transcript. */
    fillImages?: boolean;
    /** Fill an omitted `knowledge` argument (and `criteria`, when declared) with QDash's reference for `task_name`. */
    fillKnowledge?: boolean;
  } = {},
): ToolRegistration {
  const writesQDash = isExperimentalWriteTool(tool.name);
  const parameters = withParameterOverrides(tool.name, tool.parameters);
  return defineTool({
    name: tool.name,
    description: writesQDash
      ? `${tool.description} The user is shown the exact arguments and must approve before it runs.`
      : tool.description,
    parameters: withoutRuntimeArguments(parameters),
    // Reviewed pi-qdash tools default to safe: a repeated read is harmless,
    // and a write never runs inside the harness, so replaying the call only
    // re-issues the approval request.
    replay: options.replay ?? "safe",
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
          output: [
            {
              type: "text",
              text: "Approval requested: the user now sees this operation with its arguments and Approve/Decline buttons. Stop here. Their decision arrives as the next message.",
            },
          ],
          details: asJson({ approval }),
          control: { terminate: true as const },
        };
      }
      let callArgs: unknown = args;
      let figureTaskId: string | undefined;
      if (options.fillImages) {
        // The model names the figure it wants evaluated by having fetched or
        // received it; the bytes are taken from the transcript, not its call.
        // Bytes the model copied into the call itself are replaced too: a
        // model retyping base64 drops or alters characters, and the provider
        // then rejects the whole request.
        const page = await api.commit(
          (tx) => tx.scanEntries({ conversationId: api.conversationId }, FIGURE_SCAN_LIMIT),
          context,
        );
        const found = latestFigures(page.items, requestedImageCount(args));
        figureTaskId = found.taskId;
        if (found.images.length || !hasImages(args)) {
          callArgs = withImages(args as object, found.images);
        }
      }
      const taskName = requestedTaskName(args);
      let reference: Reference | undefined;
      if (options.fillKnowledge && taskName && !hasKnowledge(args)) {
        // The model names the task; the reference it is judged against comes
        // from QDash, as the user, so every evaluation reads the same one.
        reference = await fetchTaskKnowledge(connection, taskName, context.abortSignal);
        if (reference) {
          console.log(
            `[agent-runtime] ${tool.name}: reference for ${taskName} (${reference.knowledge.length} chars${reference.criteria ? ", criteria" : ""})`,
          );
        }
        callArgs = withKnowledge(callArgs as object, reference, acceptsCriteria(parameters));
      }
      let examples: LabeledExample[] | undefined;
      if (options.fillKnowledge && taskName && wantsExamples(args) && !hasExamples(args)) {
        // The model only asks for examples; the figures and labels come from
        // QDash's knowledge, never from the model's own call.
        examples = await fetchTaskExamples(connection, taskName, context.abortSignal);
        console.log(`[agent-runtime] ${tool.name}: ${examples.length} labeled example(s) for ${taskName}`);
        callArgs = withExamples(callArgs as object, examples);
      }
      const started = Date.now();
      const result = await runCodingAgentTool(
        tool,
        api.callId,
        callArgs,
        context.abortSignal,
        modelRuntime,
        cwd,
        connection,
        await conversationModel(api, context, modelRuntime),
      );
      // An evaluation result records what the host put into the call (figure
      // hashes, the reference, the context), so a planner turn leaves the
      // same record as a direct evaluation (see evaluate.ts).
      const details =
        options.fillImages && result.details !== undefined && typeof result.details === "object"
          ? {
              ...(result.details as object),
              host: hostRecord(
                callArgs,
                reference ?? referenceOf(callArgs),
                Date.now() - started,
                figureTaskId,
                examples,
              ),
            }
          : result.details;
      return {
        output: boundOutput(result.content, tool.name),
        ...(details === undefined ? {} : { details: asJson(details) }),
        ...(result.isError === undefined ? {} : { isError: result.isError }),
        ...(result.usage === undefined ? {} : { usage: result.usage }),
        ...(result.terminate ? { control: { terminate: true as const } } : {}),
      };
    },
  });
}

const MAX_RESULT_CHARS = 8_000;

/**
 * Longest text one tool result puts into the transcript. A qwen-class chat
 * model has a 64k-token window shared with a 13k-token system prompt; two
 * 90k-character results in one turn (task knowledge with inline figures) once
 * pushed a prompt past it, and compaction only runs between turns.
 */
export const MAX_TOOL_TEXT_CHARS = 24_000;
const DATA_URI = /data:[a-z]+\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]{64,}/g;

/** A tool's text blocks as the model gets them: no inline base64, and no block longer than the budget. */
export function boundToolText(text: string, toolName: string): string {
  const stripped = text.replace(DATA_URI, "data:… (inline image omitted; QDash shows it)");
  if (stripped.length <= MAX_TOOL_TEXT_CHARS) return stripped;
  return `${stripped.slice(0, MAX_TOOL_TEXT_CHARS)}\n\n[QDash runtime] ${toolName}: output truncated to ${MAX_TOOL_TEXT_CHARS} characters; ask for a narrower query if you need the rest.`;
}

function boundOutput<T>(content: ReadonlyArray<T>, toolName: string): T[] {
  return content.map((block) => {
    const text = (block as { type?: unknown; text?: unknown }) ?? {};
    if (text.type !== "text" || typeof text.text !== "string") return block;
    const bounded = boundToolText(text.text, toolName);
    return bounded === text.text ? block : ({ ...(block as object), text: bounded } as T);
  });
}

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

/**
 * Build the durable extension containing all permitted pi-qdash tools.
 *
 * Tools of the pinned pi-qdash package pass the reviewed allowlist by name.
 * An extension trusted as a whole, because its file lies under one of
 * `localExtensionRoots` (`AGENT_RUNTIME_EXTENSION_PATHS`, development only)
 * or it belongs to one of `trustedPackages` (installed at a pinned version),
 * offers every tool it defines, except that an experimental write name still
 * needs the opt-in, and a tool is replayed on recovery only when its
 * annotations say it is read-only. A trusted tool that reuses a pinned name
 * replaces the pinned implementation.
 */
export function buildQDashExtension(
  extensions: ReadonlyArray<{
    path?: string;
    tools?: Map<string, { definition: CodingAgentTool }>;
  }>,
  modelRuntime: ModelRuntime,
  cwd: string,
  connection: QDashConnection,
  enableExperimentalWriteTools = false,
  localExtensionRoots: readonly string[] = [],
  trustedPackages: readonly string[] = TRUSTED_EXTENSION_PACKAGES,
): { extension: Extension; writeTools: QDashWriteTools } {
  const allowed = new Set<string>([
    ...ALLOWED_TOOL_NAMES,
    ...(enableExperimentalWriteTools ? EXPERIMENTAL_WRITE_TOOL_NAMES : []),
  ]);
  const tools = new Map<string, ToolRegistration>();
  const writes = new Map<string, CodingAgentTool>();
  const trusted = (extension: { path?: string }) =>
    isTrusted(extension, localExtensionRoots, trustedPackages);
  // Pinned extensions first, so a trusted definition is the one that replaces.
  const ordered = [...extensions].sort((a, b) => Number(trusted(a)) - Number(trusted(b)));
  for (const extension of ordered) {
    const local = trusted(extension);
    for (const [name, registered] of extension.tools ?? []) {
      const writeName = isExperimentalWriteTool(name);
      if (local ? writeName && !enableExperimentalWriteTools : !allowed.has(name)) continue;
      if (local && tools.has(name)) {
        console.warn(`[agent-runtime] trusted extension ${extension.path} replaces tool ${name}`);
      }
      const replay = local && !registered.definition.annotations?.readOnlyHint ? "unsafe" : "safe";
      // Only trusted extensions evaluate figures; pi-qdash tools fetch them.
      const fillImages = local && acceptsImages(registered.definition.parameters);
      const fillKnowledge = local && acceptsKnowledge(registered.definition.parameters);
      tools.set(
        name,
        adaptCodingAgentTool(registered.definition, modelRuntime, cwd, connection, {
          replay,
          fillImages,
          fillKnowledge,
        }),
      );
      if (writeName) writes.set(name, registered.definition);
    }
  }
  return {
    extension: defineExtension({ name: "qdash", tools: [...tools.values()] }),
    writeTools: new QDashWriteTools(writes, modelRuntime, cwd, connection),
  };
}
