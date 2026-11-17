import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  AssistantEntry,
  createRegistry,
  defineExtension,
  defineTool,
  Harness,
  LiveDoc,
  ToolResultEntry,
  UserEntry,
} from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { Type } from "typebox";

import { BranchError, branchFrom, branchReceipt, openBranch, parseDurableId, unfinishedWork } from "../src/branch.ts";
import { CHAT_QUEUE_SETTINGS } from "../src/chat-control.ts";
import {
  buildCodemodeExtensions,
  CODEMODE_TOOL_NAME,
  createCodemodeSandbox,
  runningScriptCount,
  TOOL_SEARCH_TOOL_NAME,
} from "../src/codemode.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";

const context = BACKGROUND_CONTEXT;
const connection = { toolArgs: { profile: "runtime", configPath: "/private/config.ini", useEnv: false } };
const modelRuntime = { getModel: () => undefined };

/** A pi-qdash-style tool that answers `data` and records its calls. */
function piTool(name, data) {
  const calls = [];
  return {
    calls,
    registered: {
      definition: {
        name,
        label: name,
        description: `${name} (test)`,
        parameters: Type.Object({}),
        execute: async (_id, params) => {
          calls.push(params);
          return { content: [{ type: "text", text: JSON.stringify(data) }], details: { data } };
        },
      },
    },
  };
}

/** Tool names the faux model was offered in one request. */
function offeredTools(transcript) {
  const tools = new Set();
  for (const message of transcript.messages) {
    if (message.role !== "system") continue;
    for (const tool of message.toolsRemoved ?? []) tools.delete(tool.name);
    for (const tool of message.toolsAdded ?? []) tools.add(tool.name);
  }
  return tools;
}

let release;
const waitTool = defineTool({
  name: "wait_calibration",
  description: "Waits until the test releases it",
  parameters: Type.Object({}),
  execute: async (_args, _api, toolContext) => {
    await new Promise((resolve, reject) => {
      release = resolve;
      toolContext.abortSignal?.addEventListener("abort", () => reject(new Error("cancelled")), { once: true });
    });
    return { output: [{ type: "text", text: "finished" }] };
  },
});
const askUser = defineTool({
  name: "ask_user",
  description: "Asks the user (test)",
  parameters: Type.Object({}),
  execute: async () => ({ output: [{ type: "text", text: "asked" }] }),
});

/**
 * One store opened as the runtime opens a chat: QDash's deferred tools, Code
 * Mode, tool_search, scheduling paused until resumed. `conversationId` opens a
 * branch instead of the root.
 */
async function openStore(path, { faux, responses, conversationId, resume = true } = {}) {
  faux ??= fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const cryostats = piTool("qdash_list_cryostats", [{ name: "fridge-1" }]);
  const cooldowns = piTool("qdash_list_cooldowns", [{ id: "cd1" }]);
  const qdash = buildQDashExtension(
    [{ tools: new Map([cryostats, cooldowns].map((tool) => [tool.registered.definition.name, tool.registered])) }],
    modelRuntime,
    "/tmp/work",
    connection,
    [],
    [],
  );
  const sandbox = createCodemodeSandbox();
  const registry = createRegistry();
  registry.install(qdash.extension);
  for (const extension of buildCodemodeExtensions(sandbox, qdash)) registry.install(extension);
  registry.install(defineExtension({ name: "test-tools", tools: [waitTool, askUser] }));
  if (responses) faux.setResponses(responses);
  const harness = await Harness.open(
    await openNodeSqliteStorage(path),
    { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } },
    context,
  );
  const agent = { model: { provider: model.provider, modelId: model.id } };
  const conversation =
    conversationId === undefined
      ? await harness.root(context, { agent })
      : await openBranch(harness, conversationId, context);
  await conversation.configure(agent, context);
  if (resume) harness.resume();
  return {
    faux,
    harness,
    conversation,
    close: async () => {
      await harness.close(context);
      await sandbox.close();
    },
  };
}

async function ask(conversation, content) {
  const submission = await conversation.submit({ type: "input", content }, context);
  return submission.wait(context);
}

async function entryIds(conversation) {
  return (await conversation.context(context)).entries.map((entry) => entry.id);
}

function lastUserText(transcript) {
  const message = transcript.messages.filter((m) => m.role === "user").at(-1);
  return typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
}

const script = (code, id) =>
  fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id })], { stopReason: "toolUse" });
const search = (query, id) =>
  fauxAssistantMessage([fauxToolCall(TOOL_SEARCH_TOOL_NAME, { query }, { id })], { stopReason: "toolUse" });

