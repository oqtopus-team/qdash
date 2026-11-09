import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createProvider, fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";

import {
  CLASSIFY_CHAT_TOOL,
  CLASSIFY_GUIDELINE,
  buildClassifyChatTool,
  classifyContext,
  classifyWithin,
  configureClassify,
  decideClassification,
} from "../src/classify-tool.ts";
import { configureClassifierModels } from "../src/classifier-models.ts";
import { toNdjsonEvents } from "../src/events.ts";
import { PRESENT_TOOL, PRESENTATION_GUIDELINE } from "../src/presentation-tool.ts";
import { buildSystemPrompt } from "../src/prompt.ts";
import { ViewEventStream } from "../src/view-events.ts";

const config = (overrides = {}) => ({
  provider: "test-classifier",
  name: "jev",
  minProbability: 0.6,
  minMargin: 0.2,
  timeoutMs: 2_000,
  ...overrides,
});

const args = {
  question: "What most likely caused this fit failure?",
  categories: [
    { name: "readout_problem", description: "The readout signal is too weak or noisy." },
    { name: "drive_problem", description: "The drive amplitude or frequency is off." },
    { name: "unclear", description: "The evidence does not point to either." },
  ],
  context: "Q04 rabi: fit did not converge; readout SNR 0.8; amplitude 0.12.",
};
const names = args.categories.map((category) => category.name);

const answer = (choice, probabilities) => ({
  stopReason: "stop",
  answers: { category: { type: "choice", choice, probabilities, confidence: 0.5 } },
});

function classifierProvider(classify) {
  return createProvider({
    id: "test-classifier",
    auth: { apiKey: { name: "test", resolve: async () => ({ auth: { apiKey: "k" } }) } },
    models: [
      {
        type: "classifier",
        id: "jev",
        name: "Jev",
        api: "mock-classify",
        provider: "test-classifier",
        baseUrl: "http://classifier.invalid",
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 32768,
      },
    ],
    classifiers: { "mock-classify": { classify } },
  });
}

