import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { validateToolArguments } from "@earendil-works/pi-ai/utils/validation";

import { toNdjsonEvents } from "../src/events.ts";
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

test("render_ui accepts a valid spec and returns a versioned block with fallback text", async () => {
  const result = await uiTool.execute({ spec: valid });
  const ui = result.details.ui;
  assert.equal(ui.version, 1);
  assert.deepEqual(ui.spec.elements.t1.props, valid.elements.t1.props);
  assert.match(ui.fallback, /- T1: 42\.1 us \(Q03\)/);
  assert.match(ui.fallback, /\| Qubit \| T1 \(us\) \|\n\| --- \| ---: \|\n\| Q03 \| 42\.1 \|/);
  assert.match(result.output[0].text, /UI rendered in the chat \(3 elements\)/);
});

test("render_ui fails the call with the problems listed so the model can correct it", async () => {
  await assert.rejects(
    uiTool.execute({ spec: { root: "m", elements: { m: metric({ value: undefined }) } } }),
    /render_ui spec is invalid:\n- elements\.m \(Metric\) props: value/,
  );
});

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

test("render_ui handles a spec sent as a JSON string like the same spec sent as an object", async () => {
  const fromObject = await callAsHarness({ spec: valid });
  const fromString = await callAsHarness({ spec: JSON.stringify(valid) });
  const fromPretty = await callAsHarness({ spec: JSON.stringify(valid, null, 2) });
  assert.deepEqual(fromString.details, fromObject.details);
  assert.deepEqual(fromPretty.details, fromObject.details);
});

test("prepareArguments leaves object specs and non-string specs to schema validation", async () => {
  const args = { spec: valid };
  assert.equal(prepareUiArguments(args), args);
  const numeric = { spec: 3 };
  assert.equal(prepareUiArguments(numeric), numeric);
  await assert.rejects(callAsHarness(numeric), /Validation failed for tool "render_ui"/);
  const original = JSON.stringify(valid);
  const stringArgs = { spec: original };
  prepareUiArguments(stringArgs);
  assert.equal(stringArgs.spec, original, "the call's arguments are not modified");
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
  assert.match(message, /Send `spec` as a JSON object, not a string\./);
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

test("a valid JSON string spec is still checked against the catalog and limits", async () => {
  const unknown = JSON.stringify({ root: "x", elements: { x: { type: "Html", props: {} } } });
  await assert.rejects(callAsHarness({ spec: unknown }), /Validation failed for tool "render_ui"/);
  const extraProp = JSON.stringify({ root: "m", elements: { m: metric({ onClick: "alert(1)" }) } });
  await assert.rejects(callAsHarness({ spec: extraProp }), /render_ui spec is invalid:[\s\S]*Unrecognized key/);
  const badLink = JSON.stringify({
    root: "l",
    elements: { l: { type: "Link", props: { label: "x", href: "https://evil.example" }, children: [] } },
  });
  await assert.rejects(callAsHarness({ spec: badLink }), /render_ui spec is invalid/);
});

test("the tool description asks for spec as an object", () => {
  assert.match(uiTool.description, /Pass `spec` as a JSON object, not as a string holding JSON\./);
});

test("render_ui offers the catalog types as a plain enum", () => {
  const type = uiTool.parameters.properties.spec.properties.elements.patternProperties;
  const element = Object.values(type)[0];
  assert.deepEqual(element.properties.type.enum, [
    "Stack",
    "Card",
    "Metric",
    "Table",
    "Alert",
    "Text",
    "Chart",
    "Link",
  ]);
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
