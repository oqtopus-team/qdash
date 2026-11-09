import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, defineTool, Harness, MemoryStorage } from "@earendil-works/pi-durable";
import { Type } from "typebox";

import { toNdjsonEvents } from "../src/events.ts";
import { ViewEventStream, ViewEventTranslator } from "../src/view-events.ts";

const RUN = { taskId: 7, inputs: [1], turns: 0 };

function view(entries, live = {}, before) {
  return { entries, docs: { "pi.live": live }, ...(before === undefined ? {} : { before }) };
}

function streaming(content, attempt = 1) {
  return { run: RUN, generation: { attempt, message: { role: "assistant", content } } };
}

function lines(translator, revision) {
  return translator.advance(revision).flatMap((event) => toNdjsonEvents(event));
}

const user = { id: 1, kind: "pi.user", model: [{ role: "user", content: "hi" }] };

test("history in the first value is not streamed again", () => {
  const translator = new ViewEventTranslator(view([user]));
  assert.deepEqual(lines(translator, view([user])), []);
});

test("growing text and thinking stream as appends", () => {
  const translator = new ViewEventTranslator(view([user]));
  assert.deepEqual(
    lines(translator, view([user], streaming([{ type: "thinking", thinking: "Hm" }]))),
    [{ type: "thinking_delta", delta: "Hm" }],
  );
  assert.deepEqual(
    lines(
      translator,
      view(
        [user],
        streaming([
          { type: "thinking", thinking: "Hmm." },
          { type: "text", text: "Hel" },
        ]),
      ),
    ),
    [
      { type: "thinking_delta", delta: "m." },
      { type: "text_delta", delta: "Hel" },
    ],
  );
});

test("an answer's tail that no partial showed comes from its entry, once", () => {
  const translator = new ViewEventTranslator(view([user]));
  lines(translator, view([user], streaming([{ type: "text", text: "Hel" }])));
  const answer = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [{ role: "assistant", stopReason: "stop", content: [{ type: "text", text: "Hello" }] }],
  };
  assert.deepEqual(lines(translator, view([user, answer])), [{ type: "text_delta", delta: "lo" }]);
  assert.deepEqual(lines(translator, view([user, answer])), []);
});

test("a retried attempt streams anew after the failed attempt's entry", () => {
  const translator = new ViewEventTranslator(view([user]));
  lines(translator, view([user], streaming([{ type: "text", text: "Par" }], 1)));
  const aborted = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [
      { role: "assistant", stopReason: "error", content: [{ type: "text", text: "Partial" }] },
    ],
  };
  assert.deepEqual(
    lines(translator, view([user, aborted], streaming([{ type: "text", text: "Ok" }], 2))),
    [{ type: "text_delta", delta: "Ok" }],
  );
});

test("a tool call being written streams as a draft and argument appends", () => {
  const translator = new ViewEventTranslator(view([user]));
  const call = (code) => ({
    type: "toolCall",
    id: "call-1",
    name: "bash",
    arguments: { command: code },
  });
  assert.deepEqual(lines(translator, view([user], streaming([call("ls")]))), [
    { type: "tool_draft", name: "bash", index: 0, id: "call-1" },
    { type: "tool_args_delta", index: 0, path: ["command"], delta: "ls" },
  ]);
  assert.deepEqual(lines(translator, view([user], streaming([call("ls -la")]))), [
    { type: "tool_args_delta", index: 0, path: ["command"], delta: " -la" },
  ]);
});

test("a tool call that started and ended between revisions still starts and ends", () => {
  const translator = new ViewEventTranslator(view([user]));
  const asking = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [
      {
        role: "assistant",
        stopReason: "toolUse",
        content: [{ type: "toolCall", id: "c1", name: "render_chart", arguments: { data: [] } }],
      },
    ],
  };
  const chart = { data: [], layout: {} };
  const result = {
    id: 3,
    kind: "pi.tool-result",
    model: [
      {
        role: "toolResult",
        toolCallId: "c1",
        toolName: "render_chart",
        isError: false,
        content: [],
        details: { chart },
      },
    ],
  };
  assert.deepEqual(lines(translator, view([user, asking, result], { run: RUN })), [
    { type: "tool_draft", name: "render_chart", index: 0, id: "c1" },
    { type: "tool_start", name: "render_chart", id: "c1", args: { data: [] } },
    { type: "chart", chart },
    { type: "tool_end", name: "render_chart", isError: false, id: "c1" },
  ]);
});

