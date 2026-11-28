import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

// A chat turn parks on an expert's answer (as qdash_wait_agent_intervention
// does), its HTTP stream drops meanwhile, and the chat reattaches. Each
// scenario runs the server in its own process with a mocked runtime whose
// stores are real SQLite durable harnesses and whose model is scripted.
const preamble = (dir) => `
  import assert from "node:assert/strict";
  import { once } from "node:events";
  import { Server } from "node:http";
  import { join } from "node:path";
  import { mock } from "bun:test";
  import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
  import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
  import { createModels } from "@earendil-works/pi-ai/models";
  import { AssistantEntry, createRegistry, defineExtension, defineTool, Harness, ROOT_CONVERSATION_ID, UserEntry } from "@earendil-works/pi-durable";
  import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
  import { Type } from "typebox";
  import { CHAT_QUEUE_SETTINGS, readSteerReceipt } from "../src/chat-control.ts";

  const dir = ${JSON.stringify(dir)};
  let server;
  const listen = Server.prototype.listen;
  Server.prototype.listen = function () {
    server = this;
    return listen.call(this, 0, "127.0.0.1");
  };

  // The expert's answer, read by the parked wait on each of its polls.
  let expertAnswer;
  let polls = 0;
  let stepRuns = 0;
  let modelCalls = 0;
  // Parks between polls like the pinned waiting tools (durable-waits.ts).
  const waitExpert = defineTool({
    name: "wait_expert",
    description: "Waits for the expert (test)",
    parameters: Type.Object({}),
    replay: "safe",
    execute: async (_args, api) => {
      polls++;
      if (expertAnswer === undefined) return { kind: "sleep", checkpoint: {}, until: api.now() + 20 };
      return { output: [{ type: "text", text: "expert: " + expertAnswer }] };
    },
  });
  // A step that writes: it must run exactly once whatever the stream does.
  const runStep = defineTool({
    name: "run_step",
    description: "Runs the next calibration step (test)",
    parameters: Type.Object({}),
    execute: async () => {
      stepRuns++;
      return { output: [{ type: "text", text: "step " + stepRuns + " done" }] };
    },
  });
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const agent = { model: { provider: model.provider, modelId: model.id } };
  const text = (message) => typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
  let callId = 0;
  const reply = (ctx) => {
    modelCalls++;
    const last = ctx.messages.at(-1);
    if (last.role === "user") {
      return fauxAssistantMessage([fauxText("Asking the expert."), fauxToolCall("wait_expert", {}, { id: "w" + ++callId })], { stopReason: "toolUse" });
    }
    if (last.role === "toolResult" && last.toolName === "wait_expert") {
      return fauxAssistantMessage([fauxText("Resuming."), fauxToolCall("run_step", {}, { id: "s" + ++callId })], { stopReason: "toolUse" });
    }
    const results = ctx.messages.filter((m) => m.role === "toolResult").map(text);
    return fauxAssistantMessage(fauxText("Resumed after " + results.join(", ")));
  };
  faux.setResponses(Array.from({ length: 50 }, () => reply));

  const pathOf = (owner, store) => join(dir, owner + "-" + store + ".sqlite");
  let openHarnesses = 0;
  const open = async (owner, store) => {
    const registry = createRegistry();
    registry.install(defineExtension({ name: "t", tools: [waitExpert, runStep] }));
    const harness = await Harness.open(await openNodeSqliteStorage(pathOf(owner, store)), { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } }, BACKGROUND_CONTEXT);
    openHarnesses++;
    return { harness, close: async () => { await harness.close(BACKGROUND_CONTEXT); openHarnesses--; } };
  };
  mock.module("../src/runtime.ts", () => ({
    BACKGROUND_CONTEXT,
    SharedRuntime: { create: async () => ({
      listToolNames: () => [],
      expandSkillCommand: (message) => message,
      storePath: pathOf,
      steerReceipt: (owner, session, project, requestId, target = {}) =>
        readSteerReceipt(pathOf(owner, target.storeSessionId ?? session), project, requestId, BACKGROUND_CONTEXT, target.conversationId ?? ROOT_CONVERSATION_ID),
      openSession: async (request) => {
        const { harness, close } = await open(request.ownerId, request.storeSessionId ?? request.sessionId);
        try {
          const conversation = await harness.root(BACKGROUND_CONTEXT, { agent });
          await conversation.configure(agent, BACKGROUND_CONTEXT);
          return { harness, conversation, writeTools: {}, close };
        } catch (error) {
          await close();
          throw error;
        }
      },
    }) },
    answerText: async (conversation, id) => {
      const entry = await conversation.commit((tx) => tx.entry(AssistantEntry, id), BACKGROUND_CONTEXT);
      return entry.model[0].content.filter((b) => b.type === "text").map((b) => b.text).join("");
    },
    pendingApproval: async () => undefined,
  }));
  process.env.CHAT_PING_MS = "0";
  process.env.CHAT_TIMEOUT_MS = "0";
  process.env.CHAT_WRAP_UP_MS = "0";
  process.env.AGENT_RUNTIME_TOKEN = "test-runtime-token";
  delete process.env.AGENT_RUNTIME_TOKEN_FILE;
  await import("../src/server.ts");
  if (!server.listening) await once(server, "listening");
  const base = "http://127.0.0.1:" + server.address().port;
  const headers = (project = "p1") => ({
    "Content-Type": "application/json",
    Authorization: "Bearer test-runtime-token",
    "x-qdash-token": "user-token",
    ...(project ? { "x-qdash-project-id": project } : {}),
  });
  const post = (path, body, h = headers(), signal) => fetch(base + path, { method: "POST", headers: h, body: JSON.stringify(body), signal });
  const turn = { owner_id: "alice", conversation_id: "c1", model: { provider: model.provider, name: model.id } };

  // Reads NDJSON lines from a streaming response until \`until\` matches one.
  const lineReader = (response) => {
    if (response.status !== 200) throw new Error("HTTP " + response.status);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const seen = [];
    return {
      seen,
      async until(match) {
        for (;;) {
          const hit = seen.find(match);
          if (hit) return hit;
          const { done, value } = await reader.read();
          if (done) throw new Error("stream ended before the expected line: " + JSON.stringify(seen));
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\\n");
          buffer = parts.pop();
          for (const part of parts) if (part.trim()) seen.push(JSON.parse(part));
        }
      },
      async rest() {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
        }
        for (const part of buffer.split("\\n")) if (part.trim()) seen.push(JSON.parse(part));
        return seen;
      },
    };
  };
  const users = async () => {
    const storage = await openNodeSqliteStorage(pathOf("alice", "c1"));
    const harness = await Harness.open(storage, { models, registry: createRegistry(), readOnly: true }, BACKGROUND_CONTEXT);
    try {
      const conversation = await harness.conversation(ROOT_CONVERSATION_ID, BACKGROUND_CONTEXT);
      const view = await conversation.context(BACKGROUND_CONTEXT);
      return view.entries.filter((entry) => UserEntry.is(entry)).map((entry) => text(entry.model[0]));
    } finally {
      await harness.close(BACKGROUND_CONTEXT);
    }
  };
  const until = async (check) => {
    for (let i = 0; i < 500; i++) {
      if (check()) return;
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    throw new Error("condition never held");
  };
  const deltas = (lines) => lines.filter((l) => l.type === "text_delta").map((l) => l.delta).join("");
  const tools = (lines, type) => lines.filter((l) => l.type === type).map((l) => l.name);
  try {
`;