async function refusal(promise) {
  try {
    await promise;
  } catch (error) {
    assert.ok(error instanceof BranchError, String(error));
    return error.reason;
  }
  assert.fail("expected the branch to be refused");
}

async function scriptsDone() {
  for (let i = 0; i < 100 && runningScriptCount() > 0; i++) await new Promise((resolve) => setTimeout(resolve, 20));
}

test("a branch starts from the answer's context, tools, and Code Mode store; the source is unchanged", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-branch-"));
  const path = join(dir, "session.sqlite");
  const seen = [];
  const record = (step) => (transcript) => {
    seen.push({ tools: offeredTools(transcript), user: lastUserText(transcript), count: transcript.messages.length });
    return typeof step === "function" ? step(transcript) : step;
  };
  const chat = await openStore(path, {
    responses: [
      // Turn 1: load the cryostat tool, keep k = 1, answer A1.
      search("cryostats", "t1"),
      script("await store('k', 1); text('stored 1');", "s1"),
      fauxAssistantMessage(fauxText("A1")),
      // Turn 2: load the cooldown tool, keep k = 2, answer A2.
      search("cooldowns", "t2"),
      script("await store('k', 2); text('stored 2');", "s2"),
      fauxAssistantMessage(fauxText("A2")),
    ],
  });
  let a1;
  let sourceIds;
  let branchId;
  try {
    const first = await ask(chat.conversation, "Q1");
    assert.equal(first.status, "done");
    a1 = first.answer;
    assert.equal((await ask(chat.conversation, "Q2")).status, "done");
    sourceIds = await entryIds(chat.conversation);
    const sourceUsage = await chat.harness.usage(context);

    const created = await branchFrom(chat.harness, chat.conversation, a1, "b1", context);
    assert.equal(created.created, true);
    branchId = created.conversationId;
    assert.notEqual(branchId, chat.conversation.id);

    // The branch's transcript ends at A1; the source still has everything, unchanged.
    const branch = await chat.harness.conversation(branchId, context);
    const branchIds = await entryIds(branch);
    assert.equal(branchIds.at(-1), a1);
    assert.deepEqual(branchIds, sourceIds.slice(0, sourceIds.indexOf(a1) + 1));
    assert.deepEqual(await entryIds(chat.conversation), sourceIds);
    assert.deepEqual(await chat.harness.usage(context), sourceUsage);
    const live = await branch.commit(async (tx) => (await tx.doc(LiveDoc, branch.id)).run, context);
    assert.equal(live, undefined);

    // The receipt names the source and the answer.
    assert.deepEqual(await branchReceipt(chat.harness, "b1", context), {
      conversation: branchId,
      source: chat.conversation.id,
      at: a1,
    });
  } finally {
    await chat.close();
    await scriptsDone();
  }

  // Reopened as the next chat request opens the branch: it has the tools and the store of A1.
  const branchChat = await openStore(path, {
    conversationId: branchId,
    responses: [
      record(script("text(String(await load('k')));", "s3")),
      record((transcript) => {
        const result = transcript.messages.filter((m) => m.role === "toolResult").at(-1);
        return fauxAssistantMessage(fauxText(`k=${result.content.map((b) => b.text ?? "").join("")}`));
      }),
    ],
  });
  try {
    assert.equal(branchChat.conversation.id, branchId);
    const settled = await ask(branchChat.conversation, "On the branch");
    assert.equal(settled.status, "done");
    assert.equal(seen[0].user, "On the branch");
    assert.equal(seen[0].tools.has("qdash_list_cryostats"), true, "loaded before A1");
    assert.equal(seen[0].tools.has("qdash_list_cooldowns"), false, "loaded after A1");
    const answer = await branchChat.conversation.commit((tx) => tx.entry(AssistantEntry, settled.answer), context);
    assert.match(answer.model[0].content[0].text, /Output:\n1$/);
    // The model saw Q1/A1 and the new message, not Q2/A2.
    const view = await branchChat.conversation.context(context);
    const users = view.entries.filter((entry) => UserEntry.is(entry)).map((entry) => entry.model[0].content);
    assert.deepEqual(users, ["Q1", "On the branch"]);
  } finally {
    await branchChat.close();
    await scriptsDone();
  }

  // The source is as it was: its transcript, its tools, and its store.
  const source = await openStore(path, {
    responses: [
      record(script("text(String(await load('k')));", "s4")),
      record(fauxAssistantMessage(fauxText("source again"))),
    ],
  });
  try {
    assert.deepEqual((await entryIds(source.conversation)).slice(0, sourceIds.length), sourceIds);
    assert.equal((await ask(source.conversation, "Back on the source")).status, "done");
    assert.equal(seen[2].tools.has("qdash_list_cooldowns"), true);
    const results = (await source.conversation.context(context)).entries.filter((entry) => ToolResultEntry.is(entry));
    assert.match(results.at(-1).model[0].content.map((b) => b.text ?? "").join(""), /Output:\n2$/);
  } finally {
    await source.close();
    await scriptsDone();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a branch request is idempotent by target and refuses another answer for the same target", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-branch-idem-"));
  const path = join(dir, "session.sqlite");
  const chat = await openStore(path, {
    responses: [fauxAssistantMessage(fauxText("A1")), fauxAssistantMessage(fauxText("A2"))],
  });
  try {
    const a1 = (await ask(chat.conversation, "Q1")).answer;
    const a2 = (await ask(chat.conversation, "Q2")).answer;
    const first = await branchFrom(chat.harness, chat.conversation, a1, "b1", context);
    const again = await branchFrom(chat.harness, chat.conversation, a1, "b1", context);
    assert.deepEqual(again, { conversationId: first.conversationId, created: false });
    assert.equal(await refusal(branchFrom(chat.harness, chat.conversation, a2, "b1", context)), "conflict");
    // The same target from a branch of the source is another request too.
    const branch = await chat.harness.conversation(first.conversationId, context);
    assert.equal(await refusal(branchFrom(chat.harness, branch, a1, "b1", context)), "conflict");
    // Another target at the same answer is another branch.
    const second = await branchFrom(chat.harness, chat.conversation, a1, "b2", context);
    assert.equal(second.created, true);
    assert.notEqual(second.conversationId, first.conversationId);
    // A branch of a branch, at an answer it inherited.
    const nested = await branchFrom(chat.harness, branch, a1, "b3", context);
    assert.equal(nested.created, true);
    assert.equal((await entryIds(await chat.harness.conversation(nested.conversationId, context))).at(-1), a1);
  } finally {
    await chat.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("only a completed final answer with nothing waiting for the user can be branched from", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-branch-refuse-"));
  const path = join(dir, "session.sqlite");
  const chat = await openStore(path, {
    responses: [
      fauxAssistantMessage([fauxToolCall("ask_user", {}, { id: "a1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("Which qubit? Pick one above.")),
      fauxAssistantMessage(fauxText("Q5 it is.")),
      fauxAssistantMessage(fauxText("partial"), { stopReason: "error", errorMessage: "boom" }),
    ],
  });
  try {
    const asked = await ask(chat.conversation, "Calibrate");
    assert.equal(asked.status, "done");
    const answered = await ask(chat.conversation, "Q5");
    const failed = await ask(chat.conversation, "Fail please");
    assert.notEqual(failed.status, "done");
    const entries = (await chat.conversation.context(context)).entries;
    const user = entries.find((entry) => UserEntry.is(entry));
    const toolCall = entries.find(
      (entry) => AssistantEntry.is(entry) && entry.model[0].content.some((b) => b.type === "toolCall"),
    );
    const errored = entries.findLast((entry) => AssistantEntry.is(entry));
    assert.equal(errored.model[0].stopReason, "error");

    const refuse = (at) => refusal(branchFrom(chat.harness, chat.conversation, at, `t${at}`, context));
    assert.equal(await refuse(user.id), "not_final_answer");
    assert.equal(await refuse(toolCall.id), "not_final_answer");
    assert.equal(await refuse(errored.id), "not_final_answer");
    // The answer after ask_user waits for the user: its card must not become actionable on a branch.
    assert.equal(await refuse(asked.answer), "awaiting_user");
    assert.equal(await refuse(999999), "entry_not_found");
    // Once the user answered, the next answer can be.
    assert.equal((await branchFrom(chat.harness, chat.conversation, answered.answer, "ok", context)).created, true);
    // Nothing was written for the refused requests.
    for (const at of [user.id, toolCall.id, errored.id, asked.answer]) {
      assert.equal(await branchReceipt(chat.harness, `t${at}`, context), undefined);
    }
  } finally {
    await chat.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("only an entry not visible from the source is entry_not_found; a storage fault is not a refusal", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-branch-visible-"));
  const path = join(dir, "session.sqlite");
  const chat = await openStore(path, {
    responses: [fauxAssistantMessage(fauxText("A1")), fauxAssistantMessage(fauxText("B2"))],
  });
  try {
    const a1 = (await ask(chat.conversation, "Q1")).answer;
    const first = await branchFrom(chat.harness, chat.conversation, a1, "b1", context);
    const branch = await chat.harness.conversation(first.conversationId, context);
    const b2 = (await ask(branch, "Q2 on the branch")).answer;
    // An answer of a sibling conversation exists in the store but is not visible from the root.
    assert.equal(await refusal(branchFrom(chat.harness, chat.conversation, b2, "t-sibling", context)), "entry_not_found");
    // A failing read of the store surfaces as itself, so the API reports a fault and may retry.
    const fault = new Error("disk I/O error");
    const failing = new Proxy(chat.conversation, {
      get(target, property, receiver) {
        if (property === "context") return async () => Promise.reject(fault);
        const value = Reflect.get(target, property, receiver);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
    await assert.rejects(branchFrom(chat.harness, failing, a1, "t-fault", context), (error) => error === fault);
    assert.equal(await branchReceipt(chat.harness, "t-fault", context), undefined);
  } finally {
    await chat.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a running, queued, or dead run refuses a branch; a branch opens only by its runtime ID", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-branch-busy-"));
  const path = join(dir, "session.sqlite");
  const chat = await openStore(path, {
    responses: [
      fauxAssistantMessage(fauxText("A1")),
      fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("never")),
    ],
  });
  let a1;
  try {
    a1 = (await ask(chat.conversation, "Q1")).answer;
    await chat.conversation.submit({ type: "input", content: "Run it" }, context);
    for (let i = 0; i < 200 && !release; i++) await new Promise((resolve) => setTimeout(resolve, 10));
    assert.ok(release, "the tool started");
    assert.equal(await refusal(branchFrom(chat.harness, chat.conversation, a1, "busy", context)), "busy");
    // Another conversation of the store is not a branch: it does not open as one.
    const other = await chat.harness.createConversation({ ownership: { kind: "ownerless" } }, context);
    assert.equal(await refusal(openBranch(chat.harness, other.id, context)), "conversation_not_found");
  } finally {
    // Closing mid-run leaves the run as a crash would: unfinished in the store.
    await chat.close();
    release = undefined;
  }
  const reopened = await openStore(path, { resume: false });
  try {
    assert.equal(await refusal(branchFrom(reopened.harness, reopened.conversation, a1, "dead", context)), "busy");
    assert.equal(await branchReceipt(reopened.harness, "dead", context), undefined);
    assert.equal((await reopened.harness.inspect(context)).scheduling, "paused");
  } finally {
    await reopened.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("work a crash left in a sibling branch refuses a branch from any conversation of the store", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-branch-sibling-"));
  const path = join(dir, "session.sqlite");
  const chat = await openStore(path, { responses: [fauxAssistantMessage(fauxText("A1"))] });
  let a1;
  let sibling;
  try {
    a1 = (await ask(chat.conversation, "Q1")).answer;
    sibling = (await branchFrom(chat.harness, chat.conversation, a1, "b", context)).conversationId;
    assert.deepEqual(await unfinishedWork(chat.harness, context), []);
  } finally {
    await chat.close();
  }
  // The sibling starts a long tool call, and the runtime dies with it running.
  const branch = await openStore(path, {
    conversationId: sibling,
    responses: [
      fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("never")),
    ],
  });
  try {
    await branch.conversation.submit({ type: "input", content: "Run it" }, context);
    for (let i = 0; i < 200 && !release; i++) await new Promise((resolve) => setTimeout(resolve, 10));
    assert.ok(release, "the tool started");
  } finally {
    await branch.close();
    release = undefined;
  }
  // After the restart nothing in memory holds the store: only the store says so.
  const reopened = await openStore(path, { resume: false });
  try {
    assert.deepEqual(await unfinishedWork(reopened.harness, context), [sibling]);
    // The root itself is idle, yet the store is not.
    assert.deepEqual(await unfinishedWork(reopened.harness, context, reopened.conversation.id), [sibling]);
    assert.deepEqual(await unfinishedWork(reopened.harness, context, sibling), []);
    assert.equal(await refusal(branchFrom(reopened.harness, reopened.conversation, a1, "c", context)), "busy");
    assert.equal(await branchReceipt(reopened.harness, "c", context), undefined);
    assert.equal((await reopened.harness.inspect(context)).scheduling, "paused");
  } finally {
    await reopened.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("durable IDs parse from their decimal wire form only", () => {
  assert.equal(parseDurableId("42"), 42);
  for (const bad of ["", "-1", "1.5", "0x10", "1e3", " 4", "9999999999999999", 42, null, undefined]) {
    assert.equal(parseDurableId(bad), undefined, String(bad));
  }
});
