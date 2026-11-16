import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { BACKGROUND_CONTEXT as context } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  AssistantEntry,
  createRegistry,
  defineExtension,
  defineTool,
  Harness,
  MemoryStorage,
  ToolResultEntry,
  UserEntry,
} from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { Type } from "typebox";

import { askUserTool } from "../src/ask-tool.ts";
import {
  ActiveChat,
  awaitsUser,
  CHAT_QUEUE_SETTINGS,
  continueBlocker,
  settleChat,
  STEER_ENTRY,
  readSteerReceipt,
  STEER_RECEIPT_BUSY_TIMEOUT_MS,
  steerKey,
  steerOutcomeOf,
  submissionByRequest,
} from "../src/chat-control.ts";
import { pendingApproval } from "../src/runtime.ts";
import { ViewEventStream } from "../src/view-events.ts";

/** A promise with its resolver, to hold a tool or a model call until the test releases it. */
function gate() {
  let open;
  const promise = new Promise((resolve) => (open = resolve));
  return { promise, open };
}

/** A tool that runs until the test releases it, and reports when it started. */
function waitingTool() {
  const started = gate();
  const release = gate();
  const tool = defineTool({
    name: "wait_calibration",
    description: "Waits for a calibration (test)",
    parameters: Type.Object({}),
    execute: async (_args, _api, toolContext) => {
      started.open();
      await new Promise((resolve, reject) => {
        release.promise.then(resolve);
        toolContext.abortSignal?.addEventListener("abort", () => reject(new Error("cancelled")), { once: true });
      });
      return { output: [{ type: "text", text: "calibration finished" }] };
    },
  });
  return { tool, started: started.promise, release: release.open };
}

async function openChat({ tools = [], storage = new MemoryStorage(), faux = fauxProvider({ tokensPerSecond: 0 }) } = {}) {
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const registry = createRegistry();
  registry.install(defineExtension({ name: "test-tools", tools }));
  const harness = await Harness.open(
    storage,
    { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } },
    context,
  );
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return { faux, harness, conversation };
}

/** The user-visible transcript: who said what, in canonical order. */
async function transcript(conversation) {
  const view = await conversation.context(context);
  return view.entries.flatMap((entry) => {
    const message = entry.model?.[0];
    if (STEER_ENTRY.is(entry)) return [`steer:${text(message)}`];
    if (UserEntry.is(entry)) return [`user:${text(message)}`];
    if (ToolResultEntry.is(entry)) return [`tool:${message.toolName}`];
    if (AssistantEntry.is(entry)) {
      return message.stopReason === "toolUse" ? ["assistant:tools"] : [`assistant:${text(message)}`];
    }
    return [];
  });
}

function text(message) {
  if (typeof message?.content === "string") return message.content;
  return (message?.content ?? []).filter((block) => block.type === "text").map((block) => block.text).join("");
}

/** The last user-side message the model received in a request. */
function lastUserText(transcriptContext) {
  const users = transcriptContext.messages.filter((message) => message.role === "user");
  return text(users.at(-1));
}

/** Collect the stream events of a conversation while a turn runs. */
async function recordEvents(conversation) {
  const events = [];
  const watch = await conversation.watch(context);
  const stream = new ViewEventStream(conversation, watch.value, (event) => events.push(event), context);
  watch.start(async (call) => {
    if (call.kind === "value") await stream.push(call.value);
  });
  return { events, finish: () => stream.finish(watch) };
}