test("a running slot starts its call once and a faulted slot ends it as an error", () => {
  const translator = new ViewEventTranslator(view([user]));
  const slot = { callId: "c2", name: "qdash_query", taskId: 9 };
  assert.deepEqual(
    lines(translator, view([user], { run: RUN, tools: [{ ...slot, status: "running" }] })),
    [{ type: "tool_start", name: "qdash_query", id: "c2" }],
  );
  assert.deepEqual(
    lines(translator, view([user], { run: RUN, tools: [{ ...slot, status: "running" }] })),
    [],
  );
  assert.deepEqual(
    lines(translator, view([user], { run: RUN, tools: [{ ...slot, status: "done" }] })),
    [{ type: "tool_end", name: "qdash_query", isError: true, id: "c2" }],
  );
  assert.deepEqual(lines(translator, view([user], {})), []);
});

test("a started call whose slot left without a result ends as an error", () => {
  const translator = new ViewEventTranslator(view([user]));
  lines(
    translator,
    view([user], { run: RUN, tools: [{ callId: "c3", name: "bash", status: "running" }] }),
  );
  assert.deepEqual(lines(translator, view([user], {})), [
    { type: "tool_end", name: "bash", isError: true, id: "c3" },
  ]);
});

test("a window that moved past the stream names the gap, and its entries stream once, in order", () => {
  const asking = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [
      {
        role: "assistant",
        stopReason: "toolUse",
        content: [{ type: "toolCall", id: "g1", name: "bash", arguments: { command: "ls" } }],
      },
    ],
  };
  const result = {
    id: 3,
    kind: "pi.tool-result",
    model: [{ role: "toolResult", toolCallId: "g1", toolName: "bash", isError: false, content: [] }],
  };
  const answer = {
    id: 4,
    kind: "pi.assistant",
    byTaskId: 8,
    model: [{ role: "assistant", stopReason: "stop", content: [{ type: "text", text: "Done." }] }],
  };
  const translator = new ViewEventTranslator(view([user]));
  // Entries 2 and 3 left the window before a revision showed them.
  const later = view([answer], {}, 3);
  assert.deepEqual(translator.gap(later), { after: 1, through: 3 });
  assert.deepEqual(
    translator.advance(later, [asking, result]).flatMap((event) => toNdjsonEvents(event)),
    [
      { type: "tool_draft", name: "bash", index: 0, id: "g1" },
      { type: "tool_args_delta", index: 0, path: ["command"], delta: "ls" },
      { type: "tool_start", name: "bash", id: "g1", args: { command: "ls" } },
      { type: "tool_end", name: "bash", isError: false, id: "g1" },
      { type: "text_delta", delta: "Done." },
    ],
  );
  assert.equal(translator.gap(later), undefined);
  assert.deepEqual(lines(translator, later), []);
});

test("history before an empty first window is not a gap", () => {
  const translator = new ViewEventTranslator(view([], {}, 40));
  assert.equal(translator.gap(view([], {}, 40)), undefined);
  assert.deepEqual(translator.gap(view([], {}, 45)), { after: 40, through: 45 });
});

test("a call whose slot came and went unseen without a result ends as an error", () => {
  const translator = new ViewEventTranslator(view([user]));
  const asking = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [
      {
        role: "assistant",
        stopReason: "toolUse",
        content: [{ type: "toolCall", id: "f1", name: "qdash_query", arguments: {} }],
      },
    ],
  };
  // The run faulted: no result entry, and the slot left with the run.
  assert.deepEqual(lines(translator, view([user, asking], {})), [
    { type: "tool_draft", name: "qdash_query", index: 0, id: "f1" },
    { type: "tool_start", name: "qdash_query", id: "f1", args: {} },
    { type: "tool_end", name: "qdash_query", isError: true, id: "f1" },
  ]);
  assert.deepEqual(lines(translator, view([user, asking], {})), []);
});

