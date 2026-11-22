import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  createRegistry,
  defineExtension,
  defineTool,
  Harness,
  MemoryStorage,
  ToolResultEntry,
} from "@earendil-works/pi-durable";
import { createCodemodeExtension } from "@earendil-works/pi-durable/codemode";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { Type } from "typebox";

import {
  DEFERRED_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
  isNestedReadTool,
} from "../src/allowed-tools.ts";
import {
  buildCodemodeExtensions,
  CODEMODE_TOOL_NAME,
  createCodemodeSandbox,
  DEFAULT_SCRIPT_TIMEOUT_MS,
  MAX_NESTED_DATA_BYTES,
  MAX_SCRIPT_TIMEOUT_MS,
  runningScriptCount,
  TOOL_SEARCH_TOOL_NAME,
  toolPolicyExtension,
  withScriptDeadline,
} from "../src/codemode.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";
import { QDASH_TOOL_NAMESPACE } from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";
import { buildPresentationTools, PRESENT_TOOL, PRESENTATION_INTERNAL_CALLS } from "../src/presentation-tool.ts";
import { nestedCallSummary, toNdjsonEvents } from "../src/events.ts";
import { pendingApproval } from "../src/runtime.ts";

const context = BACKGROUND_CONTEXT;
const connection = { toolArgs: { profile: "runtime", configPath: "/private/config.ini", useEnv: false } };
const modelRuntime = { getModel: () => undefined };

const CHIPS = [
  { chip_id: "A", qubits: 16 },
  { chip_id: "B", qubits: 64 },
];
const T1 = { A: 30, B: 80 };

/** A pi-qdash-style tool: JSON text for the model, the data in `details.data`; records its calls. */
function piTool(name, respond = () => ({ ok: true })) {
  const calls = [];
  return {
    calls,
    registered: {
      definition: {
        name,
        label: name,
        description: `${name} (test)`,
        parameters: Type.Object({ chipId: Type.Optional(Type.String()), title: Type.Optional(Type.String()) }),
        execute: async (_id, params) => {
          calls.push(params);
          const data = respond(params);
          return { content: [{ type: "text", text: JSON.stringify(data) }], details: { data } };
        },
      },
    },
  };
}

function piExtension(tools, path) {
  return { ...(path ? { path } : {}), tools: new Map(tools.map((tool) => [tool.registered.definition.name, tool.registered])) };
}

/** Tool names offered in the request the faux model received: the transcript's tool additions and removals. */
function offeredTools(transcript) {
  const tools = new Set();
  for (const message of transcript.messages) {
    if (message.role !== "system") continue;
    for (const tool of message.toolsRemoved ?? []) tools.delete(tool.name);
    for (const tool of message.toolsAdded ?? []) tools.add(tool.name);
  }
  return tools;
}

