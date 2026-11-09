import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createProvider, fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, defineTool, Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { Type } from "typebox";

import { buildSystemPrompt } from "../src/prompt.ts";
import {
  CLASSIFY_TOOL,
  PRESENTATION_GUIDELINE,
  PRESENT_TOOL,
  buildPresentationTools,
  classifierState,
  configurePresentation,
  decideCategory,
  renderTemplate,
} from "../src/presentation-tool.ts";
import { classifierEndpointProvider, configureClassifierModels } from "../src/classifier-models.ts";
import { uiBlockFromDetails, uiTool, validateUiSpec } from "../src/ui-tool.ts";

const thresholds = { minProbability: 0.6, minMargin: 0.2 };
const config = (overrides = {}) => ({
  provider: "test-classifier",
  name: "jev",
  minProbability: 0.6,
  minMargin: 0.2,
  timeoutMs: 2_000,
  ...overrides,
});

const choice = (category, probabilities) => ({
  stopReason: "stop",
  answers: { category: { type: "choice", choice: category, probabilities, confidence: probabilities[category] } },
});
const probs = (top, p = 0.85) => {
  const rest = (1 - p) / 3;
  return Object.fromEntries(
    ["calibration_summary", "execution_comparison", "failure_list", "text"].map((c) => [c, c === top ? p : rest]),
  );
};

const summaryArgs = {
  request: "Show me the latest T1 and fidelity for Q03 and Q04",
  sources: ["qdash_get_metrics"],
  title: "Chip 64Qv1, 2026-11-08",
  records: [
    { subject: "Q03", status: "ok", values: [{ name: "t1", value: 42.13, unit: "us" }, { name: "x90_fidelity", value: 0.9971 }] },
    { subject: "Q04", status: "failed", message: "fit did not converge", values: [{ name: "t1", value: 38.5, unit: "us" }] },
  ],
};

/** Every number and string shown in the spec's tables and metrics. */
function shownValues(spec) {
  const out = [];
  for (const element of Object.values(spec.elements)) {
    if (element.type === "Metric") out.push(element.props.value);
    if (element.type === "Table") for (const row of element.props.rows) out.push(...Object.values(row));
  }
  return out.filter((value) => value !== null);
}

/** The values a template may show: the records' values, subjects, statuses, messages and value names. */
function allowedValues(args) {
  const allowed = new Set();
  for (const record of args.records) {
    allowed.add(record.subject);
    if (record.status) allowed.add(record.status);
    if (record.message) allowed.add(record.message);
    for (const value of record.values) {
      allowed.add(value.value);
      allowed.add(value.name);
      if (value.unit) {
        allowed.add(`${value.name} (${value.unit})`);
        allowed.add(`${value.value} ${value.unit}`);
      }
    }
  }
  allowed.add("Status");
  return allowed;
}

// --- config ---

const repoFile = (name) => readFileSync(new URL(`../../config/copilot/${name}`, import.meta.url), "utf8");

function fakeRuntime({ providers = [], catalog = [], auth = [] } = {}) {
  const registered = [];
  return {
    registered,
    getProvider: (id) => (providers.includes(id) || registered.some((p) => p.id === id) ? {} : undefined),
    registerNativeProvider: (provider) => registered.push(provider),
    getModelOfType: (_type, provider, id) => (catalog.includes(`${provider}/${id}`) ? {} : undefined),
    hasConfiguredAuth: (provider) => auth.includes(provider),
  };
}
function capturedLog() {
  const lines = [];
  const push = (line) => lines.push(line);
  return { lines, log: { log: push, warn: push, error: push } };
}

const endpointYaml = `classifier_models:
  - provider: system-one-classifier
    name: ZefanCai/Open-Jev-2B
    base_url: env:CLASSIFIER_BASE_URL
    api_key_env: CLASSIFIER_API_KEY
`;
const endpointEnv = {
  CLASSIFIER_BASE_URL: "https://classifier.example/jev/v1",
  CLASSIFIER_API_KEY: "secret-token-value",
};
const classifiersFor = (yaml, env = endpointEnv, runtime = fakeRuntime()) =>
  configureClassifierModels(yaml, runtime, env, capturedLog().log);

