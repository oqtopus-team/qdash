import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import { createOwnershipCheck, type SourceInfoLike } from "./extension-identity.js";
import { CODEMODE_TOOL_NAME, TOOL_SEARCH_TOOL_NAME } from "./qdash-guidance.js";
import {
  boundScriptData,
  isDeferredTool,
  isNestedReadTool,
  isReviewedWriteTool,
  nestedBlockMessage,
  QDASH_TOOL_NAMESPACE,
  scriptDataOf,
  withScriptDeadline,
} from "./tool-policy.js";
import {
  branchSelection,
  leaveHandoff,
  SELECTION_ENTRY,
  settingsSelection,
  takeHandoff,
  type ManagedTool,
  type ToolSelection,
} from "./tool-selection.js";

/**
 * pi CLI enforcement of the shared QDash tool policy (tool-policy.ts) with
 * pi's native `codemode` and `tool_search` tools, so a standalone pi session
 * batches and discovers QDash tools the way QDash chat does:
 *
 * - Audited read tools declare an output schema, and a script calling one
 *   gets its redacted response data as JSON, bounded per call.
 * - Every other QDash tool is model-only (unreachable from scripts) or, when
 *   deferred, blocked from scripts by the `tool_call` hook. Writes keep the
 *   write gate's confirmation, which a script cannot pass.
 * - While pi-qdash is loaded, a `codemode` script may call other tools only
 *   when they declare `readOnlyHint` and are not destructive; `bash`, `write`,
 *   `edit`, and unannotated tools are called directly.
 * - Deferred tools use `exposure: "deferred"`, and pi-qdash activates
 *   `tool_search` for them like pi's MCP extension does. Without an active
 *   `tool_search` tool they are registered again as direct tools.
 * - Scripts get the same default and maximum deadline as in QDash chat.
 * - A QDash tool name keeps script access only while pi runs pi-qdash's own
 *   registration for it (extension-identity.ts); another extension's tool
 *   with an audited name is blocked from scripts.
 *
 * pi-qdash activates `codemode` and `tool_search` for a new user and keeps a
 * selection the user made across reload, new sessions, forks, and resumes
 * (tool-selection.ts). `PI_QDASH_CODEMODE=off` keeps pi-qdash from
 * activating `codemode` by default; the script policy still applies when the
 * user enables it.
 */

/** Environment variable that stops pi-qdash from activating `codemode`. */
export const CODEMODE_ENV = "PI_QDASH_CODEMODE";

/** What a script receives from an audited read tool. */
export const SCRIPT_DATA_SCHEMA = Type.Unknown({
  description:
    "The tool's redacted QDash response data as JSON: the data its text answer summarizes, not truncated.",
});

/** pi built-ins that run commands or change files; never callable from a script while pi-qdash is loaded. */
const SIDE_EFFECT_BUILTINS = new Set(["bash", "powershell", "write", "edit"]);

type Exposure = "direct" | "model-only" | "codemode" | "deferred" | "hidden";

/** The fields of a tool definition the policy reads and sets. */
export interface PolicyToolDefinition {
  name: string;
  parameters?: unknown;
  exposure?: Exposure;
  outputSchema?: unknown;
  /** pi's `ToolNamespace`: the group code mode lists the tool under. */
  namespace?: { name: string; description?: string; instructions?: string; aliases?: readonly string[] };
  annotations?: { readOnlyHint?: boolean; destructiveHint?: boolean; idempotentHint?: boolean; openWorldHint?: boolean };
}

/** A registered tool as `pi.getAllTools()` reports it. */
interface ToolInfoLike {
  name: string;
  exposure?: string;
  annotations?: PolicyToolDefinition["annotations"];
  parameters?: unknown;
  sourceInfo?: SourceInfoLike;
  reachesTools?: unknown;
}

/**
 * A pi-qdash tool definition with the shared policy applied: deferred tools
 * become `deferred`; audited reads declare the script data schema and a
 * read-only hint; every other QDash tool becomes `model-only` so scripts
 * cannot reach it. Every QDash tool joins the shared `qdash` namespace
 * (`QDASH_TOOL_NAMESPACE`), as in QDash chat. An exposure or namespace the
 * tool already states is kept.
 */
export function applyToolPolicy<T extends PolicyToolDefinition>(definition: T): T {
  const name = definition.name;
  if (!name.startsWith("qdash_")) return definition;
  const read = isNestedReadTool(name);
  const exposure: Exposure | undefined =
    definition.exposure ?? (isDeferredTool(name) ? "deferred" : read ? undefined : "model-only");
  return {
    ...definition,
    namespace: definition.namespace ?? QDASH_TOOL_NAMESPACE,
    ...(exposure ? { exposure } : {}),
    ...(read
      ? {
          outputSchema: definition.outputSchema ?? SCRIPT_DATA_SCHEMA,
          annotations: { readOnlyHint: true, destructiveHint: false, ...definition.annotations },
        }
      : {}),
    ...(isReviewedWriteTool(name)
      ? { annotations: { readOnlyHint: false, destructiveHint: true, ...definition.annotations } }
      : {}),
  };
}

