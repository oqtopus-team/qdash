/**
 * Host-neutral evidence hydration for calibration-evaluation tools such as
 * pi-qcaleval's `qcal_evaluate`, shared by the standalone pi CLI
 * (qcal-hydration-hook.ts) and the QDash Agent Runtime
 * (agent-runtime/src/durable-tools.ts).
 *
 * An evaluation tool declares `images`, `knowledge`, `criteria`, and
 * `examples` parameters next to `task_name`. A model cannot be trusted to copy
 * image bytes or a long reference into its arguments, so the host fills them:
 *
 * - `images` from the newest figure in the conversation that belongs to the
 *   requested task, never from a figure of another task;
 * - `knowledge` and `criteria` from QDash's task knowledge for `task_name`;
 * - `examples` from the same knowledge response, when the model sets
 *   `use_examples: true`.
 *
 * The evaluation tool itself stays independent of QDash: it only reads its
 * arguments. Each host supplies the conversation's messages and a loader for
 * the knowledge response; this module decides what goes into the call.
 *
 * The module has no runtime dependencies so either host can import it.
 */

// ---------------------------------------------------------------------------
// Figures
// ---------------------------------------------------------------------------

export interface ImageBlock {
  type: "image";
  data: string;
  mimeType: string;
}

/** The wire shape of one image in a tool's `images` argument. */
export interface ImageArgument {
  data: string;
  mimeType: string;
}

/** A conversation message as both hosts store it: content blocks and the tool's details. */
export interface FigureMessage {
  content?: unknown;
  details?: unknown;
}

/** The figures chosen for an evaluation and, when a QDash tool fetched them, their task result. */
export interface SelectedFigures {
  images: ImageBlock[];
  /** `details.taskId` of the tool result that carried the figures. */
  taskId?: string;
  /** The task name that result recorded. */
  taskName?: string;
}

/** Whether a tool declares an `images` parameter the host may fill. */
export function acceptsImages(parameters: unknown): boolean {
  const props = propertiesOf(parameters);
  return props !== undefined && "images" in props;
}

/** Most figures a tool may ask the host to supply. */
export const MAX_SUPPLIED_IMAGES = 4;

/**
 * How many of the newest figures the tool asked for via `max_images`
 * (default 1); the tool's own limit still applies downstream.
 */
export function requestedImageCount(args: unknown, limit = MAX_SUPPLIED_IMAGES): number {
  const value = (args as { max_images?: unknown } | null)?.max_images;
  if (typeof value !== "number" || !Number.isFinite(value)) return 1;
  return Math.min(Math.max(Math.floor(value), 1), limit);
}

/**
 * Shortest payload accepted as image bytes. A model that invents an `images`
 * argument writes placeholders such as "<image 1>" or "see attached", never a
 * base64 string of a real PNG, whose header alone is longer than this.
 */
const MIN_IMAGE_BASE64_LENGTH = 64;
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

/** Leading bytes of the image formats an evaluation model accepts. */
const IMAGE_SIGNATURES: ReadonlyArray<readonly number[]> = [
  [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], // PNG
  [0xff, 0xd8, 0xff], // JPEG
  [0x47, 0x49, 0x46, 0x38], // GIF8
  [0x52, 0x49, 0x46, 0x46], // RIFF (WebP)
];

const BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** The first bytes of a base64 string, decoded without a Buffer so either host can run it. */
function leadingBytes(base64: string, count: number): number[] {
  const bytes: number[] = [];
  let buffer = 0;
  let bits = 0;
  for (const char of base64.slice(0, Math.ceil((count * 4) / 3) + 4)) {
    const value = BASE64_ALPHABET.indexOf(char);
    if (value === -1) break;
    buffer = (buffer << 6) | value;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((buffer >> bits) & 0xff);
      if (bytes.length === count) break;
    }
  }
  return bytes;
}

/**
 * Whether `data` is base64 of a real PNG, JPEG, GIF, or WebP image. Text a
 * model fabricated (placeholders, a retyped fragment, arbitrary base64) fails
 * the length, alphabet, or file-signature check.
 */
export function isImageData(data: unknown): data is string {
  if (typeof data !== "string" || data.length < MIN_IMAGE_BASE64_LENGTH || !BASE64.test(data)) return false;
  const head = leadingBytes(data, 8);
  return IMAGE_SIGNATURES.some((signature) => signature.every((byte, index) => head[index] === byte));
}

/** Whether the model passed real image bytes of its own for every image. */
export function hasImages(args: unknown): boolean {
  const images = (args as { images?: unknown } | null)?.images;
  if (!Array.isArray(images) || images.length === 0) return false;
  return images.every((image) => isImageData((image as { data?: unknown } | null)?.data));
}

