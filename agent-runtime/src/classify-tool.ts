import type { JsonValue } from "@earendil-works/chord";
import type { ClassifierContext, ClassifierModel, ClassifierResult, ClassifierApi } from "@earendil-works/pi-ai";
import { defineTool } from "@earendil-works/pi-durable";
import { Type, type Static } from "typebox";

import { classifierLabel, selectClassifierModel, type ClassifierModels, type Log } from "./classifier-models.ts";

/**
 * `classify`: the chat model asks the configured classifier model to pick one
 * of a few categories it defines, when an answer turns on such a judgment.
 *
 * The model passes a question, two to eight candidate categories with one-line
 * descriptions, and the facts the decision rests on. The tool asks the first
 * usable classifier of classifier.yaml (pi-ai `Models.classify`, one choice
 * question) and returns the chosen category with its probability, its lead
 * over the runner-up and the full distribution. It only answers the question:
 * it shows nothing in the chat and supplies no value. The chat uses it for
 * intent, cause triage, the next check and the choice of a custom view (see
 * CLASSIFY_GUIDELINE); the fixed layouts are classified by `present_results`
 * itself.
 *
 * A clear answer (see CLASSIFY_DEFAULTS) is `classified`; a split one is
 * `ambiguous` and still reported, so the model can weigh it. A classifier that
 * is unavailable, errors, times out, is cancelled or answers malformed ends the
 * call as an error with a fixed reason; the provider's own message is only
 * logged, never returned to the model or the chat.
 *
 * Not replay-safe: a classification a restart cut off ends as an error rather
 * than being asked again.
 */

export const CLASSIFY_CHAT_TOOL = "classify";

export interface ClassifyConfig {
  /** pi provider id of the classifier model, from classifier.yaml. */
  provider: string;
  /** Classifier model id, from classifier.yaml. */
  name: string;
  /** Lowest probability of the chosen category that reads as `classified`. */
  minProbability: number;
  /** Lowest lead of the chosen category over the runner-up that reads as `classified`. */
  minMargin: number;
  /** Longest wait for the classifier before the call fails. */
  timeoutMs: number;
}

/**
 * When an answer counts as clear rather than ambiguous. Heuristics, as
 * PRESENTATION_DEFAULTS: a clear majority and a lead no close second matches,
 * not a calibrated chance of being right.
 */
export const CLASSIFY_DEFAULTS = { minProbability: 0.6, minMargin: 0.2, timeoutMs: 5_000 } as const;

/** Bounds keep the classifier's input, the tool result and the chat's step small. */
export const CLASSIFY_LIMITS = {
  minCategories: 2,
  maxCategories: 8,
  maxQuestionChars: 300,
  maxCategoryNameChars: 40,
  maxCategoryDescriptionChars: 200,
  maxContextChars: 4_000,
} as const;

/**
 * Offer `classify` with the first usable model classifier.yaml declares.
 * Undefined, with the reason logged, when there is none: the chat then has no
 * `classify` tool.
 */
export function configureClassify(classifiers: ClassifierModels, log: Log): ClassifyConfig | undefined {
  const selected = selectClassifierModel(classifiers);
  if ("error" in selected) {
    log.log(`[agent-runtime] classify not offered: ${selected.error}`);
    return undefined;
  }
  const { provider, name } = selected.model;
  const config = { provider, name, ...CLASSIFY_DEFAULTS };
  log.log(`[agent-runtime] classify: classifier ${classifierLabel(config)}`);
  return config;
}

// ---------------------------------------------------------------- input

const CATEGORY_NAME = new RegExp(`^[a-z][a-z0-9_]{0,${CLASSIFY_LIMITS.maxCategoryNameChars - 1}}$`);

export const CLASSIFY_PARAMETERS = Type.Object(
  {
    question: Type.String({
      minLength: 1,
      maxLength: CLASSIFY_LIMITS.maxQuestionChars,
      description: "What to decide, as one question about the context, such as \"What most likely caused this fit failure?\"",
    }),
    categories: Type.Array(
      Type.Object(
        {
          name: Type.String({
            pattern: CATEGORY_NAME.source,
            description: "Short snake_case id, such as readout_problem.",
          }),
          description: Type.String({
            minLength: 1,
            maxLength: CLASSIFY_LIMITS.maxCategoryDescriptionChars,
            description: "One line saying when this category applies.",
          }),
        },
        { additionalProperties: false },
      ),
      {
        minItems: CLASSIFY_LIMITS.minCategories,
        maxItems: CLASSIFY_LIMITS.maxCategories,
        description: "The candidate answers, mutually exclusive; include an `other` or `unclear` category when none may fit.",
      },
    ),
    context: Type.String({
      minLength: 1,
      maxLength: CLASSIFY_LIMITS.maxContextChars,
      description:
        "The facts the decision rests on, copied from tool results or the user's words: messages, statuses, values with units. Only what is relevant; no secrets.",
    }),
  },
  { additionalProperties: false },
);
export type ClassifyArgs = Static<typeof CLASSIFY_PARAMETERS>;

