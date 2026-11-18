import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { extractToolRouting, investigationPolicyBullets } from "./qdash-guidance.js";

/**
 * pi CLI integration of the shared QDash guidance (qdash-guidance.ts).
 *
 * The guidance goes into one named system prompt section that is set again
 * before every run. pi keeps its own prompt, the user's `--system-prompt`,
 * `--append-system-prompt` and context files around it, and patches the model
 * only when the section text changes, so repeated runs do not accumulate
 * copies. The routing guide follows the tools selected for the run.
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

/**
 * The guidance section for a run with `availableTools`, or null when no
 * QDash tool is available. `skillMarkdown` is the `qdash` skill, or null when
 * it cannot be read; the policy still applies without a routing guide.
 */
export function buildQDashGuidanceSection(
  availableTools: readonly string[],
  skillMarkdown: string | null,
): string | null {
  if (!availableTools.some((name) => name.startsWith("qdash_"))) return null;
  const routing = skillMarkdown ? extractToolRouting(skillMarkdown, availableTools) : null;
  return [
    "When a request involves QDash data, follow these rules alongside the instructions above.",
    "",
    "Investigation and evidence:",
    ...investigationPolicyBullets(),
    ...(routing ? ["", "QDash tool routing:", routing] : []),
  ].join("\n");
}

/** Set, replace, or remove the guidance section in `options` for the tools it selects. */
export function applyQDashGuidance(options: GuidancePromptOptions, skillMarkdown: string | null): void {
  const section = buildQDashGuidanceSection(declaredTools(options), skillMarkdown);
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
    applyQDashGuidance(event.systemPromptOptions, skill());
  });
}
