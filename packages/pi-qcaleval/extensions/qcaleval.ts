/**
 * pi-qcaleval: evaluate calibration plots with a dedicated calibration VLM.
 *
 * The extension has no QDash dependency. It takes a plot (plus the experiment
 * background and criteria the host supplies for the task, and the context the
 * planner already knows) and asks the evaluation model the six QCalEval
 * questions, each as its own single-turn request the way the benchmark and
 * the Ising-Calibration training data lay them out. The planner decides what
 * to do with the diagnosis; whether a calibration loop continues is the
 * host's policy, not this tool's.
 */

import type { Api, AssistantMessage, ImageContent, Model, Usage } from "@earendil-works/pi-ai";
import type {
  AgentToolResult,
  ExtensionAPI,
  ExtensionToolContext,
} from "@earendil-works/pi-coding-agent";
import { Type, type Static } from "typebox";

/** Figures per evaluation; a 16k-token deployment holds a few plots comfortably. */
export const MAX_IMAGES = 4;

/** Labeled example plots shown before the query, and the figures they may hold in total. */
export const MAX_EXAMPLES = 6;
export const MAX_EXAMPLE_IMAGES = 6;

/** Model ids of models fine-tuned for calibration plots; preferred when configured. */
export const CALIBRATION_MODEL_PATTERN = /ising-calibration/i;

/** Output budget when the model declares none; one answer is a few hundred tokens. */
const DEFAULT_MAX_TOKENS = 2048;
const MAX_OUTPUT_TOKENS = 4096;

export interface ModelSpec {
  provider: string;
  modelId: string;
}

/** Parse an explicit `provider/modelId` override; the model id may contain slashes (nvidia/...). */
export function parseModelSpec(value: string | undefined): ModelSpec | undefined {
  const spec = (value ?? "").trim();
  if (!spec) return undefined;
  const slash = spec.indexOf("/");
  if (slash <= 0 || slash === spec.length - 1) {
    throw new Error(`QCALEVAL_MODEL must be provider/modelId, got "${spec}"`);
  }
  return { provider: spec.slice(0, slash), modelId: spec.slice(slash + 1) };
}

/** The slice of pi's model registry the resolution needs. */
export interface ModelLookup {
  find(provider: string, modelId: string): Model<Api> | undefined;
  getAvailable(): Model<Api>[];
}

export type EvaluationModel =
  | { model: Model<Api>; fallback: false }
  | { model: Model<Api>; fallback: true }
  | { model?: undefined; error: string };

/**
 * Pick the model that judges the plot, without any host-specific setting:
 *
 * 1. `QCALEVAL_MODEL` (`provider/modelId`), an explicit override for the pi CLI;
 * 2. a configured calibration VLM, recognised by its id (Ising-Calibration);
 * 3. the conversation's own model, when it accepts images.
 *
 * A host that declares the calibration model in its models.json gets it
 * everywhere; one that does not (no Ising deployment) still gets a diagnosis
 * from the vision model it already runs, marked as a fallback.
 */
export function resolveEvaluationModel(
  registry: ModelLookup,
  current: Model<Api> | undefined,
  override: string | undefined,
): EvaluationModel {
  const spec = parseModelSpec(override);
  if (spec) {
    const model = registry.find(spec.provider, spec.modelId);
    return model
      ? { model, fallback: false }
      : { error: `model ${spec.provider}/${spec.modelId} is not configured (QCALEVAL_MODEL)` };
  }
  const calibration = registry.getAvailable().find((model) => CALIBRATION_MODEL_PATTERN.test(model.id));
  if (calibration) return { model: calibration, fallback: false };
  if (current?.input.includes("image")) return { model: current, fallback: true };
  return {
    error:
      "no evaluation model: declare a calibration VLM (Ising-Calibration) in models.json, or run with a vision model",
  };
}

/** Output budget for one answer, within what the model allows. */
export function outputBudget(model: Pick<Model<Api>, "maxTokens">): number {
  return model.maxTokens > 0 ? Math.min(model.maxTokens, MAX_OUTPUT_TOKENS) : DEFAULT_MAX_TOKENS;
}

// ---------------------------------------------------------------------------
// The six questions
// ---------------------------------------------------------------------------

/**
 * The QCalEval questions, keyed as the benchmark keys its responses, in the
 * order the paper numbers them (Q1–Q6). Each is asked in its own request.
 */
export const QUESTIONS = [
  "technical_description",
  "experimental_conclusion",
  "experimental_significance",
  "fit_reliability",
  "parameter_extraction",
  "calibration_diagnosis",
] as const;
export type Question = (typeof QUESTIONS)[number];