/** Why a nested call may not run, or undefined when it may. */
export function nestedCallBlock(
  name: string,
  options: {
    /** Tool name of the call that made this one; undefined when unknown. */
    parent?: string;
    /** Whether `name` resolves to pi-qdash's own registration. */
    ownTool: boolean;
    annotations?: PolicyToolDefinition["annotations"];
  },
): string | undefined {
  if (name.startsWith("qdash_") || isReviewedWriteTool(name)) {
    return isNestedReadTool(name) && options.ownTool ? undefined : nestedBlockMessage(name);
  }
  // Another extension's orchestrating tool is not ours to police; a script is.
  if (options.parent !== undefined && options.parent !== CODEMODE_TOOL_NAME) return undefined;
  const hints = options.annotations;
  if (!SIDE_EFFECT_BUILTINS.has(name) && hints?.readOnlyHint === true && hints.destructiveHint !== true) {
    return undefined;
  }
  return `${name} cannot be called from a code mode script while pi-qdash is loaded: scripts may only call QDash's read-only tools and tools that declare themselves read-only. Call ${name} directly instead.`;
}

/** Most top-level calls remembered to name the parent of a nested call. */
const PARENT_MEMORY = 256;

/** pi's tools whose activation pi-qdash manages, in activation order. */
const MANAGED_TOOLS: readonly ManagedTool[] = [TOOL_SEARCH_TOOL_NAME as ManagedTool, CODEMODE_TOOL_NAME as ManagedTool];

export interface QDashToolPolicyOptions {
  /**
   * The extension entry pi loads pi-qdash from, as `import.meta.url` of
   * `extensions/qdash.ts`. Script access to QDash tools requires pi's
   * registry to report this file as their source; without it scripts reach
   * no QDash tool.
   */
  entry?: string | URL;
  env?: NodeJS.ProcessEnv;
}

type SessionContextLike = {
  sessionManager?: {
    getBranch?: () => unknown[];
    getSessionFile?: () => string | undefined;
  };
};

/**
 * Install the policy hooks and return the `pi` that pi-qdash registers its
 * tools through, so each registration gets the policy applied.
 */