test("a call in a failed attempt's partial is not a tool round", () => {
  const translator = new ViewEventTranslator(view([user]));
  const failed = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [
      {
        role: "assistant",
        stopReason: "aborted",
        content: [{ type: "toolCall", id: "x1", name: "bash", arguments: {} }],
      },
    ],
  };
  assert.deepEqual(lines(translator, view([user, failed], {})), []);
});

test("a listener call that arrives after finish streams nothing", async () => {
  const answer = {
    id: 2,
    kind: "pi.assistant",
    byTaskId: 7,
    model: [{ role: "assistant", stopReason: "stop", content: [{ type: "text", text: "Hello" }] }],
  };
  const watchOf = (value) => ({ value, stop: async () => ({ kind: "ended" }) });
  const source = {
    watch: async () => watchOf(view([user, answer], {})),
    entries: async () => ({ items: [] }),
  };
  const out = [];
  const stream = new ViewEventStream(
    source,
    view([user]),
    (event) => out.push(...toNdjsonEvents(event)),
    BACKGROUND_CONTEXT,
  );
  await stream.finish(watchOf(view([user])));
  assert.deepEqual(out, [{ type: "text_delta", delta: "Hello" }]);
  // An older revision the stopped watch was still delivering: the answer's partial.
  await stream.push(view([user], streaming([{ type: "text", text: "Hel" }])));
  assert.deepEqual(out, [{ type: "text_delta", delta: "Hello" }]);
});

// --- A real Harness: the drain and window paths the chat stream runs. ---

const answerOf = (out) =>
  out
    .filter((line) => line.type === "text_delta")
    .map((line) => line.delta)
    .join("");

function deferred() {
  let resolve;
  const promise = new Promise((done) => (resolve = done));
  return { promise, resolve };
}

/** A Harness with a faux model and the given tools, its root conversation, and `history` answered first. */
async function openConversation({ tools, responses, settings, history }) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const registry = createRegistry();
  registry.install({ name: "test", tools });
  faux.setResponses([...(history ? [fauxAssistantMessage(fauxText(history))] : []), ...responses]);
  const context = BACKGROUND_CONTEXT;
  const harness = await Harness.open(
    new MemoryStorage(),
    { models, registry, ...(settings ? { settings } : {}) },
    context,
  );
  const agent = { model: { provider: model.provider, modelId: model.id } };
  const conversation = await harness.root(context, { agent });
  harness.resume();
  if (history) {
    const first = await conversation.submit({ type: "input", content: "earlier" }, context);
    assert.equal((await first.wait(context)).status, "done");
  }
  return { harness, conversation, context };
}

/**
 * Watch `conversation` as the chat handler does, through a listener that waits for `gate` before it hands a revision
 * to the stream, so the test decides what the watch delivered when the turn settles. Records every revision pushed.
 */
async function watchGated(conversation, context, gate) {
  const out = [];
  const pushed = [];
  const watch = await conversation.watch(context);
  const reads = { entries: 0 };
  const source = {
    watch: (...args) => conversation.watch(...args),
    entries: (...args) => {
      reads.entries += 1;
      return conversation.entries(...args);
    },
  };
  const stream = new ViewEventStream(source, watch.value, (event) => out.push(...toNdjsonEvents(event)), context);
  const idle = deferred();
  watch.start(async (call) => {
    if (call.kind !== "value") return;
    await gate;
    await stream.push(call.value);
    pushed.push(call.value);
    if (call.value.docs["pi.live"]?.run === undefined) idle.resolve();
  });
  return { out, pushed, reads, stream, watch, idle: idle.promise };
}

function assertOnce(out, type) {
  const ids = out.filter((line) => line.type === type).map((line) => line.id);
  assert.equal(new Set(ids).size, ids.length, `${type} repeated: ${JSON.stringify(out)}`);
  return ids;
}