/** Questions that take labeled demonstrations (the benchmark's ICL mode). */
export const ICL_QUESTIONS: ReadonlySet<Question> = new Set<Question>([
  "experimental_significance",
  "parameter_extraction",
  "calibration_diagnosis",
]);

/** The four outcomes of Q2, as the benchmark words them, with the key the diagnosis uses. */
export const OUTCOMES = [
  { key: "expected", option: "Expected behavior", meaning: "Experiment produced usable calibration data" },
  {
    key: "suboptimal",
    option: "Suboptimal parameters",
    meaning: "Working but needs parameter adjustment within this experiment",
  },
  {
    key: "anomalous",
    option: "Anomalous behavior",
    meaning: "Requires upstream recalibration or shows uncontrollable quantum effects",
  },
  { key: "apparatus", option: "Apparatus issue", meaning: "No meaningful signal — measurement system misconfigured" },
] as const;
export type Outcome = (typeof OUTCOMES)[number]["key"];

/** The three answers of Q4, with the key the diagnosis uses. */
export const FIT_ASSESSMENTS = [
  { key: "reliable", option: "Reliable" },
  { key: "unreliable", option: "Unreliable" },
  { key: "no_fit", option: "No fit" },
] as const;
export type FitAssessment = (typeof FIT_ASSESSMENTS)[number]["key"];

/** What Q3 asks the model to explain when the host gives no task-specific points. */
export const DEFAULT_GUIDANCE = [
  "What the observed behavior indicates about the calibration",
  "Whether the measurement is valid for its purpose (sweep range, resolution, signal quality)",
  "What calibration step follows",
] as const;

/** Q6 statuses when the host gives none; a task's own criteria replace them. */
export const DEFAULT_STATUSES: Readonly<Record<string, string>> = {
  SUCCESS: "The plot shows the expected behavior described above and the result is usable",
  SUBOPTIMAL: "Usable data, but a parameter of this experiment (range, amplitude, resolution) needs adjustment",
  NO_SIGNAL: "Flat or random data with no usable signal",
  ANOMALOUS: "Behavior that calls for upstream recalibration or shows uncontrolled effects",
};
export const DEFAULT_RANGE_FORMAT = "(<min>, <max>) of the swept parameter";

/** Task-specific pieces of the question templates, supplied by the host. */
export interface Criteria {
  /** Q3 "Explain:" bullets. */
  guidance?: ReadonlyArray<string>;
  /** Q5 schema: parameter name to its type or description. */
  parameters?: Readonly<Record<string, string>>;
  /** Q6 decision criteria: status code to the criterion; SUCCESS first. */
  statuses?: Readonly<Record<string, string>>;
  /** Q6 suggested-range format, e.g. "(<min 1/alpha>, <max 1/alpha>)". */
  range_format?: string;
}

export interface Figure {
  data: string;
  mimeType: string;
}

/** One labeled example plot: its figure(s) and the answers an expert validated. */
export interface LabeledExample {
  images: ReadonlyArray<Figure>;
  /** What the example shows, e.g. "drag_failure_no_signal" or a short title. */
  scenario?: string;
  /** Q3 answer for the example. */
  analysis?: string;
  /** Q5 answer for the example: JSON text or an object. */
  parameters?: string | Readonly<Record<string, unknown>>;
  /** Q6 status code of the example. */
  status?: string;
  /** Q6 suggested range of the example; "N/A" or empty for a success. */
  suggested_range?: string;
}

export type UserContentBlock =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string };

export interface PromptInput {
  /** The experiment background: what is swept and what a successful result looks like. */
  background?: string;
  /** The host's context: task, target, anything the background cannot know. */
  context: string;
  /** A specific point to address in the analysis (Q3). */
  question?: string;
  criteria?: Criteria;
  /** The figures; the last one is the measured result to judge. */
  images: ReadonlyArray<Figure>;
  examples?: ReadonlyArray<LabeledExample>;
}

/** The marker the templates use for the figure to judge, as the benchmark's prompts do. */
const IMAGE = "<image>";

function paragraphs(...parts: Array<string | undefined>): string {
  return parts.filter((part): part is string => Boolean(part && part.trim())).join("\n\n");
}

function opening(input: PromptInput, withBackground = true): string {
  const context = input.context.trim();
  return paragraphs(
    withBackground ? input.background?.trim() : undefined,
    context ? `Experiment context: ${context}` : undefined,
  );
}

