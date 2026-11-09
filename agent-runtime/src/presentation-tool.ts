import type { JsonValue } from "@earendil-works/chord";
import type { ClassifierContext, ClassifierResult } from "@earendil-works/pi-ai";
import { defineTool } from "@earendil-works/pi-durable";
import { Type, type Static } from "typebox";

import { classifierLabel, selectClassifierModel, type ClassifierModels, type Log } from "./classifier-models.ts";
// See ui-tool.ts for why this path resolves in the image too.
import {
  UI_BLOCK_VERSION,
  UI_SPEC_LIMITS,
  uiSpecToText,
  validateUiSpec,
  type UiBlockPayload,
} from "../../ui/src/lib/copilotUiSpec.ts";

type JsonObject = ClassifierContext["state"];

/**
 * `present_results`: a fixed presentation of values the model already has,
 * chosen by a classifier model.
 *
 * The model passes the user's request and the values it read from QDash tool
 * results as typed records. A classifier (pi-ai `Models.classify`) picks one of
 * four presentations from the request and the shape of those records; the tool
 * then builds the matching json-render spec from the records alone, so every
 * value shown is one the model passed, unchanged. The classifier only picks the
 * layout: it never sees a value to compute and nothing it returns is shown.
 *
 * The classification runs as a nested call (`api.executeTool`) under a fixed
 * key, so it is journaled with the call: a rerun of this replay-safe tool after
 * a restart gets the committed result back instead of asking the classifier
 * again. The nested tool is not replay-safe, so one a restart cut off is not
 * retried; it ends as an error and the call falls back.
 *
 * Any failure to classify (no model, an error or timeout, an invalid answer,
 * a low winning probability) or records the chosen layout cannot hold falls back: no UI,
 * and the model is told to use `render_ui` or plain text, as without this tool.
 *
 * The tool exists only when classifier.yaml declares a usable model (the
 * first usable one is used); otherwise the runtime registers neither tool and
 * nothing changes. The classifier is called only when the chat calls the tool.
 */

export const PRESENT_TOOL = "present_results";
/** Internal nested tool behind the classification; never offered to the model. */
export const CLASSIFY_TOOL = "qdash.presentation.classify";
/** The nested call's key, fixed so a rerun reattaches to the committed classification. */
const CLASSIFY_KEY = "classify";

export const PRESENTATION_CATEGORIES = {
  calibration_summary:
    "An overview of calibration results: the current values or status of one or more qubits, couplings or a chip.",
  execution_comparison:
    "A side-by-side comparison of two or more executions, runs or points in time, value by value.",
  failure_list: "A list of failed or problematic tasks, qubits or executions and what went wrong.",
  text: "None of these: a short answer, an explanation, or values a table would not make clearer.",
} as const;
export type PresentationCategory = keyof typeof PRESENTATION_CATEGORIES;
const CATEGORY_LABELS = Object.keys(PRESENTATION_CATEGORIES) as PresentationCategory[];

// ---------------------------------------------------------------- config

export interface PresentationConfig {
  /** pi provider id of the classifier model, from classifier.yaml. */
  provider: string;
  /** Classifier model id, from classifier.yaml. */
  name: string;
  /** Lowest probability of the chosen category that is accepted. */
  minProbability: number;
  /** Lowest lead of the chosen category over the runner-up that is accepted. */
  minMargin: number;
  /** Longest wait for the classifier before falling back. */
  timeoutMs: number;
}

/**
 * When a chosen layout is accepted: the chosen category's probability and its
 * lead over the runner-up, and the longest wait for the classifier. With four
 * categories an uninformed answer gives each 0.25; 0.6 asks for a clear
 * majority and 0.2 for a lead no close second can match. Both are heuristics
 * for when a fixed layout is worth showing, not calibrated guarantees.
 */
export const PRESENTATION_DEFAULTS = { minProbability: 0.6, minMargin: 0.2, timeoutMs: 5_000 } as const;

/**
 * Offer `present_results` with the first usable model classifier.yaml
 * declares (see classifier-models.ts). Undefined, with the reason logged, when
 * the file declares none, is invalid, or none of its models is usable (no
 * endpoint, token or credentials): the chat then has no `present_results` and
 * renders as before. Never picks a model classifier.yaml does not declare.
 */
