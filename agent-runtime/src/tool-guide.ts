/**
 * Tool routing guide taken from the pi-qdash `qdash` skill.
 *
 * The skill's "Preferred tools" section says which tool answers which kind of
 * question. pi-qdash owns the section and its filtering (qdash-guidance.ts),
 * which the pi CLI also uses; here the guide goes straight into the system
 * prompt, because a small local model picks better among sixty tools when the
 * guide is in front of it. The rest of the skill (cooldown rules, timeseries
 * comparison) stays behind `read_skill`.
 *
 * Only tools the runtime actually exposes are kept: the allowlist and the
 * write-tools switch drop some pi-qdash tools. Deferred tools, which the
 * model loads with `tool_search` before calling, are marked `*` so the model
 * searches first instead of failing one call per tool. The pi CLI marks them
 * the same way when `tool_search` is active (pi-qdash guidance-hook.ts).
 */

import {
  DEFERRED_MARK,
  extractToolRouting,
  markDeferredTools,
  QDASH_GUIDANCE_SKILL,
  toolRoutingNames,
} from "@oqtopus-team/pi-qdash/extensions/lib/qdash-guidance.ts";

export const TOOL_GUIDE_SKILL = QDASH_GUIDANCE_SKILL;

/** Marker after a deferred tool's name in the guide. */
export { DEFERRED_MARK };

/** The tool names a guide mentions. */
export const toolGuideNames = toolRoutingNames;

/**
 * The "Preferred tools" section of the skill, limited to `enabledTools`, with
 * `deferredTools` marked, or null.
 */
export function extractToolGuide(
  skillMarkdown: string,
  enabledTools: Iterable<string>,
  deferredTools: Iterable<string> = [],
): string | null {
  const guide = extractToolRouting(skillMarkdown, enabledTools);
  return guide ? markDeferredTools(guide, deferredTools) : null;
}