/** Keep examples in order within the example and figure budgets; later ones are dropped. */
export function fitExamples(examples: ReadonlyArray<LabeledExample>): LabeledExample[] {
  const kept: LabeledExample[] = [];
  let figures = 0;
  for (const example of examples) {
    if (kept.length >= MAX_EXAMPLES) break;
    const labeled = Boolean(example.analysis?.trim() || example.status?.trim() || example.parameters);
    if (!labeled || !example.images?.length) continue;
    if (figures + example.images.length > MAX_EXAMPLE_IMAGES) break;
    figures += example.images.length;
    kept.push(example);
  }
  return kept;
}

function parametersText(value: LabeledExample["parameters"]): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value === "string") return value.trim() || undefined;
  return JSON.stringify(value);
}

function statusList(statuses: Readonly<Record<string, string>>): string {
  return Object.entries(statuses)
    .map(([code, criterion]) => `- ${code}: ${criterion}`)
    .join("\n");
}

/**
 * The text of one question's prompt, with `<image>` where each figure goes:
 * the example figures in order, then the figure to judge. Templates follow the
 * QCalEval dataset's prompts; the host's criteria fill the family-specific parts.
 */
export function questionTemplate(question: Question, input: PromptInput): { text: string; images: Figure[] } {
  const criteria = input.criteria ?? {};
  const examples = fitExamples(input.examples ?? []);
  const exampleImages: Figure[] = [];
  const demo = (example: LabeledExample): string => {
    exampleImages.push(...example.images);
    return example.images.map(() => IMAGE).join(" ");
  };
  const specific = input.question?.trim();
  let text: string;

  switch (question) {
    case "technical_description": {
      text = [
        `Describe the figure ${IMAGE} in JSON format.`,
        "",
        "Required fields:",
        "{",
        '  "plot_type": "scatter" | "line" | "heatmap" | "histogram",',
        '  "x_axis": {"label": string, "scale": "linear" | "log", "range": [min, max]},',
        '  "y_axis": {"label": string, "scale": "linear" | "log", "range": [min, max]},',
        '  "main_features": string',
        "}",
      ].join("\n");
      break;
    }
    case "experimental_conclusion": {
      text = paragraphs(
        opening(input),
        `Based on what you observe in the data ${IMAGE}, classify the experimental outcome.`,
        ["Options:", ...OUTCOMES.map((o) => `- ${o.option}: ${o.meaning}`)].join("\n"),
        "Provide your answer as:\nClassification: <your choice>\nReason: <brief explanation>",
      );
      break;
    }
    case "experimental_significance": {
      const shown = examples.filter((example) => example.analysis?.trim());
      if (shown.length > 0) {
        text = paragraphs(
          opening(input),
          "Here are example analyses for each scenario type in this experiment family:",
          ...shown.map(
            (example, index) =>
              `${demo(example)} Scenario "${example.scenario?.trim() || `example ${index + 1}`}":\n${example.analysis!.trim()}`,
          ),
          specific ? `Also address: ${specific}` : undefined,
          `Now analyze this chart:\n\n${IMAGE}`,
        );
      } else {
        const guidance = criteria.guidance?.filter((line) => line.trim()).length
          ? criteria.guidance.filter((line) => line.trim())
          : DEFAULT_GUIDANCE;
        text = paragraphs(
          opening(input),
          `What does this result ${IMAGE} imply?`,
          ["Explain:", ...guidance.map((line) => `- ${line.trim()}`), ...(specific ? [`- ${specific}`] : [])].join(
            "\n",
          ),
          "Provide your assessment.",
        );
      }
      break;
    }
    case "fit_reliability": {
      text = paragraphs(
        opening(input),
        `Assess whether the fit to the data in this plot ${IMAGE} is reliable for parameter extraction.`,
        ["Options:", ...FIT_ASSESSMENTS.map((f) => `- ${f.option}`)].join("\n"),
        "Provide your answer as:\nAssessment: <your choice>\nReason: <brief explanation>",
      );
      break;
    }
    case "parameter_extraction": {
      const shown = examples.find((example) => parametersText(example.parameters));
      const schema = Object.entries(criteria.parameters ?? {});
      if (shown) {
        text = paragraphs(
          opening(input),
          "Here is an example of parameter extraction from a similar chart:",
          `${demo(shown)} Extracted parameters: ${parametersText(shown.parameters)}`,
          `Now extract parameters from this chart:\n\n${IMAGE}`,
        );
      } else if (schema.length > 0) {
        text = paragraphs(
          opening(input),
          `Extract the following parameters from this plot ${IMAGE}.`,
          `Report in JSON format:\n{${schema.map(([name, type]) => `"${name}": ${type}`).join(", ")}}\nUse "Unreliable" for a value the plot does not determine.`,
        );
      } else {
        text = paragraphs(
          opening(input),
          `Extract the physical parameters this plot ${IMAGE} determines.`,
          'Report in JSON format, one key per parameter with its value and unit, e.g. {"<parameter>": <value>, "<parameter>_unit": "<unit>"}. Use "Unreliable" for a value the plot does not determine.',
        );
      }
      break;
    }
    case "calibration_diagnosis": {
      const statuses = criteria.statuses && Object.keys(criteria.statuses).length > 0 ? criteria.statuses : DEFAULT_STATUSES;
      const range = criteria.range_format?.trim() || DEFAULT_RANGE_FORMAT;
      const shown = examples.filter((example) => example.status?.trim());
      if (shown.length > 0) {
        text = paragraphs(
          opening(input),
          `Classify this chart given the following labeled examples.\n\nDECISION CRITERIA\n${statusList(statuses)}`,
          ...shown.map(
            (example) =>
              `${demo(example)} Status: ${example.status!.trim().toUpperCase()}\nSuggested range: ${example.suggested_range?.trim() || "N/A"}`,
          ),
          `Now classify this chart:\n\n${IMAGE}`,
        );
      } else {
        text = paragraphs(
          opening(input),
          `Evaluate the image ${IMAGE} and determine the experiment status.`,
          `DECISION CRITERIA\n${statusList(statuses)}`,
          `When the status is not SUCCESS, provide a SPECIFIC suggested ${range}.`,
          `The response MUST follow this exact format:\n\nStatus: <one of the listed statuses>\nSuggested range: ${range} (or "N/A" if SUCCESS)\nNotes: <1-3 sentences explaining your reasoning>`,
        );
      }
      break;
    }
  }

  // A reference figure ahead of the measured one (a task review opens with
  // the expected plot) is shown first, as the benchmark shows its examples.
  const query = input.images[input.images.length - 1];
  const references = input.images.slice(0, -1);
  if (references.length > 0) {
    text = paragraphs(
      `Reference figure${references.length === 1 ? "" : "s"} for comparison (expected result); the last figure is the measured result to judge:\n${references.map(() => IMAGE).join(" ")}`,
      text,
    );
  }
  return { text, images: [...references, ...exampleImages, ...(query ? [query] : [])] };
}

