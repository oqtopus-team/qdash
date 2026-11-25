import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKGROUND_CONTEXT as context } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxThinking, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  CompactionEntry,
  createRegistry,
  defineExtension,
  defineTool,
  Harness,
  MemoryStorage,
  ToolResultEntry,
  UserEntry,
} from "@earendil-works/pi-durable";
import { Type } from "typebox";

import { continueBlocker } from "../src/chat-control.ts";
import {
  buildCompactionExtension,
  COMPACTION_FAILED_MESSAGE,
  estimateTextTokens,
  isCompactionFailure,
  SUMMARY_ATTEMPTS,
  summaryBudget,
  summaryRequest,
  summarySource,
} from "../src/compaction.ts";

// Every model below is an injected faux provider: no request leaves the process.
// The window is small so a large tool result reaches the blocking compaction
// threshold within a turn, as a dashboard chat's metric reads do on the
// 64k-window local model, and the output cap is what a reasoning summary has
// to fit in.
const WINDOW = 24_000;
const OUTPUT = 2_048;
const SETTINGS = {
  retry: { enabled: false },
  compaction: { enabled: true, reserveTokens: 11_000, keepRecentTokens: 1_000, backgroundTokens: 0 },
};

/** Which kind of request the faux model got: pi-ai puts the system prompt first. */
function requestKind(ctx) {
  const first = ctx.messages[0];
  const system = first?.role === "system" ? String(first.content) : "";
  if (system.startsWith("You are a context summarization assistant. Read")) return "qdash-summary";
  if (system.startsWith("You are a context summarization assistant.")) return "builtin-summary";
  return "chat";
}

function lastUserText(ctx) {
  const message = ctx.messages.filter((m) => m.role === "user").at(-1);
  if (!message) return "";
  return typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
}

/** Japanese and JSON heavy text, as dashboard chats are. */
const FILLER = "量子ビットのT1とT2を比較するダッシュボード {\"qid\":\"Q12\",\"t1\":41.2} ".repeat(20);
const METRICS = JSON.stringify(Array.from({ length: 2_000 }, (_, i) => ({ qid: `Q${i}`, t1: 41.2, t2: 30.1 })));

/**
 * A harness over memory storage with the QDash compaction extension, a write
 * tool and a large read tool, each counting its executions. The first turn
 * ("Save ...") saves once; the second ("Explain ...") reads metrics, whose
 * result passes the blocking threshold, so the turn's next request waits for
 * a compaction. `summarize(kind, ctx, options)` answers every summary request.
 */
async function openChat({ summarize, extension = true, logs = [], outputTokens = OUTPUT }) {
  const faux = fauxProvider({
    tokensPerSecond: 0,
    models: [{ id: "local-qwen", reasoning: true, contextWindow: WINDOW, maxTokens: outputTokens }],
  });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const calls = { chat: 0, "qdash-summary": 0, "builtin-summary": 0, summaryOptions: [], saves: 0, reads: 0 };
  const readTool = defineTool({
    name: "read_metrics",
    description: "Reads metric values (test)",
    parameters: Type.Object({}),
    execute: async () => {
      calls.reads++;
      return { output: [{ type: "text", text: METRICS }] };
    },
  });
  const saveTool = defineTool({
    name: "save_dashboard",
    description: "Saves a dashboard (test)",
    parameters: Type.Object({ script: Type.String() }),
    execute: async () => {
      calls.saves++;
      return { output: [{ type: "text", text: "saved dashboard d-42 revision 7" }] };
    },
  });
  const reply = (ctx, options) => {
    const kind = requestKind(ctx);
    calls[kind]++;
    if (kind !== "chat") {
      calls.summaryOptions.push({ kind, maxTokens: options?.maxTokens, reasoning: options?.reasoning });
      return summarize(kind, ctx, options);
    }
    const user = lastUserText(ctx);
    const last = ctx.messages.at(-1);
    if (last?.role === "user" && user.startsWith("Save")) {
      return fauxAssistantMessage([fauxToolCall("save_dashboard", { script: "def metric(): return 1" }, { id: "s1" })], {
        stopReason: "toolUse",
      });
    }
    if (last?.role === "user" && user.startsWith("Explain")) {
      return fauxAssistantMessage([fauxToolCall("read_metrics", {}, { id: "r1" })], { stopReason: "toolUse" });
    }
    return fauxAssistantMessage(fauxText(`Answer ${calls.chat}`));
  };
  faux.setResponses(Array.from({ length: 200 }, () => reply));
  const registry = createRegistry();
  registry.install(defineExtension({ name: "t", tools: [saveTool, readTool] }));
  if (extension) registry.install(buildCompactionExtension({ log: (line) => logs.push(line) }));
  const harness = await Harness.open(new MemoryStorage(), { models, registry, settings: SETTINGS }, context);
  const conversation = await harness.root(context, {
    agent: { model: { provider: model.provider, modelId: model.id }, thinkingLevel: "medium" },
  });
  return { harness, conversation, calls };
}

