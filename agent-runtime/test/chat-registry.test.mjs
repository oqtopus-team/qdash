import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createProvider, fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, defineExtension, defineTool, Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";
import { createCodemodeExtension } from "@earendil-works/pi-durable/codemode";
import { Type } from "typebox";

import { askUserTool } from "../src/ask-tool.ts";
import { chartTool } from "../src/chart-tool.ts";
import { buildChatRegistry, buildCopilotExtension } from "../src/chat-registry.ts";
import {
  CODEMODE_TOOL_NAME,
  createCodemodeSandbox,
  MAX_CONCURRENT_SCRIPTS,
  runningScriptCount,
  toolPolicyExtension,
} from "../src/codemode.ts";
import {
  buildPresentationTools,
  CLASSIFY_TOOL,
  PRESENT_TOOL,
  PRESENTATION_INTERNAL_CALLS,
} from "../src/presentation-tool.ts";
import { uiTool } from "../src/ui-tool.ts";

const context = BACKGROUND_CONTEXT;
const connection = { toolArgs: { profile: "runtime", configPath: "/private/config.ini", useEnv: false } };
const modelRuntime = { getModel: () => undefined };
const LOCAL = "/app/extensions/local";

const presentationConfig = {
  provider: "test-classifier",
  name: "jev",
  minProbability: 0.6,
  minMargin: 0.2,
  timeoutMs: 2_000,
};
const failureList = {
  stopReason: "stop",
  answers: {
    category: {
      type: "choice",
      choice: "failure_list",
      probabilities: { calibration_summary: 0.05, execution_comparison: 0.05, failure_list: 0.85, text: 0.05 },
      confidence: 0.85,
    },
  },
};
const presentArgs = {
  request: "Which qubits failed?",
  sources: ["qdash_list_chips"],
  records: [{ subject: "Q04", status: "failed", message: "fit did not converge", values: [{ name: "t1", value: 38.5, unit: "us" }] }],
};

function classifierProvider(classify) {
  return createProvider({
    id: "test-classifier",
    auth: { apiKey: { name: "test", resolve: async () => ({ auth: { apiKey: "k" } }) } },
    models: [
      {
        type: "classifier",
        id: "jev",
        name: "Jev",
        api: "mock-classify",
        provider: "test-classifier",
        baseUrl: "http://classifier.invalid",
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 32768,
      },
    ],
    classifiers: { "mock-classify": { classify } },
  });
}

/** A pi-qdash-style tool that records its calls. */
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

const piExtension = (tools, path) => ({
  ...(path ? { path } : {}),
  tools: new Map(tools.map((tool) => [tool.registered.definition.name, tool.registered])),
});

/** Models with the faux chat model and a classifier that records its calls. */
function chatModels(classify) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const classifierCalls = [];
  models.setProvider(
    classifierProvider(async (model, ctx) => {
      classifierCalls.push(ctx);
      return classify(model, ctx);
    }),
  );
  return { faux, models, classifierCalls, model: faux.getModel() };
}

