/**
 * One calibration evaluation without a planner.
 *
 * The chat path lets the planner decide to summarise a task result
 * (`qdash_build_qcal_evidence`) and judge its figure (`qcal_evaluate`). This
 * module runs exactly those two tools, in that order, for one task result, so
 * a bulk request from the UI or an evaluation loop gets the same evaluation
 * the planner would, minus the planner. The result records what the
 * evaluation model saw (context, reference, figure hashes) and what it
 * answered, so a stored run can be replayed and compared later.
 *
 * Pure orchestration: the tool runner and the knowledge fetch are injected,
 * so the sequence is testable without pi or QDash.
 */

import { createHash } from "node:crypto";

import { compactCriteria, examplesOf, referenceIdentity, renderReference, toolExample } from "./knowledge-context.ts";
import type { LabeledExample, Reference, TaskKnowledgeLike } from "./knowledge-context.ts";
import type { ExtensionPackage } from "./local-extensions.ts";

/** The pi-qdash tool that turns a task result into evidence text plus its figure. */
export const EVIDENCE_TOOL = "qdash_build_qcal_evidence";
/** The pi-qcaleval tool that judges the figure. */
export const EVALUATION_TOOL = "qcal_evaluate";

/** Most figures one evaluation may embed; pi-qcaleval accepts up to four. */
export const MAX_EVALUATION_FIGURES = 4;

export interface EvaluateRequest {
  taskId: string;
  /** A specific question for the evaluation model, on top of the standard diagnosis. */
  question?: string;
  /** Figures of the task result to embed, newest first in pi-qdash's order (default 1). */
  maxFigures?: number;
  /** Show the task's expert-labeled example plots before the figure (in-context examples). */
  withExamples?: boolean;
  /** Read this uploaded knowledge draft instead of the task's shared knowledge. */
  knowledgeDraftId?: string;
}

/** One labeled example the model saw, by identity and figure hashes rather than bytes. */
export interface ExampleRecord {
  id: string;
  title: string;
  outcome: string;
  /** The example's status code, when it carries one (its Q6 label). */
  status?: string;
  /** Each figure's hash, plus its path in the knowledge repository so it can be shown again. */
  figures: Array<FigureRecord & { path?: string }>;
}

/** How the evaluation was reached: the two tools run directly, or a planner turn. */
export type EvaluationMode = "direct" | "planner";

/** What the planner did around the evaluation, when one was in the loop. */
export interface PlannerRecord {
  /** `provider/modelId` of the planner. */
  model: string;
  /** The planner's final answer. */
  answer: string;
  /** Tool names the planner called, in order. */
  tool_calls: string[];
  /** Wall time of the whole planner turn. */
  duration_ms: number;
}

/** A text or image block as pi tools return them. */
export type ToolBlock =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string };

/** The slice of a pi tool result the sequence reads. */
export interface ToolRun {
  content: ReadonlyArray<ToolBlock | { type: string }>;
  details?: unknown;
  isError?: boolean;
  usage?: unknown;
}

export interface EvaluateDeps {
  /** Run one enabled extension tool with the user's QDash connection. */
  runTool(name: string, args: Record<string, unknown>): Promise<ToolRun>;
  /** QDash's reference for a task (background and criteria), as the user; undefined when it has none. */
  fetchKnowledge(taskName: string): Promise<Reference | undefined>;
  /** QDash's labeled examples for a task, as the user; empty when it has none. */
  fetchExamples?(taskName: string): Promise<LabeledExample[]>;
  /** The package that provides the evaluation tool, for the record. */
  evaluator?: ExtensionPackage;
}

export type EvaluationStage = "request" | "knowledge" | "evidence" | "evaluation";

/** A failure of one stage, with the HTTP status the route answers with. */
export class EvaluationError extends Error {
  constructor(
    readonly stage: EvaluationStage,
    message: string,
    readonly status = 502,
  ) {
    super(message);
    this.name = "EvaluationError";
  }
}

export interface FigureRecord {
  sha256: string;
  mime_type: string;
  bytes: number;
  /** Exact bytes for durable, content-addressed storage by QDash. */
  data?: string;
}

