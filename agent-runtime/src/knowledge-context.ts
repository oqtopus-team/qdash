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

import type { TSchema } from "typebox";

import type { QDashConnection } from "./auth.ts";

/** Longest fallback reference passed when the API serves no structured one. */
export const MAX_KNOWLEDGE_CHARS = 6000;

/** Family-specific parts of the question templates, as pi-qcaleval takes them. */
export interface Criteria {
  /** Q3 "Explain:" bullets. */
  guidance?: string[];
  /** Q5 schema: parameter name to its type or description. */
  parameters?: Record<string, string>;
  /** Q6 decision criteria: status code to criterion, SUCCESS first. */
  statuses?: Record<string, string>;
  /** Q6 suggested range format. */
  range_format?: string;
}

/** What the host passes as the reference: the background text and the criteria. */
export interface Reference {
  knowledge: string;
  criteria?: Criteria;
}

function properties(parameters: TSchema): Record<string, unknown> | undefined {
  return (parameters as { properties?: Record<string, unknown> }).properties;
}

/** Whether a tool declares both `task_name` and a host-fillable `knowledge`. */
export function acceptsKnowledge(parameters: TSchema): boolean {
  const props = properties(parameters);
  return props !== undefined && "knowledge" in props && "task_name" in props;
}

/** Whether a tool takes the structured `criteria` next to the background. */
export function acceptsCriteria(parameters: TSchema): boolean {
  const props = properties(parameters);
  return props !== undefined && "criteria" in props;
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

/**
 * The model's arguments with the host's reference filled in: the background
 * as `knowledge`, and the criteria when the tool declares them.
 */
export function withKnowledge<T extends object>(
  args: T,
  reference: Reference | undefined,
  includeCriteria = true,
): T {
  if (reference === undefined) return args;
  const criteria = includeCriteria ? compactCriteria(reference.criteria) : undefined;
  return { ...args, knowledge: reference.knowledge, ...(criteria ? { criteria } : {}) };
}

/** The reference the model passed itself, for the record when the host filled none. */
export function referenceOf(args: unknown): Reference | undefined {
  const a = args as { knowledge?: unknown; criteria?: unknown } | null;
  if (typeof a?.knowledge !== "string" || !a.knowledge.trim()) return undefined;
  const criteria =
    a.criteria && typeof a.criteria === "object" && !Array.isArray(a.criteria)
      ? compactCriteria(a.criteria as Criteria)
      : undefined;
  return { knowledge: a.knowledge, ...(criteria ? { criteria } : {}) };
}

/** The text a reference is identified by (hashed and measured for the record). */
export function referenceIdentity(reference: Reference): string {
  return `${reference.knowledge}\n${JSON.stringify(reference.criteria ?? {})}`;
}

/** Whether a tool can take host-supplied labeled examples next to `task_name`. */
export function acceptsExamples(parameters: TSchema): boolean {
  const props = properties(parameters);
  return props !== undefined && "examples" in props && "task_name" in props;
}

/** Whether the model asked for the host's labeled examples (`use_examples: true`). */
export function wantsExamples(args: unknown): boolean {
  return (args as { use_examples?: unknown } | null)?.use_examples === true;
}

/** Whether the model passed examples of its own. */
export function hasExamples(args: unknown): boolean {
  const value = (args as { examples?: unknown } | null)?.examples;
  return Array.isArray(value) && value.length > 0;
}

/** The model's arguments with the host's examples filled in. */
export function withExamples<T extends object>(args: T, examples: LabeledExample[] | undefined): T {
  if (examples === undefined || examples.length === 0) return args;
  return { ...args, examples: examples.map(toolExample) };
}

/**
 * One expert-labeled example plot of a task, with its identity for the
 * record and the labels pi-qcaleval shows per question: the analysis (Q3),
 * the extracted parameters (Q5), the status and suggested range (Q6).
 */
export interface LabeledExample {
  id: string;
  title: string;
  outcome: string;
  status: string;
  suggested_range: string;
  /** JSON text of the extracted parameters; empty when the example has none. */
  parameters: string;
  /** The expert's analysis of the figure(s). */
  analysis: string;
  images: Array<{ data: string; mimeType: string }>;
  /** Each image's path in the knowledge repository, in the same order, for the record. */
  paths: string[];
}

/** The example as pi-qcaleval takes it: figures and the labels it has, nothing of its identity. */
export interface ToolExample {
  images: Array<{ data: string; mimeType: string }>;
  scenario?: string;
  analysis?: string;
  parameters?: Record<string, unknown> | string;
  status?: string;
  suggested_range?: string;
}

export function toolExample(example: LabeledExample): ToolExample {
  const parameters = parseParameters(example.parameters);
  return {
    images: example.images,
    ...(example.title ? { scenario: example.title } : {}),
    ...(example.analysis ? { analysis: example.analysis } : {}),
    ...(parameters !== undefined ? { parameters } : {}),
    ...(example.status ? { status: example.status } : {}),
    ...(example.suggested_range ? { suggested_range: example.suggested_range } : {}),
  };
}

/** The example's parameters as an object when the text is a JSON object, else as the text. */
function parseParameters(text: string): Record<string, unknown> | string | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // Not JSON: the text is passed as written.
  }
  return trimmed;
}

