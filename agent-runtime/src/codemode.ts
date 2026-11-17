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
 * present_results' classifier: it runs only while a tool named as its caller
 * is executing and is that call's parent. A script's parent is the `codemode`
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
  ToolTask,
  wrapSection,
  wrapTool,
  type Agent,
  type Extension,
  type ToolExecutionResult,
  type ToolHookCall,
  type TaskId,
  type ToolRegistration,
} from "@earendil-works/pi-durable";
import { CODEMODE_TOOL_NAME, createCodemodeExtension } from "@earendil-works/pi-durable/codemode";
import { createToolSearchExtension, TOOL_SEARCH_TOOL_NAME } from "@earendil-works/pi-durable/tool-search";

export { CODEMODE_TOOL_NAME, TOOL_SEARCH_TOOL_NAME };

/** Heap of one script's VM. */
export const CODEMODE_MEMORY_LIMIT_BYTES = 128 * 1024 * 1024;
/** Scripts running at once in this process; each runs in its own worker thread. */
export const MAX_CONCURRENT_SCRIPTS = 8;
/** Deadline of a script that sets none. */
export const DEFAULT_SCRIPT_TIMEOUT_MS = 120_000;
/** Longest deadline a script may set. */
export const MAX_SCRIPT_TIMEOUT_MS = 300_000;
/** Largest `timeout_ms` Code Mode accepts (`setTimeout`'s limit); a larger one is its error to report. */
const CODEMODE_TIMEOUT_LIMIT_MS = 2_147_483_647;
/**
 * Largest value one nested call hands a script, as serialized JSON. Pi
 * journals each nested result until the script ends and its output limits do
 * not bound `structuredOutput`, so a larger response fails the call instead.
 */
export const MAX_NESTED_DATA_BYTES = 512 * 1024;

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

/**
 * The script source with a bounded deadline: a script without one gets the
 * default, and a longer one is cut to the maximum. A malformed options line,
 * or a `timeout_ms` Code Mode would reject, is left for Code Mode to report.
 */