export interface EvaluateResult {
  task_id: string;
  mode: EvaluationMode;
  /** The task's name as QDash knows it, when the evidence names it. */
  task_name: string | null;
  target: { kind?: string; id?: string; chip_id?: string } | null;
  /** The context the evaluation model received: the task and its target, without fitted values. */
  context: string;
  figures: FigureRecord[];
  /** The reference the host supplied (background and criteria), by size and hash; the prompt holds the text. */
  knowledge: { chars: number; sha256: string } | null;
  /** The labeled examples shown before the figure; empty for a zero-shot evaluation. */
  examples: ExampleRecord[];
  evaluation: {
    /** `provider/modelId` of the model that judged the plot. */
    model: string | null;
    fallback: boolean;
    /** Every question prompt the model was sent, with [figure] where an image was. */
    prompt: string | null;
    /** The system prompt the model was sent, when the evaluator reports it. */
    system_prompt: string | null;
    diagnosis: Record<string, unknown> | null;
    /** The answer when it was not the requested JSON, or not all of it. */
    raw: string | null;
    /** Each answered question's text as the model returned it, when the evaluator reports them. */
    answers: Record<string, string> | null;
    /** The questions asked, in order, when the evaluator reports them. */
    questions: string[];
    /** Questions the answer lacks, when the evaluator reports them. */
    missing_keys: string[];
    /** Model calls the evaluator made for the answer, when it reports them. */
    attempts: number | null;
    /** Whether decoding was constrained to the diagnosis schema, when the evaluator reports it. */
    structured: boolean | null;
    /** Why the model stopped, when the evaluator reports it. */
    stop_reason: string | null;
    /** Every model call the evaluator made, in order, when it reports them. */
    calls: EvaluationCall[];
    duration_ms: number;
    usage: unknown;
  };
  evaluator: ExtensionPackage | null;
  /** The planner turn, in planner mode. */
  planner: PlannerRecord | null;
}

/** One model call of an evaluation: how long it took and how it ended. */
export interface EvaluationCall {
  /** The question the call asked, when the evaluator asks per question. */
  question?: string;
  duration_ms: number;
  stop_reason: string;
  structured: boolean;
  /** Prompt tokens the model counted, images included, when the evaluator reports them. */
  input_tokens?: number;
  output_tokens?: number;
  missing_keys?: string[];
}

/** The evaluator's call records, kept when they have the expected shape. */
export function callRecords(value: unknown): EvaluationCall[] {
  if (!Array.isArray(value)) return [];
  const calls: EvaluationCall[] = [];
  for (const entry of value) {
    const c = entry as Partial<EvaluationCall> | null;
    if (typeof c?.duration_ms !== "number" || typeof c.stop_reason !== "string") continue;
    calls.push({
      ...(typeof c.question === "string" ? { question: c.question } : {}),
      duration_ms: c.duration_ms,
      stop_reason: c.stop_reason,
      structured: c.structured === true,
      ...(typeof c.input_tokens === "number" ? { input_tokens: c.input_tokens } : {}),
      ...(typeof c.output_tokens === "number" ? { output_tokens: c.output_tokens } : {}),
      ...(Array.isArray(c.missing_keys)
        ? { missing_keys: c.missing_keys.filter((key): key is string => typeof key === "string") }
        : {}),
    });
  }
  return calls;
}

/**
 * What the host put into one `qcal_evaluate` call, recorded on its result as
 * `details.host` by the durable wrapper and built the same way by the direct
 * path, so a planner turn and a direct evaluation leave the same record.
 */
export interface HostRecord {
  context: string;
  question: string | null;
  task_name: string | null;
  figures: FigureRecord[];
  knowledge: { chars: number; sha256: string } | null;
  examples?: ExampleRecord[];
  /** Wall time of the tool call, when the wrapper measured it. */
  duration_ms?: number;
  /** The task result the figures came from, when a tool fetched them. */
  task_id?: string | null;
}

function textOf(content: ReadonlyArray<{ type: string }>): string {
  return content
    .map((block) => {
      const text = (block as { text?: unknown }).text;
      return block.type === "text" && typeof text === "string" ? text : "";
    })
    .filter(Boolean)
    .join("\n")
    .trim();
}

function imagesOf(content: ReadonlyArray<{ type: string }>): Array<{ data: string; mimeType: string }> {
  const images: Array<{ data: string; mimeType: string }> = [];
  for (const block of content) {
    if (block.type !== "image") continue;
    const { data, mimeType } = block as { data?: unknown; mimeType?: unknown };
    if (typeof data === "string" && typeof mimeType === "string") images.push({ data, mimeType });
  }
  return images;
}