/** A Harness with the chat's QDash tools, Code Mode, tool_search, and the tool policy. */
async function openChat({ piExtensions, responses, storage = new MemoryStorage(), faux, extraTools = [], internalCalls }) {
  faux ??= fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const qdash = buildQDashExtension(
    piExtensions,
    modelRuntime,
    "/tmp/work",
    connection,
    ["/app/packages/local"],
    [],
  );
  const sandbox = createCodemodeSandbox();
  const registry = createRegistry();
  registry.install(qdash.extension);
  if (extraTools.length) registry.install(defineExtension({ name: "extra", tools: extraTools }));
  for (const extension of buildCodemodeExtensions(sandbox, { ...qdash, internalCalls })) registry.install(extension);
  if (responses) faux.setResponses(responses);
  const harness = await Harness.open(storage, { models, registry, settings: { retry: { enabled: false } } }, context);
  const agent = { model: { provider: model.provider, modelId: model.id } };
  const conversation = await harness.root(context, { agent });
  // As `openSession` does on every open: it must not reset loaded tools.
  await conversation.configure(agent, context);
  harness.resume();
  return {
    faux,
    harness,
    conversation,
    qdash,
    storage,
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

/** The tool results of the conversation, by tool name, as the model received them. */
async function results(conversation) {
  const view = await conversation.context(context);
  return view.entries
    .filter((entry) => ToolResultEntry.is(entry))
    .map((entry) => entry.model[0]);
}

const resultText = (message) => message.content.map((block) => block.text ?? "").join("");

test("a script batches and filters read-only QDash data; only its output reaches the model", async () => {
  const chips = piTool("qdash_list_chips", () => CHIPS);
  const metrics = piTool("qdash_get_chip_metrics", (params) => ({ chip_id: params.chipId, t1_us: T1[params.chipId] }));
  let followUp;
  const code = [
    "const chips = await tools.qdash_list_chips({});",
    "const all = await Promise.all(chips.map((chip) => tools.qdash_get_chip_metrics({ chipId: chip.chip_id })));",
    "text(all.filter((m) => m.t1_us > 50).map((m) => `${m.chip_id}: ${m.t1_us} us`).join('\\n'));",
  ].join("\n");
  const chat = await openChat({
    piExtensions: [piExtension([chips, metrics])],
    responses: [
      fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" })], { stopReason: "toolUse" }),
      (transcript) => {
        followUp = transcript;
        return fauxAssistantMessage(fauxText("Chip B has T1 above 50 us."));
      },
    ],
  });
  try {
    const settled = await ask(chat.conversation, "Which chips have T1 above 50 us?");
    assert.equal(settled.status, "done");

    // The tools ran in this process with the runtime's connection, never with script-supplied credentials.
    assert.equal(chips.calls.length, 1);
    assert.deepEqual(
      metrics.calls.map((call) => call.chipId).sort(),
      ["A", "B"],
    );
    for (const call of [...chips.calls, ...metrics.calls]) {
      assert.equal(call.profile, "runtime");
      assert.equal(call.configPath, "/private/config.ini");
      assert.equal("confirmWrite" in call, false);
    }

    const [script] = await results(chat.conversation);
    assert.equal(script.toolName, CODEMODE_TOOL_NAME);
    assert.equal(script.isError, false);
    assert.match(resultText(script), /B: 80 us/);
    assert.doesNotMatch(resultText(script), /A: 30 us/);
    assert.deepEqual(
      script.details.calls.map((call) => [call.name, call.status]),
      [
        ["qdash_list_chips", "ok"],
        ["qdash_get_chip_metrics", "ok"],
        ["qdash_get_chip_metrics", "ok"],
      ],
    );
    // The model's next request holds the script's output, not the nested results.
    const toolMessages = followUp.messages.filter((message) => message.role === "toolResult");
    assert.deepEqual(toolMessages.map((message) => message.toolName), [CODEMODE_TOOL_NAME]);

    // The chat stream shows the output and the calls the script made.
    const end = toNdjsonEvents({
      type: "tool_execution_end",
      toolName: CODEMODE_TOOL_NAME,
      toolCallId: "s1",
      entry: { model: [script] },
    }).find((event) => event.type === "tool_end");
    assert.match(end.output, /B: 80 us/);
    assert.match(end.output, /Tool calls: 3\n/);
    assert.match(end.output, /ok\s+qdash_get_chip_metrics/);
  } finally {
    await chat.close();
  }
  // A worker is released once it exits, which can be after its result settled.
  for (let i = 0; i < 100 && runningScriptCount() > 0; i++) await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(runningScriptCount(), 0);
});

test("write tools and unaudited tools cannot run from a script; the direct approval path stays", async () => {
  const post = piTool("qdash_create_forum_post");
  const save = piTool("qdash_save_flow");
  const chips = piTool("qdash_list_chips", () => CHIPS);
  // A trusted root's replacement of an audited name is not audited.
  const local = piTool("qdash_get_chip_metrics", () => ({ t1_us: 1 }));
  let rogueRuns = 0;
  const rogue = defineTool({
    name: "rogue_side_effect",
    description: "A tool that states no callers",
    parameters: Type.Object({}),
    execute: async () => {
      rogueRuns += 1;
      return { output: [{ type: "text", text: "ran" }] };
    },
  });
  // Without `modelOnlyTools`, so only the policy hook stands between it and a script.
  const unrestricted = defineExtension({ name: "unrestricted", tools: [{ ...rogue, callers: ["model", "tools"] }] });
  const code = [
    "const outcomes = [];",
    "for (const name of ['qdash_create_forum_post', 'qdash_save_flow', 'qdash_get_chip_metrics', 'rogue_side_effect', 'qdash_list_chips']) {",
    "  try { const fn = tools[name]; if (!fn) { outcomes.push(name + ': absent'); continue; }",
    "    await fn({ title: 'x' }); outcomes.push(name + ': ran'); }",
    "  catch (error) { outcomes.push(name + ': ' + error.message); }",
    "}",
    "text(outcomes.join('\\n'));",
  ].join("\n");
  const chat = await openChat({
    piExtensions: [piExtension([post, save, chips]), piExtension([local], "/app/packages/local/index.ts")],
    responses: [
      fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxToolCall("qdash_save_flow", { title: "flow" }, { id: "w1" })], {
        stopReason: "toolUse",
      }),
      fauxAssistantMessage(fauxText("never")),
    ],
  });
  try {
    const settled = await ask(chat.conversation, "post it");
    assert.equal(settled.status, "done");
    const [script, write] = await results(chat.conversation);
    const output = resultText(script);
    // Model-only tools are not in a script's `tools` at all.
    assert.match(output, /qdash_create_forum_post: tools.qdash_create_forum_post does not exist/);
    assert.match(output, /qdash_save_flow: tools.qdash_save_flow does not exist/);
    assert.match(output, /qdash_get_chip_metrics: tools.qdash_get_chip_metrics does not exist/);
    assert.match(output, /qdash_list_chips: ran/);
    assert.equal(post.calls.length, 0);
    assert.equal(save.calls.length, 0);
    assert.equal(local.calls.length, 0);
    // The script left no approval behind: only the model's own write call asks the user.
    const approvals = (await results(chat.conversation)).filter((message) => message.details?.approval);
    assert.deepEqual(approvals.map((message) => message.toolCallId), ["w1"]);

    // The model's own call to a write tool still asks the user, with the exact arguments.
    assert.equal(write.toolName, "qdash_save_flow");
    assert.deepEqual(write.details.approval, { id: "w1", tool: "qdash_save_flow", label: "qdash_save_flow", args: { title: "flow" }, model: { provider: "faux", modelId: "faux-1" } });
    assert.deepEqual(await pendingApproval(chat.conversation, "w1"), write.details.approval);
    assert.equal(save.calls.length, 0);
  } finally {
    await chat.close();
  }

  // A tool that lets scripts call it, outside the audited set: scripts are not
  // given it, and with Code Mode unfiltered the policy hook still blocks it.
  const runRogue = async (codemodeExtensions) => {
    const faux = fauxProvider({ tokensPerSecond: 0 });
    const models = createModels();
    models.setProvider(faux.provider);
    const model = faux.getModel();
    const qdash = buildQDashExtension([piExtension([chips])], modelRuntime, "/tmp/work", connection, [], []);
    const sandbox = createCodemodeSandbox();
    const registry = createRegistry();
    registry.install(qdash.extension);
    registry.install(unrestricted);
    for (const extension of codemodeExtensions(sandbox, qdash)) registry.install(extension);
    faux.setResponses([
      fauxAssistantMessage(
        [
          fauxToolCall(
            CODEMODE_TOOL_NAME,
            { code: "try { await tools.rogue_side_effect({}); text('ran'); } catch (e) { text('blocked: ' + e.message); }" },
            { id: "s3" },
          ),
        ],
        { stopReason: "toolUse" },
      ),
      fauxAssistantMessage(fauxText("ok")),
    ]);
    const harness = await Harness.open(new MemoryStorage(), { models, registry }, context);
    const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
    harness.resume();
    try {
      assert.equal((await ask(conversation, "go")).status, "done");
      const [script] = await results(conversation);
      return script;
    } finally {
      await harness.close(context);
      await sandbox.close();
    }
  };
  const filtered = await runRogue(buildCodemodeExtensions);
  assert.match(resultText(filtered), /blocked: tools.rogue_side_effect does not exist/);
  const unfiltered = await runRogue((sandbox, qdash) => [
    createCodemodeExtension({ sandbox, models: false }),
    toolPolicyExtension(qdash),
  ]);
  assert.match(resultText(unfiltered), /blocked: rogue_side_effect cannot be called from a code mode script/);
  assert.equal(unfiltered.details.calls[0].status, "error");
  assert.equal(rogueRuns, 0);
});