export function configurePresentation(classifiers: ClassifierModels, log: Log): PresentationConfig | undefined {
  const selected = selectClassifierModel(classifiers);
  if ("error" in selected) {
    log.log(`[agent-runtime] present_results not offered: ${selected.error}`);
    return undefined;
  }
  const { provider, name } = selected.model;
  const config = { provider, name, ...PRESENTATION_DEFAULTS };
  log.log(`[agent-runtime] present_results: classifier ${classifierLabel(config)}`);
  return config;
}

// ---------------------------------------------------------------- input

/** Bounds keep the classifier's input and the rendered spec small. */
export const PRESENTATION_LIMITS = {
  maxRecords: 50,
  maxValuesPerRecord: 10,
  maxSources: 8,
  maxRequestChars: 500,
} as const;

const STATUSES = ["ok", "warning", "failed", "unknown"] as const;
type RecordStatus = (typeof STATUSES)[number];

const label = (maxLength: number, description: string) => Type.String({ minLength: 1, maxLength, description });

export const PRESENT_PARAMETERS = Type.Object(
  {
    request: label(
      PRESENTATION_LIMITS.maxRequestChars,
      "The user's request this answers, quoted or closely paraphrased.",
    ),
    sources: Type.Array(label(64, "Tool name."), {
      minItems: 1,
      maxItems: PRESENTATION_LIMITS.maxSources,
      description: "Names of the QDash tools whose results the values below came from.",
    }),
    title: Type.Optional(label(120, "Short title, such as the chip and date.")),
    records: Type.Array(
      Type.Object(
        {
          subject: label(60, "What the record describes: a qubit (Q03), a coupling (Q03-Q04), or an execution id."),
          status: Type.Optional(
            Type.Unsafe<RecordStatus>({
              type: "string",
              enum: [...STATUSES],
              description: "Only a status a tool result reported.",
            }),
          ),
          message: Type.Optional(
            Type.String({ maxLength: 300, description: "A status or error message from a tool result." }),
          ),
          values: Type.Array(
            Type.Object(
              {
                name: label(40, "Parameter name, such as t1 or x90_fidelity."),
                value: Type.Union([Type.Number(), Type.String({ maxLength: 60 })]),
                unit: Type.Optional(Type.String({ maxLength: 16 })),
              },
              { additionalProperties: false },
            ),
            { maxItems: PRESENTATION_LIMITS.maxValuesPerRecord },
          ),
        },
        { additionalProperties: false },
      ),
      { minItems: 1, maxItems: PRESENTATION_LIMITS.maxRecords },
    ),
  },
  { additionalProperties: false },
);
export type PresentArgs = Static<typeof PRESENT_PARAMETERS>;
type PresentRecord = PresentArgs["records"][number];

// ---------------------------------------------------------------- classification

/** What the classifier sees: the request and the shape of the data, never a value. */
export function classifierState(args: PresentArgs): JsonObject {
  const names = [...new Set(args.records.flatMap((record) => record.values.map((value) => value.name)))];
  const statuses = [...new Set(args.records.map((record) => record.status).filter((s) => s !== undefined))];
  return {
    request: args.request.slice(0, PRESENTATION_LIMITS.maxRequestChars),
    ...(args.title ? { title: args.title } : {}),
    sources: args.sources,
    record_count: args.records.length,
    subjects: args.records.slice(0, 12).map((record) => record.subject),
    value_names: names.slice(0, 12),
    statuses: statuses as string[],
    has_messages: args.records.some((record) => Boolean(record.message)),
  };
}

export function classifierContext(state: JsonObject): ClassifierContext {
  return {
    state,
    questions: {
      category: {
        type: "choice",
        instructions:
          "A QDash Copilot user asked `request`, and the assistant retrieved data with the shape described by the other fields. Choose how the chat should present it.",
        criteria: { ...PRESENTATION_CATEGORIES },
      },
    },
  };
}

export type ClassificationDecision =
  | { outcome: "category"; category: PresentationCategory; probability: number; margin: number }
  | { outcome: "fallback"; reason: string; probability?: number; margin?: number };

/**
 * Turn a classifier result into a decision. Anything but a well-formed answer
 * whose top category clears both thresholds falls back.
 *
 * The decision reads only the answer's `probabilities`, the per-label
 * distribution pi-ai's `ClassifierChoiceAnswer` documents: the chosen label's
 * probability and its lead over the runner-up. The answer's `confidence` is
 * a separate service-defined score (Open-Jev reported 0.928 for a label whose
 * probability was 0.952) and is not used. Neither is a calibrated chance that
 * the layout is right.
 */