function sha256(bytes: Buffer | string): string {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Hash and size of one base64-encoded figure. */
export function figureRecord(image: { data: string; mimeType: string }): FigureRecord {
  const bytes = Buffer.from(image.data, "base64");
  return {
    sha256: sha256(bytes),
    mime_type: image.mimeType,
    bytes: bytes.length,
    data: image.data,
  };
}

function stringField(value: unknown, key: string): string | undefined {
  const field = (value as Record<string, unknown> | null)?.[key];
  return typeof field === "string" && field.trim() ? field : undefined;
}

/** What the evidence tool recorded about the task, from its `details.evidence`. */
export function evidenceSummary(details: unknown): {
  taskName: string | null;
  target: EvaluateResult["target"];
} {
  const evidence = (details as { evidence?: unknown } | null)?.evidence;
  const task = (evidence as { task?: unknown } | null)?.task;
  const target = (evidence as { target?: unknown } | null)?.target;
  const kind = stringField(target, "kind");
  const id = stringField(target, "id");
  const chipId = stringField(target, "chipId");
  return {
    taskName: stringField(task, "name") ?? null,
    target:
      kind || id || chipId
        ? { ...(kind ? { kind } : {}), ...(id ? { id } : {}), ...(chipId ? { chip_id: chipId } : {}) }
        : null,
  };
}

/**
 * The context the evaluation model is given, from the evidence tool's
 * `details.evidence`: the task, its target and status, and the task's own
 * message when it left one. Undefined when the evidence carries no details
 * (an older evidence tool), so the caller falls back to its text.
 */
export function evidenceContext(details: unknown): string | undefined {
  const evidence = (details as { evidence?: unknown } | null)?.evidence;
  if (!evidence || typeof evidence !== "object") return undefined;
  const task = (evidence as { task?: unknown }).task;
  const target = (evidence as { target?: unknown }).target;
  const name = stringField(task, "name");
  if (!name) return undefined;
  const kind = stringField(target, "kind");
  const id = stringField(target, "id");
  const chipId = stringField(target, "chipId");
  const status = stringField(task, "status");
  let line = `Task ${name}`;
  if (id) line += ` on ${kind && kind !== "system" ? `${kind} ${id}` : id}`;
  if (chipId) line += ` (chip ${chipId})`;
  if (status) line += `, status ${status}`;
  line += ".";
  const lines = [line];
  const sweeps = evidenceSweeps(details);
  if (sweeps.length > 0) lines.push(`Sweep: ${sweeps.map(formatSweep).join("; ")}.`);
  const settings = runSettings(evidence, new Set(sweeps.map((sweep) => sweep.name)));
  if (settings.length > 0) lines.push(`Settings: ${settings.join("; ")}.`);
  const notes = (evidence as { notes?: unknown }).notes;
  const message =
    typeof notes === "string" ? notes.split("\n").find((text) => text.startsWith("Task message: ")) : undefined;
  if (message) lines.push(message);
  return lines.join("\n");
}

/** A swept parameter as the evidence tool records it: the axis the plot was taken along. */
export interface EvidenceSweep {
  name: string;
  unit: string;
  spacing: "linear" | "log" | "list";
  start: number;
  stop: number;
  points: number;
  step?: number;
}

/** The sweeps the evidence tool read from the task's run parameters, when it reports them. */
export function evidenceSweeps(details: unknown): EvidenceSweep[] {
  const evidence = (details as { evidence?: { sweeps?: unknown } } | null)?.evidence;
  const sweeps = Array.isArray(evidence?.sweeps) ? evidence.sweeps : [];
  return sweeps.filter(
    (sweep): sweep is EvidenceSweep =>
      typeof (sweep as EvidenceSweep)?.name === "string" &&
      typeof (sweep as EvidenceSweep).start === "number" &&
      typeof (sweep as EvidenceSweep).stop === "number" &&
      typeof (sweep as EvidenceSweep).points === "number",
  );
}

/** A number for the model: up to four significant digits, no trailing zeros. */
function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Number.isInteger(value) && Math.abs(value) < 1e15) return String(value);
  const text = Math.abs(value) >= 1e6 || Math.abs(value) < 1e-4 ? value.toExponential(3) : value.toPrecision(4);
  return text.includes("e") ? text.replace(/\.?0+e/, "e") : text.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function withUnit(value: number, unit: string): string {
  const text = formatNumber(value);
  return unit && unit !== "a.u." ? `${text} ${unit}` : text;
}

