/**
 * Code Mode and deferred tools for the chat agent.
 *
 * Code Mode (`@earendil-works/pi-durable/codemode`) gives the model a
 * `codemode` tool: it writes JavaScript that calls tools as
 * `await tools.<name>(args)` in a QuickJS sandbox, and only the script's
 * output reaches the model. QDash uses it to batch and filter read-only data.
 * Each call a script makes is a nested durable tool call, journaled so a
 * restarted script resumes without repeating finished calls.
 *
 * The sandbox holds no credentials: a script reaches QDash only through the
 * tools, which run in this process with the signed-in user's connection.
 * Which tools a script may call is decided three times. Every tool states its
 * `callers` (see `buildQDashExtension` and `modelOnly`); a script is shown
 * and given only the audited read-only tools; and a hook blocks every nested
 * call outside that set, so a tool added later without a decision cannot run
 * from a script. Write tools in particular stay model-only: their approval
 * card only exists for a call the model made.
 *
 * The one other kind of nested call is an internal tool, such as
 * present_results' classifier: it runs only as a nested call whose parent is
 * a call to a tool named as its caller. A script's parent is the `codemode`
 * call, never such a caller, so a script cannot reach it.
 *
 * Deferred tools (`deferred: true`) are not offered to the model until it
 * loads them with `tool_search` (`@earendil-works/pi-durable/tool-search`),
 * which records them in the conversation's `modelTools`, so they stay offered
 * on that branch. pi-ai sends a changed tool set the way each provider accepts
 * it (mid-conversation additions where supported, else the whole set with
 * the request), so it does not depend on a model's support for dynamic tools.
 * A model that calls a deferred tool by name without loading it gets it
 * loaded for its next request and is told to call again.
 */

import type { Context } from "@earendil-works/chord/context";
import {
  CODEMODE_OPTIONS_PREFIX,
  CodemodeSandbox,
  loadQuickJSWasm,
  type CodemodeWasmModule,
} from "@earendil-works/pi-codemode";
import {
  defineExtension,
  hook,
  LiveDoc,
  ToolTask,
  wrapSection,
  type Agent,
  type Extension,
  type ToolExecutionResult,
  type HookApi,
  type ToolHookCall,
  type ToolRegistration,
} from "@earendil-works/pi-durable";
import { CODEMODE_TOOL_NAME, createCodemodeExtension } from "@earendil-works/pi-durable/codemode";
import { createToolSearchExtension, TOOL_SEARCH_TOOL_NAME } from "@earendil-works/pi-durable/tool-search";
import {
  deferredToolsGuideline,
  QDASH_SCRIPT_GUIDELINE,
} from "@oqtopus-team/pi-qdash/extensions/lib/qdash-guidance.ts";
import {
  boundScriptData,
  DEFAULT_SCRIPT_TIMEOUT_MS,
  MAX_NESTED_DATA_BYTES,
  MAX_SCRIPT_TIMEOUT_MS,
  withScriptDeadline as sharedScriptDeadline,
  nestedBlockMessage,
  nestedDataTooLargeMessage,
} from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";

export { CODEMODE_TOOL_NAME, TOOL_SEARCH_TOOL_NAME };

/** Heap of one script's VM. */
export const CODEMODE_MEMORY_LIMIT_BYTES = 128 * 1024 * 1024;
/** Scripts running at once in this process; each runs in its own worker thread. */
export const MAX_CONCURRENT_SCRIPTS = 8;
/** Script deadlines, shared with the pi CLI. */
export { DEFAULT_SCRIPT_TIMEOUT_MS, MAX_SCRIPT_TIMEOUT_MS };
/**
 * Largest value one nested call hands a script, as serialized JSON (shared
 * with the pi CLI). Pi journals each nested result until the script ends and
 * its output limits do not bound `structuredOutput`, so a larger response
 * fails the call instead.
 */
export { MAX_NESTED_DATA_BYTES };

let wasm: Promise<CodemodeWasmModule> | undefined;

/** QuickJS, compiled once per process and shared by every session's sandbox. */
function quickjs(): Promise<CodemodeWasmModule> {
  wasm ??= loadQuickJSWasm().catch((error: unknown) => {
    // A failed load is retried by the next script instead of failing them all.
    wasm = undefined;
    throw error;
  });
  return wasm;
}

let runningScripts = 0;

/** Admit one more script worker, or refuse with a message the model reads. */
function acquireWorker(): () => void {
  if (runningScripts >= MAX_CONCURRENT_SCRIPTS) {
    throw new Error(
      `QDash is already running ${MAX_CONCURRENT_SCRIPTS} code mode scripts; try again shortly or call the tools directly.`,
    );
  }
  runningScripts += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    runningScripts -= 1;
  };
}

