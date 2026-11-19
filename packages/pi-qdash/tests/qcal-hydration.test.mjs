import assert from "node:assert/strict";
import test from "node:test";

import {
  hydrateEvaluationArgs,
  isImageData,
  selectEvaluationFigures,
} from "../.test-dist/lib/qcal-hydration.js";
import { branchMessagesNewestFirst, installQcalHydration } from "../.test-dist/lib/qcal-hydration-hook.js";

const png = (fill) => Buffer.from(`\x89PNG\r\n\x1a\n${fill.repeat(80)}`, "latin1").toString("base64");
const RABI = png("r");
const T1 = png("t");
const ATTACHED = png("a");
const image = (data) => ({ type: "image", data, mimeType: "image/png" });
const figure = (data, taskName, taskId = `${taskName}-id`) => ({ content: [{ type: "text", text: "figure" }, image(data)], details: { tool: "qdash_get_task_figures", taskId, taskName } });

const PARAMETERS = { properties: { task_name: {}, knowledge: {}, criteria: {}, images: {}, examples: {}, use_examples: {}, max_images: {} } };
const KNOWLEDGE = {
  reference: { background: "Rabi background", statuses: { SUCCESS: "ok", FAIL: "bad" } },
  examples: [{ id: "e1", status: "SUCCESS", diagnosis: "fine", figures: [{ base64_data: png("e"), mime_type: "image/png", path: "e1.png" }] }],
};

test("only real image bytes count as a model's own figure", () => {
  assert.equal(isImageData(RABI), true);
  assert.equal(isImageData(Buffer.from(`\xff\xd8\xff${"j".repeat(80)}`, "latin1").toString("base64")), true);
  for (const data of ["<image 1>", "see attached", "A".repeat(120), Buffer.from("x".repeat(90)).toString("base64"), 42, undefined]) {
    assert.equal(isImageData(data), false, String(data).slice(0, 20));
  }
});

test("figures are taken only from the requested task", () => {
  // Newest first: a T1 figure after a Rabi figure.
  const messages = [figure(T1, "CheckT1"), figure(RABI, "CheckRabi")];
  assert.deepEqual(selectEvaluationFigures(messages, { taskName: "CheckRabi" }), { images: [image(RABI)], taskId: "CheckRabi-id", taskName: "CheckRabi" });
  assert.deepEqual(selectEvaluationFigures(messages, { taskName: "checkrabi" }).taskName, "CheckRabi");
  assert.deepEqual(selectEvaluationFigures(messages, {}).images, [image(T1)]);
  assert.deepEqual(selectEvaluationFigures(messages, { taskName: "CheckRamsey" }), { images: [] });
  // An unlabeled attachment counts until a figure of another task is newer than it.
  assert.deepEqual(selectEvaluationFigures([{ content: [image(ATTACHED)] }, figure(T1, "CheckT1")], { taskName: "CheckRabi" }).images, [image(ATTACHED)]);
  assert.deepEqual(selectEvaluationFigures([figure(T1, "CheckT1"), { content: [image(ATTACHED)] }], { taskName: "CheckRabi" }).images, []);
  // qdash_build_qcal_evidence records the task in its evidence.
  const evidence = { content: [image(RABI)], details: { tool: "qdash_build_qcal_evidence", taskId: "t9", evidence: { id: "t9", task: { name: "CheckRabi" } } } };
  assert.equal(selectEvaluationFigures([evidence], { taskName: "CheckRabi" }).taskId, "t9");
});

test("one knowledge request fills the reference, criteria, and examples; the model's own reference wins", async () => {
  const loads = [];
  const sources = (messages) => ({
    parameters: PARAMETERS,
    messages: () => messages,
    loadKnowledge: async (name) => { loads.push(name); return KNOWLEDGE; },
  });
  const filled = await hydrateEvaluationArgs(
    { task_name: "CheckRabi", use_examples: true, images: [{ data: "<image 1>", mimeType: "image/png" }] },
    sources([figure(T1, "CheckT1"), figure(RABI, "CheckRabi")]),
  );
  assert.deepEqual(loads, ["CheckRabi"]);
  assert.deepEqual(filled.args.images, [{ data: RABI, mimeType: "image/png" }]);
  assert.equal(filled.args.knowledge, "Rabi background");
  assert.deepEqual(filled.args.criteria, { statuses: { SUCCESS: "ok", FAIL: "bad" } });
  assert.equal(filled.args.examples.length, 1);
  assert.deepEqual(filled.summary, {
    task_name: "CheckRabi", figure_origin: "conversation", figures: 1, figure_task_id: "CheckRabi-id",
    knowledge: "host", criteria: true, examples: 1,
  });

  loads.length = 0;
  const own = await hydrateEvaluationArgs({ task_name: "CheckRabi", knowledge: "mine", images: [{ data: ATTACHED, mimeType: "image/png" }] }, sources([]));
  assert.deepEqual(loads, []);
  assert.equal(own.args.knowledge, "mine");
  assert.deepEqual(own.args.images, [{ data: ATTACHED, mimeType: "image/png" }]);
  assert.equal(own.summary.figure_origin, "arguments");
  assert.equal(own.summary.knowledge, "arguments");

  const placeholder = await hydrateEvaluationArgs({ context: "x", images: [{ data: "A".repeat(100), mimeType: "image/png" }] }, sources([]));
  assert.equal("images" in placeholder.args, false);
  assert.equal(placeholder.summary.figure_origin, "none");
});

