import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import {
  CODEMODE_TOOL_NAME,
  deferredToolsGuideline,
  extractToolRouting,
  investigationPolicyBullets,
  markDeferredTools,
  QDASH_SCRIPT_GUIDELINE,
  TOOL_SEARCH_TOOL_NAME,
  toolRoutingNames,
} from "./qdash-guidance.js";

/**
 * pi CLI integration of the shared QDash guidance (qdash-guidance.ts).
 *
 * The guidance goes into one named system prompt section that is set again
 * before every run. pi keeps its own prompt, the user's `--system-prompt`,
 * `--append-system-prompt` and context files around it, and patches the model
 * only when the section text changes, so repeated runs do not accumulate
 * copies. The routing guide follows the tools selected for the run.
 *
 * When pi's `codemode` or `tool_search` tool is active, the section also
 * gives the QDash advice QDash chat gives for them: how scripts receive QDash
 * data, and which QDash tools are deferred (marked in the routing guide and
 * loadable with `tool_search`).
 */

/** Name of the system prompt section; pi wraps it in a tag of the same name. */
export const QDASH_GUIDANCE_SECTION = "qdash_guidance";

/** The `qdash` skill shipped next to this extension. */
export const BUNDLED_QDASH_SKILL_PATH = fileURLToPath(new URL("../../skills/qdash/SKILL.md", import.meta.url));

/** The prompt inputs the hook reads and changes; a subset of pi's BuildSystemPromptOptions. */
export interface GuidancePromptOptions {
  selectedTools?: string[];
  hiddenTools?: string[];
  sections?: Record<string, string>;
}

/** Tools the model can call directly in this run. */
function declaredTools(options: GuidancePromptOptions): string[] {
  const hidden = new Set(options.hiddenTools ?? []);
  return (options.selectedTools ?? []).filter((name) => !hidden.has(name));
}

/** What the run offers beyond its declared tools. */
export interface GuidanceOrchestration {
  /** QDash tools registered as deferred and not declared yet; listed only while `tool_search` is declared. */
  deferredTools?: readonly string[];
}

/**
 * The guidance section for a run with `availableTools` (the declared tools),
 * or null when no QDash tool is available. `skillMarkdown` is the `qdash`
 * skill, or null when it cannot be read; the policy still applies without a
 * routing guide.
 */
export function buildQDashGuidanceSection(
  availableTools: readonly string[],
  skillMarkdown: string | null,
  orchestration: GuidanceOrchestration = {},
): string | null {
  const loader = availableTools.includes(TOOL_SEARCH_TOOL_NAME);
  const deferred = loader ? [...(orchestration.deferredTools ?? [])] : [];
  const reachable = [...availableTools, ...deferred];
  if (!reachable.some((name) => name.startsWith("qdash_"))) return null;
  const guide = skillMarkdown ? extractToolRouting(skillMarkdown, reachable) : null;
  const routing = guide ? markDeferredTools(guide, deferred) : null;
  const scripts = availableTools.includes(CODEMODE_TOOL_NAME) && availableTools.some((name) => name.startsWith("qdash_"));
  const deferredRule = deferredToolsGuideline(
    deferred.filter((name) => name.startsWith("qdash_")),
    toolRoutingNames(routing),
  );
  const orchestrationRules = [...(scripts ? [QDASH_SCRIPT_GUIDELINE] : []), ...(deferredRule ? [deferredRule] : [])];
  return [
    "When a request involves QDash data, follow these rules alongside the instructions above.",
    "",
    "Investigation and evidence:",
    ...investigationPolicyBullets(),
    ...(routing ? ["", "QDash tool routing:", routing] : []),
    ...(orchestrationRules.length ? ["", "QDash scripts and tool loading:", ...orchestrationRules] : []),
  ].join("\n");
}

/** Set, replace, or remove the guidance section in `options` for the tools it selects. */
export function applyQDashGuidance(
  options: GuidancePromptOptions,
  skillMarkdown: string | null,
  orchestration: GuidanceOrchestration = {},
): void {
  const declared = declaredTools(options);
  const deferred = (orchestration.deferredTools ?? []).filter((name) => !declared.includes(name));
  const section = buildQDashGuidanceSection(declared, skillMarkdown, { deferredTools: deferred });
  if (section) {
    options.sections ??= {};
    options.sections[QDASH_GUIDANCE_SECTION] = section;
  } else if (options.sections) {
    delete options.sections[QDASH_GUIDANCE_SECTION];
  }
}

/** Read `path` once; later calls return the same text, or null when it is unreadable. */
function cachedSkill(path: string): () => string | null {
  let loaded = false;
  let text: string | null = null;
  return () => {
    if (!loaded) {
      loaded = true;
      try {
        text = readFileSync(path, "utf8");
      } catch {
        text = null;
      }
    }
    return text;
  };
}

/** Register the hook that keeps the guidance section current before each run. */
export function installQDashGuidance(pi: ExtensionAPI, skillPath: string = BUNDLED_QDASH_SKILL_PATH): void {
  const skill = cachedSkill(skillPath);
  pi.on("before_agent_start", (event) => {
    const deferredTools = (pi.getAllTools?.() ?? [])
      .filter((tool) => tool.exposure === "deferred" && tool.name.startsWith("qdash_"))
      .map((tool) => tool.name);
    applyQDashGuidance(event.systemPromptOptions, skill(), { deferredTools });
  });
}