function formatSweep(sweep: EvidenceSweep): string {
  const range = `${sweep.name} ${formatNumber(sweep.start)} to ${withUnit(sweep.stop, sweep.unit ?? "")}`;
  if (sweep.spacing === "log") return `${range}, ${sweep.points} points log-spaced`;
  if (sweep.spacing === "list" || sweep.step === undefined) return `${range}, ${sweep.points} points`;
  return `${range} in steps of ${withUnit(sweep.step, sweep.unit ?? "")} (${sweep.points} points)`;
}

/** Scalar run settings as "name value unit", the sweeps left out. */
function runSettings(evidence: object, skip: ReadonlySet<string>): string[] {
  const parameters = (evidence as { runParameters?: unknown }).runParameters;
  if (!parameters || typeof parameters !== "object") return [];
  const items: string[] = [];
  for (const [name, record] of Object.entries(parameters as Record<string, unknown>)) {
    if (skip.has(name) || !record || typeof record !== "object") continue;
    const { value, unit } = record as { value?: unknown; unit?: unknown };
    const unitText = typeof unit === "string" ? unit : "";
    if (typeof value === "number") items.push(`${name} ${withUnit(value, unitText)}`);
    else if (typeof value === "boolean") items.push(`${name} ${value}`);
    else if (typeof value === "string" && value.length <= 40) items.push(`${name} ${value}`);
  }
  return items;
}

/**
 * The Q6 suggested-range format from the task's sweep, as the benchmark words
 * it for each family ("(<min 1/alpha>, <max 1/alpha>)"): the swept parameter
 * with its unit. Undefined when the evidence reports no sweep.
 */
export function sweepRangeFormat(details: unknown): string | undefined {
  const sweep = evidenceSweeps(details)[0];
  if (!sweep) return undefined;
  const unit = sweep.unit && sweep.unit !== "a.u." ? ` [${sweep.unit}]` : "";
  return `(<min ${sweep.name}>, <max ${sweep.name}>)${unit}`;
}

/** The host record for one evaluation call, from its (filled) arguments. */
export function hostRecord(
  args: unknown,
  reference: Reference | undefined,
  durationMs?: number,
  taskId?: string,
  examples?: LabeledExample[],
): HostRecord {
  const a = (args ?? {}) as {
    context?: unknown;
    question?: unknown;
    task_name?: unknown;
    images?: unknown;
  };
  const images = Array.isArray(a.images)
    ? a.images.filter(
        (image): image is { data: string; mimeType: string } =>
          typeof (image as { data?: unknown })?.data === "string" &&
          typeof (image as { mimeType?: unknown })?.mimeType === "string",
      )
    : [];
  return {
    context: typeof a.context === "string" ? a.context : "",
    question: typeof a.question === "string" && a.question.trim() ? a.question : null,
    task_name: typeof a.task_name === "string" && a.task_name.trim() ? a.task_name : null,
    figures: images.map(figureRecord),
    knowledge: reference ? referenceRecord(reference) : null,
    ...(examples && examples.length > 0 ? { examples: examples.map(exampleRecord) } : {}),
    ...(durationMs === undefined ? {} : { duration_ms: durationMs }),
    ...(taskId ? { task_id: taskId } : {}),
  };
}

/** Size and hash of the reference text and criteria together. */
function referenceRecord(reference: Reference): { chars: number; sha256: string } {
  const identity = referenceIdentity(reference);
  return { chars: identity.length, sha256: sha256(identity) };
}

/** The record of one labeled example: identity, status, and figure hashes. */
export function exampleRecord(example: LabeledExample): ExampleRecord {
  return {
    id: example.id,
    title: example.title,
    outcome: example.outcome,
    ...(example.status ? { status: example.status } : {}),
    figures: example.images.map((image, index) => {
      const path = example.paths?.[index];
      return { ...figureRecord(image), ...(path ? { path } : {}) };
    }),
  };
}

/** The evaluator's per-question answers, kept when they are a map of text. */
function answerRecord(value: unknown): Record<string, string> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const entries = Object.entries(value as Record<string, unknown>).filter(
    (entry): entry is [string, string] => typeof entry[1] === "string",
  );
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