/** A chat whose model calls `classify` once with `callArgs`, then answers. */
async function openChat({ classify, classifyConfig = config(), callArgs = args, log }) {
  const calls = [];
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  models.setProvider(
    classifierProvider(async (model, context, options) => {
      calls.push({ model: `${model.provider}/${model.id}`, context });
      return classify(model, context, options);
    }),
  );
  const model = faux.getModel();
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall(CLASSIFY_CHAT_TOOL, callArgs, { id: "c1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage(fauxText("Most likely a readout problem.")),
  ]);
  const registry = createRegistry();
  registry.install({ name: "test", tools: [buildClassifyChatTool(classifyConfig, log ?? { log() {}, warn() {}, error() {} })] });
  const context = BACKGROUND_CONTEXT;
  const harness = await Harness.open(new MemoryStorage(), { models, registry }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return { harness, conversation, context, calls };
}

async function runTurn(options) {
  const chat = await openChat(options);
  try {
    const submission = await chat.conversation.submit({ type: "input", content: "why did Q04 fail?" }, chat.context);
    const settled = await submission.wait(chat.context);
    const view = await chat.conversation.context(chat.context);
    const result = view.entries
      .filter((entry) => ToolResultEntry.is(entry))
      .map((entry) => entry.model[0])
      .find((message) => message?.role === "toolResult" && message.toolName === CLASSIFY_CHAT_TOOL);
    return { settled, result, calls: chat.calls };
  } finally {
    await chat.harness.close(chat.context);
  }
}

test("classify is offered with the first usable classifier, and only then", () => {
  const runtime = {
    getProvider: () => undefined,
    registerNativeProvider: () => {},
    getModelOfType: (_type, provider, id) => (`${provider}/${id}` === "typesafe/jev-latest" ? {} : undefined),
    hasConfiguredAuth: (provider) => provider === "typesafe",
  };
  const quiet = { log() {}, warn() {}, error() {} };
  const yaml = "classifier_models:\n  - provider: typesafe\n    name: jev-latest\n";
  assert.deepEqual(configureClassify(configureClassifierModels(yaml, runtime, {}, quiet), quiet), {
    provider: "typesafe",
    name: "jev-latest",
    minProbability: 0.6,
    minMargin: 0.2,
    timeoutMs: 5000,
  });
  assert.equal(configureClassify(configureClassifierModels(undefined, runtime, {}, quiet), quiet), undefined);
  assert.doesNotMatch(buildSystemPrompt("en", "en"), /`classify`/);
  assert.match(buildSystemPrompt("en", "en", [], null, null, false, null, CLASSIFY_GUIDELINE), /`classify`/);
});

test("the guideline asks for classify at concrete decision points and keeps its limits", () => {
  // Proactive: no blanket restraint, and the four decision points it serves.
  assert.doesNotMatch(CLASSIFY_GUIDELINE, /routinely|choose a layout/);
  assert.match(CLASSIFY_GUIDELINE, /^- Call `classify` whenever your next step turns on a judgment/);
  for (const use of ["Intent:", "Cause triage:", "Next investigation:", "Presentation:"]) {
    assert.ok(CLASSIFY_GUIDELINE.includes(`  - ${use}`), use);
  }
  // Custom views only: the fixed layouts stay with present_results, classified once.
  assert.match(CLASSIFY_GUIDELINE, /`render_ui`.*`render_chart`.*fixed layouts do not cover/);
  assert.match(CLASSIFY_GUIDELINE, /Do not classify a layout `present_results` offers; call `present_results` directly/);
  // Simple decisions, values, uncertainty, failure and approval stay with the chat.
  assert.match(CLASSIFY_GUIDELINE, /Skip it when a tool result, a threshold, a status, or the user's words already decide/);
  assert.match(CLASSIFY_GUIDELINE, /never supplies a value to show/);
  assert.match(CLASSIFY_GUIDELINE, /evidence, not authority/);
  assert.match(CLASSIFY_GUIDELINE, /`ambiguous` as weak evidence or ask with `ask_user`/);
  assert.match(CLASSIFY_GUIDELINE, /decide yourself when it fails/);
  assert.match(CLASSIFY_GUIDELINE, /never approves a write tool or replaces its approval card/);

  // The tool description matches: it serves custom-view choice and leaves the fixed layouts alone.
  const tool = buildClassifyChatTool(config(), { log() {}, warn() {}, error() {} });
  assert.match(tool.description, /which custom view suits values no fixed layout covers/);
  assert.match(tool.description, /supplies no value to show; for a calibration summary.*call `present_results`/);
  assert.doesNotMatch(tool.description, /does not choose a layout/);

  // Both guidelines sit in the prompt's guideline list, presentation first.
  const prompt = buildSystemPrompt("en", "en", [], null, null, false, PRESENTATION_GUIDELINE, CLASSIFY_GUIDELINE);
  const at = prompt.indexOf(CLASSIFY_GUIDELINE);
  assert.ok(prompt.indexOf(PRESENTATION_GUIDELINE) > prompt.indexOf("Guidelines:"));
  assert.ok(at > prompt.indexOf(PRESENTATION_GUIDELINE));
  assert.ok(at < prompt.indexOf("call `ask_user`"));
});

test("the classifier gets the context as state and one choice question over the categories", () => {
  assert.deepEqual(classifyContext(args), {
    state: { context: args.context },
    questions: {
      category: {
        type: "choice",
        instructions: args.question,
        criteria: Object.fromEntries(args.categories.map((c) => [c.name, c.description])),
      },
    },
  });
});

test("decideClassification tells clear, ambiguous and malformed answers apart", () => {
  const t = { minProbability: 0.6, minMargin: 0.2 };
  const clear = decideClassification(answer("readout_problem", { readout_problem: 0.8, drive_problem: 0.15, unclear: 0.05 }), names, t);
  assert.equal(clear.outcome, "classified");
  assert.deepEqual(clear.probabilities.map((p) => p.category), ["readout_problem", "drive_problem", "unclear"]);
  const split = decideClassification(answer("drive_problem", { readout_problem: 0.4, drive_problem: 0.45, unclear: 0.15 }), names, t);
  assert.equal(split.outcome, "ambiguous");
  assert.equal(split.category, "drive_problem");
  for (const bad of [
    { stopReason: "error", answers: {} },
    { stopReason: "stop", answers: { category: { type: "bool", probability: 1 } } },
    answer("other", { readout_problem: 0.8, drive_problem: 0.15, unclear: 0.05 }),
    answer("readout_problem", { readout_problem: 0.8, drive_problem: 0.15 }),
    answer("readout_problem", { readout_problem: 0.8, drive_problem: 0.3, unclear: 0.05 }),
    answer("drive_problem", { readout_problem: 0.8, drive_problem: 0.15, unclear: 0.05 }),
  ]) {
    assert.equal(decideClassification(bad, names, t).outcome, "failed");
  }
});

test("the model's classify call asks the configured classifier and gets the decision back", async () => {
  const { settled, result, calls } = await runTurn({
    classify: async () => answer("readout_problem", { readout_problem: 0.8, drive_problem: 0.15, unclear: 0.05 }),
  });
  assert.equal(settled.status, "done");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].model, "test-classifier/jev");
  assert.deepEqual(calls[0].context.state, { context: args.context });
  assert.equal(result.isError, false);
  assert.deepEqual(result.details.classification, {
    classifier: "test-classifier/jev",
    outcome: "classified",
    category: "readout_problem",
    probability: 0.8,
    margin: 0.65,
    probabilities: [
      { category: "readout_problem", probability: 0.8 },
      { category: "drive_problem", probability: 0.15 },
      { category: "unclear", probability: 0.05 },
    ],
  });
  assert.match(result.content[0].text, /Classified as readout_problem/);
  assert.equal(result.details.ui, undefined);
});