export function decideCategory(
  result: Pick<ClassifierResult, "stopReason" | "errorMessage" | "answers"> | undefined,
  thresholds: Pick<PresentationConfig, "minProbability" | "minMargin">,
): ClassificationDecision {
  if (!result) return { outcome: "fallback", reason: "no classifier result" };
  if (result.stopReason !== "stop") {
    return {
      outcome: "fallback",
      reason: `classifier ${result.stopReason}${result.errorMessage ? `: ${result.errorMessage.slice(0, 200)}` : ""}`,
    };
  }
  const answer = result.answers?.category;
  if (!answer || answer.type !== "choice" || !answer.probabilities) {
    return { outcome: "fallback", reason: "invalid classifier answer: no category choice" };
  }
  const probabilities = CATEGORY_LABELS.map((category) => answer.probabilities[category]);
  if (probabilities.some((p) => typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1)) {
    return { outcome: "fallback", reason: "invalid classifier answer: probabilities missing or out of range" };
  }
  // Allow rounding noise, but never normalize malformed service output ourselves.
  const total = probabilities.reduce((sum, probability) => sum + probability, 0);
  if (Object.keys(answer.probabilities).length !== CATEGORY_LABELS.length || Math.abs(total - 1) > 1e-6) {
    return { outcome: "fallback", reason: "invalid classifier answer: probabilities must sum to one over the known categories" };
  }
  if (!CATEGORY_LABELS.includes(answer.choice as PresentationCategory)) {
    return { outcome: "fallback", reason: `invalid classifier answer: unknown category ${JSON.stringify(answer.choice)}` };
  }
  const choice = answer.choice as PresentationCategory;
  const probability = answer.probabilities[choice]!;
  const runnerUp = Math.max(
    ...CATEGORY_LABELS.filter((category) => category !== choice).map((category) => answer.probabilities[category]!),
  );
  const margin = probability - runnerUp;
  if (margin < 0) {
    return { outcome: "fallback", reason: "invalid classifier answer: choice is not the most probable category" };
  }
  if (probability < thresholds.minProbability || margin < thresholds.minMargin) {
    return {
      outcome: "fallback",
      reason: `ambiguous classification (${choice} ${probability.toFixed(2)}, lead ${margin.toFixed(2)})`,
      probability,
      margin,
    };
  }
  return { outcome: "category", category: choice, probability, margin };
}

// ---------------------------------------------------------------- templates

type Cell = string | number | null;
type Element = { type: string; props: Record<string, unknown>; children: string[] };
type TemplateResult = { ok: true; spec: unknown } | { ok: false; reason: string };

const TONE: Record<RecordStatus, string> = { ok: "success", warning: "warning", failed: "error", unknown: "neutral" };
const DEFAULT_TITLE: Record<Exclude<PresentationCategory, "text">, string> = {
  calibration_summary: "Calibration summary",
  execution_comparison: "Execution comparison",
  failure_list: "Failures",
};

interface Column {
  name: string;
  /** Set when every value of the column has this unit, or none has one. */
  unit: string | undefined;
  /** Several units: each cell then carries its own. */
  mixed: boolean;
}

/** Value names in first-seen order, each with the unit its column header can carry. */
function columnsOf(records: readonly PresentRecord[]): Column[] {
  const units = new Map<string, Set<string>>();
  for (const record of records) {
    for (const { name, unit } of record.values) {
      if (!units.has(name)) units.set(name, new Set());
      units.get(name)!.add(unit ?? "");
    }
  }
  return [...units].map(([name, set]) => {
    const only = set.size === 1 ? [...set][0] : undefined;
    return { name, unit: only || undefined, mixed: set.size > 1 };
  });
}

const headerOf = (column: Column) => (column.unit ? `${column.name} (${column.unit})` : column.name);

/** A record's value for a column, unchanged; with its unit as text only when the column mixes units. */
function cellOf(record: PresentRecord, column: Column): Cell {
  const entry = record.values.find((value) => value.name === column.name);
  if (!entry) return null;
  if (column.mixed && entry.unit) return `${entry.value} ${entry.unit}`;
  return entry.value;
}

function provenance(sources: readonly string[]): string {
  return `Values as reported by the assistant from these tool results: ${sources.join(", ")}.`;
}

function frame(
  args: PresentArgs,
  category: Exclude<PresentationCategory, "text">,
  body: [string, Element][],
): { root: string; elements: Record<string, Element> } {
  const elements: [string, Element][] = [
    ["root", { type: "Card", props: { title: args.title ?? DEFAULT_TITLE[category] }, children: [...body.map(([id]) => id), "source"] }],
    ...body,
    ["source", { type: "Text", props: { text: provenance(args.sources), variant: "muted" }, children: [] }],
  ];
  return { root: "root", elements: Object.fromEntries(elements) };
}