test("the repository offers present_results with its System One classifier once the endpoint is set", () => {
  // chat.yaml carries no presentation settings; classifier.yaml alone decides.
  assert.doesNotMatch(repoFile("chat.yaml"), /presentation/);
  const classifiers = classifiersFor(repoFile("classifier.yaml"));
  assert.deepEqual(classifiers.declared[0], {
    provider: "system-one-classifier",
    name: "ZefanCai/Open-Jev-2B",
    endpoint: { baseUrl: "env:CLASSIFIER_BASE_URL", apiKeyEnv: "CLASSIFIER_API_KEY" },
  });
  const { lines, log } = capturedLog();
  assert.deepEqual(configurePresentation(classifiers, log), {
    provider: "system-one-classifier",
    name: "ZefanCai/Open-Jev-2B",
    minProbability: 0.6,
    minMargin: 0.2,
    timeoutMs: 5000,
  });
  assert.doesNotMatch(lines.join("\n"), /secret-token-value|classifier\.example/);
});

test("compose hardcodes no classifier endpoint: its URL and token come from .env only", () => {
  const compose = readFileSync(new URL("../../compose.yaml", import.meta.url), "utf8");
  const service = compose.slice(compose.indexOf("\n  agent-runtime:\n"), compose.indexOf("\n  agent-exec:\n"));
  assert.match(service, /\n    env_file:\n      - \.env\n/);
  assert.doesNotMatch(compose, /CLASSIFIER_BASE_URL[A-Z_]*=|CLASSIFIER_API_KEY[A-Z_]*=/);
  assert.doesNotMatch(compose, /SYSTEM_ONE_/);
  // The repository's classifier reads its URL from the environment, never a literal endpoint.
  assert.match(repoFile("classifier.yaml"), /\n    base_url: env:CLASSIFIER_BASE_URL\n    api_key_env: CLASSIFIER_API_KEY\n/);
  const envExample = readFileSync(new URL("../../.env.example", import.meta.url), "utf8");
  assert.match(envExample, /\nCLASSIFIER_BASE_URL=\nCLASSIFIER_API_KEY=\n/);
});

test("without the endpoint URL the repository's classifier is unavailable and the chat starts without present_results", () => {
  const runtime = fakeRuntime();
  const { lines, log } = capturedLog();
  const classifiers = configureClassifierModels(
    repoFile("classifier.yaml"),
    runtime,
    { CLASSIFIER_API_KEY: "secret-token-value", CF_ACCESS_CLIENT_ID: "a", CF_ACCESS_CLIENT_SECRET: "b" },
    log,
  );
  assert.equal(runtime.registered.length, 0);
  assert.equal(configurePresentation(classifiers, log), undefined);
  assert.match(lines.join("\n"), /present_results not offered: no usable classifier: system-one-classifier\/ZefanCai\/Open-Jev-2B unavailable: CLASSIFIER_BASE_URL not set/);
  assert.doesNotMatch(lines.join("\n"), /secret-token-value/);
});

test("without the token the repository's classifier is unavailable and the chat starts without present_results", () => {
  const runtime = fakeRuntime();
  const { lines, log } = capturedLog();
  const classifiers = configureClassifierModels(
    repoFile("classifier.yaml"),
    runtime,
    { CLASSIFIER_BASE_URL: "https://classifier.example/jev/v1", CF_ACCESS_CLIENT_ID: "a", CF_ACCESS_CLIENT_SECRET: "b" },
    log,
  );
  assert.equal(runtime.registered.length, 0);
  assert.equal(configurePresentation(classifiers, log), undefined);
  assert.match(lines.join("\n"), /present_results not offered: no usable classifier: system-one-classifier\/ZefanCai\/Open-Jev-2B unavailable: CLASSIFIER_API_KEY not set/);
});

test("present_results uses the first usable declared classifier, and only a declared one", () => {
  const yaml = `${endpointYaml}  - provider: typesafe
    name: jev-latest
`;
  const catalog = { catalog: ["typesafe/jev-latest"], auth: ["typesafe"] };
  const both = classifiersFor(yaml, endpointEnv, fakeRuntime(catalog));
  assert.deepEqual(configurePresentation(both, capturedLog().log), {
    provider: "system-one-classifier",
    name: "ZefanCai/Open-Jev-2B",
    minProbability: 0.6,
    minMargin: 0.2,
    timeoutMs: 5000,
  });
  // The first entry has no endpoint: the next usable one is used.
  assert.equal(configurePresentation(classifiersFor(yaml, {}, fakeRuntime(catalog)), capturedLog().log).name, "jev-latest");
  // None usable: not offered, with each reason logged. Pi's catalog is never used unasked.
  const { lines, log } = capturedLog();
  assert.equal(configurePresentation(classifiersFor(yaml, {}, fakeRuntime()), log), undefined);
  assert.match(lines.join("\n"), /present_results not offered: no usable classifier: .*CLASSIFIER_API_KEY not set; typesafe\/jev-latest unavailable: not in the model catalog/);
  // No classifier.yaml, or an empty list: not offered.
  const none = capturedLog();
  assert.equal(configurePresentation(classifiersFor(undefined), none.log), undefined);
  assert.match(none.lines.join("\n"), /declares no classifier_models/);
});