function imageBlocks(content: unknown): ImageBlock[] {
  if (!Array.isArray(content)) return [];
  const out: ImageBlock[] = [];
  for (const block of content) {
    if (
      typeof block === "object" &&
      block !== null &&
      (block as { type?: unknown }).type === "image" &&
      typeof (block as { data?: unknown }).data === "string" &&
      typeof (block as { mimeType?: unknown }).mimeType === "string"
    ) {
      const { data, mimeType } = block as ImageBlock;
      out.push({ type: "image", data, mimeType });
    }
  }
  return out;
}

function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * The task result and task name a figure message records: pi-qdash figure
 * tools set `taskId` and `taskName`, and `qdash_build_qcal_evidence` records
 * the task in its evidence.
 */
export function figureSource(details: unknown): { taskId?: string; taskName?: string } {
  const d = (details ?? {}) as {
    taskId?: unknown;
    taskName?: unknown;
    evidence?: { id?: unknown; task?: { name?: unknown } };
  };
  const taskId = nonEmpty(d.taskId) ?? nonEmpty(d.evidence?.id);
  const taskName = nonEmpty(d.taskName) ?? nonEmpty(d.evidence?.task?.name);
  return { ...(taskId ? { taskId } : {}), ...(taskName ? { taskName } : {}) };
}