const chartTool = defineTool({
  name: "render_chart",
  description: "Render a chart",
  parameters: Type.Object({ data: Type.Array(Type.Any()) }),
  replay: "safe",
  execute: async (params) => ({
    output: [{ type: "text", text: "Chart rendered." }],
    details: { chart: { data: params.data, layout: {} } },
  }),
});

test("finish streams a turn the watch had not delivered when it settled", async () => {
  const { harness, conversation, context } = await openConversation({
    tools: [chartTool],
    history: "Earlier answer.",
    responses: [
      fauxAssistantMessage([fauxToolCall("render_chart", { data: [1] }, { id: "c1" })], {
        stopReason: "toolUse",
      }),
      fauxAssistantMessage(fauxText("Here is the chart.")),
    ],
  });
  try {
    const gate = deferred();
    const { out, stream, watch } = await watchGated(conversation, context, gate.promise);
    const submission = await conversation.submit({ type: "input", content: "plot" }, context);
    assert.equal((await submission.wait(context)).status, "done");
    // The listener has handed nothing to the stream: every event must come from the drain.
    assert.deepEqual(out, []);
    await stream.finish(watch);
    gate.resolve();
    // A listener call still on its way after the drain adds nothing.
    await watch.closed;
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(
      out.filter((line) => line.type !== "text_delta" && line.type !== "tool_args_delta"),
      [
        { type: "tool_draft", name: "render_chart", index: 0, id: "c1" },
        { type: "tool_start", name: "render_chart", id: "c1", args: { data: [1] } },
        { type: "chart", chart: { data: [1], layout: {} } },
        { type: "tool_end", name: "render_chart", isError: false, id: "c1" },
      ],
    );
    assert.equal(answerOf(out), "Here is the chart.");
  } finally {
    await harness.close(context);
  }
});

test("finish right after settling keeps what the running listener streamed, once", async () => {
  const { harness, conversation, context } = await openConversation({
    tools: [chartTool],
    responses: [
      fauxAssistantMessage([fauxToolCall("render_chart", { data: [2] }, { id: "c1" })], {
        stopReason: "toolUse",
      }),
      fauxAssistantMessage(fauxText("Plotted.")),
    ],
  });
  try {
    const { out, stream, watch } = await watchGated(conversation, context, Promise.resolve());
    const submission = await conversation.submit({ type: "input", content: "plot" }, context);
    assert.equal((await submission.wait(context)).status, "done");
    await stream.finish(watch);

    assert.deepEqual(assertOnce(out, "tool_start"), ["c1"]);
    assert.deepEqual(assertOnce(out, "tool_end"), ["c1"]);
    assert.equal(out.filter((line) => line.type === "chart").length, 1);
    assert.equal(answerOf(out), "Plotted.");
  } finally {
    await harness.close(context);
  }
});