test("an ambiguous answer is still reported, as weak evidence", async () => {
  const { result } = await runTurn({
    classify: async () => answer("drive_problem", { readout_problem: 0.4, drive_problem: 0.45, unclear: 0.15 }),
  });
  assert.equal(result.isError, false);
  assert.equal(result.details.classification.outcome, "ambiguous");
  assert.match(result.content[0].text, /weak evidence or ask the user/);
});

for (const [name, options, reason] of [
  ["a provider error", { classify: async () => ({ stopReason: "error", errorMessage: "401 Unauthorized token=abc", answers: {} }) }, "classifier request failed"],
  ["a throwing implementation", { classify: async () => { throw new Error("connect ECONNREFUSED 10.0.0.1"); } }, "classifier request failed"],
  ["a malformed answer", { classify: async () => ({ stopReason: "stop", answers: {} }) }, "invalid classifier answer"],
  ["a timeout", { classify: () => new Promise(() => {}), classifyConfig: config({ timeoutMs: 150 }) }, "timed out after 0.15 s"],
  ["an unknown model", { classify: async () => answer("unclear", {}), classifyConfig: config({ name: "missing" }) }, "classifier unavailable"],
]) {
  test(`${name} fails the call with a fixed reason, never the provider's message`, async () => {
    const warnings = [];
    const { settled, result } = await runTurn({ ...options, log: { log() {}, warn: (line) => warnings.push(line), error() {} } });
    assert.equal(settled.status, "done");
    assert.equal(result.isError, true);
    const classifier = `test-classifier/${options.classifyConfig?.name ?? "jev"}`;
    assert.deepEqual(result.details.classification, { classifier, outcome: "failed", reason });
    assert.doesNotMatch(JSON.stringify(result), /401|token=abc|ECONNREFUSED|10\.0\.0\.1/);
    if (name === "a provider error") assert.match(warnings.join("\n"), /401 Unauthorized/);
  });
}

test("duplicate category names are refused before the classifier is asked", async () => {
  const { result, calls } = await runTurn({
    classify: async () => answer("unclear", {}),
    callArgs: { ...args, categories: [args.categories[0], args.categories[0]] },
  });
  assert.equal(calls.length, 0);
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /distinct names/);
});

test("arguments over the bounds are refused by the schema", async () => {
  const { result, calls } = await runTurn({
    classify: async () => answer("unclear", {}),
    callArgs: { ...args, context: "x".repeat(4001) },
  });
  assert.equal(calls.length, 0);
  assert.equal(result.isError, true);
});

