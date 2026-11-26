import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { configure, Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { Type } from "typebox";

import { askUserTool } from "../src/ask-tool.ts";
import { buildAgentExtension, buildChatRegistry } from "../src/chat-registry.ts";
import { toNdjsonEvents } from "../src/events.ts";
import {
  MAX_PARALLEL_SUBAGENTS,
  MAX_SUBAGENT_TASKS,
  runningSubagentCount,
  SUBAGENT_TOOL,
  SubagentDoc,
  subagentBlockMessage,
  subagentsFromDetails,
} from "../src/subagent-tool.ts";
import { ViewEventTranslator } from "../src/view-events.ts";

const context = BACKGROUND_CONTEXT;
const SECRET_CONFIG = "/private/qdash-secret.ini";
const connection = { toolArgs: { profile: "runtime", configPath: SECRET_CONFIG, useEnv: false } };
const modelRuntime = { getModel: () => undefined };

/** A pi-qdash-style tool that records its calls; `respond` may wait, and sees the call's signal. */
function piTool(name, respond = () => ({ ok: true })) {
  const calls = [];
  return {
    calls,
    registered: {
      definition: {
        name,
        label: name,
        description: `${name} (test)`,
        parameters: Type.Object({
          chipId: Type.Optional(Type.String()),
          title: Type.Optional(Type.String()),
          path: Type.Optional(Type.String()),
        }),
        execute: async (_id, params, signal) => {
          calls.push(params);
          const data = await respond(params, signal);
          return { content: [{ type: "text", text: JSON.stringify(data) }], details: { data } };
        },
      },
    },
  };
}

const piExtension = (tools) => ({
  tools: new Map(tools.map((tool) => [tool.registered.definition.name, tool.registered])),
});

/** The production chat assembly with subagents on. */
function chatRegistry(tools) {
  return buildChatRegistry(
    {
      extensions: [piExtension(tools)],
      modelRuntime,
      workDir: "/tmp/work",
      extensionPaths: [],
      agent: buildAgentExtension("QDash parent prompt", [askUserTool]),
      internalCalls: {},
      codingTools: true,
      subagents: true,
    },
    connection,
  );
}

/** Text of a message's content. */
function textOf(message) {
  const content = message?.content;
  if (typeof content === "string") return content;
  return (content ?? []).map((block) => block.text ?? "").join("");
}

/**
 * A faux model that answers each request with `parent(results, transcript)` or
 * `child(prompt, results, transcript)`, by whether the request is a subagent's.
 */
function brain({ parent, child }) {
  const transcripts = [];
  const respond = (transcript) => {
    transcripts.push(transcript);
    const system = JSON.stringify(transcript.messages.filter((m) => m.role === "system"));
    const results = transcript.messages.filter((m) => m.role === "toolResult");
    if (system.includes("read-only research subagent")) {
      const prompt = textOf(transcript.messages.find((m) => m.role === "user"));
      return child(prompt, results, transcript);
    }
    return parent(results, transcript);
  };
  return { transcripts, steps: Array.from({ length: 80 }, () => respond) };
}

async function open(registry, steps, storage = new MemoryStorage()) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  faux.setResponses(steps);
  const harness = await Harness.open(storage, { models, registry, settings: { retry: { enabled: false } } }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return { harness, conversation, faux };
}

const delegate = (tasks, id = "d1") =>
  fauxAssistantMessage([fauxToolCall(SUBAGENT_TOOL, { tasks }, { id })], { stopReason: "toolUse" });

async function toolResults(conversation) {
  const view = await conversation.context(context);
  return view.entries.filter((entry) => ToolResultEntry.is(entry)).map((entry) => entry.model[0]);
}

async function until(check, what, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (await check()) return;
    assert.ok(Date.now() < deadline, `timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

/** The tools a request offered: what its system messages added, less what they removed. */
function offeredTools(transcript) {
  const names = new Set(transcript.tools?.map((tool) => tool.name) ?? []);
  for (const message of transcript.messages) {
    if (message.role !== "system") continue;
    for (const tool of message.toolsAdded ?? []) names.add(tool.name);
    for (const tool of message.toolsRemoved ?? []) names.delete(typeof tool === "string" ? tool : tool.name);
  }
  return [...names];
}

const childTranscripts = (transcripts) =>
  transcripts.filter((t) => JSON.stringify(t.messages.filter((m) => m.role === "system")).includes("research subagent"));

test("the chat model delegates research tasks and reads every child's bounded answer", async () => {
  const chips = piTool("qdash_list_chips", ({ chipId }) => [{ chip_id: chipId }]);
  const metrics = piTool("qdash_get_chip_metrics");
  const evidence = piTool("qdash_get_task_result_evidence");
  const save = piTool("qdash_save_flow");
  const figure = piTool("qdash_get_figure");
  const chat = chatRegistry([chips, metrics, evidence, save, figure]);
  // Only the model may delegate: no script or other tool can start a subagent.
  const delegateTool = chat.registry.snapshot().tools().find(({ tool }) => tool.name === SUBAGENT_TOOL).tool;
  assert.deepEqual(delegateTool.callers, ["model"]);
  assert.equal(delegateTool.replay, "unsafe");
  const { transcripts, steps } = brain({
    parent: (results) =>
      results.length === 0
        ? delegate([
            { title: "Chip A", prompt: "Report chip A" },
            { title: "Chip B", prompt: "Report chip B" },
          ])
        : fauxAssistantMessage(fauxText("Both chips reported.")),
    child: (prompt, results) =>
      results.length === 0
        ? fauxAssistantMessage([fauxToolCall("qdash_list_chips", { chipId: prompt.slice(-1) }, { id: "c1" })], {
            stopReason: "toolUse",
          })
        : fauxAssistantMessage(fauxText(`answer for ${prompt}: ${textOf(results[0])}`)),
  });
  const { harness, conversation } = await open(chat.registry, steps);
  try {
    const settled = await (await conversation.submit({ type: "input", content: "Compare A and B" }, context)).wait(context);
    assert.equal(settled.status, "done");
    const [result] = await toolResults(conversation);
    assert.equal(result.toolName, SUBAGENT_TOOL);
    assert.notEqual(result.isError, true);
    const text = textOf(result);
    assert.match(text, /2 research subagents: 2 answered/);
    assert.match(text, /## Task 1: Chip A \(done, 1 tool call\)\nanswer for Report chip A: \[\{"chip_id":"A"\}\]/);
    assert.match(text, /## Task 2: Chip B \(done, 1 tool call\)\nanswer for Report chip B/);

    const tasks = result.details.subagents.tasks;
    assert.deepEqual(
      tasks.map(({ id, title, status, toolCalls }) => ({ id, title, status, toolCalls })),
      [
        { id: "1", title: "Chip A", status: "done", toolCalls: 1 },
        { id: "2", title: "Chip B", status: "done", toolCalls: 1 },
      ],
    );
    assert.ok(tasks.every((task) => task.endedAt >= task.startedAt && task.result.startsWith("answer for")));

    // The children called QDash through the chat's own connection.
    assert.equal(chips.calls.length, 2);
    for (const call of chips.calls) assert.equal(call.profile, "runtime");

    // Each child was offered exactly the audited reads, the deferred one included, and nothing else.
    const children = childTranscripts(transcripts);
    assert.equal(children.length, 4);
    for (const transcript of children) {
      const offered = offeredTools(transcript).sort();
      assert.deepEqual(offered, ["qdash_get_chip_metrics", "qdash_get_task_result_evidence", "qdash_list_chips"]);
      const system = JSON.stringify(transcript.messages.filter((m) => m.role === "system"));
      assert.doesNotMatch(system, /QDash parent prompt/);
    }
    // The parent was offered delegate_research; no request carried the connection's settings.
    assert.ok(offeredTools(transcripts[0]).includes(SUBAGENT_TOOL));
    for (const transcript of transcripts) assert.doesNotMatch(JSON.stringify(transcript), /qdash-secret|configPath/);
    assert.equal(runningSubagentCount(), 0);
  } finally {
    await harness.close(context);
    await chat.close();
  }
});

test("a child cannot reach writes, code, discovery, the workspace, raw routes, questions or delegation", async () => {
  const chips = piTool("qdash_list_chips", () => []);
  const save = piTool("qdash_save_flow");
  const figure = piTool("qdash_get_figure");
  const raw = piTool("qdash_raw_get");
  const chat = chatRegistry([chips, save, figure, raw]);
  const probes = [
    ["qdash_save_flow", { title: "x" }],
    ["codemode", { code: "await tools.qdash_save_flow({ title: 'x' }); text('ran');" }],
    ["tool_search", { query: "save flow" }],
    ["bash", { command: "curl http://api" }],
    ["write", { path: "/tmp/x", content: "x" }],
    ["ask_user", { question: "?", options: [{ label: "a" }, { label: "b" }] }],
    [SUBAGENT_TOOL, { tasks: [{ title: "again", prompt: "recurse" }] }],
    ["qdash_get_figure", { path: "/figure.png" }],
    ["qdash_raw_get", { path: "/admin" }],
  ];
  let childResults;
  const { steps } = brain({
    parent: (results) =>
      results.length === 0
        ? delegate([{ title: "Probe", prompt: "probe" }])
        : fauxAssistantMessage(fauxText("done")),
    child: (_prompt, results) => {
      if (results.length === 0) {
        return fauxAssistantMessage(
          probes.map(([name, args], i) => fauxToolCall(name, args, { id: `p${i}` })),
          { stopReason: "toolUse" },
        );
      }
      childResults = results;
      return fauxAssistantMessage(fauxText("nothing allowed"));
    },
  });
  const { harness, conversation } = await open(chat.registry, steps);
  try {
    assert.equal((await (await conversation.submit({ type: "input", content: "go" }, context)).wait(context)).status, "done");
    assert.equal(childResults.length, probes.length);
    for (const result of childResults) assert.equal(result.isError, true, `${result.toolName} ran`);
    assert.equal(save.calls.length + figure.calls.length + raw.calls.length, 0);
    // No approval card was requested from inside the child.
    assert.ok(childResults.every((result) => result.details?.approval === undefined));
    const [delegated] = await toolResults(conversation);
    assert.equal(delegated.details.subagents.tasks[0].status, "done");
  } finally {
    await harness.close(context);
    await chat.close();
  }
});

test("the guard blocks a child's call outside the reads even when its stored agent enables more", async () => {
  const chips = piTool("qdash_list_chips", () => []);
  const save = piTool("qdash_save_flow");
  const chat = chatRegistry([chips, save]);
  const { steps } = brain({
    parent: () => fauxAssistantMessage(fauxText("unused")),
    child: (_prompt, results) =>
      results.length === 0
        ? fauxAssistantMessage(
            [
              fauxToolCall("qdash_save_flow", { title: "x" }, { id: "w1" }),
              fauxToolCall("codemode", { code: "text('ran')" }, { id: "s1" }),
              fauxToolCall("qdash_list_chips", {}, { id: "r1" }),
            ],
            { stopReason: "toolUse" },
          )
        : fauxAssistantMessage(fauxText("ok")),
  });
  const { harness, faux } = await open(chat.registry, steps);
  try {
    const model = faux.getModel();
    // A child whose agent was left with every tool of the chat: only the mark confines it.
    const id = await harness.commit(async (tx) => {
      const created = await tx.createConversation({ ownership: { kind: "ownerless" } });
      const mark = await tx.doc(SubagentDoc, created.id);
      mark.child = true;
      await configure(tx, created.id, {
        model: { provider: model.provider, modelId: model.id },
        instructions: "You are a read-only research subagent (test).",
      });
      return created.id;
    }, context);
    const child = await harness.conversation(id, context);
    assert.equal((await (await child.submit({ type: "input", content: "probe" }, context)).wait(context)).status, "done");
    const byName = Object.fromEntries((await toolResults(child)).map((m) => [m.toolName, m]));
    assert.equal(byName.qdash_save_flow.isError, true);
    assert.match(textOf(byName.qdash_save_flow), new RegExp(subagentBlockMessage("qdash_save_flow").slice(0, 40)));
    assert.equal(byName.codemode.isError, true);
    assert.notEqual(byName.qdash_list_chips.isError, true);
    assert.equal(save.calls.length, 0);
    assert.equal(chips.calls.length, 1);
  } finally {
    await harness.close(context);
    await chat.close();
  }
});

test("a failed child reports its error; when every child fails the call fails", async () => {
  const chips = piTool("qdash_list_chips", () => []);
  const chat = chatRegistry([chips]);
  let tasks = [
    { title: "Fails", prompt: "fail please" },
    { title: "Works", prompt: "work please" },
  ];
  const { steps } = brain({
    parent: (_results, transcript) =>
      transcript.messages.at(-1).role === "user" ? delegate(tasks) : fauxAssistantMessage(fauxText("summary")),
    child: (prompt) =>
      prompt.startsWith("fail")
        ? fauxAssistantMessage([], { stopReason: "error", errorMessage: "provider exploded" })
        : fauxAssistantMessage(fauxText("fine")),
  });
  const { harness, conversation } = await open(chat.registry, steps);
  try {
    await (await conversation.submit({ type: "input", content: "go" }, context)).wait(context);
    const [mixed] = await toolResults(conversation);
    assert.notEqual(mixed.isError, true);
    const [failed, worked] = mixed.details.subagents.tasks;
    assert.equal(failed.status, "error");
    assert.match(failed.error, /not answered: model_error.*provider exploded/);
    assert.equal(worked.status, "done");
    assert.match(textOf(mixed), /1 answered, 1 did not[\s\S]*No answer: not answered: model_error/);

    tasks = [{ title: "Fails", prompt: "fail again" }];
    await (await conversation.submit({ type: "input", content: "again" }, context)).wait(context);
    const all = (await toolResults(conversation)).at(-1);
    assert.equal(all.isError, true);
    assert.equal(all.details.subagents.tasks[0].status, "error");
  } finally {
    await harness.close(context);
    await chat.close();
  }
});

test("stopping the chat aborts its running children and their tools", async () => {
  let aborted = 0;
  const metrics = piTool("qdash_get_chip_metrics", (_params, signal) =>
    new Promise((resolve) => {
      signal?.addEventListener("abort", () => {
        aborted += 1;
        resolve({ aborted: true });
      });
    }),
  );
  const chat = chatRegistry([metrics]);
  const { steps } = brain({
    parent: (results) => (results.length === 0 ? delegate([{ title: "Slow", prompt: "slow" }]) : fauxAssistantMessage(fauxText("x"))),
    child: () =>
      fauxAssistantMessage([fauxToolCall("qdash_get_chip_metrics", {}, { id: "m1" })], { stopReason: "toolUse" }),
  });
  const { harness, conversation } = await open(chat.registry, steps);
  try {
    const submission = await conversation.submit({ type: "input", content: "go" }, context);
    await until(() => metrics.calls.length === 1, "the child's tool");
    assert.equal(runningSubagentCount(), 1);
    await conversation.abort(context);
    const settled = await submission.wait(context);
    assert.equal(settled.status, "unanswered");
    assert.equal(aborted, 1);
    await until(() => runningSubagentCount() === 0, "the child's slot");
    const { tasks } = await harness.inspect(context);
    assert.deepEqual(tasks, []);
  } finally {
    await harness.close(context);
    await chat.close();
  }
});

test(`one call runs at most ${MAX_PARALLEL_SUBAGENTS} children at once and takes at most ${MAX_SUBAGENT_TASKS} tasks`, async () => {
  let running = 0;
  let peak = 0;
  let release;
  const held = new Promise((resolve) => (release = resolve));
  const metrics = piTool("qdash_get_chip_metrics", async () => {
    running += 1;
    peak = Math.max(peak, running);
    await held;
    running -= 1;
    return { ok: true };
  });
  const chat = chatRegistry([metrics]);
  let tasks = Array.from({ length: MAX_SUBAGENT_TASKS }, (_, i) => ({ title: `T${i + 1}`, prompt: `task ${i + 1}` }));
  const { steps } = brain({
    parent: (results, transcript) =>
      results.length === 0 || transcript.messages.at(-1).role === "user"
        ? delegate(tasks)
        : fauxAssistantMessage(fauxText("done")),
    child: (_prompt, results) =>
      results.length === 0
        ? fauxAssistantMessage([fauxToolCall("qdash_get_chip_metrics", {}, { id: "m1" })], { stopReason: "toolUse" })
        : fauxAssistantMessage(fauxText("ok")),
  });
  const { harness, conversation } = await open(chat.registry, steps);
  try {
    const submission = await conversation.submit({ type: "input", content: "go" }, context);
    await until(() => running === MAX_PARALLEL_SUBAGENTS, "the first children");
    await new Promise((resolve) => setTimeout(resolve, 300));
    assert.equal(metrics.calls.length, MAX_PARALLEL_SUBAGENTS);
    release();
    assert.equal((await submission.wait(context)).status, "done");
    assert.equal(peak, MAX_PARALLEL_SUBAGENTS);
    assert.equal(metrics.calls.length, MAX_SUBAGENT_TASKS);
    const [result] = await toolResults(conversation);
    assert.ok(result.details.subagents.tasks.every((task) => task.status === "done"));

    // One task too many is refused before any child starts.
    tasks = Array.from({ length: MAX_SUBAGENT_TASKS + 1 }, (_, i) => ({ title: `T${i}`, prompt: `p${i}` }));
    await (await conversation.submit({ type: "input", content: "more" }, context)).wait(context);
    const refused = (await toolResults(conversation)).at(-1);
    assert.equal(refused.isError, true);
    assert.equal(metrics.calls.length, MAX_SUBAGENT_TASKS);
  } finally {
    release();
    await harness.close(context);
    await chat.close();
  }
});

test("a restart ends a running delegation interrupted and aborts its children instead of rerunning them", async () => {
  const dir = await mkdtemp(join(tmpdir(), "qdash-subagent-"));
  const path = join(dir, "chat.db");
  let started = 0;
  const pending = [];
  const metrics = piTool("qdash_get_chip_metrics", (_params, signal) => {
    started += 1;
    return new Promise((resolve) => {
      pending.push(resolve);
      signal?.addEventListener("abort", () => resolve({ aborted: true }));
    });
  });
  const childStep = () =>
    fauxAssistantMessage([fauxToolCall("qdash_get_chip_metrics", {}, { id: "m1" })], { stopReason: "toolUse" });
  try {
    const firstChat = chatRegistry([metrics]);
    const first = brain({
      parent: () => delegate([{ title: "Long", prompt: "long" }]),
      child: childStep,
    });
    const one = await open(firstChat.registry, first.steps, await openNodeSqliteStorage(path));
    await one.conversation.submit({ type: "input", content: "go" }, context);
    await until(() => started === 1, "the child's tool");
    // The runtime dies while the child runs.
    await one.harness.close(context);
    await firstChat.close();
    for (const resolve of pending) resolve({ late: true });

    const secondChat = chatRegistry([metrics]);
    const second = brain({
      parent: () => fauxAssistantMessage(fauxText("The research was interrupted.")),
      child: childStep,
    });
    const two = await open(secondChat.registry, second.steps, await openNodeSqliteStorage(path));
    try {
      await until(async () => (await toolResults(two.conversation)).length === 1, "the interrupted result");
      const [result] = await toolResults(two.conversation);
      assert.equal(result.toolName, SUBAGENT_TOOL);
      assert.equal(result.isError, true);
      await until(async () => (await two.harness.inspect(context)).tasks.length === 0, "no live work");
      // The child gave no answer after the restart: its read, which may start once more as the store
      // recovers, is aborted with it, and the chat shows no task as still running.
      assert.ok(started <= 2);
      assert.ok(second.transcripts.every((t) => !JSON.stringify(t.messages).includes("research subagent")));
      const [end] = toNdjsonEvents({ type: "tool_execution_end", toolName: SUBAGENT_TOOL, toolCallId: "d1", isError: true, entry: { model: [result] } });
      for (const task of end.subagents ?? []) assert.notEqual(task.status, "running");
      assert.equal(runningSubagentCount(), 0);
    } finally {
      await two.harness.close(context);
      await secondChat.close();
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("running details stream as tool_update once per change, and a replay shows the same tasks", () => {
  const user = { id: 1, kind: "pi.user", model: [{ role: "user", content: "hi" }] };
  const running = (tasks) => ({
    entries: [user],
    docs: { "pi.live": { run: { taskId: 7, inputs: [1], turns: 1 }, tools: [{ callId: "d1", name: SUBAGENT_TOOL, status: "running", taskId: 9, details: { subagents: { tasks } } }] } },
  });
  const queued = [{ id: "1", title: "A", status: "queued", toolCalls: 0 }];
  const busy = [{ id: "1", title: "A", status: "running", toolCalls: 2, activity: "qdash_list_chips", startedAt: 5 }];
  const lines = (translator, view) => translator.advance(view).flatMap((event) => toNdjsonEvents(event));

  const live = new ViewEventTranslator({ entries: [user], docs: {} });
  assert.deepEqual(lines(live, running(queued)), [
    { type: "tool_start", name: SUBAGENT_TOOL, id: "d1" },
    { type: "tool_update", name: SUBAGENT_TOOL, id: "d1", subagents: queued },
  ]);
  assert.deepEqual(lines(live, running(queued)), []);
  assert.deepEqual(lines(live, running(busy)), [{ type: "tool_update", name: SUBAGENT_TOOL, id: "d1", subagents: busy }]);

  // A stream that reattaches after a restart starts empty and gets the latest state at once.
  const replay = new ViewEventTranslator({ entries: [], docs: {}, before: 1 });
  assert.deepEqual(lines(replay, running(busy)).at(-1), { type: "tool_update", name: SUBAGENT_TOOL, id: "d1", subagents: busy });

  // The result ends the call with its final tasks; a task its result still shows running was cut off.
  const done = { id: "1", title: "A", status: "done", toolCalls: 2, result: "ok", startedAt: 5, endedAt: 9 };
  const result = {
    id: 3,
    kind: "pi.toolResult",
    model: [{ role: "toolResult", toolCallId: "d1", toolName: SUBAGENT_TOOL, isError: false, content: [], details: { subagents: { tasks: [done, busy[0]].map((t, i) => ({ ...t, id: String(i + 1) })) } } }],
  };
  const end = lines(live, { entries: [user, result], docs: {} }).find((event) => event.type === "tool_end");
  assert.deepEqual(end.subagents.map((task) => task.status), ["done", "interrupted"]);
  assert.equal(end.subagents[1].activity, undefined);
});

test("subagent details are sanitized and bounded before they leave the runtime", () => {
  assert.equal(subagentsFromDetails({ other: 1 }), undefined);
  assert.equal(subagentsFromDetails({ subagents: { tasks: [{ id: "1", title: "x", status: "bogus" }] } }), undefined);
  const [task] = subagentsFromDetails({
    subagents: {
      tasks: [{ id: "1", title: "t".repeat(500), status: "done", toolCalls: 2.7, result: "r".repeat(10_000), token: "secret", error: 5 }],
    },
  });
  assert.equal(task.title.length, 81);
  assert.ok(task.result.length <= 4_001);
  assert.equal(task.toolCalls, 2);
  assert.equal(task.token, undefined);
  assert.equal(task.error, undefined);
  assert.equal(subagentsFromDetails({ subagents: { tasks: Array.from({ length: 9 }, (_, i) => ({ id: String(i), title: "t", status: "done" })) } }).length, MAX_SUBAGENT_TASKS);
});


test("timeout configuration rejects invalid and nonpositive values in a fresh process", () => {
  for (const value of ["invalid", "0", "-1", "Infinity", ""]) {
    const output = execFileSync(process.execPath, ["--eval", "import { SUBAGENT_TIMEOUT_MS } from './src/subagent-tool.ts'; console.log(SUBAGENT_TIMEOUT_MS)"], {
      cwd: new URL("..", import.meta.url),
      env: { ...process.env, AGENT_SUBAGENT_TIMEOUT_MS: value },
      encoding: "utf8",
    });
    assert.equal(output.trim(), "300000", value);
  }
});

test("concurrent chats share six slots, cancel queued work, and reuse every slot", async () => {
  let release;
  const held = new Promise((resolve) => (release = resolve));
  const metrics = piTool("qdash_get_chip_metrics", async () => { await held; return {}; });
  const opened = [];
  try {
    for (let i = 0; i < 4; i++) {
      const chat = chatRegistry([metrics]);
      const { steps } = brain({
        parent: (results) => results.length ? fauxAssistantMessage(fauxText("done")) : delegate(Array.from({ length: 3 }, (_, j) => ({ title: `T${j}`, prompt: "read" }))),
        child: (_prompt, results) => results.length ? fauxAssistantMessage(fauxText("ok")) : fauxAssistantMessage([fauxToolCall("qdash_get_chip_metrics", {}, { id: "m1" })], { stopReason: "toolUse" }),
      });
      const item = { chat, ...await open(chat.registry, steps) };
      opened.push(item);
      item.submission = await item.conversation.submit({ type: "input", content: "go" }, context);
      if (i < 2) await until(() => metrics.calls.length === (i + 1) * 3, "occupied slots");
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(metrics.calls.length, 6);
    assert.equal(runningSubagentCount(), 6);
    await opened[2].conversation.abort(context);
    await opened[2].submission.wait(context);
    release();
    for (const item of opened) await item.submission.wait(context);
    assert.equal(metrics.calls.length, 9);
    assert.equal(runningSubagentCount(), 0);
  } finally {
    release();
    for (const item of opened) { await item.harness.close(context); await item.chat.close(); }
  }
});