async function open(registry, models, model) {
  const harness = await Harness.open(new MemoryStorage(), { models, registry, settings: { retry: { enabled: false } } }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return { harness, conversation };
}

async function ask(conversation, content) {
  const submission = await conversation.submit({ type: "input", content }, context);
  return submission.wait(context);
}

async function results(conversation) {
  const view = await conversation.context(context);
  return view.entries.filter((entry) => ToolResultEntry.is(entry)).map((entry) => entry.model[0]);
}

const resultText = (message) => message.content.map((block) => block.text ?? "").join("");

/** The registry a chat gets in production, with present_results and the workspace and page tools. */
function productionRegistry(piExtensions) {
  return buildChatRegistry(
    {
      extensions: piExtensions,
      modelRuntime,
      workDir: "/tmp/work",
      extensionPaths: [LOCAL],
      trustedPackages: [],
      copilot: buildCopilotExtension("QDash test prompt", [
        chartTool,
        uiTool,
        ...buildPresentationTools(presentationConfig),
        askUserTool,
      ]),
      internalCalls: PRESENTATION_INTERNAL_CALLS,
      codingTools: true,
    },
    connection,
    "Answer briefly.",
    { path: "/workflow/t1", flow: { name: "t1", code: "x = 1\n" } },
  );
}

test("the production chat registry: present_results reaches its classifier; scripts reach only audited reads", async () => {
  const chips = piTool("qdash_list_chips", () => [{ chip_id: "A" }]);
  const save = piTool("qdash_save_flow");
  const metrics = piTool("qdash_get_chip_metrics", () => ({ t1_us: 30 }));
  // A trusted checkout's replacement of an audited read is model-only.
  const localMetrics = piTool("qdash_get_chip_metrics", () => ({ t1_us: 1 }));
  const chat = productionRegistry([piExtension([chips, save, metrics]), piExtension([localMetrics], `${LOCAL}/index.ts`)]);

  // Every tool a nested call could resolve to is an audited read or present_results' classifier.
  const callable = chat.registry
    .snapshot()
    .tools()
    .filter(({ tool }) => tool.callers === undefined || tool.callers.includes("tools"))
    .map(({ tool }) => tool.name)
    .sort();
  assert.deepEqual(callable, [CLASSIFY_TOOL, "qdash_list_chips"].sort());

  const probes = [
    "qdash_presentation_classify",
    "qdash_save_flow",
    "qdash_get_chip_metrics",
    "present_results",
    "render_ui",
    "render_chart",
    "ask_user",
    "propose_code_edit",
    "bash",
    "write",
    "edit",
    "read",
    "tool_search",
    "codemode",
  ];
  const code = [
    "const outcomes = [];",
    `for (const name of ${JSON.stringify(probes)}) {`,
    "  try { await tools[name]({ title: 'x', state: {} }); outcomes.push(name + ': ran'); }",
    "  catch (error) { outcomes.push(name + ': ' + error.message); }",
    "}",
    "outcomes.push('search: ' + JSON.stringify(await searchTools('classify presentation layout')));",
    "outcomes.push('chips: ' + JSON.stringify(await tools.qdash_list_chips({})));",
    "text(outcomes.join('\\n'));",
  ].join("\n");
  const { faux, models, classifierCalls, model } = chatModels(async () => failureList);
  const transcripts = [];
  const step = (message) => (transcript) => {
    transcripts.push(transcript);
    return message;
  };
  faux.setResponses([
    step(fauxAssistantMessage([fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" })], { stopReason: "toolUse" })),
    step(fauxAssistantMessage([fauxToolCall(PRESENT_TOOL, presentArgs, { id: "p1" })], { stopReason: "toolUse" })),
    step(fauxAssistantMessage([fauxToolCall("qdash_save_flow", { title: "flow" }, { id: "w1" })], { stopReason: "toolUse" })),
    step(fauxAssistantMessage(fauxText("never"))),
  ]);
  const { harness, conversation } = await open(chat.registry, models, model);
  try {
    assert.equal((await ask(conversation, "Which qubits failed?")).status, "done");
    const [script, present, write] = await results(conversation);

    const output = resultText(script);
    for (const name of probes) assert.match(output, new RegExp(`${name}: tools.${name} does not exist`), name);
    assert.match(output, /search: \[\]/);
    assert.match(output, /chips: \[\{"chip_id":"A"\}\]/);
    assert.equal(chips.calls.length, 1);
    assert.equal(save.calls.length, 0);
    assert.equal(metrics.calls.length + localMetrics.calls.length, 0);

    // present_results' own nested call reached the classifier and rendered its layout.
    assert.equal(classifierCalls.length, 1);
    assert.equal(present.isError, false);
    assert.equal(present.details.presentation.outcome, "template");
    assert.equal(present.details.presentation.category, "failure_list");
    assert.ok(present.details.ui);

    // The model's write call still asks the user for approval and does not run.
    assert.equal(write.toolName, "qdash_save_flow");
    assert.deepEqual(write.details.approval, { id: "w1", tool: "qdash_save_flow", label: "qdash_save_flow", args: { title: "flow" } });
    assert.equal(save.calls.length, 0);

    // Neither the model's tools nor the prompt's list of script tools names the internal classifier.
    const [system] = transcripts[0].messages;
    assert.equal(system.role, "system");
    assert.match(system.sections.codemode, /tools\.qdash_list_chips|qdash_list_chips\(/);
    for (const text of [JSON.stringify(system), JSON.stringify(transcripts.at(-1).tools ?? [])]) {
      assert.doesNotMatch(text, /presentation\.classify|qdash_presentation_classify|qdash_save_flow\(/);
    }
  } finally {
    await harness.close(context);
    await chat.close();
  }
});

test("the edit tool comes with an editor or an editable dashboard and is model-only; other pages have none", () => {
  const parts = {
    extensions: [piExtension([piTool("qdash_list_chips", () => [])])],
    modelRuntime,
    workDir: "/tmp/work",
    extensionPaths: [LOCAL],
    trustedPackages: [],
    copilot: buildCopilotExtension("QDash test prompt", []),
    internalCalls: PRESENTATION_INTERNAL_CALLS,
  };
  const editTool = (page) => {
    const chat = buildChatRegistry(parts, connection, undefined, page);
    const found = chat.registry.snapshot().tools().find(({ tool }) => tool.name === "propose_code_edit");
    void chat.close();
    return found?.tool;
  };
  const script = editTool({
    path: "/custom-dashboards/scripts/ms_1",
    metricScript: { scriptId: "ms_1", name: "ZX90", code: "x = 1\n" },
  });
  assert.ok(script);
  assert.match(script.description, /metric script `ZX90`/);
  assert.deepEqual(script.callers, ["model"]);
  assert.match(editTool({ path: "/workflow/t1", flow: { name: "t1", code: "x = 1\n" } }).description, /flow `t1`/);
  const board = editTool({ path: "/custom-dashboards/new", dashboard: { name: "", code: "{}" } });
  assert.match(board.description, /new custom dashboard/);
  assert.deepEqual(board.callers, ["model"]);
  assert.equal(editTool({ path: "/chip" }), undefined);
});

test("the policy hook blocks the classifier for any parent but a running present_results", async () => {
  const [present, classify] = buildPresentationTools(presentationConfig);
  // A model tool that is not the classifier's caller tries the same nested call.
  const impostor = defineTool({
    name: "impostor",
    description: "Calls the classifier",
    parameters: Type.Object({}),
    callers: ["model"],
    execute: async (_args, api, ctx) => {
      const nested = await api.executeTool(CLASSIFY_TOOL, { state: {} }, ctx, { key: "x", progress: false });
      return { output: [{ type: "text", text: nested.isError ? `blocked: ${nested.diagnostics.map((d) => d.message).join("; ")}` : "ran" }] };
    },
  });
  // Code Mode without QDash's script filter: only the hook stands between a script and the classifier.
  const sandbox = createCodemodeSandbox();
  const registry = createRegistry();
  registry.install(defineExtension({ name: "copilot", tools: [present, classify, impostor] }));
  registry.install(createCodemodeExtension({ sandbox, models: false }));
  registry.install(toolPolicyExtension({ nestedTools: [], deferredTools: [], internalCalls: PRESENTATION_INTERNAL_CALLS }));
  const code = "try { await tools.qdash_presentation_classify({ state: {} }); text('ran'); } catch (e) { text('blocked: ' + e.message); }";
  const { faux, models, classifierCalls, model } = chatModels(async () => failureList);
  faux.setResponses([
    fauxAssistantMessage(
      [
        fauxToolCall("impostor", {}, { id: "i1" }),
        fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: "s1" }),
        fauxToolCall(PRESENT_TOOL, { ...presentArgs, sources: ["impostor"] }, { id: "p1" }),
      ],
      { stopReason: "toolUse" },
    ),
    fauxAssistantMessage(fauxText("done")),
  ]);
  const { harness, conversation } = await open(registry, models, model);
  try {
    assert.equal((await ask(conversation, "go")).status, "done");
    const byName = Object.fromEntries((await results(conversation)).map((message) => [message.toolName, message]));
    assert.match(resultText(byName.impostor), /blocked: .*qdash\.presentation\.classify cannot be called from a code mode script/);
    assert.match(resultText(byName[CODEMODE_TOOL_NAME]), /blocked: .*cannot be called from a code mode script/);
    assert.equal(byName[PRESENT_TOOL].details.presentation.outcome, "template");
    // Only present_results' call reached the classifier.
    assert.equal(classifierCalls.length, 1);
  } finally {
    await harness.close(context);
    await sandbox.close();
  }
});

/** Wait until no script worker is running, as a worker is released once it exits. */
async function scriptsIdle() {
  for (let i = 0; i < 250 && runningScriptCount() > 0; i++) await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(runningScriptCount(), 0);
}

test("a script beyond the concurrency limit is refused with a message, and the slots are released", async () => {
  // The limit is per process: earlier scripts must have released their workers.
  await scriptsIdle();
  // Admitted scripts wait in a host tool, holding their workers, until the test
  // has seen the excess script refused; only then are they released.
  let started = 0;
  let release;
  const held = new Promise((resolve) => (release = resolve));
  const wait = defineTool({
    name: "wait_here",
    description: "Waits",
    parameters: Type.Object({}),
    callers: ["tools"],
    execute: async () => {
      started += 1;
      await held;
      return { output: [{ type: "text", text: "waited" }] };
    },
  });
  const sandbox = createCodemodeSandbox();
  const registry = createRegistry();
  registry.install(defineExtension({ name: "wait", tools: [wait] }));
  registry.install(createCodemodeExtension({ sandbox, models: false }));
  const { faux, models, model } = chatModels(async () => failureList);
  const code = "await tools.wait_here({}); text('finished');";
  const calls = Array.from({ length: MAX_CONCURRENT_SCRIPTS + 1 }, (_, i) =>
    fauxToolCall(CODEMODE_TOOL_NAME, { code }, { id: `s${i}` }),
  );
  faux.setResponses([fauxAssistantMessage(calls, { stopReason: "toolUse" }), fauxAssistantMessage(fauxText("done"))]);
  const { harness, conversation } = await open(registry, models, model);
  const refusedText = /already running \d+ code mode scripts; try again shortly/;
  try {
    const asked = ask(conversation, "go");
    // A deadline that fails the test when the refusal never shows; it never releases a slot.
    const deadline = Date.now() + 15_000;
    for (;;) {
      const outputs = (await results(conversation)).map((message) => resultText(message));
      if (outputs.some((text) => refusedText.test(text))) break;
      assert.ok(Date.now() < deadline, `the excess script was not refused in time (started ${started})`);
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    // Refused while every admitted script still held its worker.
    assert.equal(runningScriptCount(), MAX_CONCURRENT_SCRIPTS);
    release();
    assert.equal((await asked).status, "done");
    const outputs = (await results(conversation)).map((message) => resultText(message));
    const refused = outputs.filter((text) => refusedText.test(text));
    assert.equal(refused.length, 1, outputs.join("\n---\n"));
    assert.equal(outputs.filter((text) => /finished/.test(text)).length, MAX_CONCURRENT_SCRIPTS);
    assert.equal(started, MAX_CONCURRENT_SCRIPTS);
  } finally {
    // Cleanup only: a failed test must not leave scripts holding workers.
    release();
    await harness.close(context);
    await sandbox.close();
  }
  await scriptsIdle();
});