async function turn(conversation, content) {
  const submission = await conversation.submit({ type: "input", content }, context);
  return submission.wait(context);
}

/** The first turn, which saves once and stays below the threshold. */
async function saveTurn(conversation, text = FILLER) {
  assert.equal((await turn(conversation, `Save this dashboard. ${text}`)).status, "done");
}

/** Every stored entry of the conversation, also those a summary replaced. */
async function entries(conversation) {
  return (await conversation.entries({}, 1000, undefined, context)).items;
}

const lengthStop = () => fauxAssistantMessage([fauxThinking("x".repeat(500)), fauxText("## Goal\n- partial")], { stopReason: "length" });
const summaryOf = (text) => fauxAssistantMessage(fauxText(text));

test("summaryBudget gives the summary the model's output cap within its window", () => {
  assert.deepEqual(summaryBudget({ contextWindow: 65_536, maxTokens: 8_192 }), {
    maxTokens: 8_192,
    inputTokens: Math.floor((65_536 - 8_192 - 4_096) * 0.85),
  });
  // A small window keeps three quarters for the request.
  assert.equal(summaryBudget({ contextWindow: 16_384, maxTokens: 8_192 }).maxTokens, 4_096);
  // A large cloud model does not ask for its full output.
  assert.equal(summaryBudget({ contextWindow: 200_000, maxTokens: 64_000 }).maxTokens, 16_384);
  // No stated output limit: a default within the window.
  assert.equal(summaryBudget({ contextWindow: 65_536, maxTokens: 0 }).maxTokens, 8_192);
});

test("summaryBudget never exceeds a small stated limit and declines when there is no safe room", () => {
  // A tiny output limit is respected exactly, not raised to a floor.
  assert.equal(summaryBudget({ contextWindow: 65_536, maxTokens: 600 }).maxTokens, 600);
  assert.deepEqual(summaryBudget({ contextWindow: 65_536, maxTokens: 256 }), { reason: "output_limit_too_small" });
  // A small window cannot hold output and margin: no request.
  assert.deepEqual(summaryBudget({ contextWindow: 4_096, maxTokens: 8_192 }), { reason: "context_window_too_small" });
  // An unknown window is not guessed.
  assert.deepEqual(summaryBudget({ contextWindow: 0, maxTokens: 0 }), { reason: "no_context_window" });
  for (const model of [
    { contextWindow: 8_192, maxTokens: 1_000 },
    { contextWindow: 24_000, maxTokens: 2_048 },
    { contextWindow: 65_536, maxTokens: 8_192 },
  ]) {
    const budget = summaryBudget(model);
    assert.ok(budget.maxTokens <= model.maxTokens);
    assert.ok(budget.maxTokens + budget.inputTokens <= model.contextWindow);
  }
});

test("estimateTextTokens counts CJK text near one token per character", () => {
  assert.equal(estimateTextTokens("abc"), 1);
  assert.equal(estimateTextTokens("量子ビット"), 5);
});

test("summarySource keeps every message whole and bounds only tool output", () => {
  const user = (text) => ({ role: "user", content: [{ type: "text", text }], timestamp: 0 });
  const oldSummary = `<summary>\nold goal ${"g".repeat(20_000)} end of old summary\n</summary>`;
  const requirement = `ダッシュボード d-42 の要件: ${"r".repeat(20_000)} end of requirement`;
  const messages = [
    user(`The conversation history before this point was compacted into the following summary:\n\n${oldSummary}`),
    user(requirement),
    { role: "assistant", content: [{ type: "text", text: "saved d-42 revision 7" }], timestamp: 0 },
    user("newest"),
  ];
  for (const attempt of SUMMARY_ATTEMPTS) {
    const text = summarySource(messages, attempt);
    assert.ok(text.includes(oldSummary), "an oversized earlier summary is kept whole");
    assert.ok(text.includes(requirement), "the original request is kept whole");
    assert.match(text, /saved d-42 revision 7/);
    assert.match(text, /newest/);
    assert.doesNotMatch(text, /left out|truncated/);
  }
  // The stricter attempt cuts tool output shorter.
  const tool = [{ role: "toolResult", toolCallId: "c", toolName: "get", content: [{ type: "text", text: "z".repeat(5_000) }], isError: false, timestamp: 0 }];
  assert.ok(summarySource(tool, SUMMARY_ATTEMPTS[1]).length < summarySource(tool, SUMMARY_ATTEMPTS[0]).length);
});

