import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { stream as anthropic } from "@earendil-works/pi-ai/api/anthropic-messages";
import { stream as bedrock } from "@earendil-works/pi-ai/api/bedrock-converse-stream";
import { makeStrictJsonSchema } from "@earendil-works/pi-ai/api/constrained-sampling";
import { stream as completions } from "@earendil-works/pi-ai/api/openai-completions";
import { stream as responses } from "@earendil-works/pi-ai/api/openai-responses";
import { normalizeContext, toToolDeclaration } from "@earendil-works/pi-ai/utils/transcript";
import { validateToolArguments } from "@earendil-works/pi-ai/utils/validation";

import { UI_COMPONENT_TYPES } from "../../ui/src/lib/copilotUiSpec.ts";
import { toNdjsonEvents } from "../src/events.ts";
import { buildModelsConfig } from "../src/models-config.ts";
import { UI_INPUT_GROUPS } from "../src/ui-tool-input.ts";
import {
  UI_SPEC_LIMITS,
  prepareUiArguments,
  uiBlockFromDetails,
  uiTool,
  validateUiSpec,
} from "../src/ui-tool.ts";

const metric = (props = {}) => ({
  type: "Metric",
  props: { label: "T1", value: 42.1, unit: "us", detail: "Q03", ...props },
  children: [],
});

const valid = {
  root: "s",
  elements: {
    s: { type: "Stack", props: { direction: "horizontal" }, children: ["t1", "tbl"] },
    t1: metric(),
    tbl: {
      type: "Table",
      props: {
        columns: [
          { key: "qid", label: "Qubit" },
          { key: "t1", label: "T1 (us)", align: "right" },
        ],
        rows: [{ qid: "Q03", t1: 42.1 }],
      },
      children: [],
    },
  },
};

function errorsOf(spec) {
  const result = validateUiSpec(spec);
  assert.equal(result.ok, false, "expected the spec to be rejected");
  return result.errors.join("\n");
}

/** The same UI as `valid`, in the arguments render_ui declares. */
const validArgs = {
  root: "s",
  stacks: [{ id: "s", direction: "horizontal", children: ["t1", "tbl"] }],
  cards: [],
  metrics: [{ id: "t1", label: "T1", value: 42.1, unit: "us", detail: "Q03" }],
  tables: [
    {
      id: "tbl",
      columns: [
        { key: "qid", label: "Qubit" },
        { key: "t1", label: "T1 (us)", align: "right" },
      ],
      rows: [["Q03", 42.1]],
    },
  ],
  alerts: [],
  texts: [],
  charts: [],
  links: [],
};

/** Runs a call the way the harness does: prepareArguments, schema validation, then execute. */
async function callAsHarness(args) {
  const prepared = uiTool.prepareArguments(args);
  const validated = validateToolArguments(uiTool, {
    type: "toolCall",
    id: "c1",
    name: uiTool.name,
    arguments: prepared,
  });
  return uiTool.execute(validated);
}

test("render_ui maps its arguments to a versioned spec block with fallback text", async () => {
  const result = await callAsHarness(validArgs);
  const ui = result.details.ui;
  assert.equal(ui.version, 1);
  const expected = validateUiSpec(valid);
  assert.equal(expected.ok, true);
  assert.deepEqual(ui.spec, expected.spec);
  assert.match(ui.fallback, /- T1: 42\.1 us \(Q03\)/);
  assert.match(ui.fallback, /\| Qubit \| T1 \(us\) \|\n\| --- \| ---: \|\n\| Q03 \| 42\.1 \|/);
  assert.match(result.output[0].text, /UI rendered in the chat \(3 elements\)/);
});

test("render_ui fails the call with the problems listed so the model can correct it", async () => {
  await assert.rejects(
    callAsHarness({ ...validArgs, metrics: [{ id: "t1", label: "T1", value: "" }] }),
    /render_ui spec is invalid:\n- elements\.t1 \(Metric\) props: value/,
  );
});

