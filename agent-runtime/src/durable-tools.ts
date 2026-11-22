import type { Context } from "@earendil-works/chord/context";
import type { JsonValue } from "@earendil-works/chord/json";
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
  REVIEWED_WRITE_TOOL_NAMES,
  SESSION_GRANTED_WRITE_TOOL_NAMES,
  isDeferredTool,
  isNestedReadTool,
  isReviewedWriteTool,
} from "./allowed-tools.ts";
import type { QDashConnection } from "./auth.ts";
import { acceptsImages, newestMessages } from "./figure-context.ts";
import { hostRecord } from "./evaluate.ts";
import { acceptsKnowledge, fetchTaskKnowledgeResponse, referenceOf } from "./knowledge-context.ts";
import { hydrateEvaluationArgs } from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";
import { QDASH_TOOL_NAMESPACE } from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";
import {
  canonicalArgs,
  HOST_WRITE_APPROVAL_KEY,
  unserializableArgsMessage,
} from "@oqtopus-team/pi-qdash/extensions/lib/write-approval.ts";
import { isWaitToolName, WAIT_SPECS, type WaitSpec } from "@oqtopus-team/pi-qdash/extensions/lib/waits.ts";
import { HOST_MODEL_KEY, HOST_NAME_KEY } from "@oqtopus-team/pi-qdash/extensions/lib/host-model.ts";
import { isTrustedExtension } from "./bundled-extensions.ts";
import { withParameterOverrides } from "./tool-schemas.ts";
import { parkingWait } from "./durable-waits.ts";

/** Newest transcript entries searched for a figure when a tool asks for one. */
const FIGURE_SCAN_LIMIT = 50;

/** Whether an extension lies under one of the bundled roots trusted as a whole. */
function isTrusted(extension: { path?: string }, roots: readonly string[]): boolean {
  return extension.path !== undefined && isTrustedExtension(extension.path, roots);
}

/** The provider and model ID the conversation's agent runs with, from the durable agent record. */
async function conversationModelRef(
  api: Pick<ToolExecutionApi, "agent">,
  context: Context,
): Promise<ApprovalModel | undefined> {
  if (typeof api.agent !== "function") return undefined;
  const ref = (await api.agent(context)).model;
  return ref ? { provider: ref.provider, modelId: ref.modelId } : undefined;
}

/** The catalog model of a reference, for tools that call it (pi-qcaleval falls back to it). */
function catalogModel(modelRuntime: ModelRuntime, ref: ApprovalModel): Model<Api> | undefined {
  return modelRuntime.getModel(ref.provider, ref.modelId) ?? undefined;
}

/** Convert a value returned by an extension into durable's strict JSON shape. */
function asJson(value: unknown): JsonValue | undefined {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}

/**
 * What a Code Mode script receives from a nested QDash tool: the redacted
 * response data the tool's text summarizes, untruncated, so a script can
 * filter and aggregate it. Any JSON value.
 */
export const QDASH_DATA_SCHEMA = {
  description:
    "The tool's redacted QDash response data as JSON: the data its text answer summarizes, not truncated.",
} as const;

/** Text blocks of a tool result, joined. */
function textOf(content: ReadonlyArray<{ type: string; text?: string }>): string {
  return content
    .map((block) => (block.type === "text" && typeof block.text === "string" ? block.text : ""))
    .join("\n");
}

/**
 * The value a script gets for a nested call: pi-qdash's `details.data`,
 * else the text answer parsed as JSON, else the text itself.
 */
export function nestedDataOf(result: {
  content: ReadonlyArray<{ type: string; text?: string }>;
  details?: unknown;
}): JsonValue {
  const data = (result.details as { data?: unknown } | undefined)?.data;
  const json = asJson(data);
  if (json !== undefined) return json;
  const text = textOf(result.content);
  try {
    return JSON.parse(text) as JsonValue;
  } catch {
    return text;
  }
}