function table(caption: string | undefined, columns: { key: string; label: string; align?: string }[], rows: Record<string, Cell>[]): Element {
  return { type: "Table", props: { ...(caption ? { caption } : {}), columns, rows }, children: [] };
}

const MAX_COLUMNS = UI_SPEC_LIMITS.maxTableColumns;

function summaryTemplate(args: PresentArgs): TemplateResult {
  const columns = columnsOf(args.records);
  if (args.records.length === 1) {
    const [record] = args.records;
    if (record.values.length === 0) return { ok: false, reason: "the record has no values" };
    const tone = record.status ? TONE[record.status] : undefined;
    const metrics: [string, Element][] = record.values.map((value, i) => [
      `m${i}`,
      {
        type: "Metric",
        props: {
          label: value.name,
          value: value.value,
          ...(value.unit ? { unit: value.unit } : {}),
          detail: record.subject,
          ...(tone ? { tone } : {}),
        },
        children: [],
      },
    ]);
    const body: [string, Element][] = [
      ["metrics", { type: "Stack", props: { direction: "horizontal" }, children: metrics.map(([id]) => id) }],
      ...metrics,
    ];
    if (record.message) {
      body.push(["message", { type: "Text", props: { text: record.message }, children: [] }]);
    }
    return { ok: true, spec: frame(args, "calibration_summary", body) };
  }
  const hasStatus = args.records.some((record) => record.status);
  const hasMessage = args.records.some((record) => record.message);
  const fixed = 1 + Number(hasStatus) + Number(hasMessage);
  if (columns.length + fixed > MAX_COLUMNS) {
    return { ok: false, reason: `${columns.length} distinct values do not fit a ${MAX_COLUMNS}-column table` };
  }
  const tableColumns = [
    { key: "subject", label: "Subject" },
    ...(hasStatus ? [{ key: "status", label: "Status" }] : []),
    ...columns.map((column, i) => ({ key: `v${i}`, label: headerOf(column), align: "right" })),
    ...(hasMessage ? [{ key: "message", label: "Message" }] : []),
  ];
  const rows = args.records.map((record) => ({
    subject: record.subject,
    ...(hasStatus ? { status: record.status ?? null } : {}),
    ...Object.fromEntries(columns.map((column, i) => [`v${i}`, cellOf(record, column)])),
    ...(hasMessage ? { message: record.message || null } : {}),
  }));
  return { ok: true, spec: frame(args, "calibration_summary", [["table", table(undefined, tableColumns, rows)]]) };
}

function comparisonTemplate(args: PresentArgs): TemplateResult {
  const { records } = args;
  if (records.length < 2) return { ok: false, reason: "a comparison needs at least two records" };
  if (records.length + 1 > MAX_COLUMNS) {
    return { ok: false, reason: `${records.length} records do not fit a ${MAX_COLUMNS}-column comparison` };
  }
  const columns = columnsOf(records);
  if (columns.length === 0) return { ok: false, reason: "the records have no values to compare" };
  const tableColumns = [
    { key: "name", label: "Value" },
    ...records.map((record, i) => ({ key: `r${i}`, label: record.subject, align: "right" })),
  ];
  const rows: Record<string, Cell>[] = columns.map((column) => ({
    name: headerOf(column),
    ...Object.fromEntries(records.map((record, i) => [`r${i}`, cellOf(record, column)])),
  }));
  if (records.some((record) => record.status)) {
    rows.unshift({ name: "Status", ...Object.fromEntries(records.map((record, i) => [`r${i}`, record.status ?? null])) });
  }
  return { ok: true, spec: frame(args, "execution_comparison", [["table", table(undefined, tableColumns, rows)]]) };
}