/** Scripts running now, for tests and logs. */
export function runningScriptCount(): number {
  return runningScripts;
}

/**
 * A sandbox for one open session. Close it with the session; a script that
 * was running resumes with the next sandbox the session opens.
 */
export function createCodemodeSandbox(): CodemodeSandbox {
  return new CodemodeSandbox({
    wasm: quickjs(),
    memoryLimitBytes: CODEMODE_MEMORY_LIMIT_BYTES,
    acquireWorker,
  });
}

/** The script source with a bounded deadline (shared with the pi CLI). */
export function withScriptDeadline(source: string): string {
  return sharedScriptDeadline(source, CODEMODE_OPTIONS_PREFIX);
}

/** The same tool, callable by the model only, unless it already says who may call it. */
export function modelOnly<T extends ToolRegistration>(tool: T): T {
  return tool.callers === undefined ? { ...tool, callers: ["model"] } : tool;
}

/** The extension with every tool that does not say who may call it made model-only. */
export function modelOnlyTools(extension: Extension): Extension {
  if (!extension.tools?.length) return extension;
  return { ...extension, tools: extension.tools.map((tool) => modelOnly(tool)) };
}

/** Messages shared with the pi CLI (pi-qdash extensions/lib/tool-policy.ts). */
export { nestedBlockMessage, nestedDataTooLargeMessage };

/** What the model reads when it called a deferred tool it had not loaded. */
export function deferredRetryMessage(name: string): string {
  return `${name} was not loaded yet, so it did not run. It is loaded now: call ${name} again with the same arguments. Next time, load such tools first with ${TOOL_SEARCH_TOOL_NAME}.`;
}

/**
 * A nested call's result as the script and the journal keep it: without
 * `details`, which only the chat's rendering reads and which pi-qdash fills
 * with the same data again, and failed when its data is too large.
 */
function boundNestedResult(call: ToolHookCall, result: ToolExecutionResult): ToolExecutionResult {
  const { details: _details, ...rest } = result;
  if (rest.isError || rest.structuredOutput === undefined) return rest;
  const bounded = boundScriptData(call.name, rest.structuredOutput);
  if (bounded.ok) return rest;
  const { structuredOutput: _dropped, ...withoutData } = rest;
  const message = bounded.message;
  return {
    ...withoutData,
    isError: true,
    output: [{ type: "text", text: message }],
    diagnostics: [...(rest.diagnostics ?? []), { severity: "error", code: "nested_data_too_large", message }],
  };
}

function isUnavailable(result: ToolExecutionResult): boolean {
  return (result.diagnostics ?? []).some((diagnostic) => diagnostic.code === "tool_unavailable");
}

/** Internal tools, each with the tools that may call it through `executeTool()`. */
export type InternalCalls = Readonly<Record<string, readonly string[]>>;

/** What decides which nested calls run. */
export interface ToolPolicy {
  /** Tools a Code Mode script may call: the audited read-only ones. */
  nestedTools: Iterable<string>;
  /** Tools a model call to which, before they are loaded, loads them. */
  deferredTools: Iterable<string>;
  /** Internal tools that only their named callers may call; never a script. */
  internalCalls?: InternalCalls;
}

/**
 * The tool that made nested call `call`, read from the conversation's
 * committed live state: the slot of the parent's tool task, model-issued or
 * nested. The Harness writes these slots, so a script cannot name its own
 * parent, and they stay while the parent is live, also while it is parked or
 * after a restart, so the answer does not depend on the parent's code running
 * in this process when the nested call starts.
 */
async function parentToolName(call: ToolHookCall, api: HookApi, context: Context): Promise<string | undefined> {
  const parent = call.parent?.taskId;
  if (parent === undefined) return undefined;
  const live = await api.snapshot(LiveDoc, api.conversationId, context);
  return (
    live?.tools?.find((slot) => slot.taskId === parent)?.name ??
    live?.nestedTools?.find((slot) => slot.taskId === parent)?.name
  );
}

/**
 * The chat's tool policy: hooks that let a nested call run only for a tool in
 * `nestedTools` or an internal tool whose parent is one of its callers, and
 * that load a deferred tool the model called before loading it.
 *
 * A nested call names only its parent's task; the policy reads which tool
 * that task runs from the Harness's live slots (`parentToolName`). That holds
 * for a caller that parks (pi-durable 1.6.1 `{ kind: "sleep" }` or `{ kind: "wait" }`) and for
 * a nested call it started with `wait: false`, whose check runs after the
 * caller's `execute()` returned. A call whose parent it cannot find is blocked.
 */
