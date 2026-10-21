import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import {
  MAX_KNOWLEDGE_CHARS,
  acceptsCriteria,
  acceptsExamples,
  acceptsKnowledge,
  compactCriteria,
  examplesOf,
  fetchKnowledgeDraft,
  fetchTaskExamples,
  fetchTaskKnowledge,
  hasExamples,
  wantsExamples,
  withExamples,
  hasKnowledge,
  referenceIdentity,
  referenceOf,
  renderKnowledge,
  renderReference,
  requestedTaskName,
  toolExample,
  withKnowledge,
} from "../src/knowledge-context.ts";

test("only tools declaring both task_name and knowledge are filled", () => {
  assert.equal(acceptsKnowledge(Type.Object({ context: Type.String() })), false);
  assert.equal(acceptsKnowledge(Type.Object({ task_name: Type.Optional(Type.String()) })), false);
  assert.equal(
    acceptsKnowledge(
      Type.Object({ task_name: Type.Optional(Type.String()), knowledge: Type.Optional(Type.String()) }),
    ),
    true,
  );
});

test("the task the model named, and whether it already passed a reference", () => {
  assert.equal(requestedTaskName({ task_name: " CheckRabi " }), "CheckRabi");
  assert.equal(requestedTaskName({ task_name: "" }), undefined);
  assert.equal(requestedTaskName({ task_name: 3 }), undefined);
  assert.equal(requestedTaskName(null), undefined);
  assert.equal(hasKnowledge({ knowledge: "## Experiment" }), true);
  assert.equal(hasKnowledge({ knowledge: "  " }), false);
  assert.equal(hasKnowledge({}), false);
});

test("a fetched reference fills the background, and the criteria only when the tool declares them", () => {
  const args = { context: "Rabi on Q05", task_name: "CheckRabi" };
  const criteria = { statuses: { SUCCESS: "clear oscillation" }, parameters: { rabi_frequency: "float" } };
  assert.deepEqual(withKnowledge(args, { knowledge: "guide", criteria }), { ...args, knowledge: "guide", criteria });
  assert.deepEqual(withKnowledge(args, { knowledge: "guide", criteria }, false), { ...args, knowledge: "guide" });
  assert.deepEqual(withKnowledge(args, { knowledge: "guide" }), { ...args, knowledge: "guide" });
  // Empty criteria members are dropped; nothing left means no `criteria` argument.
  assert.deepEqual(withKnowledge(args, { knowledge: "guide", criteria: { guidance: [], statuses: {} } }), { ...args, knowledge: "guide" });
  assert.equal(withKnowledge(args, undefined), args);
  assert.equal(acceptsCriteria(Type.Object({ knowledge: Type.Optional(Type.String()) })), false);
  assert.equal(acceptsCriteria(Type.Object({ criteria: Type.Optional(Type.Object({})) })), true);
});

test("the reference the model passed itself is kept for the record, and identified with its criteria", () => {
  assert.equal(referenceOf({ context: "c" }), undefined);
  assert.equal(referenceOf({ knowledge: "  " }), undefined);
  assert.deepEqual(referenceOf({ knowledge: "own" }), { knowledge: "own" });
  assert.deepEqual(referenceOf({ knowledge: "own", criteria: { statuses: { SUCCESS: "s" }, guidance: [] } }), {
    knowledge: "own",
    criteria: { statuses: { SUCCESS: "s" } },
  });
  assert.equal(referenceIdentity({ knowledge: "own" }), "own\n{}");
  assert.equal(referenceIdentity({ knowledge: "own", criteria: { range_format: "(a, b)" } }), 'own\n{"range_format":"(a, b)"}');
  assert.equal(compactCriteria(undefined), undefined);
  assert.deepEqual(compactCriteria({ guidance: ["a", " "], parameters: { t1: "float", bad: 3 }, range_format: " " }), {
    guidance: ["a"],
    parameters: { t1: "float" },
  });
});