function failureTemplate(args: PresentArgs): TemplateResult {
  const failing = args.records.filter((record) => record.status === "failed" || record.status === "warning");
  if (failing.length === 0) return { ok: false, reason: "no record has a failed or warning status" };
  const columns = columnsOf(failing);
  if (columns.length + 3 > MAX_COLUMNS) {
    return { ok: false, reason: `${columns.length} distinct values do not fit a ${MAX_COLUMNS}-column table` };
  }
  const anyFailed = failing.some((record) => record.status === "failed");
  const tableColumns = [
    { key: "subject", label: "Subject" },
    { key: "status", label: "Status" },
    { key: "message", label: "Message" },
    ...columns.map((column, i) => ({ key: `v${i}`, label: headerOf(column), align: "right" })),
  ];
  const rows = failing.map((record) => ({
    subject: record.subject,
    status: record.status ?? null,
    message: record.message || null,
    ...Object.fromEntries(columns.map((column, i) => [`v${i}`, cellOf(record, column)])),
  }));
  const alert: Element = {
    type: "Alert",
    props: {
      tone: anyFailed ? "error" : "warning",
      message: "Records the tool results report as failed or with a warning.",
    },
    children: [],
  };
  return {
    ok: true,
    spec: frame(args, "failure_list", [
      ["alert", alert],
      ["table", table(undefined, tableColumns, rows)],
    ]),
  };
}

/** The spec of a category built from `args` alone, or why the records do not fit it. */
export function renderTemplate(category: Exclude<PresentationCategory, "text">, args: PresentArgs): TemplateResult {
  for (const record of args.records) {
    const names = new Set<string>();
    for (const value of record.values) {
      if (names.has(value.name)) {
        return { ok: false, reason: `duplicate value name ${JSON.stringify(value.name)} in record ${JSON.stringify(record.subject)}; use distinct names or render_ui to preserve all values` };
      }
      names.add(value.name);
    }
  }
  switch (category) {
    case "calibration_summary":
      return summaryTemplate(args);
    case "execution_comparison":
      return comparisonTemplate(args);
    case "failure_list":
      return failureTemplate(args);
  }
}

// ---------------------------------------------------------------- tools

const CLASSIFY_PARAMETERS = Type.Object({ state: Type.Record(Type.String(), Type.Unknown()) });

/** The internal tool that asks the configured classifier, bounded by `timeoutMs`. Never rejects. */
function buildClassifyTool(config: PresentationConfig) {
  const label = classifierLabel(config);
  return defineTool({
    name: CLASSIFY_TOOL,
    description: "Classify how present_results lays out its records. Internal.",
    parameters: CLASSIFY_PARAMETERS,
    structuredOutputSchema: Type.Unknown(),
    callers: ["tools"],
    // Not replay-safe: a classification a restart cut off is not asked again.
    execute: async (args, api, context) => {
      const model = api.models.getModelOfType("classifier", config.provider, config.name);
      if (!model) {
        const errorMessage = `classifier model ${label} is not in the model catalog`;
        return {
          output: [{ type: "text" as const, text: errorMessage }],
          structuredOutput: { stopReason: "unavailable", errorMessage, answers: {} },
          isError: true,
        };
      }
      const timeout = AbortSignal.timeout(config.timeoutMs);
      const signal = context.abortSignal ? AbortSignal.any([timeout, context.abortSignal]) : timeout;
      let timer: ReturnType<typeof setTimeout> | undefined;
      // `classify()` never rejects and honours `signal`; the race also bounds an
      // implementation that ignores it.
      const late = new Promise<ClassifierResult>((resolve) => {
        timer = setTimeout(
          () =>
            resolve({
              api: model.api,
              provider: model.provider,
              model: model.id,
              answers: {},
              stopReason: "aborted",
              errorMessage: `timed out after ${config.timeoutMs} ms`,
              timestamp: Date.now(),
            }),
          config.timeoutMs + 50,
        );
      });
      let result: ClassifierResult;
      try {
        result = await Promise.race([
          api.models.classify(model, classifierContext(args.state as JsonObject), {
            signal,
            ...(context.telemetry ? { telemetry: context.telemetry } : {}),
          }),
          late,
        ]);
      } finally {
        clearTimeout(timer);
      }
      if (result.stopReason === "aborted" && timeout.aborted && !result.errorMessage?.includes("timed out")) {
        result = { ...result, errorMessage: `timed out after ${config.timeoutMs} ms` };
      }
      const ok = result.stopReason === "stop";
      return {
        output: [{ type: "text" as const, text: ok ? `classified with ${label}` : `classifier ${result.stopReason}` }],
        structuredOutput: JSON.parse(
          JSON.stringify({ stopReason: result.stopReason, errorMessage: result.errorMessage, answers: result.answers }),
        ) as JsonValue,
        ...(ok ? {} : { isError: true }),
        ...(result.usage ? { usage: result.usage } : {}),
      };
    },
  });
}