/** The slice of QDash's task knowledge response the reference and examples are taken from. */
export interface TaskKnowledgeLike {
  prompt_text?: string;
  reference?: {
    background?: string;
    guidance?: string[];
    parameters?: Record<string, string>;
    statuses?: Record<string, string>;
    range_format?: string | null;
  };
  examples?: Array<{
    id?: string;
    title?: string;
    outcome?: string;
    status?: string;
    suggested_range?: string;
    parameters?: string;
    diagnosis?: string;
    figures?: Array<{ base64_data?: string; mime_type?: string; path?: string }>;
  }>;
}

/** Most labeled examples, and figures among them, passed for one evaluation. */
export const MAX_EXAMPLES = 6;
export const MAX_EXAMPLE_FIGURES = 6;

/**
 * The reference for one task from QDash's knowledge response: the structured
 * reference when the API serves one, else the full prompt text cut to
 * `MAX_KNOWLEDGE_CHARS` at a line break, with no criteria.
 */
export function renderReference(knowledge: TaskKnowledgeLike): Reference | undefined {
  const background = knowledge.reference?.background?.trim();
  if (background) {
    const criteria = compactCriteria({
      guidance: knowledge.reference?.guidance,
      parameters: knowledge.reference?.parameters,
      statuses: knowledge.reference?.statuses,
      range_format: knowledge.reference?.range_format ?? undefined,
    });
    return { knowledge: background, ...(criteria ? { criteria } : {}) };
  }
  const text = renderKnowledge(knowledge);
  return text ? { knowledge: text } : undefined;
}

/** The criteria with empty members dropped; undefined when nothing is left. */
export function compactCriteria(criteria: Criteria | undefined): Criteria | undefined {
  if (!criteria) return undefined;
  const result: Criteria = {};
  const guidance = (criteria.guidance ?? []).filter((line) => typeof line === "string" && line.trim());
  if (guidance.length > 0) result.guidance = guidance;
  const parameters = stringRecord(criteria.parameters);
  if (parameters) result.parameters = parameters;
  const statuses = stringRecord(criteria.statuses);
  if (statuses) result.statuses = statuses;
  if (typeof criteria.range_format === "string" && criteria.range_format.trim()) {
    result.range_format = criteria.range_format;
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

function stringRecord(value: unknown): Record<string, string> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const entries = Object.entries(value as Record<string, unknown>).filter(
    (entry): entry is [string, string] => typeof entry[1] === "string" && entry[0].trim().length > 0,
  );
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

/**
 * The fallback reference text: the full knowledge prompt, cut to
 * `MAX_KNOWLEDGE_CHARS` at a line break.
 */
export function renderKnowledge(knowledge: TaskKnowledgeLike, limit = MAX_KNOWLEDGE_CHARS): string | undefined {
  const text = knowledge.prompt_text?.trim() ?? "";
  if (!text) return undefined;
  if (text.length <= limit) return text;
  const cut = text.lastIndexOf("\n", limit);
  return `${text.slice(0, cut > limit / 2 ? cut : limit).trimEnd()}\n[reference truncated]`;
}

/**
 * The labeled examples of a task from QDash's knowledge response, in the
 * repository's order: each one's figures with the labels an expert validated.
 * As in QCalEval's few-shot layout, one example stands for each status, so a
 * second example with the same status is left out; examples without a status
 * are kept for the analysis demonstration. Examples without a figure, or
 * without any label, are left out.
 */
export function examplesOf(
  knowledge: TaskKnowledgeLike,
  max = MAX_EXAMPLES,
  maxFigures = MAX_EXAMPLE_FIGURES,
): LabeledExample[] {
  const examples: LabeledExample[] = [];
  const statuses = new Set<string>();
  let figureCount = 0;
  for (const example of knowledge.examples ?? []) {
    if (examples.length >= max) break;
    const figures = (example.figures ?? []).filter(
      (figure) => typeof figure.base64_data === "string" && figure.base64_data.length > 0,
    );
    const images = figures.map((figure) => ({
      data: figure.base64_data as string,
      mimeType: figure.mime_type || "image/png",
    }));
    const analysis = example.diagnosis?.trim() ?? "";
    const status = example.status?.trim() ?? "";
    const parameters = example.parameters?.trim() ?? "";
    if (images.length === 0 || (!analysis && !status && !parameters)) continue;
    if (status) {
      if (statuses.has(status)) continue;
      statuses.add(status);
    }
    if (figureCount + images.length > maxFigures) break;
    figureCount += images.length;
    examples.push({
      id: example.id ?? "",
      title: example.title ?? "",
      outcome: example.outcome ?? "",
      status,
      suggested_range: example.suggested_range?.trim() ?? "",
      parameters,
      analysis,
      images,
      paths: figures.map((figure) => figure.path ?? ""),
    });
  }
  return examples;
}

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
  const knowledge = await fetchKnowledgeJson(connection, taskName, signal, fetchImpl);
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
  const knowledge = await fetchKnowledgeJson(connection, taskName, signal, fetchImpl);
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

async function fetchKnowledgeJson(
  connection: Pick<QDashConnection, "auth" | "baseUrl">,
  taskName: string,
  signal: AbortSignal | undefined,
  fetchImpl: typeof fetch,
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