async function until(condition) {
  for (let i = 0; i < 500; i++) {
    if (await condition()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error("condition not reached");
}

test("a steer sent while a tool waits is read in the same run, after the tool round", async () => {
  const { tool, started, release } = waitingTool();
  const { faux, harness, conversation } = await openChat({ tools: [tool] });
  const seen = [];
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
    (transcriptContext) => {
      seen.push(lastUserText(transcriptContext));
      return fauxAssistantMessage(fauxText("Using Q5 instead."));
    },
  ]);
  const recorder = await recordEvents(conversation);
  try {
    const active = new ActiveChat("project-a", context);
    const own = await conversation.submit({ type: "input", content: "Calibrate Q4", requestId: "turn-1" }, context);
    active.ready(harness, conversation);
    await started;
    const steered = await active.steer("steer-1", "Use Q5 instead");
    assert.equal(steered.status, "queued");
    release();
    const settlement = await settleChat(active, harness, own, context);
    await recorder.finish();

    assert.equal(settlement.final.status, "done");
    const steer = settlement.steers.get("steer-1");
    assert.equal(steer.status, "done");
    // The steer joined the run: it settled with the same answer as the turn.
    assert.equal(steer.answer, settlement.final.answer);
    assert.deepEqual(seen, ["Use Q5 instead"]);
    assert.deepEqual(await transcript(conversation), [
      "user:Calibrate Q4",
      "assistant:tools",
      "tool:wait_calibration",
      "steer:Use Q5 instead",
      "assistant:Using Q5 instead.",
    ]);
    // The stream reports the steer where it landed: after the tool ended, before the answer.
    const order = recorder.events
      .map((event) => (event.type === "message_update" ? event.changes.some((c) => c.type === "text_delta") && "text" : event.type))
      .filter(Boolean);
    const placed = order.indexOf("steer_placed");
    assert.ok(placed > order.indexOf("tool_execution_end"));
    assert.ok(placed < order.lastIndexOf("text"));
    const event = recorder.events.find((candidate) => candidate.type === "steer_placed");
    assert.equal(event.requestId, "steer-1");
    assert.equal(event.text, "Use Q5 instead");
    assert.equal(event.answer, "");
    // After settling, a late steer is refused instead of starting a run.
    assert.deepEqual(await active.steer("steer-late", "One more thing"), { status: "rejected", reason: "idle" });
    assert.equal((await transcript(conversation)).length, 5);
  } finally {
    await harness.close(context);
  }
});

test("a steer that arrives after the last tool round follows the answer and starts the next run", async () => {
  const { harness, conversation, faux } = await openChat();
  const answering = gate();
  const hold = gate();
  faux.setResponses([
    async () => {
      answering.open();
      await hold.promise;
      return fauxAssistantMessage(fauxText("T1 is 42 us."));
    },
    (transcriptContext) => fauxAssistantMessage(fauxText(`Answering: ${lastUserText(transcriptContext)}`)),
  ]);
  const recorder = await recordEvents(conversation);
  try {
    const active = new ActiveChat(undefined, context);
    const own = await conversation.submit({ type: "input", content: "What is T1?" }, context);
    active.ready(harness, conversation);
    await answering.promise;
    assert.equal((await active.steer("steer-2", "And T2?")).status, "queued");
    hold.open();
    const settlement = await settleChat(active, harness, own, context);
    await recorder.finish();

    // The turn waited for the run the steer started; that run's answer is final.
    assert.equal(settlement.final, settlement.steers.get("steer-2"));
    assert.equal(settlement.final.status, "done");
    assert.deepEqual(await transcript(conversation), [
      "user:What is T1?",
      "assistant:T1 is 42 us.",
      "steer:And T2?",
      "assistant:Answering: And T2?",
    ]);
    const event = recorder.events.find((candidate) => candidate.type === "steer_placed");
    assert.equal(event.answer, "T1 is 42 us.");
  } finally {
    await harness.close(context);
  }
});

test("a steer to an idle conversation is refused and starts nothing", async () => {
  const { harness, conversation, faux } = await openChat();
  faux.setResponses([fauxAssistantMessage(fauxText("Done."))]);
  try {
    const active = new ActiveChat(undefined, context);
    const own = await conversation.submit({ type: "input", content: "Hello" }, context);
    active.ready(harness, conversation);
    await own.wait(context);
    // The run answered but the turn has not settled yet: the harness itself refuses it.
    assert.deepEqual(await active.steer("steer-3", "Wait"), { status: "rejected", reason: "idle" });
    const settlement = await settleChat(active, harness, own, context);
    assert.equal(settlement.steers.size, 0);
    assert.deepEqual(await transcript(conversation), ["user:Hello", "assistant:Done."]);
    assert.equal(faux.state.callCount, 1);
  } finally {
    await harness.close(context);
  }
});