test("the structured reference is preferred; the full prompt is the fallback, cut at a line", () => {
  assert.deepEqual(
    renderReference({
      prompt_text: "full",
      reference: {
        background: " This is a CheckT1 experiment. ",
        guidance: [],
        parameters: { t1: "float" },
        statuses: { SUCCESS: "single exponential decay", SHORT_T1: "flattens early" },
        range_format: null,
      },
    }),
    {
      knowledge: "This is a CheckT1 experiment.",
      criteria: { parameters: { t1: "float" }, statuses: { SUCCESS: "single exponential decay", SHORT_T1: "flattens early" } },
    },
  );
  assert.deepEqual(renderReference({ prompt_text: "full", reference: { background: "" } }), { knowledge: "full" });
  assert.deepEqual(renderReference({ prompt_text: "full" }), { knowledge: "full" });
  assert.equal(renderReference({}), undefined);
  assert.equal(renderKnowledge({ prompt_text: "full" }), "full");
  assert.equal(renderKnowledge({}), undefined);
  const lines = Array.from({ length: 400 }, (_, i) => `line ${i} ${"x".repeat(20)}`);
  const cut = renderKnowledge({ prompt_text: lines.join("\n") });
  assert.ok(cut.length <= MAX_KNOWLEDGE_CHARS + "\n[reference truncated]".length);
  assert.ok(cut.endsWith("\n[reference truncated]"));
  assert.match(cut, /x\n\[reference truncated\]$/); // ends on a whole line
});

const connection = { baseUrl: "http://api:5715", auth: { accessToken: "tok", projectId: "p1" } };

test("the reference is fetched as the user, from the task's knowledge endpoint", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, headers: init.headers });
    return { ok: true, status: 200, json: async () => ({ reference: { background: "This is a CheckRabi experiment.", statuses: { SUCCESS: "ok" } } }) };
  };
  assert.deepEqual(await fetchTaskKnowledge(connection, "Check Rabi", undefined, fetchImpl), {
    knowledge: "This is a CheckRabi experiment.",
    criteria: { statuses: { SUCCESS: "ok" } },
  });
  assert.deepEqual(calls, [
    {
      url: "http://api:5715/tasks/Check%20Rabi/knowledge",
      headers: { Authorization: "Bearer tok", Accept: "application/json", "X-Project-Id": "p1" },
    },
  ]);
});

test("a task without knowledge, or an unreachable API, yields no reference", async () => {
  const notFound = async () => ({ ok: false, status: 404, json: async () => ({}) });
  assert.equal(await fetchTaskKnowledge(connection, "Unknown", undefined, notFound), undefined);
  const down = async () => {
    throw new Error("ECONNREFUSED");
  };
  assert.equal(await fetchTaskKnowledge(connection, "CheckRabi", undefined, down), undefined);
});

test("labeled examples come from the knowledge response, one per status, without empties", () => {
  const knowledge = {
    examples: [
      { id: "e1", title: "Short T1", outcome: "suboptimal", status: "SHORT_T1", suggested_range: "(0, 50)", parameters: '{"t1": 14}', diagnosis: "T1 = 14 μs.", figures: [{ base64_data: "AAA", mime_type: "image/png", path: "examples/figures/t1.png" }] },
      { id: "no-figure", title: "x", outcome: "expected", diagnosis: "L", figures: [{ base64_data: "" }] },
      { id: "no-label", title: "y", outcome: "expected", diagnosis: "  ", status: "", figures: [{ base64_data: "BBB" }] },
      { id: "same-status", title: "Another short T1", outcome: "suboptimal", status: "SHORT_T1", diagnosis: "Also short.", figures: [{ base64_data: "EEE" }] },
      { id: "e2", title: "Flat", outcome: "apparatus", diagnosis: "No decay.", figures: [{ base64_data: "CCC" }, { base64_data: "DDD", mime_type: "image/jpeg" }] },
      { id: "e3", title: "Clean", outcome: "expected", status: "SUCCESS", figures: [{ base64_data: "FFF" }] },
    ],
  };
  assert.deepEqual(examplesOf(knowledge), [
    { id: "e1", title: "Short T1", outcome: "suboptimal", status: "SHORT_T1", suggested_range: "(0, 50)", parameters: '{"t1": 14}', analysis: "T1 = 14 μs.", images: [{ data: "AAA", mimeType: "image/png" }], paths: ["examples/figures/t1.png"] },
    { id: "e2", title: "Flat", outcome: "apparatus", status: "", suggested_range: "", parameters: "", analysis: "No decay.", images: [{ data: "CCC", mimeType: "image/png" }, { data: "DDD", mimeType: "image/jpeg" }], paths: ["", ""] },
    { id: "e3", title: "Clean", outcome: "expected", status: "SUCCESS", suggested_range: "", parameters: "", analysis: "", images: [{ data: "FFF", mimeType: "image/png" }], paths: [""] },
  ]);
  assert.equal(examplesOf(knowledge, 1).length, 1);
  // The figure budget stops the list: e2's two figures do not fit after e1's one.
  assert.deepEqual(examplesOf(knowledge, 6, 2).map((e) => e.id), ["e1"]);
  assert.deepEqual(examplesOf({}), []);
});

