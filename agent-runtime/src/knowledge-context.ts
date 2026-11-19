/**
 * Host-supplied task knowledge for evaluation tools.
 *
 * `qcal_evaluate` declares `knowledge` and `criteria` parameters next to
 * `task_name`. The model only has to name the task; the runtime fetches
 * QDash's reference for it (the experiment background, the status criteria,
 * the parameters to extract) and passes it, so the evaluation model reads the
 * plot against the same reference every time instead of against a summary
 * the planner improvised. The planner may still fill `knowledge` itself,
 * which wins.
 *
 * The reference follows the QCalEval layout: a short background ("this is a
 * ... experiment; a successful result ...") and, per question, the
 * family-specific criteria the question templates are filled with.
 */

import type { QDashConnection } from "./auth.ts";
import {
  examplesOf,
  renderReference,
  type LabeledExample,
  type Reference,
  type TaskKnowledgeLike,
} from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";

/** The reference and example rules are shared with the pi CLI (pi-qdash extensions/lib/qcal-hydration.ts). */
export {
  acceptsCriteria,
  acceptsExamples,
  acceptsKnowledge,
  compactCriteria,
  examplesOf,
  hasExamples,
  hasKnowledge,
  MAX_EXAMPLE_FIGURES,
  MAX_EXAMPLES,
  MAX_KNOWLEDGE_CHARS,
  referenceIdentity,
  referenceOf,
  renderKnowledge,
  renderReference,
  requestedTaskName,
  toolExample,
  wantsExamples,
  withExamples,
  withKnowledge,
} from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";
export type {
  Criteria,
  LabeledExample,
  Reference,
  TaskKnowledgeLike,
  ToolExample,
} from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";

/**
 * Fetch QDash's reference for a task as the user who submitted the turn.
 * A task without knowledge, or an unreachable API, yields nothing: the
 * evaluation then runs on the planner's context alone, as before.
 */
export async function fetchTaskKnowledge(
  connection: Pick<QDashConnection, "auth" | "baseUrl">,
  taskName: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<Reference | undefined> {
  const knowledge = await fetchTaskKnowledgeResponse(connection, taskName, signal, fetchImpl);
  return knowledge ? renderReference(knowledge) : undefined;
}

/**
 * The labeled examples QDash holds for a task, as the user. A task without
 * examples, or an unreachable API, yields none: the evaluation then runs
 * zero-shot, and the record shows no examples.
 */
export async function fetchTaskExamples(
  connection: Pick<QDashConnection, "auth" | "baseUrl">,
  taskName: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<LabeledExample[]> {
  const knowledge = await fetchTaskKnowledgeResponse(connection, taskName, signal, fetchImpl);
  return knowledge ? examplesOf(knowledge) : [];
}

/**
 * An uploaded knowledge draft, as the user, in the shape of a task's
 * knowledge response. A draft is asked for by id, so one the API does not
 * serve is an error rather than an evaluation without knowledge.
 */
export async function fetchKnowledgeDraft(
  connection: Pick<QDashConnection, "auth" | "baseUrl">,
  draftId: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<TaskKnowledgeLike> {
  const url = `${connection.baseUrl}/evaluations/knowledge-drafts/${encodeURIComponent(draftId)}/knowledge`;
  const response = await fetchImpl(url, { headers: knowledgeHeaders(connection), signal });
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = `: ${body.detail}`;
    } catch {
      // The status says enough.
    }
    throw new Error(`HTTP ${response.status}${detail}`);
  }
  return (await response.json()) as TaskKnowledgeLike;
}

function knowledgeHeaders(connection: Pick<QDashConnection, "auth">): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${connection.auth.accessToken}`,
    Accept: "application/json",
  };
  if (connection.auth.projectId) headers["X-Project-Id"] = connection.auth.projectId;
  return headers;
}

/**
 * QDash's knowledge response for a task, as the user; undefined when the task
 * has none or the API cannot be reached. Rejects when `signal` aborts.
 */
export async function fetchTaskKnowledgeResponse(
  connection: Pick<QDashConnection, "auth" | "baseUrl">,
  taskName: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<TaskKnowledgeLike | undefined> {
  const url = `${connection.baseUrl}/tasks/${encodeURIComponent(taskName)}/knowledge`;
  try {
    const response = await fetchImpl(url, { headers: knowledgeHeaders(connection), signal });
    if (!response.ok) {
      if (response.status !== 404) {
        console.warn(`[agent-runtime] task knowledge for ${taskName}: HTTP ${response.status}`);
      }
      return undefined;
    }
    return (await response.json()) as TaskKnowledgeLike;
  } catch (error) {
    if (signal?.aborted) throw error;
    console.warn(
      `[agent-runtime] task knowledge for ${taskName}: ${error instanceof Error ? error.message : String(error)}`,
    );
    return undefined;
  }
}