test("a steer retried with its request ID is placed once, and steers keep their send order", async () => {
  const { tool, started, release } = waitingTool();
  const { faux, harness, conversation } = await openChat({ tools: [tool] });
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage(fauxText("Noted both.")),
  ]);
  try {
    const active = new ActiveChat(undefined, context);
    const own = await conversation.submit({ type: "input", content: "Run it" }, context);
    active.ready(harness, conversation);
    await started;
    const [first, again, second] = await Promise.all([
      active.steer("steer-a", "First note"),
      active.steer("steer-a", "First note"),
      active.steer("steer-b", "Second note"),
    ]);
    assert.equal(first.submissionId, again.submissionId);
    assert.notEqual(first.submissionId, second.submissionId);
    release();
    const settlement = await settleChat(active, harness, own, context);
    assert.equal(settlement.steers.size, 2);
    assert.deepEqual(await transcript(conversation), [
      "user:Run it",
      "assistant:tools",
      "tool:wait_calibration",
      "steer:First note",
      "steer:Second note",
      "assistant:Noted both.",
    ]);
    // Retried after it was placed, it reports where it landed.
    const placed = steerOutcomeOf(await (await harness.submission(first.submissionId, context)).status(context));
    assert.equal(placed.status, "applied");
  } finally {
    await harness.close(context);
  }
});

test("a steer still queued when the run fails is withdrawn, not kept for the next message", async () => {
  const { harness, conversation, faux } = await openChat();
  const answering = gate();
  const hold = gate();
  faux.setResponses([
    async () => {
      answering.open();
      await hold.promise;
      return fauxAssistantMessage([], { stopReason: "error", errorMessage: "HTTP 503" });
    },
  ]);
  try {
    const active = new ActiveChat(undefined, context);
    const own = await conversation.submit({ type: "input", content: "Summarize" }, context);
    active.ready(harness, conversation);
    await answering.promise;
    assert.equal((await active.steer("steer-4", "Shorter please")).status, "queued");
    hold.open();
    const settlement = await settleChat(active, harness, own, context);
    assert.equal(settlement.final.status, "unanswered");
    assert.equal(settlement.final.reason, "model_error");
    assert.deepEqual(steerOutcomeOf(settlement.steers.get("steer-4")), {
      status: "withdrawn",
      submissionId: settlement.steers.get("steer-4").id,
      reason: "run_failed",
    });
    assert.deepEqual(await transcript(conversation), ["user:Summarize", "assistant:"]);
  } finally {
    await harness.close(context);
  }
});