test("an invalid classifier.yaml disables only present_results", () => {
  const { lines, log } = capturedLog();
  const broken = configureClassifierModels("classifier_models: {}\n", fakeRuntime(), endpointEnv, log);
  assert.equal(broken.declared.length, 0);
  assert.equal(configurePresentation(broken, log), undefined);
  assert.match(lines.join("\n"), /present_results not offered: classifier.yaml is invalid: classifier_models must be a list/);
});

// --- the System One endpoint through pi-ai's typesafe-system-one adapter ---

const endpointConfig = (baseUrl) => ({
  provider: "system-one-classifier",
  name: "ZefanCai/Open-Jev-2B",
  endpoint: { baseUrl, apiKeyEnv: "CLASSIFIER_API_KEY" },
});

async function classifyThrough(provider, env, response) {
  const requests = [];
  const models = createModels({ authContext: { env: async (name) => env[name], fileExists: async () => false } });
  models.setProvider(provider);
  const model = models.getModelOfType("classifier", "system-one-classifier", "ZefanCai/Open-Jev-2B");
  assert.ok(model, "the endpoint's classifier is in the catalog");
  const result = await models.classify(
    model,
    {
      state: { request: "I was charged twice and want a refund." },
      questions: {
        intent: {
          type: "choice",
          instructions: "Choose the customer intent.",
          criteria: { billing: "A payment or refund issue", technical: "A malfunction or setup issue", other: "Another request" },
        },
      },
    },
    {
      maxRetries: 0,
      fetch: async (url, init) => {
        requests.push({ url: String(url), headers: new Headers(init.headers), body: JSON.parse(init.body) });
        return Response.json(response);
      },
    },
  );
  return { result, requests };
}

/** A response the Open-Jev endpoint returned for the request below, as the user supplied it (not fetched by the tests). */
const intentAnswer = {
  answers: {
    intent: {
      type: "choice",
      choice: "billing",
      probabilities: { billing: 0.9521461497351157, technical: 0.004638120136589315, other: 0.04321573012829503 },
      confidence: 0.9282192246026734,
    },
  },
  model: "ZefanCai/Open-Jev-2B",
  usage: { input_tokens: 165, output_tokens: 0 },
  metadata: {
    method: "lora_decision_head",
    temperature: 1.518796342858676,
    candidate_sequences: 3,
    cached_tokens: 0,
    inference_seconds: 0.07774446485564113,
  },
};

test("the endpoint posts to <base_url>/systemone with the bearer token and Cloudflare Access headers", async () => {
  const env = {
    CLASSIFIER_BASE_URL: "https://classifier.example/jev/v1/",
    CLASSIFIER_API_KEY: "token-placeholder",
    CF_ACCESS_CLIENT_ID: "client-id-placeholder.access",
    CF_ACCESS_CLIENT_SECRET: "client-secret-placeholder",
  };
  const provider = classifierEndpointProvider(endpointConfig("env:CLASSIFIER_BASE_URL"), env);
  const { result, requests } = await classifyThrough(provider, env, intentAnswer);
  assert.equal(result.stopReason, "stop", result.errorMessage);
  // pi-ai's parser keeps the answer's fields apart and ignores the extra `model` and `metadata`.
  assert.deepEqual(result.answers, intentAnswer.answers);
  assert.equal(result.answers.intent.confidence, 0.9282192246026734);
  assert.equal(result.answers.intent.probabilities.billing, 0.9521461497351157);
  assert.equal(result.usage.input, 165);
  assert.equal(result.usage.output, 0);
  assert.equal(result.usage.cost.total, 0);
  assert.equal(result.model, "ZefanCai/Open-Jev-2B");
  assert.equal("metadata" in result, false);
  assert.equal(requests.length, 1);
  const [request] = requests;
  assert.equal(request.url, "https://classifier.example/jev/v1/systemone");
  assert.equal(request.headers.get("Authorization"), "Bearer token-placeholder");
  assert.equal(request.headers.get("Content-Type"), "application/json");
  assert.equal(request.headers.get("CF-Access-Client-Id"), "client-id-placeholder.access");
  assert.equal(request.headers.get("CF-Access-Client-Secret"), "client-secret-placeholder");
  // pi-ai's System One body: the configured name as `model`, then state and questions.
  assert.deepEqual(Object.keys(request.body), ["model", "state", "questions"]);
  assert.equal(request.body.model, "ZefanCai/Open-Jev-2B");
  assert.equal(request.body.questions.intent.type, "choice");
});