test("deferred tools load through tool_search and stay offered on the branch", async () => {
  const chips = piTool("qdash_list_chips", () => CHIPS);
  const cryostats = piTool("qdash_list_cryostats", () => [{ name: "fridge-1" }]);
  const seen = [];
  const record = (step) => (transcript) => {
    seen.push(offeredTools(transcript));
    return step;
  };
  const dir = mkdtempSync(join(tmpdir(), "qdash-deferred-"));
  const path = join(dir, "session.sqlite");
  const chat = await openChat({
    storage: await openNodeSqliteStorage(path),
    piExtensions: [piExtension([chips, cryostats])],
    responses: [
      record(
        fauxAssistantMessage([fauxToolCall(TOOL_SEARCH_TOOL_NAME, { query: "cryostats" }, { id: "t1" })], {
          stopReason: "toolUse",
        }),
      ),
      record(
        fauxAssistantMessage([fauxToolCall("qdash_list_cryostats", {}, { id: "c1" })], { stopReason: "toolUse" }),
      ),
      record(fauxAssistantMessage(fauxText("fridge-1"))),
      record(fauxAssistantMessage(fauxText("still loaded"))),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "Which cryostats exist?")).status, "done");
    assert.equal(seen[0].has("qdash_list_chips"), true);
    assert.equal(seen[0].has("qdash_list_cryostats"), false);
    assert.equal(seen[0].has(TOOL_SEARCH_TOOL_NAME), true);
    assert.equal(seen[1].has("qdash_list_cryostats"), true);
    const [search, listed] = await results(chat.conversation);
    assert.deepEqual(search.details, { loaded: ["qdash_list_cryostats"] });
    assert.equal(listed.isError, false);
    assert.equal(cryostats.calls.length, 1);

    // A later turn of the same conversation is still offered the loaded tool.
    assert.equal((await ask(chat.conversation, "again")).status, "done");
    assert.equal(seen[3].has("qdash_list_cryostats"), true);
  } finally {
    await chat.close();
  }

  // So is the conversation reopened from its storage, as the next chat request opens it.
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const reopened = await openChat({
    storage: await openNodeSqliteStorage(path),
    faux,
    piExtensions: [piExtension([chips, cryostats])],
    responses: [
      (transcript) => {
        seen.push(offeredTools(transcript));
        return fauxAssistantMessage(fauxText("reopened"));
      },
    ],
  });
  try {
    assert.equal((await ask(reopened.conversation, "after restart")).status, "done");
    assert.equal(seen[4].has("qdash_list_cryostats"), true);
  } finally {
    await reopened.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a deferred tool called by name before loading is loaded for the retry", async () => {
  const cooldowns = piTool("qdash_list_cooldowns", () => [{ id: "cd1" }]);
  const seen = [];
  const chat = await openChat({
    piExtensions: [piExtension([cooldowns])],
    responses: [
      fauxAssistantMessage([fauxToolCall("qdash_list_cooldowns", {}, { id: "c1" })], { stopReason: "toolUse" }),
      (transcript) => {
        seen.push(offeredTools(transcript));
        return fauxAssistantMessage([fauxToolCall("qdash_list_cooldowns", {}, { id: "c2" })], { stopReason: "toolUse" });
      },
      fauxAssistantMessage(fauxText("cd1")),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "cooldowns?")).status, "done");
    const [first, second] = await results(chat.conversation);
    assert.equal(first.isError, true);
    assert.match(resultText(first), /not loaded yet, so it did not run\. It is loaded now/);
    assert.equal(seen[0].has("qdash_list_cooldowns"), true);
    assert.equal(second.isError, false);
    assert.equal(cooldowns.calls.length, 1);
  } finally {
    await chat.close();
  }
});