export function toolPolicyExtension(options: ToolPolicy): Extension {
  const nested = new Set(options.nestedTools);
  const deferred = new Set(options.deferredTools);
  const internal = new Map(Object.entries(options.internalCalls ?? {}).map(([name, callers]) => [name, new Set(callers)]));
  const allowed = async (call: ToolHookCall, api: HookApi, context: Context): Promise<boolean> => {
    if (call.parent === undefined || nested.has(call.name)) return true;
    const callers = internal.get(call.name);
    if (callers === undefined) return false;
    const parent = await parentToolName(call, api, context);
    return parent !== undefined && callers.has(parent);
  };
  return defineExtension({
    name: "qdash-tool-policy",
    hooks: [
      hook(ToolTask, {
        beforeTool: async (call: ToolHookCall, api: HookApi, context: Context) => {
          if (await allowed(call, api, context)) return undefined;
          console.warn(`[agent-runtime] blocked nested call to ${call.name} from ${call.parent?.callId}`);
          return { block: nestedBlockMessage(call.name) };
        },
        afterTool: (call: ToolHookCall, result: ToolExecutionResult) => {
          if (call.parent !== undefined) {
            const bounded = boundNestedResult(call, result);
            // The script sees the error; the runtime log keeps a trace of it too.
            if (bounded.isError) {
              const why = (bounded.diagnostics ?? [])
                .filter((diagnostic) => diagnostic.severity === "error")
                .map((diagnostic) => diagnostic.code ?? diagnostic.message)
                .join(", ");
              console.warn(
                `[agent-runtime] nested call ${call.name} from ${call.parent.callId} failed${why ? ` (${why})` : ""}`,
              );
            }
            return bounded;
          }
          if (!deferred.has(call.name) || !isUnavailable(result)) return undefined;
          return {
            ...result,
            output: [{ type: "text", text: deferredRetryMessage(call.name) }],
            control: { addTools: [call.name] },
          };
        },
      }),
    ],
  });
}

/** The agent as a script sees it: only the tools scripts may call. */
function forScripts(agent: Agent, scriptTools: ReadonlySet<string>): Agent {
  return { ...agent, callable: agent.callable.filter((tool) => scriptTools.has(tool.name)) };
}

/**
 * The Code Mode tool with every script's deadline bounded, and with only the
 * tools in `scriptTools` in the script's `tools`.
 */
function boundedCodemode(tool: ToolRegistration, scriptTools: ReadonlySet<string>): ToolRegistration {
  return {
    ...tool,
    execute: (args: unknown, api, context: Context) => {
      const code = (args as { code?: unknown }).code;
      const bounded = typeof code === "string" ? { ...(args as object), code: withScriptDeadline(code) } : args;
      const scriptApi = { ...api, agent: async (inner: Context) => forScripts(await api.agent(inner), scriptTools) };
      return tool.execute(bounded as never, scriptApi, context);
    },
  };
}

/**
 * The extensions that bring Code Mode, `tool_search`, and the tool policy.
 * `models: false`: scripts get no `models.*`, so they cannot start model
 * calls of their own. Scripts are shown and given only `nestedTools`; the
 * policy hook enforces the same set for every nested call they make.
 */
export function buildCodemodeExtensions(sandbox: CodemodeSandbox, policy: ToolPolicy): Extension[] {
  const scriptTools: ReadonlySet<string> = new Set(policy.nestedTools);
  const codemode = createCodemodeExtension({ sandbox, models: false });
  return [
    {
      ...codemode,
      tools: (codemode.tools ?? []).map((tool) =>
        tool.name === CODEMODE_TOOL_NAME ? boundedCodemode(tool, scriptTools) : modelOnly(tool),
      ),
      // The prompt's list of tools scripts can call, cut to the same set.
      wraps: [
        ...(codemode.wraps ?? []),
        wrapSection(CODEMODE_TOOL_NAME, (inner) => ({
          ...inner,
          render: (input, context) => inner.render({ ...input, agent: forScripts(input.agent, scriptTools) }, context),
        })),
      ],
    },
    createToolSearchExtension(),
    toolPolicyExtension({ ...policy, nestedTools: scriptTools }),
  ];
}

/**
 * System prompt guidelines for `codemode` and deferred tools, shared with the
 * pi CLI (pi-qdash extensions/lib/qdash-guidance.ts).
 */
export const CODEMODE_GUIDELINE = QDASH_SCRIPT_GUIDELINE;
export { deferredToolsGuideline };