test("without the Access token the endpoint gets no Access headers; without the bearer token no request is made", async () => {
  const env = { CLASSIFIER_BASE_URL: "https://classifier.example/jev/v1", CLASSIFIER_API_KEY: "t" };
  const provider = classifierEndpointProvider(endpointConfig("env:CLASSIFIER_BASE_URL"), env);
  const { requests } = await classifyThrough(provider, env, intentAnswer);
  assert.equal(requests[0].url, "https://classifier.example/jev/v1/systemone");
  assert.equal(requests[0].headers.get("CF-Access-Client-Id"), null);

  // The token disappears after startup: an error result, no request, and no other provider.
  const { result, requests: none } = await classifyThrough(provider, { CLASSIFIER_BASE_URL: "x" }, intentAnswer);
  assert.equal(result.stopReason, "error");
  assert.equal(none.length, 0);
});

test("a suffixed CLASSIFIER_BASE_URL_<SUFFIX> gets the Access headers; another variable does not", async () => {
  const env = {
    CLASSIFIER_BASE_URL_SECOND: "https://classifier.example/v1",
    OTHER_CLASSIFIER_URL: "https://classifier.example/v1",
    CLASSIFIER_API_KEY: "t",
    CF_ACCESS_CLIENT_ID: "a",
    CF_ACCESS_CLIENT_SECRET: "b",
  };
  const suffixed = classifierEndpointProvider(endpointConfig("env:CLASSIFIER_BASE_URL_SECOND"), env);
  const { requests } = await classifyThrough(suffixed, env, intentAnswer);
  assert.equal(requests[0].url, "https://classifier.example/v1/systemone");
  assert.equal(requests[0].headers.get("CF-Access-Client-Id"), "a");
  assert.equal(requests[0].headers.get("CF-Access-Client-Secret"), "b");

  const other = classifierEndpointProvider(endpointConfig("env:OTHER_CLASSIFIER_URL"), env);
  const { requests: plain } = await classifyThrough(other, env, intentAnswer);
  assert.equal(plain[0].headers.get("CF-Access-Client-Id"), null);
});

test("a literal base URL gets no shared Access token", async () => {
  const env = { CLASSIFIER_API_KEY: "t", CF_ACCESS_CLIENT_ID: "a", CF_ACCESS_CLIENT_SECRET: "b" };
  const provider = classifierEndpointProvider(endpointConfig("https://classifier.example/jev/v1"), env);
  const { requests } = await classifyThrough(provider, env, intentAnswer);
  assert.equal(requests[0].url, "https://classifier.example/jev/v1/systemone");
  assert.equal(requests[0].headers.get("CF-Access-Client-Id"), null);
});

// --- decisions ---

test("decideCategory accepts a clear answer and falls back on everything else", () => {
  assert.deepEqual(decideCategory(choice("failure_list", probs("failure_list")), thresholds), {
    outcome: "category",
    category: "failure_list",
    probability: 0.85,
    margin: 0.85 - 0.05,
  });
  const fallback = (result, t = thresholds) => decideCategory(result, t).reason;
  assert.match(fallback({ stopReason: "error", errorMessage: "401", answers: {} }), /classifier error: 401/);
  assert.match(fallback({ stopReason: "aborted", answers: {} }), /classifier aborted/);
  assert.match(fallback(undefined), /no classifier result/);
  assert.match(fallback({ stopReason: "stop", answers: {} }), /no category choice/);
  assert.match(fallback(choice("chart", probs("text"))), /unknown category/);
  assert.match(fallback(choice("text", { ...probs("text"), failure_list: Number.NaN })), /out of range/);
  assert.match(fallback(choice("text", probs("failure_list"))), /not the most probable/);
  // A low winning probability, and a clear winner without a clear lead.
  assert.match(fallback(choice("text", probs("text", 0.4))), /ambiguous/);
  const close = { calibration_summary: 0.62, execution_comparison: 0.38, failure_list: 0, text: 0 };
  assert.match(
    fallback(choice("calibration_summary", close), { minProbability: 0.6, minMargin: 0.3 }),
    /ambiguous classification \(calibration_summary 0\.62, lead 0\.24\)/,
  );
  assert.equal(decideCategory(choice("calibration_summary", close), thresholds).outcome, "category");
});

