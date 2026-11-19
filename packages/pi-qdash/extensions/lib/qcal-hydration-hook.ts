import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import {
  acceptsImages,
  acceptsKnowledge,
  hydrateEvaluationArgs,
  type FigureMessage,
  type HydrationSummary,
  type TaskKnowledgeLike,
} from "./qcal-hydration.js";
import { isEvaluationTool } from "./tool-policy.js";

/**
 * pi CLI integration of the shared evaluation hydration (qcal-hydration.ts).
 *
 * When pi-qcaleval is installed next to pi-qdash, a `qcal_evaluate` call the
 * model makes is filled before it runs, the way QDash chat fills it: the
 * newest figure of the requested task from the session's active branch, and
 * the reference, criteria, and (on request) labeled examples from QDash's
 * task knowledge, in one request as the configured QDash user. pi-qcaleval
 * stays independent: it only reads its arguments, and without pi-qdash it
 * runs on what the model passed.
 *
 * The tool result's `details.hydration` records what was filled (counts and
 * sources, no bytes or text), the same summary the runtime test compares.
 */

/** Newest messages of the active branch searched for a figure. */
export const FIGURE_SCAN_MESSAGES = 200;

export interface QcalHydrationDependencies {
  /** QDash's knowledge response for a task as the configured user; undefined when there is none. Rejects on abort. */
  loadTaskKnowledge(taskName: string, signal?: AbortSignal): Promise<TaskKnowledgeLike | undefined>;
}

type EntryLike = { type?: string; message?: FigureMessage & { role?: string } };
type SessionLike = { buildContextEntries?: () => EntryLike[]; getBranch?: () => EntryLike[] };

/** The active branch's messages as the model sees them, newest first. */
export function* branchMessagesNewestFirst(session: SessionLike, limit = FIGURE_SCAN_MESSAGES): Generator<FigureMessage> {
  const entries = session.buildContextEntries?.() ?? session.getBranch?.() ?? [];
  let seen = 0;
  for (let index = entries.length - 1; index >= 0 && seen < limit; index -= 1) {
    const entry = entries[index];
    if (entry?.type !== "message" || !entry.message) continue;
    seen += 1;
    yield entry.message;
  }
}

/** Replace `target`'s own properties with `source`'s, keeping the object pi executes with. */
function replaceInPlace(target: Record<string, unknown>, source: Record<string, unknown>): void {
  for (const key of Object.keys(target)) if (!(key in source)) delete target[key];
  Object.assign(target, source);
}

export function installQcalHydration(pi: ExtensionAPI, deps: QcalHydrationDependencies): void {
  const summaries = new Map<string, HydrationSummary>();

  // A summary belongs to one call; a call id reused later, or in another session, never inherits it.
  const forget = () => summaries.clear();
  pi.on("session_start", forget);
  pi.on("session_shutdown", forget);
  pi.on("agent_end", forget);

  pi.on("tool_call", async (event, ctx) => {
    summaries.delete(event.toolCallId);
    // A script cannot call an evaluation tool (script-policy.ts); only the model's calls are filled.
    if (event.parentToolCallId !== undefined || !isEvaluationTool(event.toolName)) return undefined;
    const parameters = pi.getAllTools?.().find((tool) => tool.name === event.toolName)?.parameters;
    if (!acceptsImages(parameters) && !acceptsKnowledge(parameters)) return undefined;
    const input = event.input as Record<string, unknown>;
    const hydrated = await hydrateEvaluationArgs({ ...input }, {
      parameters,
      messages: () => branchMessagesNewestFirst(ctx.sessionManager as unknown as SessionLike),
      loadKnowledge: deps.loadTaskKnowledge,
      ...(ctx.signal ? { signal: ctx.signal } : {}),
    });
    replaceInPlace(input, hydrated.args as Record<string, unknown>);
    summaries.set(event.toolCallId, hydrated.summary);
    return undefined;
  });

  pi.on("tool_result", (event) => {
    const summary = summaries.get(event.toolCallId);
    if (!summary) return undefined;
    summaries.delete(event.toolCallId);
    const details = event.details && typeof event.details === "object" ? (event.details as Record<string, unknown>) : {};
    return { details: { ...details, hydration: summary } };
  });
}
