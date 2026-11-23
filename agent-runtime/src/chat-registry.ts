/**
 * The registry one chat session runs with: QDash's tools, the agent's own
 * tools and prompt, the user's preferences, the open page, the workspace
 * tools, and Code Mode with the tool policy. SharedRuntime builds the parts
 * that are the same for every chat once; this assembles them per session, so
 * tests can run the same assembly.
 */

import type { ModelRuntime, ToolDefinition as CodingAgentTool } from "@earendil-works/pi-coding-agent";
import {
  createRegistry,
  defineExtension,
  section,
  type Extension,
  type ToolRegistration,
} from "@earendil-works/pi-durable";
import { createCodingTools } from "@earendil-works/pi-durable/tools";

import type { QDashConnection } from "./auth.ts";
import { buildCodemodeExtensions, createCodemodeSandbox, modelOnlyTools, type InternalCalls } from "./codemode.ts";
import { buildQDashExtension, type QDashWriteTools } from "./durable-tools.ts";
import { buildPageContextSection, buildProposeCodeEditTool, editorOf, PAGE_SECTION, type PageContext } from "./page-context.ts";
import { buildUserInstructionsSection } from "./prompt.ts";

/** Section key of the user's preferences in the system prompt. */
export const USER_PREFERENCES_SECTION = "user-preferences";

/**
 * The agent's own tools with QDash's system prompt. They render in the chat
 * or end the turn, so they are model-only, except an internal tool that
 * already names its callers (present_results' classifier).
 */
export function buildAgentExtension(systemPrompt: string, tools: readonly ToolRegistration[]): Extension {
  return modelOnlyTools(
    defineExtension({
      name: "qdash-agent",
      sections: [section("qdash-agent", () => systemPrompt, { tag: false })],
      tools: [...tools],
    }),
  );
}

/** What every chat registry is built from. */
export interface ChatRegistryParts {
  extensions: ReadonlyArray<{ path?: string; tools?: Map<string, { definition: CodingAgentTool }> }>;
  modelRuntime: ModelRuntime;
  workDir: string;
  /** Bundled roots trusted as a whole, as `buildQDashExtension` takes them. */
  extensionPaths: readonly string[];
  /** From `buildAgentExtension`. */
  agent: Extension;
  /** Internal tools of `agent` with the tools that may call them. */
  internalCalls: InternalCalls;
  /** The workspace's read/write/edit/bash, when there is a workspace. */
  codingTools: boolean;
  /** From `buildCompactionExtension`: the summarizer chats compact with. */
  compaction?: Extension;
}

export interface ChatRegistry {
  registry: ReturnType<typeof createRegistry>;
  writeTools: QDashWriteTools;
  /** Resources the registry's tools hold for the session, such as the Code Mode sandbox. */
  close(): Promise<void>;
}

/** The registry of one chat session with the signed-in user's `connection`. */
export function buildChatRegistry(
  parts: ChatRegistryParts,
  connection: QDashConnection,
  userInstructions?: string,
  pageContext?: PageContext,
): ChatRegistry {
  const registry = createRegistry();
  const qdash = buildQDashExtension(
    parts.extensions,
    parts.modelRuntime,
    parts.workDir,
    connection,
    parts.extensionPaths,
  );
  registry.install(qdash.extension);
  registry.install(parts.agent);
  if (parts.compaction) registry.install(parts.compaction);
  // After QDash's own rules, so they come first and the user's preferences
  // read as adjustments to them.
  const preferences = buildUserInstructionsSection(userInstructions);
  if (preferences) {
    registry.install(
      defineExtension({
        name: "qdash-user-preferences",
        sections: [section(USER_PREFERENCES_SECTION, () => preferences)],
      }),
    );
  }
  // The page the user has open, after their preferences; on the Workflow editor,
  // the metric script editor or an editable dashboard it brings the edit
  // tool, which proposes and never saves.
  const pageSection = buildPageContextSection(pageContext);
  const editor = editorOf(pageContext);
  if (pageSection) {
    registry.install(
      modelOnlyTools(
        defineExtension({
          name: PAGE_SECTION,
          sections: [section(PAGE_SECTION, () => pageSection)],
          tools: editor && pageContext ? [buildProposeCodeEditTool(editor, pageContext.path)] : [],
        }),
      ),
    );
  }
  // The workspace's read/write/edit/bash, which run in the agent-exec
  // container through the environment `openSession` gives the harness.
  // The model calls them; Code Mode scripts do not.
  if (parts.codingTools) registry.install(modelOnlyTools(createCodingTools()));
  // Code Mode, tool_search, and the hooks that keep scripts to the audited
  // read-only tools and internal tools to their callers. One sandbox per
  // open session.
  const sandbox = createCodemodeSandbox();
  const policy = {
    nestedTools: qdash.nestedTools,
    deferredTools: qdash.deferredTools,
    internalCalls: parts.internalCalls,
  };
  for (const extension of buildCodemodeExtensions(sandbox, policy)) registry.install(extension);
  return { registry, writeTools: qdash.writeTools, close: () => sandbox.close() };
}