const DESCRIPTION = [
  "Show values you already read from QDash tool results in a fixed, read-only layout chosen for the user's request: a calibration summary, an execution comparison, or a failure list.",
  "Pass the user's request, the names of the tools the values came from, and one record per qubit, coupling or execution with the values exactly as the tools returned them. Never compute, estimate or round values here; pass only what a tool returned, with its status and message when it reported one.",
  "A classifier picks the layout; the values shown are only the ones you pass. When no layout fits, the result says so: then use `render_ui` for a custom view or answer in text. Still answer in text either way.",
].join("\n");

export interface PresentationDetails {
  classifier: string;
  outcome: "template" | "text" | "fallback";
  category?: PresentationCategory;
  probability?: number;
  margin?: number;
  reason?: string;
}

function textResult(text: string, presentation: PresentationDetails, ui?: UiBlockPayload) {
  return {
    output: [{ type: "text" as const, text }],
    details: { presentation, ...(ui ? { ui } : {}) } as unknown as JsonValue,
  };
}

const FALLBACK_ADVICE =
  "No UI was shown. If a view would help, compose one with `render_ui` from the same values; otherwise answer in text.";

/**
 * `present_results` and its internal classifier tool, for the classifier
 * configurePresentation picked.
 */
export function buildPresentationTools(config: PresentationConfig) {
  const classifier = classifierLabel(config);
  const presentTool = defineTool({
    name: PRESENT_TOOL,
    description: DESCRIPTION,
    parameters: PRESENT_PARAMETERS,
    callers: ["model"],
    // A rerun gets the journaled classification back (fixed key) and builds the
    // same spec from the same arguments.
    replay: "safe",
    execute: async (args, api, context) => {
      // The named sources must be tools this chat offers, and not the
      // presentation tools themselves.
      const offered = new Set((await api.agent(context)).tools.map((tool) => tool.name));
      const unknown = args.sources.filter(
        (name) => !offered.has(name) || name === PRESENT_TOOL || name === "render_ui" || name === "render_chart",
      );
      if (unknown.length > 0) {
        throw new Error(
          `present_results sources must name the QDash tools whose results hold the values; not data tools here: ${unknown.join(", ")}`,
        );
      }

      const nested = await api.executeTool(CLASSIFY_TOOL, { state: classifierState(args) as unknown as JsonValue }, context, {
        key: CLASSIFY_KEY,
        progress: false,
      });
      const result = nested.structuredOutput as ClassifierResult | undefined;
      const decision = result
        ? decideCategory(result, config)
        : {
            outcome: "fallback" as const,
            reason: `classifier did not finish: ${nested.diagnostics.map((d) => d.message).join("; ").slice(0, 200) || "no result"}`,
          };
      const base = { classifier };
      if (decision.outcome === "fallback") {
        const { reason, probability, margin } = decision;
        return textResult(`No layout chosen (${reason}). ${FALLBACK_ADVICE}`, {
          ...base,
          outcome: "fallback",
          reason,
          ...(probability === undefined ? {} : { probability, margin }),
        });
      }
      const { category, probability, margin } = decision;
      if (category === "text") {
        return textResult(
          "The request is best answered in text: no UI was shown. Answer in text with the values and where they came from.",
          { ...base, outcome: "text", category, probability, margin },
        );
      }
      const built = renderTemplate(category, args);
      const valid = built.ok ? validateUiSpec(built.spec) : undefined;
      if (!built.ok || !valid?.ok) {
        const reason = built.ok ? `template spec invalid: ${valid!.ok ? "" : valid!.errors.slice(0, 3).join("; ")}` : built.reason;
        return textResult(`No ${category} layout (${reason}). ${FALLBACK_ADVICE}`, {
          ...base,
          outcome: "fallback",
          category,
          probability,
          margin,
          reason,
        });
      }
      const ui: UiBlockPayload = { version: UI_BLOCK_VERSION, spec: valid.spec, fallback: uiSpecToText(valid.spec) };
      return textResult(
        `Shown in the chat as a ${category.replace("_", " ")} of the values you passed. Do not repeat them in full; summarize what they mean and say where they came from.`,
        { ...base, outcome: "template", category, probability, margin },
        ui,
      );
    },
  });
  return [presentTool, buildClassifyTool(config)] as const;
}

/** System prompt guideline for a chat that has `present_results`. */
export const PRESENTATION_GUIDELINE =
  "- To show values from tool results as a calibration summary, an execution comparison, or a failure list, call `present_results` with the user's request and the values exactly as the tools returned them; it picks the layout. Use `render_ui` when it finds no layout or you need another view.";
