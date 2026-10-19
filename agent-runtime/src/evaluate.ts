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

import type { LabeledExample } from "./knowledge-context.ts";
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
}

/** One labeled example the model saw, by identity and figure hashes rather than bytes. */
export interface ExampleRecord {
  id: string;
  title: string;
  outcome: string;
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
  /** QDash's review guide for a task, as the user; undefined when it has none. */
  fetchKnowledge(taskName: string): Promise<string | undefined>;
  /** QDash's labeled examples for a task, as the user; empty when it has none. */
  fetchExamples?(taskName: string): Promise<LabeledExample[]>;
  /** The package that provides the evaluation tool, for the record. */
  evaluator?: ExtensionPackage;
}

export type EvaluationStage = "request" | "evidence" | "evaluation";

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
}

export interface EvaluateResult {
  task_id: string;
  mode: EvaluationMode;
  /** The task's name as QDash knows it, when the evidence names it. */
  task_name: string | null;
  target: { kind?: string; id?: string; chip_id?: string } | null;
  /** The evidence text the evaluation model received as context. */
  context: string;
  figures: FigureRecord[];
  /** The reference the host supplied, by size and hash; the prompt holds the text. */
  knowledge: { chars: number; sha256: string } | null;
  /** The labeled examples shown before the figure; empty for a zero-shot evaluation. */
  examples: ExampleRecord[];
  evaluation: {
    /** `provider/modelId` of the model that judged the plot. */
    model: string | null;
    fallback: boolean;
    /** The user turn the model was sent: reference, context, question. */
    prompt: string | null;
    /** The system prompt the model was sent, when the evaluator reports it. */
    system_prompt: string | null;
    diagnosis: Record<string, unknown> | null;
    /** The answer when it was not the requested JSON, or not all of it. */
    raw: string | null;
    /** Diagnosis keys the answer lacks, when the evaluator reports them. */
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
  duration_ms: number;
  stop_reason: string;
  structured: boolean;
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
      duration_ms: c.duration_ms,
      stop_reason: c.stop_reason,
      structured: c.structured === true,
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
  return { sha256: sha256(bytes), mime_type: image.mimeType, bytes: bytes.length };
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

/** The host record for one evaluation call, from its (filled) arguments. */
export function hostRecord(
  args: unknown,
  knowledge: string | undefined,
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
    knowledge: knowledge ? { chars: knowledge.length, sha256: sha256(knowledge) } : null,
    ...(examples && examples.length > 0 ? { examples: examples.map(exampleRecord) } : {}),
    ...(durationMs === undefined ? {} : { duration_ms: durationMs }),
    ...(taskId ? { task_id: taskId } : {}),
  };
}

/** The record of one labeled example: identity and figure hashes. */
export function exampleRecord(example: LabeledExample): ExampleRecord {
  return {
    id: example.id,
    title: example.title,
    outcome: example.outcome,
    figures: example.images.map((image, index) => {
      const path = example.paths?.[index];
      return { ...figureRecord(image), ...(path ? { path } : {}) };
    }),
  };
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
    `First call ${EVIDENCE_TOOL} for it, then ${EVALUATION_TOOL} with task_name set to the task's name and that summary as context.`,
  ];
  if (withExamples) {
    lines.push(
      `Pass use_examples: true to ${EVALUATION_TOOL}: the figure is to be judged against the task's labeled reference examples.`,
    );
  }
  if (question?.trim()) lines.push(`Pass this question to ${EVALUATION_TOOL}: ${question.trim()}`);
  lines.push("Report fit_quality and success, and say in one or two sentences whether you agree with the diagnosis.");
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

/** Clamp the requested figure count to what the tools accept. */
export function figureCount(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 1;
  return Math.min(Math.max(Math.floor(value), 1), MAX_EVALUATION_FIGURES);
}

/**
 * Summarise one task result as evidence, then judge its figure.
 *
 * The evaluation tool gets what the planner's call would get after the
 * runtime's auto-fill: the evidence text as context, the figure bytes from the
 * evidence result, and QDash's reference for the task name the evidence
 * reports.
 */
export async function evaluateTask(
  request: EvaluateRequest,
  deps: EvaluateDeps,
): Promise<EvaluateResult> {
  const taskId = request.taskId.trim();
  if (!taskId) throw new EvaluationError("request", "task_id is required", 400);
  const maxFigures = figureCount(request.maxFigures);

  const evidence = await deps.runTool(EVIDENCE_TOOL, { taskId, maxFigures });
  const context = textOf(evidence.content);
  if (evidence.isError) {
    throw new EvaluationError("evidence", context || `${EVIDENCE_TOOL} failed`);
  }
  const images = imagesOf(evidence.content);
  if (images.length === 0) {
    throw new EvaluationError("evidence", `task ${taskId} has no figure to evaluate`, 422);
  }
  const { taskName, target } = evidenceSummary(evidence.details);

  const knowledge = taskName ? await deps.fetchKnowledge(taskName) : undefined;
  const examples =
    request.withExamples && taskName && deps.fetchExamples ? await deps.fetchExamples(taskName) : [];
  const question = request.question?.trim();
  const args = {
    context,
    ...(question ? { question } : {}),
    ...(taskName ? { task_name: taskName } : {}),
    ...(knowledge ? { knowledge } : {}),
    ...(request.withExamples ? { use_examples: true } : {}),
    ...(examples.length > 0 ? { examples: examples.map(({ label, images }) => ({ label, images })) } : {}),
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
    host: hostRecord(args, knowledge, duration, undefined, examples),
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