test("a run that failed with a model error continues without a new user message, idempotently", async () => {
  const dir = mkdtempSync(join(tmpdir(), "chat-control-"));
  const path = join(dir, "session.sqlite");
  const faux = fauxProvider({ tokensPerSecond: 0 });
  let opened = await openChat({ storage: await openNodeSqliteStorage(path), faux });
  try {
    faux.setResponses([
      fauxAssistantMessage([], { stopReason: "error", errorMessage: "HTTP 500" }),
      (transcriptContext) => fauxAssistantMessage(fauxText(`Answer to: ${lastUserText(transcriptContext)}`)),
    ]);
    let { conversation, harness } = opened;
    const failed = await (await conversation.submit({ type: "input", content: "Explain T1" }, context)).wait(context);
    assert.equal(failed.reason, "model_error");
    assert.equal(await continueBlocker(conversation, context), undefined);

    const continued = await conversation.submit({ type: "continue", requestId: "continue-1" }, context);
    const done = await continued.wait(context);
    assert.equal(done.status, "done");
    assert.deepEqual(await transcript(conversation), ["user:Explain T1", "assistant:", "assistant:Answer to: Explain T1"]);
    assert.equal(await continueBlocker(conversation, context), "nothing_to_continue");

    // After a reopen, the same request ID finds the original continue before any gate.
    await harness.close(context);
    opened = await openChat({ storage: await openNodeSqliteStorage(path), faux });
    ({ conversation, harness } = opened);
    const known = await submissionByRequest(harness, conversation, "continue-1", context);
    assert.equal(known.record.type, "continue");
    assert.equal(known.record.status, "done");
    assert.equal(known.record.answer, done.answer);
    assert.equal(await submissionByRequest(harness, conversation, "unknown", context), undefined);
    assert.equal(faux.state.callCount, 2);
  } finally {
    await opened.harness.close(context);
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a steer's receipt is read from the store after its turn closed, scoped to its project, admitting nothing", async () => {
  const dir = mkdtempSync(join(tmpdir(), "chat-receipt-"));
  const path = join(dir, "session.sqlite");
  const { tool, started, release } = waitingTool();
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const { harness, conversation } = await openChat({ tools: [tool], storage: await openNodeSqliteStorage(path), faux });
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
    (transcriptContext) => fauxAssistantMessage(fauxText(`Answer: ${lastUserText(transcriptContext)}`)),
  ]);
  let closed = false;
  try {
    assert.deepEqual(await readSteerReceipt(join(dir, "missing.sqlite"), "p1", "s1", context), { status: "not_found" });
    const active = new ActiveChat("p1", context);
    const own = await conversation.submit({ type: "input", content: "Calibrate Q4", requestId: "s1" }, context);
    active.ready(harness, conversation);
    await started;
    const queued = await active.steer("s1", "Use Q5");
    assert.equal(queued.status, "queued");
    // The turn's own request ID "s1" and the steer's do not collide.
    assert.notEqual(queued.submissionId, own.id);
    // Read beside the running writer: the steer as the store has it now.
    assert.deepEqual(await readSteerReceipt(path, "p1", "s1", context), queued);
    release();
    const settlement = await settleChat(active, harness, own, context);
    const applied = steerOutcomeOf(settlement.steers.get("s1"));
    assert.equal(applied.status, "applied");
    // The turn is over and its harness closed: nothing in memory remembers the steer.
    await harness.close(context);
    closed = true;
    assert.deepEqual(await readSteerReceipt(path, "p1", "s1", context), applied);
    assert.equal(await readSteerReceipt(path, "p2", "s1", context), "wrong_project");
    assert.equal(await readSteerReceipt(path, undefined, "s1", context), "wrong_project");
    assert.deepEqual(await readSteerReceipt(path, "p1", "s2", context), { status: "not_found" });
    // The lookup admitted nothing: reopened, the store has the same submissions.
    const reopened = await openNodeSqliteStorage(path);
    try {
      const page = await reopened.scanSubmissions({}, 100, undefined, context);
      assert.deepEqual(page.items.map((r) => r.requestId).sort(), ["s1", steerKey("p1", "s1")].sort());
    } finally {
      await reopened.close(context);
    }
    assert.equal(faux.state.callCount, 2);
  } finally {
    if (!closed) await harness.close(context);
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a steer lookup that cannot get the store's lock fails within its busy timeout, never not_found", async () => {
  const dir = mkdtempSync(join(tmpdir(), "chat-receipt-busy-"));
  const path = join(dir, "session.sqlite");
  // A store with a schema, then another connection that holds its write lock.
  await (await openNodeSqliteStorage(path)).close(context);
  const { DatabaseSync } = await import("node:sqlite");
  const holder = new DatabaseSync(path);
  try {
    holder.exec("BEGIN IMMEDIATE");
    const started = Date.now();
    await assert.rejects(readSteerReceipt(path, "p1", "s1", context), (error) => /locked|busy/i.test(String(error?.message ?? error)));
    const waited = Date.now() - started;
    assert.ok(waited >= STEER_RECEIPT_BUSY_TIMEOUT_MS - 100, `gave up after ${waited} ms`);
    assert.ok(waited < STEER_RECEIPT_BUSY_TIMEOUT_MS * 4, `waited ${waited} ms`);
    holder.exec("ROLLBACK");
    // Once the lock is free the same lookup answers.
    assert.deepEqual(await readSteerReceipt(path, "p1", "s1", context), { status: "not_found" });
  } finally {
    holder.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a continue after an answer reports nothing to answer, distinct from success", async () => {
  const { harness, conversation, faux } = await openChat();
  faux.setResponses([fauxAssistantMessage(fauxText("All done."))]);
  try {
    await (await conversation.submit({ type: "input", content: "Hi" }, context)).wait(context);
    assert.equal(await continueBlocker(conversation, context), "nothing_to_continue");
    // The SDK's own outcome, should a continue get past the gate.
    const settled = await (await conversation.submit({ type: "continue" }, context)).wait(context);
    assert.equal(settled.status, "unanswered");
    assert.equal(settled.reason, "nothing_to_answer");
    assert.equal(faux.state.callCount, 1);
  } finally {
    await harness.close(context);
  }
});

test("a stopped run continues, and its queued steer was withdrawn by the stop", async () => {
  const { tool, started } = waitingTool();
  const { faux, harness, conversation } = await openChat({ tools: [tool] });
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage(fauxText("Resumed.")),
  ]);
  try {
    const active = new ActiveChat(undefined, context);
    const own = await conversation.submit({ type: "input", content: "Long job" }, context);
    active.ready(harness, conversation);
    await started;
    assert.equal((await active.steer("steer-5", "Also plot it")).status, "queued");
    await conversation.abort(context);
    const settlement = await settleChat(active, harness, own, context);
    assert.equal(settlement.final.reason, "aborted");
    assert.equal(steerOutcomeOf(settlement.steers.get("steer-5")).status, "withdrawn");
    assert.equal(await continueBlocker(conversation, context), undefined);
    const resumed = await (await conversation.submit({ type: "continue" }, context)).wait(context);
    assert.equal(resumed.status, "done");
    const entries = await transcript(conversation);
    assert.equal(entries.filter((entry) => entry.startsWith("user:") || entry.startsWith("steer:")).length, 1);
    assert.equal(entries.at(-1), "assistant:Resumed.");
  } finally {
    await harness.close(context);
  }
});