test("strictly sampled arguments, with null for omitted fields, give the same block", async () => {
  const strict = {
    ...validArgs,
    stacks: [{ id: "s", direction: "horizontal", gap: null, children: ["t1", "tbl"] }],
    metrics: [{ id: "t1", label: "T1", value: 42.1, unit: "us", detail: "Q03", tone: null }],
    tables: [{ ...validArgs.tables[0], caption: null, columns: [
      { key: "qid", label: "Qubit", align: null },
      { key: "t1", label: "T1 (us)", align: "right" },
    ] }],
  };
  assert.deepEqual((await callAsHarness(strict)).details, (await callAsHarness(validArgs)).details);
});

test("arbitrary element ids, empty and null cells, and every component round-trip", async () => {
  const spec = {
    root: "Root-1",
    elements: {
      "Root-1": { type: "Card", props: { title: "Q03", description: "Latest" }, children: ["row_A", "note", "go"] },
      row_A: { type: "Stack", props: { direction: "horizontal", gap: "sm" }, children: ["m-1", "tbl_9", "c"] },
      "m-1": { type: "Metric", props: { label: "Fidelity", value: "0.99", tone: "success" }, children: [] },
      tbl_9: {
        type: "Table",
        props: {
          caption: "Runs",
          columns: [
            { key: "a", label: "A" },
            { key: "b", label: "B", align: "right" },
          ],
          rows: [{ a: "x", b: null }, { a: true }],
        },
        children: [],
      },
      c: {
        type: "Chart",
        props: { data: [{ type: "scatter", x: [1, 2], y: [3, 4], marker: { color: "red" } }], layout: { title: { text: "T" } } },
        children: [],
      },
      note: { type: "Alert", props: { tone: "warning", title: "Drift", message: "T1 dropped" }, children: [] },
      go: { type: "Link", props: { label: "Q03", href: "/chip/64Qv1/qubit/3" }, children: [] },
    },
  };
  const original = validateUiSpec(spec);
  assert.equal(original.ok, true);
  const { details } = await callAsHarness({ spec });
  // A missing cell comes back as null, which the chat shows the same way.
  original.spec.elements.tbl_9.props.rows[1].b = null;
  assert.deepEqual(details.ui.spec, original.spec);
  assert.deepEqual(uiBlockFromDetails(details), details.ui);
});

test("calls in the earlier spec form, as an object or a JSON string, give the same block", async () => {
  const fromArgs = await callAsHarness(validArgs);
  const fromObject = await callAsHarness({ spec: valid });
  const fromString = await callAsHarness({ spec: JSON.stringify(valid) });
  const fromPretty = await callAsHarness({ spec: JSON.stringify(valid, null, 2) });
  assert.deepEqual(fromObject.details, fromArgs.details);
  assert.deepEqual(fromString.details, fromArgs.details);
  assert.deepEqual(fromPretty.details, fromArgs.details);
});

test("prepareArguments repairs common forms without modifying the call", async () => {
  const partial = { root: "m", metrics: JSON.stringify([{ id: "m", label: "T1", value: 1 }]) };
  const snapshot = JSON.stringify(partial);
  const prepared = prepareUiArguments(partial);
  assert.equal(JSON.stringify(partial), snapshot, "the call's arguments are not modified");
  assert.deepEqual(prepared.metrics, [{ id: "m", label: "T1", value: 1 }]);
  assert.deepEqual(prepared.stacks, []);
  assert.deepEqual(prepared.links, []);

  // Rows keyed by column and chart traces as JSON values, as the stored spec keeps them.
  const { details } = await callAsHarness({
    root: "s",
    stacks: [{ id: "s", children: ["tbl", "c"] }],
    tables: [{ id: "tbl", columns: [{ key: "a", label: "A" }, { key: "b", label: "B" }], rows: [{ b: 2, a: 1 }] }],
    charts: [{ id: "c", data: [{ type: "bar", y: [1] }], layout: { title: "L" } }],
  });
  assert.deepEqual(details.ui.spec.elements.tbl.props.rows, [{ a: 1, b: 2 }]);
  assert.deepEqual(details.ui.spec.elements.c.props, { data: [{ type: "bar", y: [1] }], layout: { title: "L" } });

  await assert.rejects(callAsHarness({ root: "x", spec: 3 }), /render_ui spec is invalid:\n- spec must be an object/);
  await assert.rejects(callAsHarness({ ...validArgs, metrics: 3 }), /Validation failed for tool "render_ui"/);
});