test("a script can call a deferred read tool without loading it, and a failing call is reported", async () => {
  const cryostats = piTool("qdash_list_cryostats", () => {
    throw new Error("QDash answered 503");
  });
  const code = [
    "text(JSON.stringify(await searchTools('cryostat')));",
    "await tools.qdash_list_cryostats({});",
  ].join("\n");
  const chat = await openChat({
    piExtensions: [piExtension([cryostats])],
    responses: [
      fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("QDash is unavailable.")),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "cryostats")).status, "done");
    const [script] = await results(chat.conversation);
    assert.equal(script.isError, true);
    assert.match(resultText(script), /qdash_list_cryostats/);
    assert.match(resultText(script), /QDash answered 503/);
    assert.equal(cryostats.calls.length, 1);
    assert.deepEqual(
      script.details.calls.map((call) => [call.name, call.status]),
      [["qdash_list_cryostats", "error"]],
    );
    const summary = nestedCallSummary(script.details);
    assert.match(summary, /Tool calls: 1, 1 failed/);
    assert.match(summary, /error\s+qdash_list_cryostats \(\d+ ms\): .*QDash answered 503/);
  } finally {
    await chat.close();
  }
});

test("tool policy lists: nested tools are reviewed reads, deferred tools are reviewed", () => {
  const writes = new Set(REVIEWED_WRITE_TOOL_NAMES);
  for (const name of NESTED_READ_TOOL_NAMES) assert.equal(writes.has(name), false, name);
  assert.equal(new Set(DEFERRED_TOOL_NAMES).size, DEFERRED_TOOL_NAMES.length);
  // Image and local-file tools stay out of scripts.
  for (const name of ["qdash_get_figure", "qdash_inspect_timeseries_csv", "qdash_wait_execution"]) {
    assert.equal(isNestedReadTool(name), false, name);
  }
});

