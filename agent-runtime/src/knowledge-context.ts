/**
 * Host-supplied task knowledge for evaluation tools.
 *
 * `qcal_evaluate` declares a `knowledge` parameter next to `task_name`. The
 * model only has to name the task; the runtime fetches QDash's review guide for
 * it (expected result, review questions, failure patterns, the task's review
 * notes) and passes that text, so the evaluation model reads the plot against
 * the same reference every time instead of against a summary the planner
 * improvised. The planner may still fill `knowledge` itself, which wins.
 */

import type { TSchema } from "typebox";

import type { QDashConnection } from "./auth.ts";

/** Longest reference passed; the review guide of the largest task is ~7k chars. */
export const MAX_KNOWLEDGE_CHARS = 6000;

/** Whether a tool declares both `task_name` and a host-fillable `knowledge`. */
export function acceptsKnowledge(parameters: TSchema): boolean {
  const properties = (parameters as { properties?: Record<string, unknown> }).properties;
  return properties !== undefined && "knowledge" in properties && "task_name" in properties;
}

/** The task the model named, when it did. */
export function requestedTaskName(args: unknown): string | undefined {
  const value = (args as { task_name?: unknown } | null)?.task_name;
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Whether the model passed reference text of its own. */
export function hasKnowledge(args: unknown): boolean {
  const value = (args as { knowledge?: unknown } | null)?.knowledge;
  return typeof value === "string" && value.trim().length > 0;
}

/** The model's arguments with the host's reference filled in. */
export function withKnowledge<T extends object>(args: T, knowledge: string | undefined): T {
  if (knowledge === undefined) return args;
  return { ...args, knowledge };
}

/** The slice of QDash's task knowledge response the reference is taken from. */
export interface TaskKnowledgeLike {
  review_prompt_text?: string;
  prompt_text?: string;
}

/**
 * The reference text for one task: QDash's review guide, which the retired
 * automatic review read, or the full knowledge prompt when the task has no
 * review guide. Cut to `MAX_KNOWLEDGE_CHARS` at a line break.
 */
export function renderKnowledge(knowledge: TaskKnowledgeLike, limit = MAX_KNOWLEDGE_CHARS): string | undefined {
  const text = (knowledge.review_prompt_text?.trim() || knowledge.prompt_text?.trim()) ?? "";
  if (!text) return undefined;
  if (text.length <= limit) return text;
  const cut = text.lastIndexOf("\n", limit);
  return `${text.slice(0, cut > limit / 2 ? cut : limit).trimEnd()}\n[reference truncated]`;
}

/**
 * Fetch QDash's knowledge for a task as the user who submitted the turn.
 * A task without knowledge, or an unreachable API, yields nothing: the
 * evaluation then runs on the planner's context alone, as before.
 */
export async function fetchTaskKnowledge(
  connection: Pick<QDashConnection, "auth" | "baseUrl">,
  taskName: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<string | undefined> {
  const url = `${connection.baseUrl}/tasks/${encodeURIComponent(taskName)}/knowledge`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${connection.auth.accessToken}`,
    Accept: "application/json",
  };
  if (connection.auth.projectId) headers["X-Project-Id"] = connection.auth.projectId;
  try {
    const response = await fetchImpl(url, { headers, signal });
    if (!response.ok) {
      if (response.status !== 404) {
        console.warn(`[agent-runtime] task knowledge for ${taskName}: HTTP ${response.status}`);
      }
      return undefined;
    }
    return renderKnowledge((await response.json()) as TaskKnowledgeLike);
  } catch (error) {
    if (signal?.aborted) throw error;
    console.warn(
      `[agent-runtime] task knowledge for ${taskName}: ${error instanceof Error ? error.message : String(error)}`,
    );
    return undefined;
  }
}