test("a malformed JSON string element list is rejected with its location", () => {
  assert.throws(
    () => prepareUiArguments({ root: "m", metrics: '[{"id":"m","label":"T1","value":1}}]' }),
    /render_ui metrics was sent as a string that is not valid JSON .*"\}" at character \d+ where "\]" was expected.*Send `metrics` as a JSON array/,
  );
  assert.throws(() => prepareUiArguments({ root: "m", texts: "{}" }), /texts string must hold a JSON array/);
});

test("element ids, table cells and chart JSON are checked when mapping", async () => {
  await assert.rejects(
    callAsHarness({ ...validArgs, texts: [{ id: "t1", text: "again" }] }),
    /texts\[0\]: element id "t1" is used by another element/,
  );
  await assert.rejects(
    callAsHarness({ ...validArgs, tables: [{ ...validArgs.tables[0], rows: [["Q03", 1, "extra"]] }] }),
    /tables\[0\]\.rows\[0\] has 3 cells but the table has 2 columns/,
  );
  const chart = (data, layout) => ({ root: "c", charts: [{ id: "c", data, ...(layout === undefined ? {} : { layout }) }] });
  await assert.rejects(callAsHarness(chart("[{")), /charts\[0\]\.data is not valid JSON/);
  await assert.rejects(callAsHarness(chart("{}")), /charts\[0\]\.data must hold a JSON array/);
  await assert.rejects(callAsHarness(chart("[{}]", "[]")), /charts\[0\]\.layout must hold a JSON object/);
  await assert.rejects(
    callAsHarness(chart('[{"y":[1]}]', '{"title":{"$computed":"f"}}')),
    /expressions are not supported/,
  );
  // An id cannot reach the prototype of the mapped elements.
  await assert.rejects(
    callAsHarness({ root: "__proto__", texts: [{ id: "__proto__", text: "x" }] }),
    /render_ui spec is invalid/,
  );
});

test("a valid JSON string spec is still checked against the catalog and limits", async () => {
  const unknown = JSON.stringify({ root: "x", elements: { x: { type: "Html", props: {} } } });
  await assert.rejects(callAsHarness({ spec: unknown }), /render_ui spec is invalid:\n- elements\.x\.type must be one of/);
  const extraProp = JSON.stringify({ root: "m", elements: { m: metric({ onClick: "alert(1)" }) } });
  await assert.rejects(callAsHarness({ spec: extraProp }), /render_ui spec is invalid:[\s\S]*Unrecognized key/);
  const badLink = JSON.stringify({
    root: "l",
    elements: { l: { type: "Link", props: { label: "x", href: "https://evil.example" }, children: [] } },
  });
  await assert.rejects(callAsHarness({ spec: badLink }), /render_ui spec is invalid/);
  // The declared form is held to the same catalog.
  await assert.rejects(
    callAsHarness({ root: "l", links: [{ id: "l", label: "x", href: "https://evil.example" }] }),
    /render_ui spec is invalid/,
  );
  await assert.rejects(
    callAsHarness({ root: "m", metrics: [{ id: "m", label: "T1", value: 1, onClick: "alert(1)" }] }),
    /Validation failed for tool "render_ui"|Unrecognized key/,
  );
});