/** The classifier request for `args`: the context as state, one choice question over the categories. */
export function classifyContext(args: ClassifyArgs): ClassifierContext {
  return {
    state: { context: args.context },
    questions: {
      category: {
        type: "choice",
        instructions: args.question,
        criteria: Object.fromEntries(args.categories.map((category) => [category.name, category.description])),
      },
    },
  };
}

// ---------------------------------------------------------------- the request

/**
 * Ask `model`, bounded by `timeoutMs` and the call's own cancellation. Never
 * rejects: `classify()` resolves with an error result, and a race bounds an
 * implementation that ignores the signal. `timedOut` tells a timeout from a
 * cancellation.
 */
export async function classifyWithin(
  models: {
    classify(model: ClassifierModel<ClassifierApi>, context: ClassifierContext, options?: object): Promise<ClassifierResult>;
  },
  model: ClassifierModel<ClassifierApi>,
  request: ClassifierContext,
  timeoutMs: number,
  context: { abortSignal?: AbortSignal; telemetry?: unknown },
): Promise<{ result: ClassifierResult; timedOut: boolean }> {
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = context.abortSignal ? AbortSignal.any([timeout, context.abortSignal]) : timeout;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let raceTimedOut = false;
  const late = new Promise<ClassifierResult>((resolve) => {
    timer = setTimeout(() => {
      raceTimedOut = true;
      resolve({
        api: model.api,
        provider: model.provider,
        model: model.id,
        answers: {},
        stopReason: "aborted",
        errorMessage: `timed out after ${timeoutMs} ms`,
        timestamp: Date.now(),
      });
    }, timeoutMs + 50);
  });
  let result: ClassifierResult;
  try {
    result = await Promise.race([
      models.classify(model, request, { signal, ...(context.telemetry ? { telemetry: context.telemetry } : {}) }),
      late,
    ]);
  } finally {
    clearTimeout(timer);
  }
  const timedOut =
    result.stopReason === "aborted" && (raceTimedOut || (timeout.aborted && !context.abortSignal?.aborted));
  if (timedOut && !result.errorMessage?.includes("timed out")) {
    result = { ...result, errorMessage: `timed out after ${timeoutMs} ms` };
  }
  return { result, timedOut };
}

// ---------------------------------------------------------------- the decision

export interface CategoryProbability {
  category: string;
  probability: number;
}

/** What the chat shows of a classification (`details.classification`). Never its input. */
export interface ClassificationDetails {
  /** `provider/model` of the classifier from classifier.yaml. */
  classifier: string;
  /** `classified`: a clear answer; `ambiguous`: an answer below the thresholds; `failed`: none. */
  outcome: "classified" | "ambiguous" | "failed";
  category?: string;
  probability?: number;
  margin?: number;
  /** Every candidate's probability, highest first; at most CLASSIFY_LIMITS.maxCategories. */
  probabilities?: CategoryProbability[];
  /** Why there is no answer, when `failed`: one of a fixed set of phrases. */
  reason?: string;
}

export type ClassifyDecision =
  | Omit<ClassificationDetails, "classifier" | "reason"> & { outcome: "classified" | "ambiguous" }
  | { outcome: "failed"; reason: string };

/**
 * Read a classifier result for `categories`. The decision uses the answer's
 * `probabilities` only (see decideCategory in presentation-tool.ts for why not
 * `confidence`). Any malformed answer fails with a fixed reason.
 */
export function decideClassification(
  result: Pick<ClassifierResult, "stopReason" | "answers">,
  categories: readonly string[],
  thresholds: Pick<ClassifyConfig, "minProbability" | "minMargin">,
): ClassifyDecision {
  if (result.stopReason !== "stop") return { outcome: "failed", reason: "classifier request failed" };
  const invalid = { outcome: "failed" as const, reason: "invalid classifier answer" };
  const answer = result.answers?.category;
  if (!answer || answer.type !== "choice" || !answer.probabilities) return invalid;
  const values = categories.map((category) => answer.probabilities[category]);
  if (values.some((p) => typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1)) return invalid;
  const total = values.reduce((sum, p) => sum + p, 0);
  if (Object.keys(answer.probabilities).length !== categories.length || Math.abs(total - 1) > 1e-6) return invalid;
  if (!categories.includes(answer.choice)) return invalid;
  const ranked = categories
    .map((category, i) => ({ category, probability: values[i]! }))
    .sort((a, b) => b.probability - a.probability);
  const probability = answer.probabilities[answer.choice]!;
  const runnerUp = Math.max(...ranked.filter((entry) => entry.category !== answer.choice).map((entry) => entry.probability));
  const margin = probability - runnerUp;
  if (margin < 0) return invalid;
  const clear = probability >= thresholds.minProbability && margin >= thresholds.minMargin;
  return {
    outcome: clear ? "classified" : "ambiguous",
    category: answer.choice,
    probability,
    margin,
    probabilities: ranked,
  };
}