test("examples are filled only when the model asks and the tool takes them", () => {
  const withBoth = Type.Object({ task_name: Type.String(), examples: Type.Array(Type.Object({})) });
  assert.equal(acceptsExamples(withBoth), true);
  assert.equal(acceptsExamples(Type.Object({ examples: Type.Array(Type.Object({})) })), false);
  assert.equal(wantsExamples({ use_examples: true }), true);
  assert.equal(wantsExamples({ use_examples: "yes" }), false);
  assert.equal(hasExamples({ examples: [{ status: "x" }] }), true);
  assert.equal(hasExamples({ examples: [] }), false);
  const images = [{ data: "A", mimeType: "image/png" }];
  const example = { id: "e1", title: "Short T1", outcome: "suboptimal", status: "SHORT_T1", suggested_range: "(0, 50)", parameters: '{"t1": 14}', analysis: "Short.", images, paths: ["p.png"] };
  // Only what pi-qcaleval declares is passed on; the identity stays with the host.
  assert.deepEqual(withExamples({ context: "c" }, [example]), {
    context: "c",
    examples: [{ images, scenario: "Short T1", analysis: "Short.", parameters: { t1: 14 }, status: "SHORT_T1", suggested_range: "(0, 50)" }],
  });
  assert.deepEqual(withExamples({ context: "c" }, []), { context: "c" });
  // Labels an example lacks are left out; parameters that are not a JSON object go as text.
  assert.deepEqual(toolExample({ ...example, title: "", suggested_range: "", parameters: "t1 = 14 μs", status: "" }), {
    images,
    analysis: "Short.",
    parameters: "t1 = 14 μs",
  });
});

test("examples are fetched from the same knowledge endpoint, and none without it", async () => {
  const ok = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ prompt_text: "ref", examples: [{ id: "e1", title: "t", outcome: "expected", diagnosis: "L", figures: [{ base64_data: "A" }] }] }),
  });
  const examples = await fetchTaskExamples(connection, "CheckT1", undefined, ok);
  assert.deepEqual(examples.map((e) => e.id), ["e1"]);
  const notFound = async () => ({ ok: false, status: 404, json: async () => ({}) });
  assert.deepEqual(await fetchTaskExamples(connection, "Unknown", undefined, notFound), []);
});

test("a draft is fetched as the user by id, and one the API does not serve is an error", async () => {
  const calls = [];
  const ok = async (url, init) => {
    calls.push({ url, headers: init.headers });
    return { ok: true, status: 200, json: async () => ({ name: "CheckRabi", prompt_text: "ref" }) };
  };
  assert.deepEqual(await fetchKnowledgeDraft(connection, "ab12", undefined, ok), { name: "CheckRabi", prompt_text: "ref" });
  assert.deepEqual(calls, [
    {
      url: "http://api:5715/evaluations/knowledge-drafts/ab12/knowledge",
      headers: { Authorization: "Bearer tok", Accept: "application/json", "X-Project-Id": "p1" },
    },
  ]);

  const notFound = async () => ({ ok: false, status: 404, json: async () => ({ detail: "knowledge draft ab12 not found" }) });
  await assert.rejects(fetchKnowledgeDraft(connection, "ab12", undefined, notFound), {
    message: "HTTP 404: knowledge draft ab12 not found",
  });
  const bare = async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError("not json"); } });
  await assert.rejects(fetchKnowledgeDraft(connection, "ab12", undefined, bare), { message: "HTTP 502" });
});