test("a continue is refused while a question or an approval waits for the user", async () => {
  const { tool, started } = waitingTool();
  const { faux, harness, conversation } = await openChat({ tools: [tool, askUserTool] });
  faux.setResponses([
    fauxAssistantMessage(
      [
        fauxToolCall("ask_user", { question: "Which qubit?", options: [{ label: "Q1" }, { label: "Q2" }] }, { id: "a1" }),
        fauxToolCall("wait_calibration", {}, { id: "w1" }),
      ],
      { stopReason: "toolUse" },
    ),
  ]);
  try {
    const own = await conversation.submit({ type: "input", content: "Calibrate" }, context);
    await started;
    await until(async () => (await transcript(conversation)).includes("tool:ask_user"));
    await conversation.abort(context);
    assert.equal((await own.wait(context)).reason, "aborted");
    // Stopped with the question unanswered: the user answers it; continuing would skip it.
    assert.equal(await continueBlocker(conversation, context), "awaiting_user");
  } finally {
    await harness.close(context);
  }

  const approval = { id: "ap1", tool: "qdash_save_flow", label: "Save flow", args: {} };
  const toolResult = (toolName, details, isError = false) => ({
    kind: "pi.tool-result",
    model: [{ role: "toolResult", toolCallId: "c", toolName, content: [], details, isError }],
  });
  const user = { kind: "pi.user", model: [{ role: "user", content: "x" }] };
  const steer = { kind: "qdash.steer", data: { requestId: "s" }, model: [{ role: "user", content: "y" }] };
  assert.equal(awaitsUser([user, toolResult("qdash_save_flow", { approval })]), true);
  assert.equal(awaitsUser([user, toolResult("propose_code_edit", {})]), true);
  assert.equal(awaitsUser([user, toolResult("ask_user", {}, true)]), false);
  assert.equal(awaitsUser([toolResult("ask_user", {}), steer]), false);
  assert.equal(awaitsUser([toolResult("qdash_get_chip", {})]), false);
});

test("a steer after an approval request makes the approval stale", async () => {
  const approval = { id: "ap2", tool: "qdash_save_flow", label: "Save", args: {} };
  const entries = [
    { kind: "pi.user", model: [{ role: "user", content: "save" }] },
    { kind: "pi.tool-result", model: [{ role: "toolResult", toolCallId: "c", toolName: "qdash_save_flow", content: [], details: { approval } }] },
  ];
  const conversation = (list) => ({ context: async () => ({ entries: list }) });
  assert.deepEqual(await pendingApproval(conversation(entries), "ap2"), approval);
  const steered = [...entries, { kind: "qdash.steer", data: { requestId: "s" }, model: [{ role: "user", content: "no" }] }];
  assert.equal(await pendingApproval(conversation(steered), "ap2"), undefined);
});
