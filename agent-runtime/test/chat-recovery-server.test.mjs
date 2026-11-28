import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

// Each scenario runs the server in its own process with a mocked runtime whose
// stores are real SQLite durable harnesses, opened by store and conversation as
// runtime.ts opens them, with a scripted model and a tool the test releases.
// The runtime's store checks (generations, steer fences) are the real ones.
const preamble = (dir) => `
  import assert from "node:assert/strict";
  import { existsSync } from "node:fs";
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
  import { BranchError, branchFrom, openBranch, windsDown, workByChat } from "../src/branch.ts";
  import { CHAT_QUEUE_SETTINGS, readSteerReceipt, steerRequestId } from "../src/chat-control.ts";
  import { removeStore } from "../src/store-identity.ts";

  const dir = ${JSON.stringify(dir)};
  let server;
  const listen = Server.prototype.listen;
  Server.prototype.listen = function () {
    server = this;
    return listen.call(this, 0, "127.0.0.1");
  };

  // Every execution of the tool, and every model request, is counted.
  let toolRuns = 0;
  let modelCalls = 0;
  let toolStarted;
  let started;
  let releaseTool;
  let released;
  const arm = () => {
    started = new Promise((resolve) => (toolStarted = resolve));
    released = new Promise((resolve) => (releaseTool = resolve));
  };
  arm();
  const waitTool = defineTool({
    name: "wait_calibration",
    description: "Waits (test)",
    parameters: Type.Object({}),
    execute: async (_args, _api, toolContext) => {
      toolRuns++;
      toolStarted();
      await new Promise((resolve, reject) => {
        released.then(resolve);
        toolContext.abortSignal?.addEventListener("abort", () => reject(new Error("cancelled")), { once: true });
      });
      return { output: [{ type: "text", text: "finished" }] };
    },
  });
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const agent = { model: { provider: model.provider, modelId: model.id } };
  const text = (message) => typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
  let callId = 0;
  // A message starting with WAIT calls the waiting tool first, and again after
  // a call a restart interrupted; anything else is answered at once.
  const reply = (ctx) => {
    modelCalls++;
    const last = ctx.messages.at(-1);
    const user = text(ctx.messages.filter((m) => m.role === "user").at(-1));
    if (user.startsWith("WAIT") && (last.role === "user" || (last.role === "toolResult" && last.isError))) {
      return fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w" + ++callId })], { stopReason: "toolUse" });
    }
    return fauxAssistantMessage(fauxText("Answer: " + user));
  };
  faux.setResponses(Array.from({ length: 200 }, () => reply));

  const pathOf = (owner, store) => join(dir, owner + "-" + store + ".sqlite");
  let openHarnesses = 0;
  // What a test puts between the server and the harness or conversation it opens.
  const hooks = { harness: (h) => h, conversation: (c) => c, beforeDelete: async () => {} };
  const open = async (owner, store) => {
    const registry = createRegistry();
    registry.install(defineExtension({ name: "t", tools: [waitTool] }));
    const harness = await Harness.open(await openNodeSqliteStorage(pathOf(owner, store)), { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } }, BACKGROUND_CONTEXT);
    openHarnesses++;
    return { harness, close: async () => { await harness.close(BACKGROUND_CONTEXT); openHarnesses--; } };
  };
  const conversationOf = async (harness, conversationId) => {
    const conversation = conversationId === undefined
      ? await harness.root(BACKGROUND_CONTEXT, { agent })
      : await openBranch(harness, conversationId, BACKGROUND_CONTEXT);
    await conversation.configure(agent, BACKGROUND_CONTEXT);
    return conversation;
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
          const conversation = await conversationOf(harness, request.conversationId);
          return { harness: hooks.harness(harness), conversation: hooks.conversation(conversation), writeTools: {}, close };
        } catch (error) {
          await close();
          throw error;
        }
      },
      forkSession: async (request) => {
        if (!existsSync(pathOf(request.ownerId, request.storeSessionId))) throw new BranchError("store_not_found", "the chat's store was not found");
        const { harness, close } = await open(request.ownerId, request.storeSessionId);
        try {
          const source = request.sourceConversationId === undefined
            ? await harness.conversation(ROOT_CONVERSATION_ID, BACKGROUND_CONTEXT)
            : await openBranch(harness, request.sourceConversationId, BACKGROUND_CONTEXT);
          return await branchFrom(harness, source, request.at, request.targetSessionId, BACKGROUND_CONTEXT);
        } finally {
          await close();
        }
      },
      deleteSessionState: async (owner, store, generation) => {
        await hooks.beforeDelete();
        return removeStore(pathOf(owner, store), generation).outcome;
      },
      // As runtime.ts opens a store to stop stored work: no extension at all.
      openStoreForCleanup: async (owner, store) => {
        const harness = await Harness.open(await openNodeSqliteStorage(pathOf(owner, store)), { models, registry: createRegistry(), settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } }, BACKGROUND_CONTEXT);
        openHarnesses++;
        return { harness, close: async () => { await harness.close(BACKGROUND_CONTEXT); openHarnesses--; } };
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
  const headers = (project = "p1", token = "user-token") => ({
    "Content-Type": "application/json",
    Authorization: "Bearer test-runtime-token",
    ...(token ? { "x-qdash-token": token } : {}),
    ...(project ? { "x-qdash-project-id": project } : {}),
  });
  const post = (path, body, h = headers()) => fetch(base + path, { method: "POST", headers: h, body: JSON.stringify(body) });
  const remove = (body) => fetch(base + "/session", { method: "DELETE", headers: headers(), body: JSON.stringify({ owner_id: "alice", ...body }) });
  const lines = async (response) => (await response.text()).trim().split("\\n").filter(Boolean).map(JSON.parse);
  const turn = { owner_id: "alice", model: { provider: model.provider, name: model.id } };
  const chat = async (body) => {
    const response = await post("/chat", body);
    assert.equal(response.status, 200, await response.clone().text());
    const out = await lines(response);
    return { out, done: out.find((line) => line.type === "done"), error: out.find((line) => line.type === "error") };
  };
  const branchAt = async (store, entryId, target, generation = "G1") => {
    const response = await post("/chat/branch", { owner_id: "alice", store_session_id: store, store_generation: generation, entry_id: entryId, target_session_id: target });
    assert.equal(response.status, 200, await response.clone().text());
    return (await response.json()).conversation_id;
  };
  // The users' messages a conversation of a store holds, read without a writer.
  const users = async (store, conversationId) => {
    const storage = await openNodeSqliteStorage(pathOf("alice", store));
    const harness = await Harness.open(storage, { models, registry: createRegistry(), readOnly: true }, BACKGROUND_CONTEXT);
    try {
      const conversation = await harness.conversation(conversationId, BACKGROUND_CONTEXT);
      const view = await conversation.context(BACKGROUND_CONTEXT);
      return view.entries
        .filter((entry) => UserEntry.is(entry) || steerRequestId(entry))
        .map((entry) => text(entry.model[0]));
    } finally {
      await harness.close(BACKGROUND_CONTEXT);
    }
  };
  // The store's unfinished work by chat conversation, read with scheduling paused.
  const work = async (store) => {
    const { harness, close } = await open("alice", store);
    try {
      const byChat = await workByChat(harness, BACKGROUND_CONTEXT);
      return Object.fromEntries([...byChat].map(([id, chat]) => [id, windsDown(chat) ? "winds_down" : "runnable"]));
    } finally {
      await close();
    }
  };
  // A runtime that dies mid-run: the run stays in the store, and nothing in
  // memory knows it. Its tool was started once.
  const crash = async (store, conversationId, message, requestId) => {
    arm();
    const { harness, close } = await open("alice", store);
    const conversation = await conversationOf(harness, conversationId);
    await conversation.submit({ type: "input", content: message, ...(requestId ? { requestId } : {}) }, BACKGROUND_CONTEXT);
    await started;
    await close();
    arm();
  };
  const passThrough = (target, override) => new Proxy(target, {
    get: (t, key) => {
      if (key in override) return override[key];
      const value = t[key];
      return typeof value === "function" ? value.bind(t) : value;
    },
  });
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
  const dir = mkdtempSync(join(tmpdir(), "chat-recovery-"));
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

test("a normal second turn repeats no answer; only the turn's own message closes a recovered run's answer", { timeout: 90_000 }, () => {
  runScenario(`
    const root = { ...turn, conversation_id: "c1", store_generation: "G1" };
    const q1 = await chat({ ...root, request_id: "t1", message: "Q1" });
    assert.equal(q1.done.text, "Answer: Q1");
    // The history holds Q1 and its answer: the second turn's own message carries no answer.
    const q2 = await chat({ ...root, request_id: "t2", message: "Q2" });
    assert.deepEqual(q2.out.filter((line) => line.type === "turn_start"), [{ type: "turn_start", answer: "" }]);
    assert.equal(q2.out.filter((line) => line.type === "text_delta").map((line) => line.delta).join(""), "Answer: Q2");
    assert.equal(q2.done.text, "Answer: Q2");

    // The runtime dies mid-run with the runtime's own wrap-up queued: a plain
    // user message, no steer. The next turn recovers the run, which places the
    // wrap-up and answers it, all before that turn's own submit returns.
    {
      const { harness, close } = await open("alice", "c1");
      const conversation = await conversationOf(harness, undefined);
      await conversation.submit({ type: "input", content: "WAIT calibrate" }, BACKGROUND_CONTEXT);
      await started;
      await conversation.submit({ type: "input", content: "Wrap up now.", whenBusy: "steer", whenIdle: "reject" }, BACKGROUND_CONTEXT);
      await close();
    }
    releaseTool();
    hooks.conversation = (conversation) => passThrough(conversation, {
      submit: async (...args) => {
        await conversation.waitForIdle(BACKGROUND_CONTEXT);
        return conversation.submit(...args);
      },
    });
    const q3 = await chat({ ...turn, conversation_id: "c1", store_generation: "G1", request_id: "t3", message: "Q3" });
    hooks.conversation = (c) => c;
    // The wrap-up is not the turn's own message: one turn start, at Q3, closing the recovered answer.
    const starts = q3.out.filter((line) => line.type === "turn_start");
    assert.deepEqual(starts, [{ type: "turn_start", answer: "Answer: Wrap up now." }], JSON.stringify(q3.out));
    const at = q3.out.findIndex((line) => line.type === "turn_start");
    const before = q3.out.slice(0, at).filter((line) => line.type === "text_delta").map((line) => line.delta).join("");
    const after = q3.out.slice(at).filter((line) => line.type === "text_delta").map((line) => line.delta).join("");
    assert.equal(before, "Answer: Wrap up now.");
    assert.equal(after, "Answer: Q3");
    assert.equal(q3.done.text, "Answer: Q3");
    assert.deepEqual(await users("c1", ROOT_CONVERSATION_ID), ["Q1", "Q2", "WAIT calibrate", "Wrap up now.", "Q3"]);
  `);
});

test("a stop while the turn checks the store for a sibling's crashed run resumes nothing", { timeout: 90_000 }, () => {
  runScenario(`
    const root = { ...turn, conversation_id: "c1", store_generation: "G1" };
    const q1 = await chat({ ...root, request_id: "t1", message: "Q1" });
    const b1 = await branchAt("c1", q1.done.entry_id, "b1");
    await crash("c1", Number(b1), "WAIT crashed");
    const runs = toolRuns;
    const calls = modelCalls;
    const branchBefore = await users("c1", Number(b1));

    // The root's turn opens the store; its check for other branches' unfinished work is held.
    let inner;
    let entered;
    const inspecting = new Promise((resolve) => (entered = resolve));
    let resumeInspect;
    const gate = new Promise((resolve) => (resumeInspect = resolve));
    hooks.harness = (harness) => {
      inner = harness;
      return passThrough(harness, {
        inspect: async (...args) => {
          entered();
          await gate;
          return harness.inspect(...args);
        },
      });
    };
    const pending = post("/chat", { ...root, request_id: "t2", message: "Q2" });
    await inspecting;
    // The user stops the turn meanwhile: it is remembered, and aborts nothing yet.
    let response = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1", store_generation: "G1" });
    assert.equal(response.status, 200);
    // Aborting would have started scheduling, and with it the branch's crashed run.
    assert.equal((await inner.inspect(BACKGROUND_CONTEXT)).scheduling, "paused");
    resumeInspect();
    response = await pending;
    assert.equal(response.status, 409);
    assert.equal((await response.json()).reason, "store_busy");
    hooks.harness = (h) => h;
    assert.equal(toolRuns, runs);
    assert.equal(modelCalls, calls);
    assert.deepEqual(await users("c1", Number(b1)), branchBefore);
    assert.deepEqual(await work("c1"), { [b1]: "runnable" });
    releaseTool();
  `);
});

test("a deleted branch's crashed run is stopped from the store; siblings stay untouched and usable", { timeout: 90_000 }, () => {
  runScenario(`
    const root = { ...turn, conversation_id: "c1", store_generation: "G1" };
    const q1 = await chat({ ...root, request_id: "t1", message: "Q1" });
    const b1 = await branchAt("c1", q1.done.entry_id, "b1");
    const b2 = await branchAt("c1", q1.done.entry_id, "b2");
    const ref = (session, conversation) => ({ owner_id: "alice", conversation_id: session, store_session_id: "c1", store_conversation_id: conversation, store_generation: "G1" });
    const chatB2 = (requestId, message) => chat({ ...turn, ...ref("b2", b2), request_id: requestId, message });

    await crash("c1", Number(b1), "WAIT crashed");
    // A sibling is refused while the crashed run could resume beside it.
    let response = await post("/chat", { ...turn, ...ref("b2", b2), request_id: "x", message: "?" });
    assert.equal((await response.json()).reason, "store_busy");

    // Nothing in memory runs b1: a plain stop finds nothing, and a stored stop needs credentials.
    response = await post("/chat/abort", ref("b1", b1));
    assert.equal(response.status, 404);
    response = await post("/chat/abort", { ...ref("b1", b1), include_stored: true }, headers("p1", null));
    assert.equal(response.status, 401);

    const runs = toolRuns;
    const calls = modelCalls;
    const rootBefore = await users("c1", ROOT_CONVERSATION_ID);
    const b2Before = await users("c1", Number(b2));
    // The chat b1 was deleted: its work is stopped from the store. No sibling has work, so it ends now.
    response = await post("/chat/abort", { ...ref("b1", b1), include_stored: true });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { aborted: true, settled: true });
    assert.equal(toolRuns, runs, "no tool ran");
    assert.equal(modelCalls, calls, "no model was asked");
    assert.deepEqual(await work("c1"), {});
    assert.deepEqual(await users("c1", ROOT_CONVERSATION_ID), rootBefore);
    assert.deepEqual(await users("c1", Number(b2)), b2Before);
    // Again: nothing left to stop.
    response = await post("/chat/abort", { ...ref("b1", b1), include_stored: true });
    assert.equal(response.status, 404);
    // The sibling works.
    assert.equal((await chatB2("tb2", "QB2")).done.text, "Answer: QB2");

    // Both branches die mid-run. Stopping b1 must not start scheduling: b2's run would run unwatched.
    await crash("c1", Number(b1), "WAIT crashed again");
    await crash("c1", Number(b2), "WAIT b2 crashed");
    const runs2 = toolRuns;
    const calls2 = modelCalls;
    response = await post("/chat/abort", { ...ref("b1", b1), include_stored: true });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { aborted: true, settled: false });
    assert.equal(toolRuns, runs2);
    assert.equal(modelCalls, calls2);
    assert.deepEqual(await work("c1"), { [b1]: "winds_down", [b2]: "runnable" });
    // Repeated: still only marked, still nothing ran.
    response = await post("/chat/abort", { ...ref("b1", b1), include_stored: true });
    assert.deepEqual(await response.json(), { aborted: true, settled: false });
    assert.equal(toolRuns, runs2);
    // The root is still refused because of b2's own crashed run, not because of b1's.
    response = await post("/chat", { ...root, request_id: "t9", message: "Q9" });
    assert.equal((await response.json()).reason, "store_busy");
    // b2's own next request recovers its run, and b1's winds down beside it, answering nothing.
    releaseTool();
    const recovered = await chatB2("tb3", "QB3");
    assert.equal(recovered.done.text, "Answer: QB3");
    assert.deepEqual(await work("c1"), {});
    assert.deepEqual((await users("c1", Number(b1))).slice(-1), ["WAIT crashed again"]);
    assert.equal((await chat({ ...root, request_id: "t10", message: "Q10" })).done.text, "Answer: Q10");

    // While another branch's turn holds the store, a stored stop is refused, not guessed.
    arm();
    const running = post("/chat", { ...root, request_id: "t11", message: "WAIT root" });
    await started;
    response = await post("/chat/abort", { ...ref("b1", b1), include_stored: true });
    assert.equal(response.status, 409);
    assert.equal((await response.json()).reason, "store_busy");
    releaseTool();
    assert.equal((await lines(await running)).at(-1).type, "done");
  `);
});

test("a store's generation fences stale removals, chats, stops, and branches", { timeout: 90_000 }, () => {
  runScenario(`
    const g = (generation) => ({ ...turn, conversation_id: "g1", ...(generation ? { store_generation: generation } : {}) });
    const path = pathOf("alice", "g1");
    const q1 = await chat({ ...g("G1"), request_id: "t1", message: "Q1" });
    assert.equal(q1.done.text, "Answer: Q1");
    let response = await remove({ conversation_id: "g1", store_generation: "G1" });
    assert.deepEqual(await response.json(), { deleted: true, outcome: "removed" });
    assert.equal(existsSync(path), false);
    // A chat request of the removed generation, still on its way, cannot recreate the store.
    response = await post("/chat", { ...g("G1"), request_id: "t2", message: "late" });
    assert.equal(response.status, 409);
    assert.equal((await response.json()).reason, "stale_store");
    assert.equal(existsSync(path), false);

    // The chat is created again under the same ID.
    assert.equal((await chat({ ...g("G2"), request_id: "t3", message: "New" })).done.text, "Answer: New");
    // The first removal's retry arrives after its lease ran out and the chat was recreated: it removes nothing.
    response = await remove({ conversation_id: "g1", store_generation: "G1" });
    assert.deepEqual(await response.json(), { deleted: true, outcome: "stale" });
    // A legacy removal does not reach a store with a generation either.
    response = await remove({ conversation_id: "g1" });
    assert.equal(response.status, 409);
    assert.deepEqual(await users("g1", ROOT_CONVERSATION_ID), ["New"]);
    // Nor a branch request about the removed generation.
    response = await post("/chat/branch", { owner_id: "alice", store_session_id: "g1", store_generation: "G1", entry_id: "1", target_session_id: "b" });
    assert.equal((await response.json()).reason, "stale_store");

    // While the new chat's turn runs: a stale removal or stop says the old one is gone, and touches nothing.
    arm();
    const running = post("/chat", { ...g("G2"), request_id: "t4", message: "WAIT new" });
    await started;
    response = await remove({ conversation_id: "g1", store_generation: "G1" });
    assert.deepEqual(await response.json(), { deleted: true, outcome: "stale" });
    response = await remove({ conversation_id: "g1", store_generation: "G2" });
    assert.equal(response.status, 409);
    response = await post("/chat/abort", { owner_id: "alice", conversation_id: "g1", store_generation: "G1" });
    assert.equal(response.status, 404);
    response = await post("/chat/abort", { owner_id: "alice", conversation_id: "g1", store_generation: "G1", include_stored: true });
    assert.equal(response.status, 404);
    releaseTool();
    assert.equal((await lines(await running)).at(-1).text, "Answer: WAIT new");

    // A removal holds the store: a chat that comes meanwhile is refused, and none recreates it afterwards
    // under the removed generation.
    let entered;
    const deleting = new Promise((resolve) => (entered = resolve));
    let finishDelete;
    const gate = new Promise((resolve) => (finishDelete = resolve));
    hooks.beforeDelete = async () => {
      entered();
      await gate;
    };
    const removal = remove({ conversation_id: "g1", store_generation: "G2" });
    await deleting;
    response = await post("/chat", { ...g("G2"), request_id: "t5", message: "meanwhile" });
    assert.equal((await response.json()).reason, "store_busy");
    response = await post("/chat", { ...g("G3"), request_id: "t6", message: "meanwhile" });
    assert.equal((await response.json()).reason, "store_busy");
    finishDelete();
    hooks.beforeDelete = async () => {};
    assert.deepEqual(await (await removal).json(), { deleted: true, outcome: "removed" });
    response = await post("/chat", { ...g("G2"), request_id: "t7", message: "late" });
    assert.equal((await response.json()).reason, "stale_store");
    assert.equal((await chat({ ...g("G3"), request_id: "t8", message: "Third" })).done.text, "Answer: Third");
    assert.deepEqual(await users("g1", ROOT_CONVERSATION_ID), ["Third"]);

    // A store from before generations is adopted by the first request that names one.
    assert.equal((await chat({ ...turn, conversation_id: "legacy", request_id: "l1", message: "Old" })).done.text, "Answer: Old");
    assert.equal(existsSync(pathOf("alice", "legacy") + ".generation"), false);
    assert.equal((await chat({ ...turn, conversation_id: "legacy", store_generation: "L1", request_id: "l2", message: "Adopted" })).done.text, "Answer: Adopted");
    response = await remove({ conversation_id: "legacy" });
    assert.equal(response.status, 409);
    response = await remove({ conversation_id: "legacy", store_generation: "L1" });
    assert.deepEqual(await response.json(), { deleted: true, outcome: "removed" });
  `);
});

test("a steer a status lookup reported not found is never admitted, also by the turn requested again", { timeout: 90_000 }, () => {
  runScenario(`
    const root = { ...turn, conversation_id: "c1" };
    const ref = { owner_id: "alice", conversation_id: "c1" };
    // Turn t1 was started by a runtime that died: no request of it is in memory.
    await crash("c1", undefined, "WAIT calibrate", "t1");
    // The chat asks where its steer s9 stands: never admitted.
    let response = await post("/chat/steer/status", { ...ref, request_id: "s9" });
    assert.deepEqual(await response.json(), { status: "not_found" });

    // The turn is requested again with its own request ID, recovering its run.
    const replay = post("/chat", { ...root, request_id: "t1", message: "WAIT calibrate" });
    await started;
    // The steer request, delayed, arrives now: refused, and nothing is added.
    response = await post("/chat/steer", { ...ref, request_id: "s9", message: "late", turn_request_id: "t1" });
    assert.equal(response.status, 409);
    assert.deepEqual(await response.json(), { status: "rejected", reason: "idle" });
    // Another steer to the same turn is admitted; its retry reports the same steer.
    response = await post("/chat/steer", { ...ref, request_id: "s10", message: "Use Q5", turn_request_id: "t1" });
    const queued = await response.json();
    assert.equal(queued.status, "queued");
    response = await post("/chat/steer", { ...ref, request_id: "s10", message: "Use Q5", turn_request_id: "t1" });
    assert.equal((await response.json()).submission_id, queued.submission_id);
    releaseTool();
    const out = await lines(await replay);
    const placed = out.find((line) => line.type === "steer");
    assert.equal(placed.request_id, "s10");
    assert.equal(out.at(-1).text, "Answer: Use Q5");

    response = await post("/chat/steer/status", { ...ref, request_id: "s9" });
    assert.deepEqual(await response.json(), { status: "not_found" });
    assert.deepEqual(await users("c1", ROOT_CONVERSATION_ID), ["WAIT calibrate", "Use Q5"]);
    // A steer the store holds still reports its receipt, after its turn ended too.
    response = await post("/chat/steer", { ...ref, request_id: "s10", message: "Use Q5", turn_request_id: "t1" });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "applied", submission_id: queued.submission_id, entry_id: placed.entry_id });
  `);
});