const epilogue = `
    assert.equal(openHarnesses, 0);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
  console.log("SCENARIO OK");
`;

function runScenario(body) {
  const dir = mkdtempSync(join(tmpdir(), "chat-reattach-"));
  try {
    const result = spawnSync("bun", ["--eval", preamble(dir) + body + epilogue], {
      cwd: new URL(".", import.meta.url),
      encoding: "utf8",
      timeout: Number(process.env.SCENARIO_TIMEOUT_MS ?? 80_000),
    });
    assert.equal(result.status, 0, `${result.error ?? ""}\n${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /SCENARIO OK/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("a stream dropped while the turn waits for the expert reattaches and receives the resumed turn", { timeout: 90_000 }, () => {
  runScenario(`
    // The turn starts and parks on the expert's answer.
    const dropped = new AbortController();
    const first = lineReader(await post("/chat", { ...turn, request_id: "t1", message: "calibrate Q0" }, headers(), dropped.signal));
    await first.until((l) => l.type === "tool_start" && l.name === "wait_expert");
    await until(() => polls >= 2);
    // A proxy drops the quiet stream. The turn keeps running.
    dropped.abort();
    await until(() => polls >= 4);

    // Another message is still refused: the turn runs. A reattach naming another turn is too.
    let response = await post("/chat", { ...turn, request_id: "t2", message: "hello" });
    assert.equal(response.status, 409);
    await response.body?.cancel();
    response = await post("/chat", { ...turn, request_id: "t2", reattach: true });
    assert.equal(response.status, 409);
    await response.body?.cancel();
    // A reattach from another project is refused.
    response = await post("/chat", { ...turn, request_id: "t1", reattach: true }, headers("p2"));
    assert.equal(response.status, 403);
    await response.body?.cancel();

    // The chat reattaches while the wait is still parked: the turn so far is replayed.
    const again = lineReader(await post("/chat", { ...turn, request_id: "t1", reattach: true }));
    await again.until((l) => l.type === "tool_start" && l.name === "wait_expert");
    assert.equal(deltas(again.seen), "Asking the expert.");
    assert.equal(stepRuns, 0);

    // The expert answers; the parked wait wakes, and what follows reaches the reattached stream.
    expertAnswer = "use 5.1 GHz";
    const out = await again.rest();
    const done = out.find((l) => l.type === "done");
    assert.ok(done, JSON.stringify(out));
    assert.equal(done.text, "Resumed after expert: use 5.1 GHz, step 1 done");
    assert.deepEqual(tools(out, "tool_start"), ["wait_expert", "run_step"]);
    assert.deepEqual(tools(out, "tool_end"), ["wait_expert", "run_step"]);
    assert.equal(out.find((l) => l.type === "tool_end" && l.name === "run_step").isError, false);
    assert.equal(deltas(out), "Asking the expert.Resuming.Resumed after expert: use 5.1 GHz, step 1 done");
    assert.equal(out.at(-1).type, "done");
    // Nothing ran twice and the model was asked once per round: no new turn, no repeated step.
    assert.equal(stepRuns, 1);
    assert.equal(modelCalls, 3);
    assert.deepEqual(await users(), ["calibrate Q0"]);

    // Reattaching after the turn ended reads the answer from the store, again without running anything.
    const late = await post("/chat", { ...turn, request_id: "t1", reattach: true });
    assert.equal(late.status, 200);
    const replayed = await lineReader(late).rest();
    assert.equal(replayed.find((l) => l.type === "done").text, done.text);
    assert.deepEqual(tools(replayed, "tool_end"), ["wait_expert", "run_step"]);
    assert.equal(stepRuns, 1);
    assert.equal(modelCalls, 3);
    assert.deepEqual(await users(), ["calibrate Q0"]);

    // A turn the store never saw is not started by a reattach.
    response = await post("/chat", { ...turn, request_id: "t-unknown", message: "calibrate Q1", reattach: true });
    assert.equal(response.status, 404);
    assert.equal((await response.json()).reason, "turn_not_found");
    assert.equal(modelCalls, 3);
    assert.deepEqual(await users(), ["calibrate Q0"]);
  `);
});

test("a reattached stream and the original both end with the turn; a stop still ends a parked wait", { timeout: 90_000 }, () => {
  runScenario(`
    const original = lineReader(await post("/chat", { ...turn, request_id: "t1", message: "calibrate Q0" }));
    await original.until((l) => l.type === "tool_start" && l.name === "wait_expert");
    const attached = lineReader(await post("/chat", { ...turn, request_id: "t1", reattach: true }));
    await attached.until((l) => l.type === "tool_start" && l.name === "wait_expert");
    // A late stop of an earlier turn leaves this one running.
    const stale = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1", turn_request_id: "t0" });
    assert.equal(stale.status, 404);
    const response = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1", turn_request_id: "t1" });
    assert.equal(response.status, 200);
    const [a, b] = await Promise.all([original.rest(), attached.rest()]);
    for (const out of [a, b]) {
      assert.equal(out.at(-1).type, "error", JSON.stringify(out));
      assert.match(out.at(-1).message, /aborted/);
      assert.equal(out.filter((l) => l.type === "tool_end" && l.name === "wait_expert").length, 1);
    }
    assert.equal(stepRuns, 0);
  `);
});

test("a reattach to a finished turn replays that turn only, not the turns after it", { timeout: 90_000 }, () => {
  runScenario(`
    expertAnswer = "use 5.1 GHz";
    const ends = (lines) => lines.filter((l) => l.type === "tool_end").map((l) => [l.name, l.entry_id, l.before_turn]);
    // Turns A and B both finish, each with its own tool calls.
    const a = await lineReader(await post("/chat", { ...turn, request_id: "A", message: "calibrate Q0" })).rest();
    const b = await lineReader(await post("/chat", { ...turn, request_id: "B", message: "calibrate Q1" })).rest();
    assert.equal(a.at(-1).type, "done");
    assert.equal(b.at(-1).type, "done");
    assert.equal(ends(a).length, 2);
    assert.equal(ends(b).length, 2);
    // Every result is named by its durable entry, and none is an earlier turn's.
    for (const [, entry, before] of [...ends(a), ...ends(b)]) {
      assert.match(entry, /^\\d+$/);
      assert.equal(before, undefined);
    }
    assert.equal(stepRuns, 2);
    const calls = modelCalls;

    // Reattaching A after B ended replays A's calls under the same names, and A's answer.
    const replayA = await lineReader(await post("/chat", { ...turn, request_id: "A", reattach: true })).rest();
    assert.deepEqual(ends(replayA), ends(a));
    assert.equal(replayA.find((l) => l.type === "done").text, a.at(-1).text);
    assert.equal(replayA.find((l) => l.type === "done").entry_id, a.at(-1).entry_id);
    assert.equal(deltas(replayA), deltas(a));
    assert.equal(replayA.filter((l) => l.type === "done").length, 1);

    // Reattaching B replays B only.
    const replayB = await lineReader(await post("/chat", { ...turn, request_id: "B", reattach: true })).rest();
    assert.deepEqual(ends(replayB), ends(b));
    assert.equal(replayB.find((l) => l.type === "done").text, b.at(-1).text);

    // Nothing ran again.
    assert.equal(stepRuns, 2);
    assert.equal(modelCalls, calls);
    assert.deepEqual(await users(), ["calibrate Q0", "calibrate Q1"]);
  `);
});

test("another window finds the running turn, follows it as a second subscriber, and sees it end", { timeout: 90_000 }, () => {
  runScenario(`
    const active = (body = {}, h = headers()) => post("/chat/active", { owner_id: "alice", conversation_id: "c1", ...body }, h);
    // Nothing runs yet.
    let response = await active();
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { running: false });

    // The first window starts a turn that parks on the expert.
    const original = lineReader(
      await post("/chat", {
        ...turn,
        request_id: "t1",
        message: "calibrate Q0",
        turn_start: { index: 0, digest: "0123456789abcdef" },
      }),
    );
    await original.until((l) => l.type === "tool_start" && l.name === "wait_expert");

    // The internal credential and the user's credentials are both required.
    response = await post("/chat/active", { owner_id: "alice", conversation_id: "c1" }, { "Content-Type": "application/json" });
    assert.equal(response.status, 401);
    await response.body?.cancel();
    response = await active({}, { "Content-Type": "application/json", Authorization: "Bearer test-runtime-token" });
    assert.equal(response.status, 401);
    await response.body?.cancel();
    // Another user's chat of the same ID, and another branch, run nothing.
    response = await post("/chat/active", { owner_id: "bob", conversation_id: "c1" });
    assert.deepEqual(await response.json(), { running: false });
    response = await active({ store_conversation_id: "7" });
    assert.deepEqual(await response.json(), { running: false });
    // Another project learns only that a turn runs, not which.
    response = await active({}, headers("p2"));
    assert.deepEqual(await response.json(), { running: true, other_project: true });

    // A second window opened late learns the turn and reattaches with it: the turn so far
    // is replayed, including the wait it is parked on, and nothing is submitted again.
    response = await active();
    const found = await response.json();
    assert.equal(found.running, true);
    assert.equal(found.request_id, "t1");
    assert.equal(found.continuing, false);
    assert.equal(typeof found.started_at, "number");
    // Where the turn starts in the saved transcript, as its window sent it.
    assert.deepEqual(found.turn_start, { index: 0, digest: "0123456789abcdef" });
    const second = lineReader(await post("/chat", { ...turn, request_id: found.request_id, reattach: true }));
    await second.until((l) => l.type === "tool_start" && l.name === "wait_expert");
    assert.equal(modelCalls, 1);
    assert.deepEqual(await users(), ["calibrate Q0"]);

    // The expert answers: both windows see the same rest of the turn and its end.
    expertAnswer = "use 5.1 GHz";
    const [a, b] = await Promise.all([original.rest(), second.rest()]);
    for (const out of [a, b]) {
      assert.equal(out.at(-1).type, "done", JSON.stringify(out));
      assert.deepEqual(tools(out, "tool_end"), ["wait_expert", "run_step"]);
    }
    assert.equal(a.at(-1).text, b.at(-1).text);
    assert.equal(stepRuns, 1);

    // Once the turn ended, nothing is reported as running.
    response = await active();
    assert.deepEqual(await response.json(), { running: false });
    assert.deepEqual(await users(), ["calibrate Q0"]);
  `);
});

test("a turn sent without a well-formed start is reported without one", { timeout: 90_000 }, () => {
  runScenario(`
    const original = lineReader(
      await post("/chat", { ...turn, request_id: "t1", message: "calibrate Q0", turn_start: { index: -1, digest: "x" } }),
    );
    await original.until((l) => l.type === "tool_start" && l.name === "wait_expert");
    const found = await (await post("/chat/active", { owner_id: "alice", conversation_id: "c1" })).json();
    assert.equal(found.request_id, "t1");
    assert.equal(found.turn_start, null);
    expertAnswer = "use 5.1 GHz";
    await original.rest();
  `);
});

test("a stream that asks for the presentation contract gets it live, on a reattach, and after the turn", { timeout: 90_000 }, () => {
  runScenario(`
    const presentation = { ...headers(), Accept: "application/vnd.qdash.agent-presentation+x-ndjson; version=1" };
    const shown = (lines, event) => lines.filter((l) => l.event === event).map((l) => l.data);
    const dropped = new AbortController();
    const response = await post("/chat", { ...turn, request_id: "t1", message: "calibrate Q0" }, presentation, dropped.signal);
    assert.equal(response.headers.get("content-type"), "application/vnd.qdash.agent-presentation+x-ndjson; version=1");
    const first = lineReader(response);
    const started = await first.until((l) => l.event === "tool_start" && l.data.tool === "wait_expert");
    assert.deepEqual(started, { v: 1, event: "tool_start", data: { id: started.data.id, tool: "wait_expert", label: "Wait expert", args: {} } });
    await until(() => polls >= 2);
    dropped.abort();

    // The reattached stream is mapped from the turn's start, in the same contract.
    const again = lineReader(await post("/chat", { ...turn, request_id: "t1", reattach: true }, presentation));
    await again.until((l) => l.event === "tool_start" && l.data.tool === "wait_expert");
    assert.equal(shown(again.seen, "delta").map((d) => d.text).join(""), "Asking the expert.");
    expertAnswer = "use 5.1 GHz";
    const out = await again.rest();
    assert.ok(out.every((l) => l.v === 1 && typeof l.event === "string"), JSON.stringify(out));
    assert.deepEqual(shown(out, "tool_end").map((d) => [d.tool, d.label, d.is_error]), [
      ["wait_expert", "Wait expert", false],
      ["run_step", "Run step", false],
    ]);
    assert.deepEqual(shown(out, "status").map((d) => d.step), ["tool_call", "thinking", "tool_call", "thinking", "complete"]);
    const [result] = shown(out, "result");
    assert.deepEqual(result.blocks, [{ type: "text", content: "Resumed after expert: use 5.1 GHz, step 1 done", chart: null }]);
    assert.match(result.entry_id, /^\\d+$/);
    assert.equal(out.at(-1).event, "result");
    assert.deepEqual(out.at(-1).internal, { answer: "Resumed after expert: use 5.1 GHz, step 1 done" });
    assert.equal(stepRuns, 1);

    // After the turn, the store's replay is mapped the same way; a plain request still gets NDJSON.
    const late = await lineReader(await post("/chat", { ...turn, request_id: "t1", reattach: true }, presentation)).rest();
    assert.deepEqual(shown(late, "result"), [result]);
    assert.deepEqual(shown(late, "tool_end"), shown(out, "tool_end"));
    const legacy = await post("/chat", { ...turn, request_id: "t1", reattach: true });
    assert.equal(legacy.headers.get("content-type"), "application/x-ndjson");
    const raw = await lineReader(legacy).rest();
    assert.equal(raw.at(-1).type, "done");
    assert.equal(stepRuns, 1);
    assert.equal(modelCalls, 3);
  `);
});