test("decisions read the probabilities, never the answer's separate confidence score", () => {
  const answer = (probabilities, confidence) => ({
    stopReason: "stop",
    answers: { category: { type: "choice", choice: "failure_list", probabilities, confidence } },
  });
  const clear = { calibration_summary: 0.02, execution_comparison: 0.01, failure_list: 0.95, text: 0.02 };
  const split = { calibration_summary: 0.45, execution_comparison: 0.05, failure_list: 0.5, text: 0 };
  // A low confidence score does not reject a clear distribution, nor does a high one rescue a split.
  assert.equal(decideCategory(answer(clear, 0.1), thresholds).outcome, "category");
  assert.equal(decideCategory(answer(clear, 0.1), thresholds).probability, 0.95);
  assert.equal(decideCategory(answer(split, 0.99), thresholds).outcome, "fallback");
});

// --- templates ---

for (const category of ["calibration_summary", "execution_comparison", "failure_list"]) {
  test(`${category} renders only the values it was given`, () => {
    const built = renderTemplate(category, summaryArgs);
    assert.equal(built.ok, true, built.reason);
    const valid = validateUiSpec(built.spec);
    assert.equal(valid.ok, true, valid.errors?.join("\n"));
    const allowed = allowedValues(summaryArgs);
    for (const value of shownValues(valid.spec)) assert.ok(allowed.has(value), `${category} shows ${JSON.stringify(value)}`);
    const text = JSON.stringify(valid.spec);
    assert.match(text, /Values as reported by the assistant from these tool results: qdash_get_metrics/);
    assert.doesNotMatch(text, /verified/i);
  });
}

test("each template lays out the records its own way", () => {
  const summary = renderTemplate("calibration_summary", summaryArgs).spec;
  assert.deepEqual(summary.elements.table.props.rows[0], {
    subject: "Q03",
    status: "ok",
    v0: 42.13,
    v1: 0.9971,
    message: null,
  });
  assert.equal(summary.elements.table.props.columns[2].label, "t1 (us)");

  const comparison = renderTemplate("execution_comparison", summaryArgs).spec;
  assert.deepEqual(
    comparison.elements.table.props.columns.map((column) => column.label),
    ["Value", "Q03", "Q04"],
  );
  assert.deepEqual(comparison.elements.table.props.rows[1], { name: "t1 (us)", r0: 42.13, r1: 38.5 });

  const failures = renderTemplate("failure_list", summaryArgs).spec;
  assert.deepEqual(failures.elements.table.props.rows, [
    { subject: "Q04", status: "failed", message: "fit did not converge", v0: 38.5 },
  ]);
  assert.equal(failures.elements.alert.props.tone, "error");

  const single = renderTemplate("calibration_summary", { ...summaryArgs, records: [summaryArgs.records[0]] }).spec;
  assert.deepEqual(single.elements.m0.props, { label: "t1", value: 42.13, unit: "us", detail: "Q03", tone: "success" });
});

test("templates refuse records they cannot hold", () => {
  const one = { ...summaryArgs, records: [summaryArgs.records[0]] };
  assert.match(renderTemplate("execution_comparison", one).reason, /at least two records/);
  assert.match(renderTemplate("failure_list", one).reason, /no record has a failed or warning status/);
  const wide = {
    ...summaryArgs,
    records: [{ subject: "Q1", values: Array.from({ length: 10 }, (_, i) => ({ name: `p${i}`, value: i })) }, {
      subject: "Q2",
      status: "ok",
      message: "m",
      values: [{ name: "extra", value: 1 }],
    }],
  };
  assert.match(renderTemplate("calibration_summary", wide).reason, /do not fit/);
  const mixed = {
    ...summaryArgs,
    records: [
      { subject: "A", values: [{ name: "t1", value: 40, unit: "us" }] },
      { subject: "B", values: [{ name: "t1", value: 40000, unit: "ns" }] },
    ],
  };
  // Mixed units keep each value's own unit instead of converting.
  assert.deepEqual(renderTemplate("calibration_summary", mixed).spec.elements.table.props.rows.map((r) => r.v0), [
    "40 us",
    "40000 ns",
  ]);
});