export function installQDashToolPolicy(pi: ExtensionAPI, options: QDashToolPolicyOptions = {}): ExtensionAPI {
  const env = options.env ?? process.env;
  const registered = new Map<string, PolicyToolDefinition>();
  const register = pi.registerTool.bind(pi) as (definition: PolicyToolDefinition) => void;
  const ownership = createOwnershipCheck(options.entry);
  const allTools = (): ToolInfoLike[] => {
    try {
      return (pi.getAllTools?.() ?? []) as ToolInfoLike[];
    } catch {
      return [];
    }
  };
  /** pi's registration for `name`, and whether it is the definition pi-qdash registered. */
  const info = (name: string) => {
    const tool = allTools().find((candidate) => candidate.name === name);
    const definition = registered.get(name);
    return { tool, ownTool: definition !== undefined && ownership.owns(tool, definition.parameters) };
  };

  const parents = new Map<string, string>();
  const parentOf = (id: string): string | undefined => parents.get(id) ?? parents.get(id.split("/")[0] ?? id);

  pi.on("tool_call", (event) => {
    if (event.parentToolCallId === undefined) {
      parents.delete(event.toolCallId);
      parents.set(event.toolCallId, event.toolName);
      if (parents.size > PARENT_MEMORY) parents.delete(parents.keys().next().value as string);
      if (event.toolName === CODEMODE_TOOL_NAME) {
        const input = event.input as { code?: unknown };
        if (typeof input.code === "string") input.code = withScriptDeadline(input.code);
      }
      return undefined;
    }
    const { tool, ownTool } = info(event.toolName);
    const reason = nestedCallBlock(event.toolName, {
      parent: parentOf(event.parentToolCallId),
      ownTool,
      annotations: tool?.annotations,
    });
    return reason ? { block: true, reason } : undefined;
  });

  pi.on("tool_result", (event) => {
    if (event.parentToolCallId === undefined) {
      // Its nested calls have all finished; the id may be reused later.
      parents.delete(event.toolCallId);
      return undefined;
    }
    if (event.isError || !isNestedReadTool(event.toolName)) return undefined;
    if (!info(event.toolName).ownTool) return undefined;
    const bounded = boundScriptData(event.toolName, scriptDataOf(event));
    if (bounded.ok) return { structuredContent: bounded.value as never };
    // New content without structured content: the script gets the error text.
    return { content: [{ type: "text" as const, text: bounded.message }], isError: true };
  });

  pi.on("agent_end", () => {
    parents.clear();
  });

  /** Managed tools this session can activate: registered, able to reach tools, and not hidden. */
  const loaders = (tools: ToolInfoLike[]): ManagedTool[] =>
    MANAGED_TOOLS.filter((name) =>
      tools.some((tool) => tool.name === name && Boolean(tool.reachesTools) && tool.exposure !== "hidden"),
    );
  const deferredDefinitions = () => [...registered.values()].filter((definition) => definition.exposure === "deferred");
  const currentSelection = (names: readonly ManagedTool[]): ToolSelection => {
    const active = new Set(pi.getActiveTools());
    return Object.fromEntries(names.map((name) => [name, active.has(name)])) as ToolSelection;
  };
  const branchOf = (ctx: SessionContextLike) => {
    try {
      return (ctx.sessionManager?.getBranch?.() ?? []) as Parameters<typeof branchSelection>[0];
    } catch {
      return [];
    }
  };
  /** Record the selection on the branch when it differs from what the branch records. */
  const recordSelection = (ctx: SessionContextLike, names: readonly ManagedTool[]) => {
    if (names.length === 0) return undefined;
    const current = currentSelection(names);
    const { selection } = branchSelection(branchOf(ctx), MANAGED_TOOLS);
    if (names.some((name) => selection[name] !== current[name])) {
      try {
        pi.appendEntry(SELECTION_ENTRY, current);
      } catch {
        // A session that no longer accepts entries keeps its last record.
      }
    }
    return current;
  };

  pi.on("session_start", (event, ctx) => {
    parents.clear();
    const tools = allTools();
    if (tools.length === 0) return;
    const available = loaders(tools);
    const deferred = deferredDefinitions();
    let active = pi.getActiveTools();
    // pi keeps the active tools across a reload.
    if (event.reason !== "reload" && available.length > 0) {
      const context = ctx as SessionContextLike;
      const branch = branchSelection(branchOf(context), MANAGED_TOOLS);
      const handoff = takeHandoff({
        reason: event.reason,
        sessionFile: context.sessionManager?.getSessionFile?.(),
        sessionManager: (context.sessionManager ?? context) as object,
      });
      const settings = settingsSelection(safeSettings(pi)?.defaultTools, MANAGED_TOOLS);
      const byDefault: ToolSelection = {
        [TOOL_SEARCH_TOOL_NAME]: deferred.length > 0,
        [CODEMODE_TOOL_NAME]: (env[CODEMODE_ENV] ?? "").toLowerCase() !== "off",
      };
      const next = new Set(active);
      for (const name of available) {
        // pi already restored what its own loadout records say.
        if (branch.fromPi.has(name)) continue;
        const wanted = branch.selection[name] ?? handoff?.[name] ?? settings[name] ?? byDefault[name];
        if (wanted) next.add(name);
        else next.delete(name);
      }
      const changed = next.size !== active.length || active.some((name) => !next.has(name));
      if (changed) {
        pi.setActiveTools([...active.filter((name) => next.has(name)), ...[...next].filter((name) => !active.includes(name))]);
        active = pi.getActiveTools();
      }
    }
    // Deferred tools need an active tool_search; otherwise offer them directly rather than not at all.
    if (deferred.length > 0 && !(available.includes(TOOL_SEARCH_TOOL_NAME as ManagedTool) && active.includes(TOOL_SEARCH_TOOL_NAME))) {
      for (const definition of deferred) register({ ...definition, exposure: "direct" });
    }
  });

  pi.on("agent_start", (_event, ctx) => {
    recordSelection(ctx as SessionContextLike, loaders(allTools()));
    return undefined;
  });

  pi.on("session_shutdown", (event, ctx) => {
    parents.clear();
    const context = ctx as SessionContextLike;
    const selection = recordSelection(context, loaders(allTools()));
    if (selection && (event.reason === "new" || event.reason === "fork")) {
      leaveHandoff({
        selection,
        reason: event.reason,
        targetSessionFile: event.targetSessionFile,
        sessionManager: (context.sessionManager ?? context) as object,
      });
    }
  });

  return new Proxy(pi, {
    get(target, property) {
      if (property === "registerTool") {
        return (definition: PolicyToolDefinition) => {
          const applied = applyToolPolicy(definition);
          registered.set(applied.name, applied);
          register(applied);
        };
      }
      const value = Reflect.get(target, property) as unknown;
      return typeof value === "function" ? (value as (...args: unknown[]) => unknown).bind(target) : value;
    },
  });
}

/** pi's effective settings, or undefined when this pi cannot report them. */
function safeSettings(pi: ExtensionAPI): { defaultTools?: unknown } | undefined {
  try {
    return (pi as { getSettings?: () => { defaultTools?: unknown } }).getSettings?.();
  } catch {
    return undefined;
  }
}