/** A write call waiting for the user, as stored in the tool result and shown in the UI. */
export interface ApprovalRequest {
  /** The tool call id; the user's decision names it. */
  id: string;
  tool: string;
  label: string;
  args: Record<string, unknown>;
  /**
   * The conversation's model when it made the call, captured by the runtime
   * (never from the call's arguments). The approved call reports it to QDash
   * as the model of the records it writes; a model switch before the user
   * decides does not change it.
   */
  model?: ApprovalModel;
}

/** A model reference: pi provider ID and model ID, nothing else. */
export interface ApprovalModel {
  provider: string;
  modelId: string;
}

// pi-qdash connection plumbing, meaningless to the person approving the call,
// and the retired `confirmWrite`, which a model may still send and which
// approves nothing.
const HIDDEN_ARGS = new Set(["confirmWrite", "profile", "configPath", "useEnv"]);

function approvalArgs(args: unknown): Record<string, unknown> {
  if (typeof args !== "object" || args === null) return {};
  return Object.fromEntries(Object.entries(args).filter(([key]) => !HIDDEN_ARGS.has(key)));
}

/** Connection settings belong exclusively to the runtime; the model sees none of them. */
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
  /**
   * The user approved this exact call in the approval card (`runApproved`
   * only). pi-qdash reads it from the extension context, where the model
   * cannot put it; no argument approves a write.
   */
  approvedByUser = false,
  /**
   * The provider and model ID the harness runs the conversation with (for an
   * approved write: the model that made the call). pi-qdash reports it with
   * the QDash records the call writes (host-model.ts); unlike `model` it needs
   * no catalog entry.
   */
  modelRef?: ApprovalModel,
) {
  const approved = approvedByUser && isReviewedWriteTool(tool.name);
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
    // pi-qdash reports QDash records as written by this host, with this model (host-model.ts).
    [HOST_NAME_KEY]: "qdash-web-agent",
    ...(modelRef ? { [HOST_MODEL_KEY]: { provider: modelRef.provider, id: modelRef.modelId } } : {}),
    ...(approved
      ? { [HOST_WRITE_APPROVAL_KEY]: { toolCallId: callId, toolName: tool.name } }
      : {}),
  };
  const params = { ...approvalArgs(args), ...connection.toolArgs };
  const run = tool.execute(
    callId,
    (approved ? frozenCopy(params, tool.name) : params) as never,
    signal,
    undefined,
    extensionContext as never,
  );
  return untilAborted(run, signal, tool.name);
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object") {
    for (const item of Object.values(value)) deepFreeze(item);
    Object.freeze(value);
  }
  return value;
}

/**
 * A deeply frozen plain-data copy of an approved call's arguments. The tool
 * gets its own copy, so neither it nor anything else can change what runs
 * after the approval, nor the persisted approval request the user saw.
 * Arguments that are not plain JSON data are refused.
 */