test("an aborted knowledge request fails the hydration", async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    hydrateEvaluationArgs({ task_name: "CheckRabi" }, {
      parameters: PARAMETERS,
      messages: () => [],
      loadKnowledge: async (_name, signal) => { if (signal?.aborted) throw new Error("aborted"); return KNOWLEDGE; },
      signal: controller.signal,
    }),
    /aborted/,
  );
});

test("the CLI hook fills the model's qcal_evaluate call in place and records what it filled", async () => {
  const handlers = new Map();
  const pi = {
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    getAllTools: () => [{ name: "qcal_evaluate", parameters: PARAMETERS }],
  };
  const loads = [];
  installQcalHydration(pi, { loadTaskKnowledge: async (name) => { loads.push(name); return KNOWLEDGE; } });
  const entries = [
    { type: "message", message: { role: "user", content: "evaluate" } },
    { type: "message", message: { role: "toolResult", ...figure(RABI, "CheckRabi") } },
    { type: "custom", customType: "qdash-context" },
    { type: "message", message: { role: "toolResult", ...figure(T1, "CheckT1") } },
  ];
  const ctx = { sessionManager: { buildContextEntries: () => entries } };
  const input = { task_name: "CheckRabi", images: [{ data: "<image>", mimeType: "image/png" }] };
  const [onCall] = handlers.get("tool_call");
  assert.equal(await onCall({ toolName: "qcal_evaluate", toolCallId: "q1", input }, ctx), undefined);
  assert.deepEqual(input.images, [{ data: RABI, mimeType: "image/png" }]);
  assert.equal(input.knowledge, "Rabi background");
  assert.deepEqual(loads, ["CheckRabi"]);
  const [onResult] = handlers.get("tool_result");
  const patched = await onResult({ toolName: "qcal_evaluate", toolCallId: "q1", details: { dry_run: true } });
  assert.equal(patched.details.dry_run, true);
  assert.equal(patched.details.hydration.figure_task_id, "CheckRabi-id");
  assert.equal(await onResult({ toolName: "qcal_evaluate", toolCallId: "q1", details: {} }), undefined);

  // A script's call and other tools are not filled.
  const nested = { task_name: "CheckRabi" };
  await onCall({ toolName: "qcal_evaluate", toolCallId: "c1/1", parentToolCallId: "c1", input: nested }, ctx);
  await onCall({ toolName: "other_tool", toolCallId: "o1", input: nested }, ctx);
  assert.deepEqual(nested, { task_name: "CheckRabi" });
  assert.deepEqual([...branchMessagesNewestFirst({ getBranch: () => entries }, 2)].map((message) => message.details?.taskName), ["CheckT1", "CheckRabi"]);
});


test("hydration preserves explicit criteria in arguments and the effective reference record", async () => {
  const criteria = { guidance: ["explicit"] };
  const result = await hydrateEvaluationArgs({ task_name: "CheckRabi", criteria }, {
    parameters: PARAMETERS,
    messages: () => [],
    loadKnowledge: async () => KNOWLEDGE,
  });
  assert.equal(result.args.knowledge, "Rabi background");
  assert.deepEqual(result.args.criteria, criteria);
  assert.deepEqual(result.reference.criteria, criteria);
});

test("a hydration record never reaches a reused call id, another session, or a branch it was not filled from", async () => {
  const handlers = new Map();
  const pi = {
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    getAllTools: () => [{ name: "qcal_evaluate", parameters: PARAMETERS }],
  };
  installQcalHydration(pi, { loadTaskKnowledge: async () => KNOWLEDGE });
  const fire = async (event, payload, ctx) => {
    let last;
    for (const handler of handlers.get(event) ?? []) last = (await handler(payload, ctx)) ?? last;
    return last;
  };
  // Two branches of one session: the active one decides the figure.
  let entries = [{ type: "message", message: { role: "toolResult", ...figure(RABI, "CheckRabi") } }];
  const ctx = { sessionManager: { buildContextEntries: () => entries } };
  const evaluate = (id) => ({ toolName: "qcal_evaluate", toolCallId: id, input: { task_name: "CheckRabi" } });

  // q1 is filled but never reports a result (blocked by a later hook); the id is then reused by another tool.
  await fire("tool_call", evaluate("q1"), ctx);
  await fire("tool_call", { toolName: "other_tool", toolCallId: "q1", input: {} }, ctx);
  assert.equal(await fire("tool_result", { toolName: "other_tool", toolCallId: "q1", details: {} }), undefined);

  // Filled in one session, reported after a new session started with the same id.
  await fire("tool_call", evaluate("q2"), ctx);
  await fire("session_start", { type: "session_start", reason: "new" }, ctx);
  assert.equal(await fire("tool_result", { toolName: "qcal_evaluate", toolCallId: "q2", details: {} }), undefined);

  // After moving to a branch without the figure, a call is filled from that branch only.
  entries = [{ type: "message", message: { role: "user", content: "other branch" } }];
  const input = evaluate("q3").input;
  await fire("tool_call", { ...evaluate("q3"), input }, ctx);
  assert.equal(input.images, undefined);
  const result = await fire("tool_result", { toolName: "qcal_evaluate", toolCallId: "q3", details: {} });
  assert.equal(result.details.hydration.figure_task_id ?? undefined, undefined);
});