/**
 * One evaluation record from a `qcal_evaluate` result's details (the tool's
 * own `model`, `fallback`, `diagnosis`, `raw`, `prompt` plus the wrapper's
 * `host`), whichever path produced it.
 */
export function recordFromDetails(
  taskId: string,
  details: unknown,
  extra: {
    mode: EvaluationMode;
    target?: EvaluateResult["target"];
    usage?: unknown;
    durationMs?: number;
    evaluator?: ExtensionPackage;
    planner?: PlannerRecord;
    text?: string;
  },
): EvaluateResult {
  const d = (details ?? {}) as {
    model?: { provider?: string; modelId?: string };
    fallback?: boolean;
    diagnosis?: Record<string, unknown> | null;
    raw?: string;
    answers?: unknown;
    questions?: unknown;
    missing_keys?: unknown;
    attempts?: unknown;
    structured?: unknown;
    stop_reason?: unknown;
    calls?: unknown;
    prompt?: string;
    system_prompt?: string;
    host?: Partial<HostRecord>;
  };
  const host = d.host ?? {};
  const model =
    d.model?.provider && d.model.modelId ? `${d.model.provider}/${d.model.modelId}` : null;
  const diagnosis = typeof d.diagnosis === "object" && d.diagnosis !== null ? d.diagnosis : null;
  return {
    task_id: taskId || host.task_id || "",
    mode: extra.mode,
    task_name: host.task_name ?? null,
    target: extra.target ?? null,
    context: host.context ?? "",
    figures: host.figures ?? [],
    knowledge: host.knowledge ?? null,
    examples: host.examples ?? [],
    evaluation: {
      model,
      fallback: d.fallback === true,
      prompt: typeof d.prompt === "string" ? d.prompt : null,
      system_prompt: typeof d.system_prompt === "string" ? d.system_prompt : null,
      diagnosis,
      // The evaluator keeps the text when the answer was not JSON or not all
      // of the diagnosis; an older one reports it only when not JSON.
      raw: (typeof d.raw === "string" ? d.raw : diagnosis ? null : extra.text) || null,
      answers: answerRecord(d.answers),
      questions: Array.isArray(d.questions)
        ? d.questions.filter((key): key is string => typeof key === "string")
        : [],
      missing_keys: Array.isArray(d.missing_keys)
        ? d.missing_keys.filter((key): key is string => typeof key === "string")
        : [],
      attempts: typeof d.attempts === "number" ? d.attempts : null,
      structured: typeof d.structured === "boolean" ? d.structured : null,
      stop_reason: typeof d.stop_reason === "string" ? d.stop_reason : null,
      calls: callRecords(d.calls),
      duration_ms: extra.durationMs ?? host.duration_ms ?? 0,
      usage: extra.usage ?? null,
    },
    evaluator: extra.evaluator ?? null,
    planner: extra.planner ?? null,
  };
}

/** The turn a planner is given to evaluate one task result the way the chat does. */
export function plannerInstruction(taskId: string, question?: string, withExamples = false): string {
  const lines = [
    `Evaluate QDash task result ${taskId} with pi-qcaleval.`,
    `First call ${EVIDENCE_TOOL} for it, then ${EVALUATION_TOOL} with task_name set to the task's name.`,
    "As context pass only the task name and its target (qubit or coupling, chip) from the evidence, not the fitted metrics: the evaluation model judges the plot on its own, the way the QCalEval benchmark does.",
  ];
  if (withExamples) {
    lines.push(
      `Pass use_examples: true to ${EVALUATION_TOOL}: the figure is to be judged against the task's labeled reference examples.`,
    );
  }
  if (question?.trim()) lines.push(`Pass this question to ${EVALUATION_TOOL}: ${question.trim()}`);
  lines.push(
    "Report the status (calibration_diagnosis), the fit reliability and the outcome classification, and say in one or two sentences whether you agree with the diagnosis.",
  );
  return lines.join("\n");
}

/** The slice of a durable transcript entry the planner outcome reads. */
export type TranscriptEntryLike = {
  model?: ReadonlyArray<{
    role?: string;
    toolName?: string;
    isError?: boolean;
    details?: unknown;
    content?: unknown;
    usage?: unknown;
  }>;
};