export function withScriptDeadline(source: string): string {
  const newline = source.indexOf("\n");
  const first = (newline === -1 ? source : source.slice(0, newline)).replace(/\r$/, "");
  const trimmed = first.trimStart();
  if (!trimmed.startsWith(CODEMODE_OPTIONS_PREFIX)) {
    return `${CODEMODE_OPTIONS_PREFIX} ${JSON.stringify({ timeout_ms: DEFAULT_SCRIPT_TIMEOUT_MS })}\n${source}`;
  }
  let options: unknown;
  try {
    options = JSON.parse(trimmed.slice(CODEMODE_OPTIONS_PREFIX.length).trim());
  } catch {
    return source;
  }
  if (typeof options !== "object" || options === null || Array.isArray(options)) return source;
  let timeout: number;
  if (!Object.hasOwn(options, "timeout_ms")) {
    timeout = DEFAULT_SCRIPT_TIMEOUT_MS;
  } else {
    const requested = (options as { timeout_ms: unknown }).timeout_ms;
    // Code Mode rejects any other value with its own message.
    const valid =
      typeof requested === "number" &&
      Number.isSafeInteger(requested) &&
      requested > 0 &&
      requested <= CODEMODE_TIMEOUT_LIMIT_MS;
    if (!valid) return source;
    timeout = Math.min(requested, MAX_SCRIPT_TIMEOUT_MS);
  }
  const rest = newline === -1 ? "" : source.slice(newline);
  return `${CODEMODE_OPTIONS_PREFIX} ${JSON.stringify({ ...options, timeout_ms: timeout })}${rest}`;
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

/** What the model reads when a script tried a tool it may not call. */
export function nestedBlockMessage(name: string): string {
  return `${name} cannot be called from a code mode script: scripts may only call QDash's read-only tools. Call ${name} directly instead; write tools then ask the user for approval.`;
}

/** What the model reads when it called a deferred tool it had not loaded. */
export function deferredRetryMessage(name: string): string {
  return `${name} was not loaded yet, so it did not run. It is loaded now: call ${name} again with the same arguments. Next time, load such tools first with ${TOOL_SEARCH_TOOL_NAME}.`;
}

/** What a script reads when a nested call returned more data than it may receive. */
export function nestedDataTooLargeMessage(name: string, bytes: number): string {
  return `${name} returned ${bytes} bytes of data, more than the ${MAX_NESTED_DATA_BYTES} bytes a script may receive from one call. Narrow the request (a chip, qubit, task, time range, or limit) or split it into several calls.`;
}

/**
 * A nested call's result as the script and the journal keep it: without
 * `details`, which only the chat's rendering reads and which pi-qdash fills
 * with the same data again, and failed when its data is too large.
 */
function boundNestedResult(call: ToolHookCall, result: ToolExecutionResult): ToolExecutionResult {
  const { details: _details, ...rest } = result;
  if (rest.isError || rest.structuredOutput === undefined) return rest;
  const bytes = Buffer.byteLength(JSON.stringify(rest.structuredOutput) ?? "", "utf8");
  if (bytes <= MAX_NESTED_DATA_BYTES) return rest;
  const { structuredOutput: _dropped, ...withoutData } = rest;
  const message = nestedDataTooLargeMessage(call.name, bytes);
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
 * The chat's tool policy: hooks that let a nested call run only for a tool in
 * `nestedTools` or an internal tool whose parent is one of its callers, and
 * that load a deferred tool the model called before loading it.
 *
 * A nested call names only its parent's task, so the policy wraps each caller
 * to note its task while it executes. The note lives in this process; a
 * caller resumed after a restart notes itself again before it can make a
 * nested call, and a call it cannot match is blocked.
 */
export function toolPolicyExtension(options: ToolPolicy): Extension {
  const nested = new Set(options.nestedTools);
  const deferred = new Set(options.deferredTools);
  const internal = new Map(Object.entries(options.internalCalls ?? {}).map(([name, callers]) => [name, new Set(callers)]));
  const callers = new Set([...internal.values()].flatMap((names) => [...names]));
  /** Task of each caller call executing now, with the caller's name. */
  const executing = new Map<TaskId, { tool: string; count: number }>();
  const track = (tool: ToolRegistration): ToolRegistration => ({
    ...tool,
    execute: async (args, api, context) => {
      const entry = executing.get(api.taskId) ?? { tool: tool.name, count: 0 };
      entry.count += 1;
      executing.set(api.taskId, entry);
      try {
        return await tool.execute(args as never, api, context);
      } finally {
        entry.count -= 1;
        if (entry.count === 0) executing.delete(api.taskId);
      }
    },
  });
  const allowed = (call: ToolHookCall): boolean => {
    if (call.parent === undefined || nested.has(call.name)) return true;
    const parent = executing.get(call.parent.taskId);
    return parent !== undefined && internal.get(call.name)?.has(parent.tool) === true;
  };
  return defineExtension({
    name: "qdash-tool-policy",
    wraps: [...callers].map((name) => wrapTool({ name } as ToolRegistration, track)),
    hooks: [
      hook(ToolTask, {
        beforeTool: (call: ToolHookCall) => {
          if (allowed(call)) return undefined;
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

/** System prompt guideline for `codemode`. */
export const CODEMODE_GUIDELINE = [
  "- Use `codemode` when a question needs many read-only QDash calls or more data than you want to read: write a short JavaScript script that calls the tools as `await tools.qdash_list_chips({})`, filters or aggregates the results, and prints only what you need with `text(...)`. Only the printed output reaches you. In a script, QDash tools resolve to their response data as JSON, not their text answer; print a small sample first when you do not know its shape. Scripts can call only QDash's read-only tools; call write tools, figures, charts, and other tools directly. Use direct tool calls for one or two lookups.",
].join("\n");

/**
 * System prompt guideline for deferred tools; null when there are none.
 * Tools the tool guide already names (`listed`) are marked there, so only the
 * others are listed here.
 */
export function deferredToolsGuideline(
  names: readonly string[],
  listed: ReadonlySet<string> = new Set(),
): string | null {
  if (names.length === 0) return null;
  const marked = names.some((name) => listed.has(name));
  const others = names.filter((name) => !listed.has(name)).sort();
  return [
    `Deferred tools are not offered until you load them: call \`${TOOL_SEARCH_TOOL_NAME}\` with the tool name or what you need, then call the loaded tool in your next step. Load every tool you need with one search when you can. \`codemode\` scripts can call the read-only ones without loading them.`,
    ...(marked ? ["Tools marked * in the tool guide are deferred."] : []),
    ...(others.length ? [`${marked ? "Other deferred tools" : "Deferred tools"}: ${others.join(", ")}`] : []),
  ].join("\n");
}