test("an aborted turn drains its tool call's end", async () => {
  const started = deferred();
  const blocking = defineTool({
    name: "qdash_query",
    description: "Wait until aborted",
    parameters: Type.Object({}),
    replay: "safe",
    execute: async (_params, _api, ctx) => {
      started.resolve();
      await new Promise((_resolve, reject) => {
        const signal = ctx.abortSignal;
        if (signal?.aborted) reject(new Error("aborted"));
        signal?.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
      });
      return { output: [] };
    },
  });
  const { harness, conversation, context } = await openConversation({
    tools: [blocking],
    responses: [
      fauxAssistantMessage([fauxToolCall("qdash_query", {}, { id: "q1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("never")),
    ],
  });
  try {
    const gate = deferred();
    const { out, stream, watch } = await watchGated(conversation, context, gate.promise);
    const submission = await conversation.submit({ type: "input", content: "query" }, context);
    await started.promise;
    await conversation.abort(context);
    const settled = await submission.wait(context);
    assert.equal(settled.status, "unanswered");
    await stream.finish(watch);
    gate.resolve();

    assert.deepEqual(assertOnce(out, "tool_start"), ["q1"]);
    const ends = out.filter((line) => line.type === "tool_end");
    assert.deepEqual(ends, [{ type: "tool_end", name: "qdash_query", isError: true, id: "q1" }]);
    assert.equal(answerOf(out), "");
  } finally {
    await harness.close(context);
  }
});

test("a turn that ends in a model error drains its tool round and no failed text", async () => {
  const { harness, conversation, context } = await openConversation({
    tools: [chartTool],
    settings: { retry: { enabled: false } },
    responses: [
      fauxAssistantMessage([fauxToolCall("render_chart", { data: [3] }, { id: "c1" })], {
        stopReason: "toolUse",
      }),
      fauxAssistantMessage(fauxText("Broken"), { stopReason: "error", errorMessage: "boom" }),
    ],
  });
  try {
    const gate = deferred();
    const { out, stream, watch } = await watchGated(conversation, context, gate.promise);
    const submission = await conversation.submit({ type: "input", content: "plot" }, context);
    const settled = await submission.wait(context);
    assert.equal(settled.status, "unanswered");
    assert.equal(settled.reason, "model_error");
    await stream.finish(watch);
    gate.resolve();

    assert.deepEqual(assertOnce(out, "tool_start"), ["c1"]);
    assert.deepEqual(
      out.filter((line) => line.type === "tool_end"),
      [{ type: "tool_end", name: "render_chart", isError: false, id: "c1" }],
    );
    assert.equal(out.filter((line) => line.type === "chart").length, 1);
    assert.equal(answerOf(out), "");
  } finally {
    await harness.close(context);
  }
});

/** A turn of `CALLS` tool calls: more result entries than the default window (50 to 100) holds. */
const CALLS = 120;

async function openBurst() {
  const echo = defineTool({
    name: "echo",
    description: "Echo",
    parameters: Type.Object({ n: Type.Number() }),
    replay: "safe",
    execute: async (params) => ({ output: [{ type: "text", text: String(params.n) }] }),
  });
  const calls = Array.from({ length: CALLS }, (_, n) => fauxToolCall("echo", { n }, { id: `e${n}` }));
  return openConversation({
    tools: [echo],
    history: "Earlier answer.",
    responses: [
      fauxAssistantMessage(calls, { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("All echoed.")),
    ],
  });
}

function assertBurst(out) {
  const expected = Array.from({ length: CALLS }, (_, n) => `e${n}`).sort();
  assert.deepEqual([...assertOnce(out, "tool_start")].sort(), expected);
  assert.deepEqual([...assertOnce(out, "tool_end")].sort(), expected);
  for (const id of expected) {
    const start = out.findIndex((line) => line.type === "tool_start" && line.id === id);
    const end = out.findIndex((line) => line.type === "tool_end" && line.id === id);
    assert.ok(start < end, id);
  }
  assert.ok(out.every((line) => line.type !== "tool_end" || line.isError === false));
  // The answer streams once, and the earlier turn is not replayed.
  assert.equal(answerOf(out), "All echoed.");
}

test("a revision whose window dropped entries the stream had not seen reads them", async () => {
  const { harness, conversation, context } = await openBurst();
  try {
    const gate = deferred();
    const { out, pushed, reads, stream, watch, idle } = await watchGated(
      conversation,
      context,
      gate.promise,
    );
    const submission = await conversation.submit({ type: "input", content: "echo" }, context);
    assert.equal((await submission.wait(context)).status, "done");
    // The listener now gets the burst folded into one revision, its window moved past the stream.
    gate.resolve();
    await idle;
    assert.ok(pushed.some((revision) => revision.before !== undefined), "window never dropped entries");
    assert.ok(reads.entries > 0, "the gap was not read");
    await stream.finish(watch);
    assertBurst(out);
  } finally {
    await harness.close(context);
  }
});

test("finish reads a settled turn larger than the window it starts", async () => {
  const { harness, conversation, context } = await openBurst();
  try {
    const gate = deferred();
    const { out, reads, stream, watch } = await watchGated(conversation, context, gate.promise);
    const submission = await conversation.submit({ type: "input", content: "echo" }, context);
    assert.equal((await submission.wait(context)).status, "done");
    await stream.finish(watch);
    gate.resolve();
    assert.ok(reads.entries > 0, "the gap was not read");
    assertBurst(out);
  } finally {
    await harness.close(context);
  }
});