test("the tool description explains the declared argument form", () => {
  assert.match(uiTool.description, /List each element under its type \(`stacks`, `cards`/);
  assert.match(uiTool.description, /A table row lists one cell per column, in column order/);
});

test("every catalog component has an argument list, with the catalog's enums", () => {
  assert.deepEqual(Object.keys(UI_INPUT_GROUPS), UI_COMPONENT_TYPES);
  const { properties } = uiTool.parameters;
  for (const group of Object.values(UI_INPUT_GROUPS)) {
    assert.equal(properties[group].type, "array", group);
    assert.ok(uiTool.parameters.required.includes(group), group);
  }
  assert.deepEqual(properties.metrics.items.properties.tone.enum, ["neutral", "info", "success", "warning", "error"]);
  assert.deepEqual(properties.alerts.items.properties.tone.enum, ["info", "success", "warning", "error"]);
});

/** Keywords Anthropic's strict tool mode rejects (pi-ai 1.5.0 anthropic-messages.js). */
const ANTHROPIC_STRICT_UNSUPPORTED = [
  "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "maxItems",
  "uniqueItems", "minContains", "maxContains", "minProperties", "maxProperties", "minItems", "format",
];

test("render_ui prefers constrained sampling with a schema strict mode can express", () => {
  assert.deepEqual(uiTool.constrainedSampling, { type: "json_schema", strict: "prefer" });
  const strict = makeStrictJsonSchema(uiTool.parameters);
  let unions = 0;
  const walk = (node, path) => {
    if (!node || typeof node !== "object") return;
    if (!Array.isArray(node)) {
      for (const key of ANTHROPIC_STRICT_UNSUPPORTED) assert.equal(node[key], undefined, `${path}.${key}`);
      if (Array.isArray(node.anyOf)) unions++;
    }
    for (const [key, value] of Object.entries(node)) walk(value, `${path}.${key}`);
  };
  walk(strict, "$");
  // Anthropic and Bedrock reject more than 16 optional or union-typed parameters across strict tools.
  assert.ok(unions <= 16, `${unions} optional or union-typed parameters`);
});

/** The request body a provider API builds for one turn offering render_ui, captured before any network I/O. */
async function requestBody(stream, model) {
  let body;
  const context = normalizeContext({
    systemPrompt: "test",
    messages: [{ role: "user", content: "show T1", timestamp: 0 }],
    // The declaration pi-durable records in the transcript.
    tools: [toToolDeclaration(uiTool)],
  });
  const events = stream(model, context, {
    apiKey: "test-key",
    maxRetries: 0,
    fetch: async (_url, init) => {
      body = JSON.parse(init.body);
      return new Response("{}", { status: 418 });
    },
    onPayload: (payload) => {
      // Bedrock's SDK has no fetch hook; stop it before it signs a request.
      if (model.api === "bedrock-converse-stream") {
        body = payload;
        throw new Error("captured");
      }
      return undefined;
    },
  });
  for await (const _ of events) {
    // Drain; the captured request then fails.
  }
  return body;
}

const testModel = (fields) => ({
  id: "test-model",
  name: "test-model",
  reasoning: false,
  input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 65_536,
  maxTokens: 1024,
  ...fields,
});

test("providers with strict tools receive render_ui with strict: true and its strict schema", async () => {
  const expected = makeStrictJsonSchema(toToolDeclaration(uiTool).parameters);
  const { providers } = buildModelsConfig(
    `chat_models:
  - provider: openai-compatible-chat
    name: test-model
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT
    strict_tool_schemas: true
`,
    undefined,
    { OPENAI_COMPATIBLE_BASE_URL_CHAT: "http://127.0.0.1:9/v1" },
  );
  const provider = providers["openai-compatible-chat"];
  const [entry] = provider.models;
  const optedIn = await requestBody(
    completions,
    testModel({ ...entry, provider: "openai-compatible-chat", api: provider.api, baseUrl: provider.baseUrl, compat: { ...provider.compat, ...entry.compat } }),
  );
  assert.equal(optedIn.tools[0].function.strict, true);
  assert.deepEqual(optedIn.tools[0].function.parameters, expected);

  const openai = await requestBody(
    responses,
    testModel({ provider: "openai", api: "openai-responses", baseUrl: "http://127.0.0.1:9/v1", compat: { supportsStrictMode: true } }),
  );
  assert.equal(openai.tools[0].strict, true);
  assert.deepEqual(openai.tools[0].parameters, expected);

  const claude = await requestBody(
    anthropic,
    testModel({ provider: "anthropic", api: "anthropic-messages", baseUrl: "http://127.0.0.1:9", compat: { supportsStrictTools: true } }),
  );
  assert.equal(claude.tools[0].strict, true);
  assert.deepEqual(claude.tools[0].input_schema, expected);

  const bedrockBody = await requestBody(
    bedrock,
    testModel({ provider: "amazon-bedrock", api: "bedrock-converse-stream", baseUrl: "http://127.0.0.1:9", compat: { supportsStrictMode: true } }),
  );
  assert.equal(bedrockBody.toolConfig.tools[0].toolSpec.strict, true);
  assert.deepEqual(bedrockBody.toolConfig.tools[0].toolSpec.inputSchema.json, expected);
});

test("endpoints without strict tools still get render_ui, unenforced, instead of a failed request", async () => {
  // A custom OpenAI-compatible endpoint as models-config.ts writes it without strict_tool_schemas.
  const model = testModel({
    provider: "openai-compatible-chat",
    api: "openai-completions",
    baseUrl: "http://127.0.0.1:9/v1",
    compat: { supportsDeveloperRole: false, supportsReasoningEffort: false, supportsStore: false, maxTokensField: "max_tokens" },
  });
  const body = await requestBody(completions, model);
  const [tool] = body.tools;
  assert.equal(tool.function.name, "render_ui");
  assert.equal("strict" in tool.function, false, "no strict field for endpoints that may reject it");
  assert.deepEqual(tool.function.parameters, toToolDeclaration(uiTool).parameters);

  // Why "prefer": "require" would fail every request to such an endpoint before it is sent.
  const required = { ...toToolDeclaration(uiTool), constrainedSampling: { type: "json_schema", strict: "require" } };
  let error = "";
  const events = completions(
    model,
    normalizeContext({ systemPrompt: "test", messages: [{ role: "user", content: "x", timestamp: 0 }], tools: [required] }),
    { apiKey: "test-key", maxRetries: 0, fetch: async () => assert.fail("no request is sent") },
  );
  for await (const event of events) if (event.type === "error") error = event.error.errorMessage;
  assert.match(error, /requires JSON-schema constrained sampling, but strict tools are unsupported/);
});

test("a malformed JSON string spec is rejected with its location, not repaired", () => {
  // An extra "}" after the Table's props closes `elements` early, so the Table's
  // children and the later elements fall outside it.
  const malformed =
    '{"root":"s","elements":{"s":{"type":"Stack","props":{},"children":["fails","links"]},' +
    '"fails":{"type":"Table","props":{"columns":[{"key":"t","label":"タスク"}],"rows":[{"t":"CheckT1"}]}}},"children":[]},' +
    '"links":{"type":"Stack","props":{"direction":"horizontal"},"children":["l1"]},' +
    '"l1":{"type":"Link","props":{"label":"q37","href":"/chip/144Qv2/qubit/37"},"children":[]}}}';
  assert.throws(() => JSON.parse(malformed));
  let message = "";
  try {
    prepareUiArguments({ spec: malformed });
  } catch (error) {
    message = error.message;
  }
  assert.match(message, /render_ui spec was sent as a string that is not valid JSON/);
  assert.match(message, /top-level object closes at character \d+ but text continues/);
  assert.match(message, /⟨here⟩,"links":\{"type":"Stack"/);
  assert.match(message, /Send the elements as JSON objects, not as a string\./);
});

test("other malformed or non-object JSON string specs are rejected with a reason", () => {
  const reject = (spec, pattern) => assert.throws(() => prepareUiArguments({ spec }), pattern);
  reject('{"root":"s","elements":{"s":{"type":"Text","props":{"text":"hi"}}', /2 bracket\(s\) are not closed/);
  reject('{"root":"s","elements":{"s":[}}}', /"\}" at character \d+ where "\]" was expected/);
  reject('{"root":"s', /a string is not terminated/);
  reject("", /not valid JSON/);
  reject("[1, 2]", /must hold a JSON object with root and elements/);
  reject('"{}"', /must hold a JSON object/);
  reject("x".repeat(UI_SPEC_LIMITS.maxBytes * 2 + 1), /the limit is 100000 characters/);
});

test("unknown components and unknown or extra props are rejected", () => {
  assert.match(
    errorsOf({ root: "x", elements: { x: { type: "Html", props: { html: "<b>" } } } }),
    /elements\.x\.type must be one of/,
  );
  assert.match(
    errorsOf({ root: "m", elements: { m: metric({ onClick: "alert(1)" }) } }),
    /Unrecognized key/,
  );
  assert.match(
    errorsOf({ root: "a", elements: { a: { type: "Alert", props: { tone: "loud", message: "x" } } } }),
    /tone/,
  );
});

test("dynamic json-render features are rejected", () => {
  for (const field of ["visible", "on", "watch", "repeat", "slots"]) {
    assert.match(
      errorsOf({ root: "m", elements: { m: { ...metric(), [field]: true } } }),
      new RegExp(`elements\\.m\\.${field} is not supported`),
    );
  }
  assert.match(errorsOf({ ...valid, state: { a: 1 } }), /spec\.state is not supported/);
  assert.match(
    errorsOf({ root: "m", elements: { m: metric({ value: { $state: "/t1" } }) } }),
    /elements\.m\.props\.value\.\$state: expressions are not supported/,
  );
  assert.match(
    errorsOf({
      root: "c",
      elements: {
        c: { type: "Chart", props: { data: [{ y: [1] }], layout: { title: { $computed: "f" } } } },
      },
    }),
    /expressions are not supported/,
  );
});

test("cycles, shared children, orphans and missing children are rejected", () => {
  assert.match(
    errorsOf({
      root: "a",
      elements: {
        a: { type: "Stack", props: {}, children: ["b"] },
        b: { type: "Card", props: {}, children: ["a"] },
      },
    }),
    /cycle/,
  );
  assert.match(
    errorsOf({
      root: "a",
      elements: {
        a: { type: "Stack", props: {}, children: ["b", "c"] },
        b: { type: "Card", props: {}, children: ["m"] },
        c: { type: "Card", props: {}, children: ["m"] },
        m: metric(),
      },
    }),
    /more than one parent/,
  );
  assert.match(
    errorsOf({ root: "a", elements: { a: { type: "Stack", props: {}, children: ["nope"] } } }),
    /nope/,
  );
  assert.match(errorsOf({ root: "a", elements: { a: metric(), b: metric() } }), /orphan|not reachable|b/i);
  assert.match(errorsOf({ root: "zzz", elements: { a: metric() } }), /zzz/);
  assert.match(
    errorsOf({ root: "m", elements: { m: { ...metric(), children: ["n"] }, n: metric() } }),
    /Metric cannot have children/,
  );
});

test("size, element count and depth are bounded", () => {
  const deep = { root: "d0", elements: {} };
  for (let i = 0; i <= UI_SPEC_LIMITS.maxDepth; i++) {
    deep.elements[`d${i}`] = { type: "Stack", props: {}, children: i < UI_SPEC_LIMITS.maxDepth ? [`d${i + 1}`] : [] };
  }
  assert.match(errorsOf(deep), /deeper than 8 levels/);

  const many = { root: "s", elements: { s: { type: "Stack", props: {}, children: [] } } };
  for (let i = 0; i < UI_SPEC_LIMITS.maxElements; i++) many.elements[`m${i}`] = metric();
  assert.match(errorsOf(many), /the limit is 60/);

  const big = {
    root: "t",
    elements: { t: { type: "Text", props: { text: "x".repeat(UI_SPEC_LIMITS.maxBytes) } } },
  };
  assert.match(errorsOf(big), /characters; the limit is/);

  const cyclic = { root: "a", elements: {} };
  cyclic.elements.a = { type: "Stack", props: { self: cyclic } };
  assert.match(errorsOf(cyclic), /not serializable/);
});

test("links must be internal QDash pages", () => {
  const link = (href) => ({ root: "l", elements: { l: { type: "Link", props: { label: "Open", href } } } });
  assert.equal(validateUiSpec(link("/chip/64Qv3/qubit/32")).ok, true);
  assert.equal(validateUiSpec(link("/executions/abc?tab=tasks#t1")).ok, true);
  for (const href of [
    "https://evil.example/chip",
    "//evil.example/chip",
    "javascript:alert(1)",
    "/\\evil.example",
    "/api/executions",
    "/admin/users",
    "/chip/%0a",
    "chip/1",
    "/chip/\n1",
  ]) {
    const result = validateUiSpec(link(href));
    if (href === "/chip/%0a") {
      // Percent-encoded text stays inside the path and is harmless.
      assert.equal(result.ok, true);
      continue;
    }
    assert.equal(result.ok, false, `${href} should be rejected`);
  }
});

test("a ui block in tool details is streamed before tool_end, also from a durable entry", () => {
  const ui = { version: 1, spec: valid, fallback: "T1" };
  const live = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "render_ui",
    isError: false,
    result: { details: { ui } },
  });
  assert.equal(live[0].type, "ui");
  assert.equal(live[0].ui.fallback, "T1");
  assert.deepEqual(live[1], { type: "tool_end", name: "render_ui", isError: false });

  const replayed = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "render_ui",
    entry: { model: [{ role: "toolResult", details: { ui } }] },
  });
  assert.equal(replayed[0].type, "ui");
  assert.deepEqual(replayed[0].ui.spec.root, "s");
});