/**
 * One question's user turn as content blocks: the template text with each
 * `<image>` replaced by the next figure, images as native blocks. `prompt` is
 * the same turn as text with `[figure]` where an image was, for the record.
 */
export function buildQuestionContent(
  question: Question,
  input: PromptInput,
): { content: UserContentBlock[]; prompt: string } {
  const { text, images } = questionTemplate(question, input);
  const content: UserContentBlock[] = [];
  const parts = text.split(IMAGE);
  parts.forEach((part, index) => {
    if (part.trim()) content.push({ type: "text", text: part.trim() });
    const figure = images[index];
    if (index < parts.length - 1 && figure) content.push({ type: "image", data: figure.data, mimeType: figure.mimeType });
  });
  const prompt = text.replace(/<image>/g, "[figure]").replace(/\n{3,}/g, "\n\n").trim();
  return { content, prompt };
}

/** The prompts of several questions as one text, headed by the question key, for the record. */
export function promptRecord(prompts: ReadonlyArray<{ question: Question; prompt: string }>): string {
  return prompts.map(({ question, prompt }) => `## ${question}\n${prompt}`).join("\n\n");
}

// ---------------------------------------------------------------------------
// Answers
// ---------------------------------------------------------------------------

/** Pull the text blocks of the assistant answer, dropping thinking. */
export function answerText(message: AssistantMessage): string {
  return message.content
    .map((block) => (block.type === "text" ? block.text : ""))
    .join("")
    .trim();
}

/**
 * Parse the first JSON object in an answer, tolerating a code fence, a
 * "thought" preamble or trailing commentary around it: the first balanced
 * `{...}` is taken.
 */
export function parseJsonObject(text: string): Record<string, unknown> | undefined {
  const start = text.indexOf("{");
  if (start < 0) return undefined;
  let depth = 0;
  let inString = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (ch === "\\") i++;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{") depth++;
    else if (ch === "}" && --depth === 0) {
      return parseObject(text.slice(start, i + 1));
    }
  }
  return undefined;
}

/**
 * Parse one JSON object. The model writes LaTeX such as `\pi` inside strings,
 * which is an invalid JSON escape, so a failed strict parse is retried with
 * every backslash that does not start a JSON escape doubled.
 */