test("a script's deadline is bounded", () => {
  assert.equal(withScriptDeadline("text(1)"), `// @options: {"timeout_ms":${DEFAULT_SCRIPT_TIMEOUT_MS}}\ntext(1)`);
  assert.equal(
    withScriptDeadline('// @options: {"max_output_tokens": 500}\ntext(1)'),
    `// @options: {"max_output_tokens":500,"timeout_ms":${DEFAULT_SCRIPT_TIMEOUT_MS}}\ntext(1)`,
  );
  assert.equal(
    withScriptDeadline('// @options: {"timeout_ms": 999999999}\ntext(1)'),
    `// @options: {"timeout_ms":${MAX_SCRIPT_TIMEOUT_MS}}\ntext(1)`,
  );
  assert.equal(withScriptDeadline("// @options: {bad\ntext(1)"), "// @options: {bad\ntext(1)");
  // A value Code Mode rejects is left for it to report, not replaced by the default.
  for (const value of ['"60000"', "0", "-5", "1.5", "null", "2147483648"]) {
    const source = `// @options: {"timeout_ms": ${value}}\ntext(1)`;
    assert.equal(withScriptDeadline(source), source, value);
  }
  assert.equal(
    withScriptDeadline('// @options: {"timeout_ms": 5000}\ntext(1)'),
    '// @options: {"timeout_ms":5000}\ntext(1)',
  );
});