test("summaryRequest counts the system prompt and instructions in its estimate", () => {
  const { request, tokens } = summaryRequest("[User]: hi", 1_000, "focus on d-42", 0);
  const text = request.messages[0].content[0].text;
  assert.ok(text.includes("focus on d-42"));
  assert.ok(tokens >= estimateTextTokens(request.systemPrompt) + estimateTextTokens(text));
});

test("a stored summary is placed again without asking the model", async () => {
  const extension = buildCompactionExtension({ log: () => {} });
  const beforeCompact = extension.hooks[0].handlers.beforeCompact;
  const api = {
    memo: async () => "## Goal\n- stored",
    snapshot: async () => assert.fail("no model lookup"),
    models: { completeSimple: async () => assert.fail("no request") },
  };
  const result = await beforeCompact({ entries: [{ id: 3 }], firstKept: 9, messages: [] }, api, context);
  assert.deepEqual(result, { kind: "summary", summary: "## Goal\n- stored" });
});

test("a transcript too large to send whole sends no QDash request and falls back, logged", async () => {
  const logs = [];
  const chat = await openChat({ logs, summarize: () => summaryOf("## Goal\n- built-in summary") });
  try {
    // The first request is far larger than this model's window by the conservative estimate.
    await saveTurn(chat.conversation, "要件".repeat(15_000));
    assert.equal((await turn(chat.conversation, `Explain it. ${FILLER}`)).status, "done");
    assert.equal(chat.calls["qdash-summary"], 0, "no QDash request with a partial transcript");
    assert.equal(chat.calls["builtin-summary"], 1);
    assert.ok(logs.some((line) => line.includes("attempt 1/2") && line.includes("not sent")));
    assert.ok(logs.some((line) => line.includes("whole transcript too large")));
    assert.equal(chat.calls.saves, 1);
  } finally {
    await chat.harness.close(context);
  }
});

test("a small model output limit caps the summary request", async () => {
  const chat = await openChat({ outputTokens: 600, summarize: () => summaryOf("## Goal\n- Compare T1 and T2") });
  try {
    await saveTurn(chat.conversation);
    assert.equal((await turn(chat.conversation, `Explain it. ${FILLER}`)).status, "done");
    assert.equal(chat.calls["qdash-summary"], 1);
    for (const options of chat.calls.summaryOptions) assert.ok(options.maxTokens <= 600, String(options.maxTokens));
  } finally {
    await chat.harness.close(context);
  }
});

test("a summary cut off at the token limit is retried once, smaller, without reasoning, and the turn answers", async () => {
  const logs = [];
  let attempt = 0;
  const chat = await openChat({
    logs,
    summarize: () => {
      attempt++;
      return attempt === 1 ? lengthStop() : summaryOf("## Goal\n- Compare T1 and T2 on dashboard d-42 (saved, revision 7)");
    },
  });
  try {
    await saveTurn(chat.conversation);
    const settled = await turn(chat.conversation, `Explain it. ${FILLER}`);
    assert.equal(settled.status, "done");
    assert.equal(chat.calls["qdash-summary"], 2);
    assert.equal(chat.calls["builtin-summary"], 0);
    for (const options of chat.calls.summaryOptions) {
      assert.equal(options.reasoning, undefined, "the summary request runs with thinking off");
      assert.equal(options.maxTokens, summaryBudget({ contextWindow: WINDOW, maxTokens: OUTPUT }).maxTokens);
    }
    const all = await entries(chat.conversation);
    const summaries = all.filter((entry) => CompactionEntry.is(entry));
    assert.equal(summaries.length, 1);
    assert.match(JSON.stringify(summaries[0].model), /dashboard d-42/);
    // The raw history is still stored, and each tool ran once.
    assert.equal(all.filter((entry) => UserEntry.is(entry)).length, 2);
    assert.equal(all.filter((entry) => ToolResultEntry.is(entry)).length, 2);
    assert.equal(chat.calls.saves, 1);
    assert.equal(chat.calls.reads, 1);
    assert.ok(logs.some((line) => line.includes("attempt 1/2") && line.includes("stop=length")));
    assert.ok(logs.every((line) => !line.includes("量子") && !line.includes("d-42")), "diagnostics hold no conversation text");
  } finally {
    await chat.harness.close(context);
  }
});

test("a provider error falls back to the built-in summarizer once", async () => {
  const chat = await openChat({
    summarize: (kind) =>
      kind === "qdash-summary"
        ? fauxAssistantMessage([], { stopReason: "error", errorMessage: "HTTP 503" })
        : summaryOf("## Goal\n- built-in summary"),
  });
  try {
    await saveTurn(chat.conversation);
    assert.equal((await turn(chat.conversation, `Explain it. ${FILLER}`)).status, "done");
    assert.equal(chat.calls["qdash-summary"], 1);
    assert.equal(chat.calls["builtin-summary"], 1);
  } finally {
    await chat.harness.close(context);
  }
});