function parseObject(json: string): Record<string, unknown> | undefined {
  for (const candidate of [json, json.replace(/\\(?!["\\/bfnrtu])/g, "\\\\")]) {
    try {
      const parsed: unknown = JSON.parse(candidate);
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
      return undefined;
    } catch {
      // Try the lenient candidate next.
    }
  }
  return undefined;
}

/** The value after `Label:` on its own line (markdown emphasis tolerated), or undefined. */
export function labeledLine(text: string, label: string): string | undefined {
  const match = text.match(new RegExp(`^[ \\t]*[*_#]*${label}[*_]*[ \\t]*:[*_ \\t]*(.+?)[ \\t]*$`, "im"));
  return match?.[1]?.replace(/[*_]+$/, "").trim() || undefined;
}

/** Everything after `Label:` to the end of the text, across lines. */
function labeledRest(text: string, label: string): string | undefined {
  const match = text.match(new RegExp(`^[ \\t]*[*_#]*${label}[*_]*[ \\t]*:[*_ \\t]*([\\s\\S]*)$`, "im"));
  return match?.[1]?.trim() || undefined;
}

export function parseOutcome(text: string): Outcome | null {
  const line = (labeledLine(text, "Classification") ?? text).toLowerCase();
  for (const outcome of OUTCOMES) {
    if (line.includes(outcome.key) || line.includes(outcome.option.toLowerCase())) return outcome.key;
  }
  return null;
}

export function parseFitAssessment(text: string): FitAssessment | null {
  const line = (labeledLine(text, "Assessment") ?? text).toLowerCase();
  if (/\bno fit\b|\bno_fit\b/.test(line)) return "no_fit";
  if (/\bunreliable\b/.test(line)) return "unreliable";
  if (/\breliable\b/.test(line)) return "reliable";
  return null;
}

/** A status code as the benchmark normalises it: trimmed, upper-cased, spaces as underscores. */
export function normalizeStatus(value: string | undefined): string | null {
  const code = (value ?? "")
    .replace(/[`*]+/g, "")
    .trim()
    .split(/\s*\(|\s+[—–-]\s+/)[0]
    ?.trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
  return code && /^[A-Z][A-Z0-9_]*$/.test(code) ? code : null;
}

/** The parsed value of one answer, in the shape the diagnosis stores for that question. */
export function parseAnswer(question: Question, text: string): unknown {
  switch (question) {
    case "technical_description":
      return parseJsonObject(text) ?? text;
    case "experimental_conclusion":
      return { classification: parseOutcome(text), reason: labeledRest(text, "Reason") ?? "" };
    case "experimental_significance":
      return text;
    case "fit_reliability":
      return { assessment: parseFitAssessment(text), reason: labeledRest(text, "Reason") ?? "" };
    case "parameter_extraction": {
      const object = parseJsonObject(text);
      if (object) return object;
      return text.trim().toLowerCase() === "null" ? null : text;
    }
    case "calibration_diagnosis": {
      const range = labeledLine(text, "Suggested range");
      return {
        status: normalizeStatus(labeledLine(text, "Status")),
        suggested_range: range && !/^n\/?a$/i.test(range) ? range : null,
        notes: labeledRest(text, "Notes") ?? "",
      };
    }
  }
}

/**
 * The diagnosis from the parsed answers, plus `success`: the Q6 status is
 * SUCCESS; without a Q6 answer, the Q2 outcome is expected; null when neither
 * was answered.
 */
export function assembleDiagnosis(answers: Partial<Record<Question, unknown>>): Record<string, unknown> {
  const diagnosis: Record<string, unknown> = {};
  for (const question of QUESTIONS) {
    if (question in answers) diagnosis[question] = answers[question];
  }
  const status = (answers.calibration_diagnosis as { status?: unknown } | undefined)?.status;
  const outcome = (answers.experimental_conclusion as { classification?: unknown } | undefined)?.classification;
  diagnosis.success =
    typeof status === "string"
      ? status === "SUCCESS"
      : answers.calibration_diagnosis === undefined && typeof outcome === "string"
        ? outcome === "expected"
        : null;
  return diagnosis;
}

/** One model call made for an answer, for the record: how long it took and how it ended. */
export interface CallRecord {
  question: Question;
  duration_ms: number;
  stop_reason: string;
  /** Prompt tokens the model counted for the call, images included. */
  input_tokens?: number;
  output_tokens?: number;
}

/** The answers of one evaluation, read for the record. */
export interface Answers {
  diagnosis: Record<string, unknown>;
  /** Every answered question's text, as returned. */
  answers: Partial<Record<Question, string>>;
  questions: Question[];
  /** Questions asked that got no answer (a model error, or an empty reply). */
  missing: Question[];
  /** Model calls made, retries included. */
  attempts: number;
  stopReason: string;
  usage?: Usage;
  calls: CallRecord[];
  /** The error of the last failed call, when every call for some question failed. */
  errors: Partial<Record<Question, string>>;
}

/** Token usage of two calls together, so a retried answer is billed as both. */
export function addUsage(a: Usage | undefined, b: Usage | undefined): Usage | undefined {
  if (!a || !b) return a ?? b;
  const sum = (x: number | undefined, y: number | undefined) => (x ?? 0) + (y ?? 0);
  return {
    ...a,
    input: sum(a.input, b.input),
    output: sum(a.output, b.output),
    cacheRead: sum(a.cacheRead, b.cacheRead),
    cacheWrite: sum(a.cacheWrite, b.cacheWrite),
    ...(a.reasoning === undefined && b.reasoning === undefined
      ? {}
      : { reasoning: sum(a.reasoning, b.reasoning) }),
    totalTokens: sum(a.totalTokens, b.totalTokens),
    cost: {
      input: sum(a.cost?.input, b.cost?.input),
      output: sum(a.cost?.output, b.cost?.output),
      cacheRead: sum(a.cost?.cacheRead, b.cost?.cacheRead),
      cacheWrite: sum(a.cost?.cacheWrite, b.cost?.cacheWrite),
      total: sum(a.cost?.total, b.cost?.total),
    },
  };
}

/**
 * Ask every question, each in its own request, all at once. A call that
 * fails (a transport or server error) is retried once, as the benchmark
 * retries API failures; an answer is never re-asked for its content. Each
 * call's duration and stop reason are kept, so a slow evaluation can be
 * traced to the question that ran long.
 */
export async function askQuestions(
  questions: ReadonlyArray<Question>,
  call: (question: Question) => Promise<AssistantMessage>,
  clock: () => number = Date.now,
): Promise<Answers> {
  const calls: CallRecord[] = [];
  const usages: Usage[] = [];
  const ask = async (question: Question): Promise<AssistantMessage> => {
    const started = clock();
    const message = await call(question);
    calls.push({
      question,
      duration_ms: Math.max(0, clock() - started),
      stop_reason: message.stopReason,
      ...(message.usage ? { input_tokens: message.usage.input, output_tokens: message.usage.output } : {}),
    });
    if (message.usage) usages.push(message.usage);
    return message;
  };
  const results = await Promise.all(
    questions.map(async (question) => {
      let message = await ask(question);
      if (message.stopReason === "error") message = await ask(question);
      return { question, message };
    }),
  );
  const answers: Partial<Record<Question, string>> = {};
  const parsed: Partial<Record<Question, unknown>> = {};
  const errors: Partial<Record<Question, string>> = {};
  const missing: Question[] = [];
  for (const { question, message } of results) {
    const text = message.stopReason === "error" ? "" : answerText(message);
    if (!text) {
      missing.push(question);
      if (message.stopReason === "error") errors[question] = message.errorMessage ?? "model error";
      continue;
    }
    answers[question] = text;
    parsed[question] = parseAnswer(question, text);
  }
  // Calls finish in any order; the record lists them by question.
  calls.sort((a, b) => QUESTIONS.indexOf(a.question) - QUESTIONS.indexOf(b.question));
  const stops = calls.map((c) => c.stop_reason);
  const stopReason = stops.includes("length") ? "length" : missing.length === questions.length && stops.length ? stops[stops.length - 1]! : "stop";
  return {
    diagnosis: assembleDiagnosis(parsed),
    answers,
    questions: [...questions],
    missing,
    attempts: calls.length,
    stopReason,
    usage: usages.reduce<Usage | undefined>((sum, usage) => addUsage(sum, usage), undefined),
    calls,
    errors,
  };
}

// ---------------------------------------------------------------------------
// The tool
// ---------------------------------------------------------------------------

const imageSchema = Type.Object({
  data: Type.String({ description: "Base64 image bytes (no data: prefix)" }),
  mimeType: Type.String({ description: "image/png or image/jpeg" }),
});

const exampleSchema = Type.Object({
  images: Type.Array(imageSchema, { minItems: 1 }),
  scenario: Type.Optional(Type.String({ description: "What the example shows, in a few words" })),
  analysis: Type.Optional(Type.String({ description: "The expert's analysis of the example (its experimental_significance answer)" })),
  parameters: Type.Optional(
    Type.Union([Type.String(), Type.Record(Type.String(), Type.Unknown())], {
      description: "The parameters read from the example plot, as JSON",
    }),
  ),
  status: Type.Optional(Type.String({ description: "The example's status code (its calibration_diagnosis answer)" })),
  suggested_range: Type.Optional(Type.String({ description: "The example's suggested range, or N/A" })),
});

const criteriaSchema = Type.Object({
  guidance: Type.Optional(Type.Array(Type.String(), { description: "Points the analysis should explain" })),
  parameters: Type.Optional(
    Type.Record(Type.String(), Type.String(), { description: "Parameters to extract: name to type, e.g. float" }),
  ),
  statuses: Type.Optional(
    Type.Record(Type.String(), Type.String(), { description: "Decision criteria: status code to criterion, SUCCESS first" }),
  ),
  range_format: Type.Optional(Type.String({ description: "Format of the suggested range for a failed status" })),
});

const questionSchema = Type.Union(QUESTIONS.map((question) => Type.Literal(question)));

const parameters = Type.Object({
  context: Type.String({
    description:
      "Experiment context the background cannot know: task name, target qubit/coupling, swept range, previous values",
  }),
  question: Type.Optional(
    Type.String({ description: "A specific point the analysis should address, on top of the standard questions" }),
  ),
  task_name: Type.Optional(
    Type.String({
      description:
        "The calibration task's name as the host knows it (e.g. CheckRabi). Lets the host supply the background and criteria for the experiment.",
    }),
  ),
  knowledge: Type.Optional(
    Type.String({
      description:
        "Normally omitted: the host supplies the experiment background for `task_name` (what is swept, what a successful result looks like). Fill only to override it with text you were given.",
    }),
  ),
  criteria: Type.Optional(criteriaSchema),
  images: Type.Optional(
    Type.Array(imageSchema, {
      description:
        "Normally omitted: the host supplies the newest figures of the conversation. Fill only with real base64 image bytes you were given; never with placeholders or descriptions.",
    }),
  ),
  max_images: Type.Optional(
    Type.Integer({
      minimum: 1,
      maximum: MAX_IMAGES,
      description:
        "How many of the newest figures the host should supply when `images` is omitted (default 1). Use 2 when an expected reference figure precedes the measured one, and describe their order in `context`.",
    }),
  ),
  use_examples: Type.Optional(
    Type.Boolean({
      description:
        "Set true only when the user asked to judge against labeled reference examples: the host then supplies its expert-labeled example plots for `task_name` (in-context examples). Default false.",
    }),
  ),
  examples: Type.Optional(
    Type.Array(exampleSchema, {
      maxItems: MAX_EXAMPLES,
      description:
        "Normally omitted: the host supplies labeled examples when `use_examples` is true. Each is one or more real figures with the expert's answers.",
    }),
  ),
  questions: Type.Optional(
    Type.Array(questionSchema, {
      minItems: 1,
      description: "The questions to ask (default: all six, in order).",
    }),
  ),
  dry_run: Type.Optional(
    Type.Boolean({
      description:
        "Build the prompts and return them without asking the model, to show what it would be sent. The figure may be omitted.",
    }),
  ),
  model: Type.Optional(
    Type.String({
      description:
        "Normally omitted: the evaluation model as `provider/modelId`, when the host offers several. It must be configured; otherwise the configured calibration VLM judges.",
    }),
  ),
});

/** Stored on the tool result; the host reads `diagnosis` without reparsing text. */
export interface EvaluationDetails {
  /** The model that judged the plot; absent when none could be resolved. */
  model?: ModelSpec;
  /** True when no calibration VLM was configured and the conversation's model judged instead. */
  fallback?: boolean;
  /** The parsed answers by question, plus `success`. */
  diagnosis?: Record<string, unknown> | null;
  /** Every answered question's text, as returned. */
  answers?: Partial<Record<Question, string>>;
  /** The questions asked, in order. */
  questions?: Question[];
  /** Questions asked that got no answer. */
  missing_keys?: Question[];
  /** Model calls made, retries included. */
  attempts?: number;
  /** "length" when a call hit the output budget; otherwise how the calls ended. */
  stop_reason?: string;
  /** Every model call made, by question: duration, stop reason, output tokens. */
  calls?: CallRecord[];
  /** The user turns the model was sent, one per question, so the host can show what it saw. */
  prompt?: string;
  /** The same turns by question. */
  prompts?: Partial<Record<Question, string>>;
  /** How many labeled examples were shown. */
  examples_used?: number;
  /** True when the prompts were built but the model was not asked. */
  dry_run?: boolean;
}

function failure(spec: ModelSpec | undefined, text: string): AgentToolResult<EvaluationDetails> {
  return {
    content: [{ type: "text", text: `qcal_evaluate: ${text}` }],
    details: spec ? { model: spec } : {},
    isError: true,
  };
}

export default function qcalevalExtension(pi: ExtensionAPI) {
  pi.registerTool<typeof parameters, EvaluationDetails>({
    name: "qcal_evaluate",
    label: "Evaluate Calibration Plot",
    description:
      "Send a calibration experiment plot to the calibration-evaluation VLM and return its diagnosis: technical description, outcome classification, significance, fit reliability, extracted parameters, and calibration status.",
    promptSnippet: "Diagnose a calibration plot with the dedicated calibration VLM",
    promptGuidelines: [
      "Use qcal_evaluate for every calibration figure you need to judge, instead of judging it yourself.",
      "Pass the task name and target as context so the diagnosis is specific; do not pass fitted values, the model reads the plot.",
      "Pass task_name when you know it: the host then supplies the background and criteria for that task.",
      "Set use_examples true only when the user asked for a judgement against labeled reference examples.",
      "Treat the returned diagnosis as the evaluation of record; add your own reasoning only on top of it.",
    ],
    parameters,
    async execute(
      _toolCallId: string,
      params: Static<typeof parameters>,
      signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ExtensionToolContext,
    ): Promise<AgentToolResult<EvaluationDetails>> {
      let resolved: EvaluationModel;
      try {
        resolved = resolveEvaluationModel(ctx.modelRegistry, ctx.model, params.model?.trim() || process.env.QCALEVAL_MODEL);
      } catch (error) {
        return failure(undefined, error instanceof Error ? error.message : String(error));
      }
      const dryRun = params.dry_run === true;
      if (!resolved.model && !dryRun) return failure(undefined, resolved.error);
      const spec: ModelSpec | undefined = resolved.model
        ? { provider: resolved.model.provider, modelId: resolved.model.id }
        : undefined;
      const images: ImageContent[] = (params.images ?? []).map((image) => ({
        type: "image",
        data: image.data,
        mimeType: image.mimeType,
      }));
      if (images.length === 0) {
        if (!dryRun) return failure(spec, "no plot was given. Pass the figure in `images` or fetch it first.");
        // The prompts are the same whatever the figure; a placeholder stands in.
        images.push({ type: "image", data: "", mimeType: "image/png" });
      }

      const requested = new Set<string>(params.questions ?? []);
      const questions: Question[] = requested.size > 0 ? QUESTIONS.filter((question) => requested.has(question)) : [...QUESTIONS];
      const input: PromptInput = {
        background: params.knowledge,
        context: params.context,
        question: params.question,
        criteria: params.criteria,
        images: images.map((image) => ({ data: image.data, mimeType: image.mimeType })),
        examples: params.examples ?? [],
      };
      const turns = new Map(questions.map((question) => [question, buildQuestionContent(question, input)]));
      const examplesUsed = fitExamples(input.examples ?? []).length;
      const prompts = Object.fromEntries(questions.map((question) => [question, turns.get(question)!.prompt])) as Partial<
        Record<Question, string>
      >;
      const prompt = promptRecord(questions.map((question) => ({ question, prompt: turns.get(question)!.prompt })));
      if (dryRun || !resolved.model) {
        return {
          content: [{ type: "text", text: prompt }],
          details: {
            ...(spec ? { model: spec } : {}),
            ...(resolved.model && resolved.fallback ? { fallback: true } : {}),
            dry_run: true,
            questions,
            prompt,
            prompts,
            ...(examplesUsed ? { examples_used: examplesUsed } : {}),
          },
        };
      }
      const { model, fallback } = resolved;
      const answers = await askQuestions(
        questions,
        (question) =>
          ctx.modelRegistry.complete(
            model,
            {
              messages: [
                {
                  role: "user",
                  content: turns.get(question)!.content.map((block) =>
                    block.type === "text"
                      ? { type: "text" as const, text: block.text }
                      : { type: "image" as const, data: block.data, mimeType: block.mimeType },
                  ),
                  timestamp: Date.now(),
                },
              ],
            },
            { signal, maxTokens: outputBudget(model) },
          ),
      );
      if (answers.missing.length === questions.length) {
        const error = Object.values(answers.errors)[0];
        return failure(spec, error ?? "the model answered none of the questions");
      }
      return {
        content: [{ type: "text", text: JSON.stringify(answers.diagnosis, null, 2) }],
        details: {
          model: spec,
          ...(fallback ? { fallback: true } : {}),
          diagnosis: answers.diagnosis,
          answers: answers.answers,
          questions: answers.questions,
          ...(answers.missing.length > 0 ? { missing_keys: answers.missing } : {}),
          attempts: answers.attempts,
          stop_reason: answers.stopReason,
          calls: answers.calls,
          prompt,
          prompts,
          ...(examplesUsed ? { examples_used: examplesUsed } : {}),
        },
        ...(answers.usage ? { usage: answers.usage } : {}),
      };
    },
  });
}