/**
 * What a planner turn left in the transcript: the last `qcal_evaluate`
 * result's details, the error text when that call failed, and the tools the
 * planner called in order.
 */
export function plannerOutcome(entries: ReadonlyArray<TranscriptEntryLike>): {
  details?: unknown;
  usage?: unknown;
  error?: string;
  toolCalls: string[];
} {
  const toolCalls: string[] = [];
  let details: unknown;
  let usage: unknown;
  let error: string | undefined;
  for (const entry of entries) {
    for (const message of entry.model ?? []) {
      if (message.role === "assistant" && Array.isArray(message.content)) {
        for (const block of message.content) {
          const call = block as { type?: unknown; name?: unknown };
          if (call.type === "toolCall" && typeof call.name === "string") toolCalls.push(call.name);
        }
      }
      if (message.role === "toolResult" && message.toolName === EVALUATION_TOOL) {
        if (message.isError) {
          error = textOf(Array.isArray(message.content) ? (message.content as { type: string }[]) : []) || `${EVALUATION_TOOL} failed`;
          details = undefined;
        } else {
          error = undefined;
          details = message.details;
          usage = message.usage;
        }
      }
    }
  }
  return { details, usage, error, toolCalls };
}

/**
 * The knowledge of an evaluation against an uploaded draft: one load of the
 * draft serves both the reference and the examples, and a draft that cannot
 * be read fails the evaluation instead of letting it run without knowledge.
 */
export function draftKnowledge(
  load: () => Promise<TaskKnowledgeLike>,
): Pick<EvaluateDeps, "fetchKnowledge" | "fetchExamples"> {
  let pending: Promise<TaskKnowledgeLike> | undefined;
  const draft = () =>
    (pending ??= load().catch((error: unknown) => {
      throw new EvaluationError(
        "knowledge",
        `knowledge draft: ${error instanceof Error ? error.message : String(error)}`,
      );
    }));
  return {
    fetchKnowledge: async () => renderReference(await draft()),
    fetchExamples: async () => examplesOf(await draft()),
  };
}

/** Clamp the requested figure count to what the tools accept. */
export function figureCount(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 1;
  return Math.min(Math.max(Math.floor(value), 1), MAX_EVALUATION_FIGURES);
}

export interface PromptPreviewRequest {
  taskName: string;
  /** Show the task's labeled examples, as an in-context evaluation would. */
  withExamples?: boolean;
  /** The context line to show; a generic one names the task when absent. */
  context?: string;
  question?: string;
  /** Build the prompts from this uploaded knowledge draft instead of the task's shared knowledge. */
  knowledgeDraftId?: string;
}

/** The prompts an evaluation of a task would send, built without a figure or a model call. */
export interface PromptPreview {
  task_name: string;
  with_examples: boolean;
  /** `provider/modelId` of the model that would judge, when one is configured. */
  model: string | null;
  questions: Array<{ key: string; prompt: string }>;
  knowledge: { chars: number; sha256: string } | null;
  examples: ExampleRecord[];
  examples_used: number;
}

/**
 * Build the prompts an evaluation of `taskName` would send, through the same
 * fill as a real evaluation (QDash's reference and labeled examples, as the
 * user) and the evaluator's own templates (`dry_run`), so the Knowledge page
 * shows exactly what a task's reference turns into. No figure is needed and
 * the model is not asked.
 */