test("a compaction that keeps failing ends the turn once, keeps the history, and Continue recovers it", async () => {
  let failing = true;
  const chat = await openChat({
    summarize: () => (failing ? lengthStop() : summaryOf("## Goal\n- Compare T1 and T2")),
  });
  try {
    await saveTurn(chat.conversation);
    const settled = await turn(chat.conversation, `Explain it. ${FILLER}`);
    assert.equal(settled.status, "unanswered");
    assert.equal(settled.reason, "model_error");
    assert.ok(isCompactionFailure(settled.reason, settled.detail), String(settled.detail));
    // Two QDash attempts and one built-in fallback, then the turn fails: no loop.
    assert.equal(chat.calls["qdash-summary"], 2);
    assert.equal(chat.calls["builtin-summary"], 1);
    const before = await entries(chat.conversation);
    assert.equal(before.filter((entry) => CompactionEntry.is(entry)).length, 0, "no partial summary is placed");
    assert.equal(before.filter((entry) => UserEntry.is(entry)).length, 2);
    assert.equal(before.filter((entry) => ToolResultEntry.is(entry)).length, 2, "the read result is kept");
    // The UI's Continue goes on without sending the message again.
    assert.equal(await continueBlocker(chat.conversation, context), undefined);
    failing = false;
    const resumed = await (await chat.conversation.submit({ type: "continue" }, context)).wait(context);
    assert.equal(resumed.status, "done");
    const after = await entries(chat.conversation);
    for (const entry of before) assert.ok(after.some((kept) => kept.id === entry.id), "no stored entry is dropped");
    assert.equal(after.filter((entry) => CompactionEntry.is(entry)).length, 1);
    assert.equal(after.filter((entry) => UserEntry.is(entry)).length, 2, "the user's message is not repeated");
    assert.equal(chat.calls.saves, 1, "the save does not run again");
    assert.equal(chat.calls.reads, 1, "the read does not run again");
  } finally {
    await chat.harness.close(context);
  }
});

test("without the extension the same reasoning summary fails as observed", async () => {
  const chat = await openChat({ extension: false, summarize: () => lengthStop() });
  try {
    await saveTurn(chat.conversation);
    const settled = await turn(chat.conversation, `Explain it. ${FILLER}`);
    assert.equal(settled.status, "unanswered");
    assert.match(String(settled.detail), /Compaction failed: Summarization hit the token limit/);
    // The built-in request carries the chat's thinking level into the shared cap.
    assert.deepEqual(chat.calls.summaryOptions, [{ kind: "builtin-summary", maxTokens: OUTPUT, reasoning: "medium" }]);
  } finally {
    await chat.harness.close(context);
  }
});

test("stopping a turn while its summary is written places nothing and asks no fallback", async () => {
  let started;
  const summaryStarted = new Promise((resolve) => (started = resolve));
  const chat = await openChat({
    summarize: (_kind, _ctx, options) =>
      new Promise((resolve) => {
        started();
        options.signal?.addEventListener(
          "abort",
          () => resolve(fauxAssistantMessage([], { stopReason: "aborted", errorMessage: "aborted" })),
          { once: true },
        );
      }),
  });
  try {
    await saveTurn(chat.conversation);
    const submission = await chat.conversation.submit({ type: "input", content: `Explain it. ${FILLER}` }, context);
    await summaryStarted;
    await chat.conversation.abort(context);
    const settled = await submission.wait(context);
    assert.equal(settled.status, "unanswered");
    assert.equal(chat.calls["qdash-summary"], 1);
    assert.equal(chat.calls["builtin-summary"], 0);
    const all = await entries(chat.conversation);
    assert.equal(all.filter((entry) => CompactionEntry.is(entry)).length, 0);
    assert.equal(all.filter((entry) => UserEntry.is(entry)).length, 2);
    assert.equal(chat.calls.saves, 1);
  } finally {
    await chat.harness.close(context);
  }
});

test("the compaction error tells the user what to do, not the provider's words", () => {
  assert.equal(isCompactionFailure("model_error", "Compaction failed: Summarization hit the token limit; the summary is incomplete"), true);
  assert.equal(isCompactionFailure("model_error", "HTTP 500"), false);
  assert.equal(isCompactionFailure("aborted", "Compaction failed: x"), false);
  assert.match(COMPACTION_FAILED_MESSAGE, /Continue/);
  assert.match(COMPACTION_FAILED_MESSAGE, /summarized form/);
  assert.doesNotMatch(COMPACTION_FAILED_MESSAGE, /token limit|model_error|Nothing was lost|nothing was run/);
});