function frozenCopy(params: Record<string, unknown>, toolName: string): Record<string, unknown> {
  const canonical = canonicalArgs(params);
  if (canonical === undefined) throw new Error(unserializableArgsMessage(toolName));
  return deepFreeze(JSON.parse(canonical) as Record<string, unknown>);
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
 * Read-only calls may be replayed after interruption. Reviewed writes
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
    /**
     * Let Code Mode scripts call the tool, which then returns its response
     * data as structured output. Only audited read-only tools; every other
     * tool can only be called by the model.
     */
    nested?: boolean;
    /** Offer the tool to the model only once `tool_search` (or a call by name) loaded it. */
    deferred?: boolean;
    /**
     * Run a pi-qdash waiting tool (`WAIT_SPECS`) one poll per durable wake,
     * parked in between, instead of running its polling loop (see
     * durable-waits.ts). Only for the pinned pi-qdash implementation.
     */
    parkingWait?: boolean;
  } = {},
): ToolRegistration {
  const writesQDash = isReviewedWriteTool(tool.name);
  const parameters = withParameterOverrides(tool.name, tool.parameters);
  const wait: WaitSpec<object, unknown> | undefined =
    options.parkingWait && !writesQDash && isWaitToolName(tool.name)
      ? (WAIT_SPECS[tool.name] as WaitSpec<never, unknown> as WaitSpec<object, unknown>)
      : undefined;
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
    // Writes and unaudited tools never run inside a script: their approval
    // card and rendering only exist for a call the model made.
    callers: options.nested && !writesQDash ? ["model", "tools"] : ["model"],
    ...(options.deferred ? { deferred: true as const } : {}),
    // A tool that declares its response shape (pi-qdash's query contracts) keeps
    // it, so a script sees the same declaration as in the pi CLI.
    ...(options.nested && !writesQDash
      ? { structuredOutputSchema: tool.outputSchema ?? QDASH_DATA_SCHEMA }
      : {}),
    ...(tool.prepareArguments ? { prepareArguments: tool.prepareArguments } : {}),
    ...(tool.executionMode ? { executionMode: tool.executionMode } : {}),
    execute: async (args, api: ToolExecutionApi, context: Context) => {
      if (writesQDash) {
        const model = await conversationModelRef(api, context);
        const approval: ApprovalRequest = {
          id: api.callId,
          tool: tool.name,
          label: tool.label || tool.name,
          args: approvalArgs(args),
          ...(model ? { model } : {}),
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
      if (wait) {
        // Connection settings come only from the runtime's connection, as for every pi-qdash call.
        // A poll in flight when the turn is stopped is dropped, not awaited.
        const spec: WaitSpec<object, unknown> = {
          ...wait,
          check: (client, params) =>
            untilAborted(wait.check(client, params, context.abortSignal), context.abortSignal, tool.name),
        };
        const step = await parkingWait(spec, approvalArgs(args), api, context, connection);
        if (!("content" in step)) return step;
        return { output: boundOutput(step.content, tool.name), details: asJson(step.details) };
      }
      let callArgs: unknown = args;
      let hydrated: Awaited<ReturnType<typeof hydrateEvaluationArgs<object>>> | undefined;
      if (options.fillImages || options.fillKnowledge) {
        // The model names the figure it wants evaluated by having fetched or
        // received it, and the task by `task_name`; the bytes come from the
        // transcript (only a figure of that task) and the reference and
        // labeled examples from QDash as the user, in one knowledge request.
        // Bytes the model copied into the call itself are replaced: a model
        // retyping base64 drops or alters characters, and the provider then
        // rejects the whole request. The rules are shared with the pi CLI.
        hydrated = await hydrateEvaluationArgs((args ?? {}) as object, {
          parameters,
          fillImages: options.fillImages === true,
          fillKnowledge: options.fillKnowledge === true,
          messages: async () => {
            const page = await api.commit(
              (tx) => tx.scanEntries({ conversationId: api.conversationId }, FIGURE_SCAN_LIMIT),
              context,
            );
            return newestMessages(page.items);
          },
          loadKnowledge: (taskName, signal) =>
            fetchTaskKnowledgeResponse(connection, taskName, signal),
          signal: context.abortSignal,
        });
        callArgs = hydrated.args;
        const summary = hydrated.summary;
        if (summary.knowledge === "host" || summary.examples > 0) {
          console.log(
            `[agent-runtime] ${tool.name}: reference for ${summary.task_name} (${hydrated.reference?.knowledge.length ?? 0} chars${summary.criteria ? ", criteria" : ""}; ${summary.examples} labeled example(s))`,
          );
        }
      }
      const figureTaskId = hydrated?.figureTaskId;
      const reference = hydrated?.reference;
      const examples = hydrated?.examples;
      const started = Date.now();
      const modelRef = await conversationModelRef(api, context);
      const result = await runCodingAgentTool(
        tool,
        api.callId,
        callArgs,
        context.abortSignal,
        modelRuntime,
        cwd,
        connection,
        modelRef ? catalogModel(modelRuntime, modelRef) : undefined,
        false,
        modelRef,
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
        // An error result carries no value: the script gets its text as the error.
        ...(options.nested && !writesQDash && !result.isError
          ? { structuredOutput: nestedDataOf(result) }
          : {}),
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
    // The model that made the call, so the records it writes name it, even
    // when the conversation switched models before the user decided.
    const result = await runCodingAgentTool(
      tool,
      approval.id,
      approval.args,
      signal,
      this.modelRuntime,
      this.cwd,
      this.connection,
      approval.model ? catalogModel(this.modelRuntime, approval.model) : undefined,
      true,
      approval.model,
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
 * `localExtensionRoots` (the bundled roots outside the allowlisted packages,
 * see bundled-extensions.ts), offers every tool it defines. Reviewed write names still require approval,
 * and a tool is replayed on recovery only when its
 * annotations say it is read-only. A trusted tool that reuses a pinned name
 * replaces the pinned implementation.
 *
 * The extension declares the shared `qdash` code mode namespace
 * (`QDASH_TOOL_NAMESPACE`, pi-durable 1.6 `Extension.namespace`), so the
 * `codemode` section lists the tools scripts may call under it and a script
 * can read its instructions with `describeNamespace("qdash")`. The namespace
 * groups tools only; Code Mode still shows and gives scripts only the audited
 * reads (see codemode.ts).
 */
export function buildQDashExtension(
  extensions: ReadonlyArray<{
    path?: string;
    tools?: Map<string, { definition: CodingAgentTool }>;
  }>,
  modelRuntime: ModelRuntime,
  cwd: string,
  connection: QDashConnection,
  localExtensionRoots: readonly string[] = [],
): {
  extension: Extension;
  writeTools: QDashWriteTools;
  /** Tools Code Mode scripts may call. */
  nestedTools: string[];
  /** Tools offered only once loaded. */
  deferredTools: string[];
} {
  // Session-granted writes run without an approval card, but only inside an
  // agent session the user approved with `autonomy: "auto"`; the tools re-read
  // the session and refuse anything outside it, and QDash checks it again.
  // Their idempotency keys derive from the call id, so a replay after an
  // interruption reuses the action or intervention it created.
  const allowed = new Set<string>([
    ...ALLOWED_TOOL_NAMES,
    ...REVIEWED_WRITE_TOOL_NAMES,
    ...SESSION_GRANTED_WRITE_TOOL_NAMES,
  ]);
  const tools = new Map<string, ToolRegistration>();
  const writes = new Map<string, CodingAgentTool>();
  const nested = new Set<string>();
  const deferred = new Set<string>();
  const trusted = (extension: { path?: string }) =>
    isTrusted(extension, localExtensionRoots);
  // Pinned extensions first, so a trusted definition is the one that replaces.
  const ordered = [...extensions].sort((a, b) => Number(trusted(a)) - Number(trusted(b)));
  for (const extension of ordered) {
    const local = trusted(extension);
    for (const [name, registered] of extension.tools ?? []) {
      const writeName = isReviewedWriteTool(name);
      if (!local && !allowed.has(name)) continue;
      if (local && tools.has(name)) {
        console.warn(`[agent-runtime] trusted extension ${extension.path} replaces tool ${name}`);
      }
      const replay = local && !registered.definition.annotations?.readOnlyHint ? "unsafe" : "safe";
      // Only trusted extensions evaluate figures; pi-qdash tools fetch them.
      const fillImages = local && acceptsImages(registered.definition.parameters);
      const fillKnowledge = local && acceptsKnowledge(registered.definition.parameters);
      // Only the pinned, audited implementation of a read tool may run from a
      // script; a trusted replacement is model-only.
      const nestedRead = !local && !writeName && isNestedReadTool(name);
      const deferredTool = isDeferredTool(name);
      // The pinned waiting tools park between polls; a trusted replacement runs its own code.
      const parkingWaitTool = !local && isWaitToolName(name);
      tools.set(
        name,
        adaptCodingAgentTool(registered.definition, modelRuntime, cwd, connection, {
          replay,
          fillImages,
          fillKnowledge,
          nested: nestedRead,
          deferred: deferredTool,
          parkingWait: parkingWaitTool,
        }),
      );
      if (nestedRead) nested.add(name);
      else nested.delete(name);
      if (deferredTool) deferred.add(name);
      if (writeName) writes.set(name, registered.definition);
    }
  }
  return {
    extension: defineExtension({ name: "qdash", namespace: QDASH_TOOL_NAMESPACE, tools: [...tools.values()] }),
    writeTools: new QDashWriteTools(writes, modelRuntime, cwd, connection),
    nestedTools: [...nested],
    deferredTools: [...deferred],
  };
}