export async function previewEvaluationPrompts(
  request: PromptPreviewRequest,
  deps: Pick<EvaluateDeps, "runTool" | "fetchKnowledge" | "fetchExamples">,
): Promise<PromptPreview> {
  const taskName = request.taskName.trim();
  if (!taskName) throw new EvaluationError("request", "task_name is required", 400);
  const knowledge = await deps.fetchKnowledge(taskName);
  const examples = request.withExamples && deps.fetchExamples ? await deps.fetchExamples(taskName) : [];
  const question = request.question?.trim();
  const criteria = compactCriteria(knowledge?.criteria);
  const args = {
    context: request.context?.trim() || `Task ${taskName}.`,
    ...(question ? { question } : {}),
    task_name: taskName,
    ...(knowledge ? { knowledge: knowledge.knowledge } : {}),
    ...(criteria ? { criteria } : {}),
    ...(request.withExamples ? { use_examples: true } : {}),
    ...(examples.length > 0 ? { examples: examples.map(toolExample) } : {}),
    dry_run: true,
  };
  const result = await deps.runTool(EVALUATION_TOOL, args);
  if (result.isError) {
    throw new EvaluationError("evaluation", textOf(result.content) || `${EVALUATION_TOOL} failed`);
  }
  const d = (result.details ?? {}) as {
    model?: { provider?: string; modelId?: string };
    questions?: unknown;
    prompts?: unknown;
    examples_used?: unknown;
  };
  const prompts = (d.prompts && typeof d.prompts === "object" ? d.prompts : {}) as Record<string, unknown>;
  const keys = Array.isArray(d.questions)
    ? d.questions.filter((key): key is string => typeof key === "string")
    : Object.keys(prompts);
  const identity = knowledge ? referenceIdentity({ knowledge: knowledge.knowledge, criteria }) : undefined;
  return {
    task_name: taskName,
    with_examples: request.withExamples === true,
    model: d.model?.provider && d.model.modelId ? `${d.model.provider}/${d.model.modelId}` : null,
    questions: keys.map((key) => ({ key, prompt: typeof prompts[key] === "string" ? (prompts[key] as string) : "" })),
    knowledge: identity ? { chars: identity.length, sha256: sha256(identity) } : null,
    examples: examples.map(exampleRecord),
    examples_used: typeof d.examples_used === "number" ? d.examples_used : 0,
  };
}

/**
 * Summarise one task result as evidence, then judge its figure.
 *
 * The evaluation tool gets what the planner's call would get after the
 * runtime's auto-fill: the task and its target as context, the figure bytes
 * from the evidence result, and QDash's reference for the task name the
 * evidence reports. The fitted values the evidence text carries stay out of
 * the context: as in the QCalEval benchmark, the model reads them off the plot.
 */
export async function evaluateTask(
  request: EvaluateRequest,
  deps: EvaluateDeps,
): Promise<EvaluateResult> {
  const taskId = request.taskId.trim();
  if (!taskId) throw new EvaluationError("request", "task_id is required", 400);
  const maxFigures = figureCount(request.maxFigures);

  const evidence = await deps.runTool(EVIDENCE_TOOL, { taskId, maxFigures });
  const evidenceText = textOf(evidence.content);
  if (evidence.isError) {
    throw new EvaluationError("evidence", evidenceText || `${EVIDENCE_TOOL} failed`);
  }
  const images = imagesOf(evidence.content);
  if (images.length === 0) {
    throw new EvaluationError("evidence", `task ${taskId} has no figure to evaluate`, 422);
  }
  const { taskName, target } = evidenceSummary(evidence.details);
  const context = evidenceContext(evidence.details) ?? evidenceText;

  const knowledge = taskName ? await deps.fetchKnowledge(taskName) : undefined;
  // The task's own sweep gives the status question its range format, unless
  // the knowledge states one.
  const criteria = compactCriteria({
    ...knowledge?.criteria,
    ...(knowledge?.criteria?.range_format ? {} : { range_format: sweepRangeFormat(evidence.details) }),
  });
  const examples =
    request.withExamples && taskName && deps.fetchExamples ? await deps.fetchExamples(taskName) : [];
  const question = request.question?.trim();
  const args = {
    context,
    ...(question ? { question } : {}),
    ...(taskName ? { task_name: taskName } : {}),
    ...(knowledge ? { knowledge: knowledge.knowledge } : {}),
    ...(criteria ? { criteria } : {}),
    ...(request.withExamples ? { use_examples: true } : {}),
    ...(examples.length > 0 ? { examples: examples.map(toolExample) } : {}),
    images,
  };
  const started = Date.now();
  const evaluation = await deps.runTool(EVALUATION_TOOL, args);
  const duration = Date.now() - started;
  if (evaluation.isError) {
    throw new EvaluationError("evaluation", textOf(evaluation.content) || `${EVALUATION_TOOL} failed`);
  }
  const details = {
    ...((evaluation.details ?? {}) as object),
    // The record hashes the reference as passed: the criteria the sweep completed.
    host: hostRecord(args, knowledge || criteria ? { knowledge: knowledge?.knowledge ?? "", criteria } : undefined, duration, undefined, examples),
  };
  return recordFromDetails(taskId, details, {
    mode: "direct",
    target,
    usage: evaluation.usage,
    durationMs: duration,
    evaluator: deps.evaluator,
    text: textOf(evaluation.content),
  });
}