test("tool details with an unknown version or invalid spec stream no ui line", () => {
  assert.equal(uiBlockFromDetails({ ui: { version: 2, spec: valid, fallback: "x" } }), undefined);
  assert.equal(uiBlockFromDetails({ ui: { version: 1, spec: { root: "x" }, fallback: "x" } }), undefined);
  assert.equal(uiBlockFromDetails({ ui: { version: 1, spec: valid } }), undefined);
  assert.equal(uiBlockFromDetails(null), undefined);
  const events = toNdjsonEvents({
    type: "tool_execution_end",
    toolName: "render_ui",
    result: { details: { ui: { version: 1, spec: { root: 1 }, fallback: "x" } } },
  });
  assert.deepEqual(events, [{ type: "tool_end", name: "render_ui", isError: false }]);
});

// ui/src/lib/copilotUiSpec.ts lives outside every root workspace package, so its
// bare imports resolve by walking up from ui/src/lib: to ui/node_modules in the UI
// build, and to the root workspace's node_modules in the runtime (CI and the
// image install no UI dependencies). The root manifest must declare each of them,
// with the UI's range, so both ends validate with the same libraries.
test("the shared render_ui catalog's dependencies are declared by the root workspace", () => {
  const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
  const source = read("../../ui/src/lib/copilotUiSpec.ts");
  const imports = new Set(
    [...source.matchAll(/^import\s[^;]*?\sfrom\s+"([^"./][^"]*)"/gms)].map(([, name]) => name),
  );
  assert.deepEqual([...imports].sort(), ["@json-render/core", "zod"]);
  const root = JSON.parse(read("../../package.json")).dependencies ?? {};
  const ui = JSON.parse(read("../../ui/package.json")).dependencies ?? {};
  for (const name of imports) {
    assert.ok(root[name], `${name} is missing from the root package.json dependencies`);
    assert.equal(root[name], ui[name], `${name} range differs between root and ui package.json`);
  }
});