test("the chat streams classify as its own step carrying the decision", async () => {
  const chat = await openChat({
    classify: async () => answer("readout_problem", { readout_problem: 0.8, drive_problem: 0.15, unclear: 0.05 }),
  });
  try {
    const out = [];
    const watch = await chat.conversation.watch(chat.context);
    const stream = new ViewEventStream(chat.conversation, watch.value, (event) => out.push(...toNdjsonEvents(event)), chat.context);
    watch.start(async (call) => {
      if (call.kind === "value") await stream.push(call.value);
    });
    const submission = await chat.conversation.submit({ type: "input", content: "why?" }, chat.context);
    assert.equal((await submission.wait(chat.context)).status, "done");
    await stream.finish(watch);
    const starts = out.filter((line) => line.type === "tool_start" && line.name === CLASSIFY_CHAT_TOOL);
    const ends = out.filter((line) => line.type === "tool_end" && line.name === CLASSIFY_CHAT_TOOL);
    assert.equal(starts.length, 1);
    assert.equal(starts[0].args.question, args.question);
    assert.equal(ends.length, 1);
    assert.equal(ends[0].isError, false);
    assert.equal(ends[0].classification.outcome, "classified");
    assert.equal(ends[0].classification.category, "readout_problem");
    // The classifier's input stays out of the step's result.
    assert.ok(!JSON.stringify(ends[0].classification).includes("SNR"));
    assert.equal(out.filter((line) => line.type === "ui").length, 0);
  } finally {
    await chat.harness.close(chat.context);
  }
});

test("tool_end carries only a well-formed, bounded classification, and only for classify", () => {
  const end = (details, toolName = CLASSIFY_CHAT_TOOL) =>
    toNdjsonEvents({ type: "tool_execution_end", toolName, entry: { model: [{ role: "toolResult", details }] } }).find(
      (line) => line.type === "tool_end",
    );
  const classification = {
    classifier: "c/m",
    outcome: "ambiguous",
    category: "a",
    probability: 0.5,
    margin: 0.1,
    probabilities: [{ category: "a", probability: 0.5 }],
  };
  assert.deepEqual(end({ classification: { ...classification, state: { context: "secret" } } }).classification, classification);
  assert.deepEqual(
    end({ classification: { classifier: "c/m", outcome: "failed", reason: "r".repeat(1000), probability: 2 } }).classification,
    { classifier: "c/m", outcome: "failed", reason: "r".repeat(200) },
  );
  const many = Array.from({ length: 20 }, (_, i) => ({ category: `c${i}`, probability: 0.05 }));
  assert.equal(end({ classification: { classifier: "c/m", outcome: "classified", probabilities: many } }).classification.probabilities.length, 8);
  assert.equal("classification" in end({ classification: { classifier: "c/m", outcome: "template" } }), false);
  assert.equal("classification" in end({ classification: { outcome: "failed" } }), false);
  assert.equal("classification" in end(undefined), false);
  // present_results keeps its own details; its layout choice is not a classify step.
  assert.equal("classification" in end({ classification, presentation: { classifier: "c/m" } }, PRESENT_TOOL), false);
});

test("classifyWithin tells a cancelled call from a timed-out one", async () => {
  const model = { api: "mock", provider: "p", id: "m" };
  // Resolves aborted once the signal fires, as pi's classify() does.
  const models = {
    classify: (_model, _context, options) =>
      new Promise((resolve) =>
        options.signal.addEventListener("abort", () => resolve({ stopReason: "aborted", answers: {}, errorMessage: "aborted" })),
      ),
  };
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 20);
  const cancelled = await classifyWithin(models, model, classifyContext(args), 2_000, { abortSignal: controller.signal });
  assert.equal(cancelled.timedOut, false);
  assert.equal(cancelled.result.stopReason, "aborted");
  const late = await classifyWithin(models, model, classifyContext(args), 50, {});
  assert.equal(late.timedOut, true);
  assert.match(late.result.errorMessage, /timed out after 50 ms/);
});