/** The fixed reason a failed request shows; never the provider's message. */
function failureReason(result: ClassifierResult, timedOut: boolean, timeoutMs: number): string {
  if (timedOut) return `timed out after ${timeoutMs / 1000} s`;
  if (result.stopReason === "aborted") return "cancelled";
  return "classifier request failed";
}

const round = (value: number) => Math.round(value * 1000) / 1000;

const DESCRIPTION = [
  "Ask a classifier model to choose one of a few categories you define, when your next step depends on such a judgment and neither a tool result nor a simple rule settles it: what kind of request a message is, which kind of problem the evidence points to, which check to run next, or which custom view suits values no fixed layout covers.",
  "Pass one question, 2-8 mutually exclusive categories (snake_case name and a one-line description; add `other` or `unclear` when none may fit), and the relevant facts from tool results or the user as context.",
  "The result names the chosen category with its probability, its lead over the runner-up and every category's probability. `ambiguous` means no clear winner: treat it as weak evidence or ask the user. It is a model's judgment, not a QDash fact: weigh it against the data and say so when you rely on it. It shows nothing to the user and supplies no value to show; for a calibration summary, an execution comparison or a failure list call `present_results`, which classifies the layout itself.",
].join("\n");

/** The `classify` tool for the classifier configureClassify picked. */
export function buildClassifyChatTool(config: ClassifyConfig, log: Log = console) {
  const classifier = classifierLabel(config);
  return defineTool({
    name: CLASSIFY_CHAT_TOOL,
    description: DESCRIPTION,
    parameters: CLASSIFY_PARAMETERS,
    callers: ["model"],
    execute: async (args, api, context) => {
      const names = args.categories.map((category) => category.name);
      if (new Set(names).size !== names.length) {
        throw new Error("classify categories must have distinct names");
      }
      const failed = (reason: string) => ({
        output: [{ type: "text" as const, text: `Classification failed (${reason}). Decide from the evidence yourself and say the classifier gave no answer.` }],
        details: { classification: { classifier, outcome: "failed", reason } satisfies ClassificationDetails } as unknown as JsonValue,
        isError: true,
      });
      const model = api.models.getModelOfType("classifier", config.provider, config.name);
      if (!model) return failed("classifier unavailable");
      const { result, timedOut } = await classifyWithin(
        api.models,
        model as ClassifierModel<ClassifierApi>,
        classifyContext(args),
        config.timeoutMs,
        context,
      );
      if (result.stopReason !== "stop") {
        if (result.errorMessage) {
          log.warn(`[agent-runtime] classify via ${classifier}: ${result.stopReason}: ${result.errorMessage.slice(0, 200)}`);
        }
        return { ...failed(failureReason(result, timedOut, config.timeoutMs)), ...(result.usage ? { usage: result.usage } : {}) };
      }
      const decision = decideClassification(result, names, config);
      if (decision.outcome === "failed") return failed(decision.reason);
      const { outcome, category, probability, margin, probabilities } = decision;
      const details: ClassificationDetails = {
        classifier,
        outcome,
        category,
        probability: round(probability!),
        margin: round(margin!),
        probabilities: probabilities!.map((entry) => ({ category: entry.category, probability: round(entry.probability) })),
      };
      const distribution = details.probabilities!.map((entry) => `${entry.category} ${entry.probability}`).join(", ");
      const verdict =
        outcome === "classified"
          ? `Classified as ${category} (probability ${details.probability}, lead ${details.margin}).`
          : `Ambiguous: ${category} leads only weakly (probability ${details.probability}, lead ${details.margin}); treat it as weak evidence or ask the user.`;
      return {
        output: [{ type: "text" as const, text: `${verdict} Probabilities: ${distribution}. Classifier: ${classifier}.` }],
        details: { classification: details } as unknown as JsonValue,
        ...(result.usage ? { usage: result.usage } : {}),
      };
    },
  });
}

/** System prompt guideline for a chat that has `classify`. */
export const CLASSIFY_GUIDELINE = [
  "- Call `classify` whenever your next step turns on a judgment between a few options that the evidence does not settle by itself; a call is short and bounded by a timeout, so use it rather than guessing. Typical uses:",
  "  - Intent: which kind of request an ambiguous message is (such as status lookup, trend, comparison, or troubleshooting), before choosing tools.",
  "  - Cause triage: which kind of problem the statuses, messages and values you read point to (such as readout, drive, frequency drift, fit failure, or unclear).",
  "  - Next investigation: which of a few checks you could run next is most likely to explain the problem.",
  "  - Presentation: which custom view (`render_ui` metric cards, comparison table or status alert, `render_chart`, or text) suits values the fixed layouts do not cover.",
  "  Skip it when a tool result, a threshold, a status, or the user's words already decide. Do not classify a layout `present_results` offers; call `present_results` directly, as it classifies on its own. Pass only facts you read; the classifier picks a category and never supplies a value to show. Its answer is evidence, not authority: weigh it against the data and say when you rely on it, treat `ambiguous` as weak evidence or ask with `ask_user`, and decide yourself when it fails. A classification never approves a write tool or replaces its approval card.",
].join("\n");
