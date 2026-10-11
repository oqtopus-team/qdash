import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import {
  MAX_KNOWLEDGE_CHARS,
  acceptsExamples,
  acceptsKnowledge,
  examplesOf,
  fetchTaskExamples,
  fetchTaskKnowledge,
  hasExamples,
  wantsExamples,
  withExamples,
  hasKnowledge,
  renderKnowledge,
  requestedTaskName,
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

test("a fetched reference is added; without one the arguments are unchanged", () => {
  const args = { context: "Rabi on Q05", task_name: "CheckRabi" };
  assert.deepEqual(withKnowledge(args, "guide"), { ...args, knowledge: "guide" });
  assert.equal(withKnowledge(args, undefined), args);
});

test("the review guide is preferred, the full prompt is the fallback, and long text is cut at a line", () => {
  assert.equal(renderKnowledge({ review_prompt_text: "review", prompt_text: "full" }), "review");
  assert.equal(renderKnowledge({ review_prompt_text: "", prompt_text: "full" }), "full");
  assert.equal(renderKnowledge({}), undefined);
  const lines = Array.from({ length: 400 }, (_, i) => `line ${i} ${"x".repeat(20)}`);
  const cut = renderKnowledge({ review_prompt_text: lines.join("\n") });
  assert.ok(cut.length <= MAX_KNOWLEDGE_CHARS + "\n[reference truncated]".length);
  assert.ok(cut.endsWith("\n[reference truncated]"));
  assert.match(cut, /x\n\[reference truncated\]$/); // ends on a whole line
});

const connection = { baseUrl: "http://api:5715", auth: { accessToken: "tok", projectId: "p1" } };

test("the reference is fetched as the user, from the task's knowledge endpoint", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, headers: init.headers });
    return { ok: true, status: 200, json: async () => ({ review_prompt_text: "## Experiment: CheckRabi" }) };
  };
  assert.equal(await fetchTaskKnowledge(connection, "Check Rabi", undefined, fetchImpl), "## Experiment: CheckRabi");
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

test("labeled examples come from the knowledge response, figures first, without empties", () => {
  const knowledge = {
    examples: [
      { id: "e1", title: "Short T1", outcome: "suboptimal", label: "Outcome: suboptimal\nT1 = 14 μs.", figures: [{ base64_data: "AAA", mime_type: "image/png" }] },
      { id: "no-figure", title: "x", outcome: "expected", label: "L", figures: [{ base64_data: "" }] },
      { id: "no-label", title: "y", outcome: "expected", label: "  ", figures: [{ base64_data: "BBB" }] },
      { id: "e2", title: "Flat", outcome: "apparatus", label: "Outcome: apparatus", figures: [{ base64_data: "CCC" }, { base64_data: "DDD", mime_type: "image/jpeg" }] },
    ],
  };
  assert.deepEqual(examplesOf(knowledge), [
    { id: "e1", title: "Short T1", outcome: "suboptimal", label: "Outcome: suboptimal\nT1 = 14 μs.", images: [{ data: "AAA", mimeType: "image/png" }] },
    { id: "e2", title: "Flat", outcome: "apparatus", label: "Outcome: apparatus", images: [{ data: "CCC", mimeType: "image/png" }, { data: "DDD", mimeType: "image/jpeg" }] },
  ]);
  assert.equal(examplesOf(knowledge, 1).length, 1);
  assert.deepEqual(examplesOf({}), []);
});

test("examples are filled only when the model asks and the tool takes them", () => {
  const withBoth = Type.Object({ task_name: Type.String(), examples: Type.Array(Type.Object({})) });
  assert.equal(acceptsExamples(withBoth), true);
  assert.equal(acceptsExamples(Type.Object({ examples: Type.Array(Type.Object({})) })), false);
  assert.equal(wantsExamples({ use_examples: true }), true);
  assert.equal(wantsExamples({ use_examples: "yes" }), false);
  assert.equal(hasExamples({ examples: [{ label: "x" }] }), true);
  assert.equal(hasExamples({ examples: [] }), false);
  const example = { id: "e1", title: "t", outcome: "expected", label: "L", images: [{ data: "A", mimeType: "image/png" }] };
  // Only what pi-qcaleval declares is passed on; the identity stays with the host.
  assert.deepEqual(withExamples({ context: "c" }, [example]), { context: "c", examples: [{ label: "L", images: example.images }] });
  assert.deepEqual(withExamples({ context: "c" }, []), { context: "c" });
});

test("examples are fetched from the same knowledge endpoint, and none without it", async () => {
  const ok = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ prompt_text: "ref", examples: [{ id: "e1", title: "t", outcome: "expected", label: "L", figures: [{ base64_data: "A" }] }] }),
  });
  const examples = await fetchTaskExamples(connection, "CheckT1", undefined, ok);
  assert.deepEqual(examples.map((e) => e.id), ["e1"]);
  const notFound = async () => ({ ok: false, status: 404, json: async () => ({}) });
  assert.deepEqual(await fetchTaskExamples(connection, "Unknown", undefined, notFound), []);
});