test("Code Mode reports an invalid timeout_ms as the SDK words it", async () => {
  const chat = await openChat({
    piExtensions: [],
    responses: [
      fauxAssistantMessage(
        [fauxToolCall(CODEMODE_TOOL_NAME, { code: '// @options: {"timeout_ms": 0}\ntext(1)' }, { id: "s1" })],
        { stopReason: "toolUse" },
      ),
      fauxAssistantMessage(fauxText("ok")),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "go")).status, "done");
    const [script] = await results(chat.conversation);
    assert.equal(script.isError, true);
    assert.match(resultText(script), /timeout_ms` must be a positive integer/);
  } finally {
    await chat.close();
  }
});

test("a nested call returning too much data fails with advice to narrow the request", async () => {
  const big = "x".repeat(MAX_NESTED_DATA_BYTES);
  const results_ = piTool("qdash_list_task_results", () => [{ id: 1, note: big }]);
  const chips = piTool("qdash_list_chips", () => CHIPS);
  const code = [
    "let message = 'none';",
    "try { await tools.qdash_list_task_results({}); } catch (error) { message = error.message; }",
    "const chips = await tools.qdash_list_chips({});",
    "text(message + '\\n' + chips.length + ' chips');",
  ].join("\n");
  const chat = await openChat({
    piExtensions: [piExtension([results_, chips])],
    responses: [
      fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("Narrowing.")),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "all results")).status, "done");
    const [script] = await results(chat.conversation);
    const output = resultText(script);
    assert.match(output, /qdash_list_task_results returned \d+ bytes of data, more than the 524288 bytes/);
    assert.match(output, /Narrow the request/);
    assert.match(output, /2 chips/);
    assert.deepEqual(
      script.details.calls.map((call) => [call.name, call.status]),
      [
        ["qdash_list_task_results", "error"],
        ["qdash_list_chips", "ok"],
      ],
    );
    // The read ran once; only its oversized result was kept from the script and the journal.
    assert.equal(results_.calls.length, 1);
  } finally {
    await chat.close();
  }
});

test("a deferred tool rescued by a direct call stays loaded after the session is reopened", async () => {
  const cooldowns = piTool("qdash_list_cooldowns", () => [{ id: "cd1" }]);
  const dir = mkdtempSync(join(tmpdir(), "qdash-rescue-"));
  const path = join(dir, "session.sqlite");
  const seen = [];
  const chat = await openChat({
    storage: await openNodeSqliteStorage(path),
    piExtensions: [piExtension([cooldowns])],
    responses: [
      (transcript) => {
        seen.push(offeredTools(transcript));
        return fauxAssistantMessage([fauxToolCall("qdash_list_cooldowns", {}, { id: "c1" })], { stopReason: "toolUse" });
      },
      fauxAssistantMessage(fauxText("Loaded; will retry.")),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "cooldowns?")).status, "done");
    assert.equal(seen[0].has("qdash_list_cooldowns"), false);
    const [first] = await results(chat.conversation);
    assert.equal(first.isError, true);
    assert.match(resultText(first), /It is loaded now/);
    assert.equal(cooldowns.calls.length, 0);
  } finally {
    await chat.close();
  }
  const reopened = await openChat({
    storage: await openNodeSqliteStorage(path),
    piExtensions: [piExtension([cooldowns])],
    responses: [
      (transcript) => {
        seen.push(offeredTools(transcript));
        return fauxAssistantMessage([fauxToolCall("qdash_list_cooldowns", {}, { id: "c2" })], { stopReason: "toolUse" });
      },
      fauxAssistantMessage(fauxText("cd1")),
    ],
  });
  try {
    assert.equal((await ask(reopened.conversation, "again")).status, "done");
    assert.equal(seen[1].has("qdash_list_cooldowns"), true);
    const second = (await results(reopened.conversation)).at(-1);
    assert.equal(second.isError, false);
    assert.equal(cooldowns.calls.length, 1);
  } finally {
    await reopened.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("present_results accepts a deferred read a script called, before and after it is loaded", async () => {
  const compare = piTool("qdash_compare_executions", () => ({ a: { t1_us: 30 }, b: { t1_us: 80 } }));
  const forum = piTool("qdash_create_forum_post", () => ({ id: "p1" }));
  // No classifier model in the catalog: present_results falls back, but only after its sources passed.
  const presentation = buildPresentationTools({
    provider: "missing",
    name: "missing",
    minProbability: 0.6,
    minMargin: 0.2,
    timeoutMs: 1000,
  });
  const present = (sources, id) =>
    fauxAssistantMessage(
      [
        fauxToolCall(
          PRESENT_TOOL,
          {
            request: "compare the two executions",
            sources,
            records: [
              { subject: "a", values: [{ name: "t1", value: 30 }] },
              { subject: "b", values: [{ name: "t1", value: 80 }] },
            ],
          },
          { id },
        ),
      ],
      { stopReason: "toolUse" },
    );
  const seen = [];
  const chat = await openChat({
    piExtensions: [piExtension([compare, forum])],
    extraTools: [...presentation],
    internalCalls: PRESENTATION_INTERNAL_CALLS,
    responses: [
      fauxAssistantMessage(
        [fauxToolCall(CODEMODE_TOOL_NAME, { code: "text(JSON.stringify(await tools.qdash_compare_executions({})));" }, { id: "s1" })],
        { stopReason: "toolUse" },
      ),
      (transcript) => {
        seen.push(offeredTools(transcript));
        return present(["qdash_compare_executions"], "p1");
      },
      // A deferred write tool is no data source, loaded or not.
      present(["qdash_create_forum_post"], "p2"),
      fauxAssistantMessage([fauxToolCall(TOOL_SEARCH_TOOL_NAME, { query: "compare executions" }, { id: "t1" })], {
        stopReason: "toolUse",
      }),
      (transcript) => {
        seen.push(offeredTools(transcript));
        return present(["qdash_compare_executions"], "p3");
      },
      fauxAssistantMessage(fauxText("Compared.")),
    ],
  });
  try {
    assert.equal((await ask(chat.conversation, "compare")).status, "done");
    const byId = new Map((await results(chat.conversation)).map((message) => [message.toolCallId, message]));
    assert.equal(byId.get("s1").isError, false);
    assert.equal(compare.calls.length, 1);
    // Before loading: offered to the model it is not, yet the script read it.
    assert.equal(seen[0].has("qdash_compare_executions"), false);
    assert.equal(byId.get("p1").isError, false, resultText(byId.get("p1")));
    assert.equal(byId.get("p1").details.presentation.outcome, "fallback");
    assert.equal(byId.get("p2").isError, true);
    assert.match(resultText(byId.get("p2")), /not data tools here: qdash_create_forum_post/);
    assert.deepEqual(byId.get("t1").details.loaded.includes("qdash_compare_executions"), true);
    // After loading it is offered, and still accepted.
    assert.equal(seen[1].has("qdash_compare_executions"), true);
    assert.equal(byId.get("p3").isError, false, resultText(byId.get("p3")));
  } finally {
    await chat.close();
  }
});

test("QDash tools form the qdash code mode namespace, limited to what scripts may call", async () => {
  const chips = piTool("qdash_list_chips", () => CHIPS);
  const metrics = piTool("qdash_get_chip_metrics", (params) => ({ chip_id: params.chipId }));
  const save = piTool("qdash_save_flow");
  const code = [
    "const ns = await describeNamespace('qdash');",
    "const found = await searchTools('chips', { namespace: 'qdash' });",
    "text(JSON.stringify({ ns, found: found.map((tool) => tool.name ?? tool) }));",
  ].join("\n");
  let section;
  const chat = await openChat({
    piExtensions: [piExtension([chips, metrics, save])],
    responses: [
      (transcript) => {
        section = transcript.messages.find((message) => message.role === "system" && message.sections?.codemode)?.sections.codemode;
        return fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" })], { stopReason: "toolUse" });
      },
      fauxAssistantMessage(fauxText("ok")),
    ],
  });
  try {
    assert.equal(chat.qdash.extension.namespace, QDASH_TOOL_NAMESPACE);
    assert.equal((await ask(chat.conversation, "which tools?")).status, "done");

    // The prompt lists the namespace once, with its one-line description, above the script tools.
    assert.ok(section.includes(`## qdash\n${QDASH_TOOL_NAMESPACE.description}\n`), section);
    assert.ok(section.indexOf("## qdash") < section.indexOf("qdash_list_chips"));
    assert.match(section, /qdash_get_chip_metrics/);
    // Instructions are only for describeNamespace(); write tools stay out of the listing.
    assert.doesNotMatch(section, /audited read-only tools/);
    assert.doesNotMatch(section, /qdash_save_flow/);

    const [script] = await results(chat.conversation);
    assert.equal(script.isError, false, resultText(script));
    const { ns, found } = JSON.parse(resultText(script).slice(resultText(script).indexOf("{")));
    assert.equal(ns.name, "qdash");
    assert.equal(ns.instructions, QDASH_TOOL_NAMESPACE.instructions);
    assert.deepEqual([...ns.tools].sort(), ["qdash_get_chip_metrics", "qdash_list_chips"]);
    assert.ok(found.includes("qdash_list_chips"), JSON.stringify(found));
    assert.ok(!found.includes("qdash_save_flow"));
  } finally {
    await chat.close();
  }
});