function sameTask(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

/**
 * The figures for an evaluation from `messages`, newest first.
 *
 * Without a requested task the newest message that carries images is used.
 * With one, a figure recorded for another task is skipped, and once such a
 * figure was seen only a figure recorded for the requested task is accepted:
 * an older unlabeled figure (an attachment) then is stale too. A message
 * carries figures in order (expected first, measured last), so its last `max`
 * are kept.
 */
export function selectEvaluationFigures(
  messages: Iterable<FigureMessage>,
  options: { max?: number; taskName?: string } = {},
): SelectedFigures {
  const max = options.max ?? 1;
  const requested = options.taskName;
  let skippedOtherTask = false;
  for (const message of messages) {
    const images = imageBlocks(message.content);
    if (images.length === 0) continue;
    const source = figureSource(message.details);
    if (requested) {
      if (source.taskName && !sameTask(source.taskName, requested)) {
        skippedOtherTask = true;
        continue;
      }
      if (!source.taskName && skippedOtherTask) continue;
    }
    return { images: images.slice(-max), ...source };
  }
  return { images: [] };
}

/**
 * The model's arguments with `images` set to the conversation's figures. They
 * replace whatever the model passed: bytes it copied into the call are
 * usually corrupt. Without conversation figures, real image bytes the model
 * passed are kept and anything else is dropped, so the tool reports a missing
 * plot instead of sending junk to its model.
 */
export function withImages<T extends object>(
  args: T,
  images: ReadonlyArray<ImageBlock>,
): T | (T & { images?: ImageArgument[] }) {
  if (images.length === 0) {
    if (hasImages(args) || !("images" in args)) return args;
    const { images: _placeholders, ...rest } = args as T & { images?: unknown };
    return rest as T;
  }
  return { ...args, images: images.map(({ data, mimeType }) => ({ data, mimeType })) };
}

// ---------------------------------------------------------------------------
// Task knowledge
// ---------------------------------------------------------------------------

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

function propertiesOf(parameters: unknown): Record<string, unknown> | undefined {
  return (parameters as { properties?: Record<string, unknown> } | null | undefined)?.properties;
}

/** Whether a tool declares both `task_name` and a host-fillable `knowledge`. */
export function acceptsKnowledge(parameters: unknown): boolean {
  const props = propertiesOf(parameters);
  return props !== undefined && "knowledge" in props && "task_name" in props;
}

/** Whether a tool takes the structured `criteria` next to the background. */
export function acceptsCriteria(parameters: unknown): boolean {
  const props = propertiesOf(parameters);
  return props !== undefined && "criteria" in props;
}

/** Whether a tool can take host-supplied labeled examples next to `task_name`. */
export function acceptsExamples(parameters: unknown): boolean {
  const props = propertiesOf(parameters);
  return props !== undefined && "examples" in props && "task_name" in props;
}

/** The task the model named, when it did. */
export function requestedTaskName(args: unknown): string | undefined {
  return nonEmpty((args as { task_name?: unknown } | null)?.task_name);
}

/** Whether the model passed reference text of its own. */
export function hasKnowledge(args: unknown): boolean {
  return nonEmpty((args as { knowledge?: unknown } | null)?.knowledge) !== undefined;
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
  const supplied = (args as { criteria?: unknown }).criteria;
  const explicit = supplied && typeof supplied === "object" && !Array.isArray(supplied)
    ? compactCriteria(supplied as Criteria)
    : undefined;
  const criteria = includeCriteria && !explicit ? compactCriteria(reference.criteria) : undefined;
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
    // QDash serves these figures; unlike model arguments they are not checked for a file signature.
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

// ---------------------------------------------------------------------------
// One evaluation call
// ---------------------------------------------------------------------------

/** What a host provides to fill one evaluation call. */
export interface EvaluationSources {
  /** The tool's parameter schema; decides which arguments may be filled. */
  parameters: unknown;
  /** Fill `images` from the conversation (default: when the tool declares `images`). */
  fillImages?: boolean;
  /** Fill `knowledge`, `criteria`, and `examples` (default: when the tool declares `knowledge` and `task_name`). */
  fillKnowledge?: boolean;
  /** The conversation's messages, newest first; read only when images are filled. */
  messages(): Iterable<FigureMessage> | Promise<Iterable<FigureMessage>>;
  /**
   * QDash's knowledge response for a task, as the user; undefined when the
   * task has none or QDash cannot be reached. Called at most once per call.
   * Must reject when `signal` aborts.
   */
  loadKnowledge(taskName: string, signal?: AbortSignal): Promise<TaskKnowledgeLike | undefined>;
  signal?: AbortSignal;
}

/** Where the evaluated figures came from. */
export type FigureOrigin = "conversation" | "arguments" | "none";

/** What the host put into an evaluation call, without bytes or text: comparable across hosts. */
export interface HydrationSummary {
  task_name: string | null;
  figure_origin: FigureOrigin;
  figures: number;
  figure_task_id: string | null;
  knowledge: "host" | "arguments" | "none";
  criteria: boolean;
  examples: number;
}

export interface HydratedEvaluation<T> {
  args: T;
  /** Task result the conversation's figures came from, when known. */
  figureTaskId?: string;
  /** The reference the host filled; undefined when it filled none. */
  reference?: Reference;
  /** The labeled examples the host filled. */
  examples?: LabeledExample[];
  summary: HydrationSummary;
}

/**
 * Fill one evaluation call's arguments from the conversation and QDash's task
 * knowledge. The knowledge response is loaded once, for both the reference
 * and the examples. A reference or examples the model passed itself win; the
 * conversation's figures replace bytes the model copied (see `withImages`).
 */
export async function hydrateEvaluationArgs<T extends object>(
  args: T,
  sources: EvaluationSources,
): Promise<HydratedEvaluation<T>> {
  const fillImages = sources.fillImages ?? acceptsImages(sources.parameters);
  const fillKnowledge = sources.fillKnowledge ?? acceptsKnowledge(sources.parameters);
  const taskName = requestedTaskName(args);
  let callArgs: T = args;
  let figures: SelectedFigures = { images: [] };
  if (fillImages) {
    figures = selectEvaluationFigures(await sources.messages(), {
      max: requestedImageCount(args),
      ...(taskName ? { taskName } : {}),
    });
    if (figures.images.length || !hasImages(args)) callArgs = withImages(callArgs, figures.images) as T;
  }
  const needsReference = fillKnowledge && taskName !== undefined && !hasKnowledge(args);
  const needsExamples =
    fillKnowledge && taskName !== undefined && wantsExamples(args) && !hasExamples(args);
  let reference: Reference | undefined;
  let examples: LabeledExample[] | undefined;
  if (taskName && (needsReference || needsExamples)) {
    const knowledge = await sources.loadKnowledge(taskName, sources.signal);
    if (needsReference) {
      reference = knowledge ? renderReference(knowledge) : undefined;
      callArgs = withKnowledge(callArgs, reference, acceptsCriteria(sources.parameters));
      // Record the effective criteria, including an explicit caller override.
      if (reference) reference = referenceOf(callArgs);
    }
    if (needsExamples) {
      examples = knowledge ? examplesOf(knowledge) : [];
      callArgs = withExamples(callArgs, examples);
    }
  }
  const images = (callArgs as { images?: unknown }).images;
  const imageCount = Array.isArray(images) ? images.length : 0;
  const filledCriteria = (callArgs as { criteria?: unknown }).criteria;
  return {
    args: callArgs,
    ...(figures.taskId ? { figureTaskId: figures.taskId } : {}),
    ...(reference ? { reference } : {}),
    ...(examples ? { examples } : {}),
    summary: {
      task_name: taskName ?? null,
      figure_origin: figures.images.length ? "conversation" : imageCount ? "arguments" : "none",
      figures: imageCount,
      figure_task_id: figures.taskId ?? null,
      knowledge: reference ? "host" : hasKnowledge(args) ? "arguments" : "none",
      criteria: filledCriteria !== undefined && filledCriteria !== null,
      examples: examples?.length ?? 0,
    },
  };
}