test("the classifier sees the request and the data's shape, not its values", () => {
  const state = classifierState(summaryArgs);
  assert.deepEqual(state.value_names, ["t1", "x90_fidelity"]);
  assert.deepEqual(state.statuses, ["ok", "failed"]);
  const text = JSON.stringify(state);
  for (const value of ["42.13", "0.9971", "38.5", "converge"]) assert.ok(!text.includes(value), value);
});

// --- a real Harness: the model calls present_results, which asks the classifier ---

const dataTool = defineTool({
  name: "qdash_get_metrics",
  description: "Metrics",
  parameters: Type.Object({}),
  replay: "safe",
  execute: async () => ({ output: [{ type: "text", text: "Q03 t1=42.13us x90=0.9971; Q04 t1=38.5us failed" }] }),
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

async function openChat({ classify, presentationConfig = config(), presentArgs = summaryArgs, storage, extraResponses }) {
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
  faux.setResponses(
    extraResponses ?? [
      fauxAssistantMessage([fauxToolCall("qdash_get_metrics", {}, { id: "d1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxToolCall(PRESENT_TOOL, presentArgs, { id: "p1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("Q04 failed its fit.")),
    ],
  );
  const registry = createRegistry();
  const tools = presentationConfig ? buildPresentationTools(presentationConfig) : [];
  registry.install({ name: "test", tools: [dataTool, uiTool, ...tools] });
  const context = BACKGROUND_CONTEXT;
  const harness = await Harness.open(storage ?? new MemoryStorage(), { models, registry }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return { harness, conversation, context, calls };
}

async function toolResults(conversation, context) {
  const view = await conversation.context(context);
  return view.entries
    .filter((entry) => ToolResultEntry.is(entry))
    .map((entry) => entry.model[0])
    .filter((message) => message?.role === "toolResult");
}

async function runTurn(options) {
  const chat = await openChat(options);
  try {
    const submission = await chat.conversation.submit({ type: "input", content: "show results" }, chat.context);
    const settled = await submission.wait(chat.context);
    const results = await toolResults(chat.conversation, chat.context);
    return { settled, results, calls: chat.calls, present: results.find((r) => r.toolName === PRESENT_TOOL) };
  } finally {
    await chat.harness.close(chat.context);
  }
}

test("present_results renders the template the classifier picks, from the passed values", async () => {
  const { settled, present, calls } = await runTurn({ classify: async () => choice("failure_list", probs("failure_list")) });
  assert.equal(settled.status, "done");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].model, "test-classifier/jev");
  assert.equal(calls[0].context.questions.category.type, "choice");
  assert.ok(!JSON.stringify(calls[0].context.state).includes("38.5"));
  assert.equal(present.isError, false);
  assert.deepEqual(present.details.presentation, {
    classifier: "test-classifier/jev",
    outcome: "template",
    category: "failure_list",
    probability: 0.85,
    margin: 0.85 - 0.05,
  });
  // The block the chat streams and stores, re-validated as replayed events are.
  const ui = uiBlockFromDetails(present.details);
  assert.ok(ui);
  assert.deepEqual(ui.spec.elements.table.props.rows, [
    { subject: "Q04", status: "failed", message: "fit did not converge", v0: 38.5 },
  ]);
  assert.match(ui.fallback, /Q04/);
});

test("the text category shows no UI", async () => {
  const { present, settled } = await runTurn({ classify: async () => choice("text", probs("text")) });
  assert.equal(settled.status, "done");
  assert.equal(present.details.presentation.outcome, "text");
  assert.equal(present.details.ui, undefined);
  assert.match(present.content[0].text, /answer in text/i);
});

for (const [name, classify, reason] of [
  ["an error result", async () => ({ stopReason: "error", errorMessage: "401 Unauthorized", answers: {} }), /classifier error: 401/],
  ["an ambiguous answer", async () => choice("text", probs("text", 0.45)), /ambiguous/],
  ["an invalid answer", async () => ({ stopReason: "stop", answers: { category: { type: "bool", probability: 1 } } }), /invalid classifier answer/],
  ["a throwing implementation", async () => { throw new Error("boom"); }, /classifier error: boom/],
]) {
  test(`${name} falls back to render_ui or text and the turn still answers`, async () => {
    const { settled, present, calls } = await runTurn({ classify });
    assert.equal(settled.status, "done");
    assert.equal(calls.length, 1);
    assert.equal(present.isError, false);
    assert.equal(present.details.presentation.outcome, "fallback");
    assert.match(present.details.presentation.reason, reason);
    assert.equal(present.details.ui, undefined);
    assert.match(present.content[0].text, /render_ui/);
  });
}

test("a template the records do not fit falls back", async () => {
  const args = { ...summaryArgs, records: [summaryArgs.records[0]] };
  const { present } = await runTurn({
    classify: async () => choice("execution_comparison", probs("execution_comparison")),
    presentArgs: args,
  });
  assert.equal(present.details.presentation.outcome, "fallback");
  assert.match(present.details.presentation.reason, /at least two records/);
});

test("an unknown classifier model falls back without a request", async () => {
  const { present, calls } = await runTurn({
    classify: async () => choice("failure_list", probs("failure_list")),
    presentationConfig: config({ name: "missing" }),
  });
  assert.equal(calls.length, 0);
  assert.match(present.details.presentation.reason, /not in the model catalog/);
});

test("a classifier that does not answer in time falls back", async () => {
  const started = Date.now();
  const { present, settled } = await runTurn({
    classify: () => new Promise(() => {}),
    presentationConfig: config({ timeoutMs: 150 }),
  });
  assert.equal(settled.status, "done");
  assert.match(present.details.presentation.reason, /timed out after 150 ms/);
  assert.ok(Date.now() - started < 2_000);
});

test("sources must be tools the chat offers", async () => {
  const { present } = await runTurn({
    classify: async () => choice("failure_list", probs("failure_list")),
    presentArgs: { ...summaryArgs, sources: ["render_ui"] },
  });
  assert.equal(present.isError, true);
  assert.match(present.content[0].text, /not data tools here: render_ui/);
});

test("the classifier tool is never offered to the model", async () => {
  const chat = await openChat({ classify: async () => choice("text", probs("text")) });
  try {
    const agent = await chat.conversation.agent?.(chat.context);
    if (agent) {
      assert.ok(agent.tools.some((tool) => tool.name === PRESENT_TOOL));
      assert.ok(!agent.tools.some((tool) => tool.name === CLASSIFY_TOOL));
    }
  } finally {
    await chat.harness.close(chat.context);
  }
});

test("without presentation, render_ui works as before and no classifier is asked", async () => {
  const renderArgs = {
    root: "m",
    stacks: [], cards: [], tables: [], alerts: [], texts: [], charts: [], links: [],
    metrics: [{ id: "m", label: "T1", value: 42.13, unit: "us" }],
  };
  const { settled, results, calls } = await runTurn({
    classify: async () => choice("failure_list", probs("failure_list")),
    presentationConfig: null,
    extraResponses: [
      fauxAssistantMessage([fauxToolCall("render_ui", renderArgs, { id: "u1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("Done.")),
    ],
  });
  assert.equal(settled.status, "done");
  assert.equal(calls.length, 0);
  const ui = uiBlockFromDetails(results.find((r) => r.toolName === "render_ui").details);
  assert.equal(ui.spec.elements.m.props.value, 42.13);
  assert.doesNotMatch(buildSystemPrompt("en", "en"), /present_results/);
  assert.match(buildSystemPrompt("en", "en", [], null, null, false, PRESENTATION_GUIDELINE), /`present_results`/);
});

test("a restart during classification does not ask the classifier again", async (t) => {
  const directory = mkdtempSync(join(tmpdir(), "presentation-replay-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const path = join(directory, "session.sqlite");
  let release;
  const first = await openChat({
    storage: await openNodeSqliteStorage(path),
    classify: (_model, _context, options) =>
      new Promise((resolve) => {
        release = resolve;
        options?.signal?.addEventListener("abort", () =>
          resolve({ stopReason: "aborted", errorMessage: "closed", answers: {} }),
        );
      }),
  });
  await first.conversation.submit({ type: "input", content: "show results" }, first.context);
  for (let i = 0; i < 200 && first.calls.length === 0; i++) await new Promise((r) => setTimeout(r, 10));
  assert.equal(first.calls.length, 1, "the classifier was asked once before the restart");
  await first.harness.close(first.context);
  release?.(choice("failure_list", probs("failure_list")));

  const second = await openChat({
    storage: await openNodeSqliteStorage(path),
    classify: async () => choice("failure_list", probs("failure_list")),
    extraResponses: [fauxAssistantMessage(fauxText("Recovered."))],
  });
  try {
    await second.conversation.waitForIdle?.(second.context);
    for (let i = 0; i < 200; i++) {
      const present = (await toolResults(second.conversation, second.context)).find((r) => r.toolName === PRESENT_TOOL);
      if (present) {
        assert.equal(second.calls.length, 0, "no classifier request after the restart");
        // The rerun reattached to the nested call, which a restart interrupts rather than retries.
        assert.match(present.details.presentation.reason, /classifier did not finish: .*interrupted/);
        assert.equal(present.details.presentation.outcome, "fallback");
        assert.equal(present.details.ui, undefined);
        return;
      }
      await new Promise((r) => setTimeout(r, 10));
    }
    assert.fail("present_results did not settle after the restart");
  } finally {
    await second.harness.close(second.context);
  }
});

test("on pi's ModelRuntime the repository's classifier is registered and reached with its env credentials", async (t) => {
  const { ModelRuntime } = await import("@earendil-works/pi-coding-agent");
  const directory = mkdtempSync(join(tmpdir(), "presentation-runtime-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const env = {
    CLASSIFIER_BASE_URL: "https://classifier.example/jev/v1",
    CLASSIFIER_API_KEY: "token-placeholder",
    CF_ACCESS_CLIENT_ID: "client-id-placeholder.access",
    CF_ACCESS_CLIENT_SECRET: "client-secret-placeholder",
  };
  const saved = Object.fromEntries(Object.keys(env).map((name) => [name, process.env[name]]));
  Object.assign(process.env, env);
  t.after(() => {
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  });
  const runtime = await ModelRuntime.create({
    modelsPath: null,
    authPath: join(directory, "auth.json"),
    modelsStorePath: join(directory, "models-store.json"),
    refreshOnCreate: false,
  });
  const classifiers = configureClassifierModels(repoFile("classifier.yaml"), runtime, process.env, capturedLog().log);
  assert.equal(classifiers.unavailable.size, 0);
  const config = configurePresentation(classifiers, capturedLog().log);
  assert.equal(config.name, "ZefanCai/Open-Jev-2B");
  const model = runtime.getModelOfType("classifier", "system-one-classifier", "ZefanCai/Open-Jev-2B");
  assert.ok(model);
  const requests = [];
  const result = await runtime.classify(
    model,
    { state: { request: "summary of Q03" }, questions: { category: { type: "choice", instructions: "x", criteria: { a: "A", b: "B" } } } },
    {
      maxRetries: 0,
      fetch: async (url, init) => {
        requests.push({ url: String(url), headers: new Headers(init.headers) });
        return Response.json({
          answers: { category: { type: "choice", choice: "a", probabilities: { a: 0.9, b: 0.1 }, confidence: 0.9 } },
        });
      },
    },
  );
  assert.equal(result.stopReason, "stop", result.errorMessage);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://classifier.example/jev/v1/systemone");
  assert.equal(requests[0].headers.get("Authorization"), "Bearer token-placeholder");
  assert.equal(requests[0].headers.get("CF-Access-Client-Id"), "client-id-placeholder.access");
  assert.equal(requests[0].headers.get("CF-Access-Client-Secret"), "client-secret-placeholder");
});


test("malformed probability totals fall back while rounding noise is accepted", () => {
  for (const distribution of [
    { calibration_summary: 0.9, execution_comparison: 0.4, failure_list: 0.1, text: 0.1 },
    { calibration_summary: 0.7, execution_comparison: 0.1, failure_list: 0, text: 0 },
    { ...probs("calibration_summary"), unexpected: 0 },
  ]) {
    assert.match(decideCategory(choice("calibration_summary", distribution), thresholds).reason, /sum to one/);
  }
  const rounded = { calibration_summary: 0.85, execution_comparison: 0.05, failure_list: 0.05, text: 0.05000001 };
  assert.equal(decideCategory(choice("calibration_summary", rounded), thresholds).outcome, "category");
});

test("all templates refuse duplicate value names instead of dropping facts", () => {
  for (const unit of ["us", "ns"]) {
    const args = structuredClone(summaryArgs);
    args.records[0].values.push({ ...args.records[0].values[0], value: 12345, unit });
    for (const category of ["calibration_summary", "execution_comparison", "failure_list"]) {
      const result = renderTemplate(category, args);
      assert.equal(result.ok, false);
      assert.match(result.reason, /duplicate value name/);
    }
  }
});
