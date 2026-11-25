import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ModelRuntime } from "@earendil-works/pi-coding-agent";

import { buildModelsConfig, chatModelAvailability } from "../src/models-config.ts";

// The committed DeepSeek chat model and the availability the chat menus read, resolved the
// way the runtime resolves them. Offline: requests go to a local fake endpoint only, and
// every key is a placeholder.
const CONFIG = new URL("../../config/agent/", import.meta.url);
const chatYaml = readFileSync(new URL("chat.yaml", CONFIG), "utf8");

const PROVIDER = "openai-compatible-deepseek";
const MODEL = "preview/DeepSeek-V4.1-Flash-1017";
const BASE_URL = "https://api.ai.sakura.ad.jp/v1";
const KEY = "deepseek-test-key-1234567890";
const KEY_NAMES = [
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "OPENAI_COMPATIBLE_API_KEY_CHAT",
  "OPENAI_COMPATIBLE_API_KEY_DEEPSEEK",
];

/** Run `body` with exactly `values` set among the model keys, restoring them afterwards. */
async function withKeys(values, body) {
  const saved = Object.fromEntries(KEY_NAMES.map((name) => [name, process.env[name]]));
  for (const name of KEY_NAMES) {
    if (name in values) process.env[name] = values[name];
    else delete process.env[name];
  }
  try {
    return await body();
  } finally {
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
}

async function runtimeFor(t, env) {
  const directory = mkdtempSync(join(tmpdir(), "deepseek-chat-model-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const config = buildModelsConfig(chatYaml, undefined, env);
  const modelsPath = join(directory, "models.json");
  writeFileSync(modelsPath, JSON.stringify(config));
  const runtime = await ModelRuntime.create({
    modelsPath,
    authPath: join(directory, "auth.json"),
    modelsStorePath: join(directory, "models-store.json"),
    refreshOnCreate: false,
  });
  assert.equal(runtime.getError(), undefined, "Pi accepts the generated models.json");
  return { runtime, config, modelsPath };
}

async function availability(t, env) {
  const { runtime } = await runtimeFor(t, env);
  const available = await runtime.getAvailable();
  return chatModelAvailability(chatYaml, new Set(available.map((m) => `${m.provider}/${m.id}`)));
}

test("the shipped DeepSeek model is a chat completions endpoint with its own credential", async (t) => {
  await withKeys({ OPENAI_COMPATIBLE_API_KEY_DEEPSEEK: KEY }, async () => {
    const env = { OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK: `${BASE_URL}/`, ...process.env };
    const { runtime, config, modelsPath } = await runtimeFor(t, env);
    const provider = config.providers[PROVIDER];
    assert.equal(provider.baseUrl, BASE_URL);
    assert.equal(provider.api, "openai-completions");
    // A reference to the variable, never its value.
    assert.equal(provider.apiKey, "$OPENAI_COMPATIBLE_API_KEY_DEEPSEEK");
    assert.equal(readFileSync(modelsPath, "utf8").includes(KEY), false);
    // The endpoint reads max_tokens and documents no reasoning_effort.
    assert.equal(provider.compat.maxTokensField, "max_tokens");
    assert.equal(provider.compat.supportsReasoningEffort, false);
    assert.deepEqual(provider.models, [
      { id: MODEL, contextWindow: 1048575, maxTokens: 32000, input: ["text", "image"] },
    ]);

    const model = runtime.getModel(PROVIDER, MODEL);
    assert.ok(model);
    assert.equal(model.reasoning, false, "no thinking control is sent");
  });
});

test("a DeepSeek request sends max_tokens and replays thinking with tool calls", async (t) => {
  const requests = [];
  const server = Bun.serve({
    port: 0,
    hostname: "127.0.0.1",
    async fetch(request) {
      requests.push({ authorization: request.headers.get("authorization"), body: await request.json() });
      const chunk = (delta, finish = null) =>
        `data: ${JSON.stringify({ id: "c1", object: "chat.completion.chunk", created: 1, model: MODEL, choices: [{ index: 0, delta, finish_reason: finish }] })}\n\n`;
      const stream = [
        chunk({ role: "assistant", reasoning: "Check T1 first." }),
        chunk({ content: "T1 is 42 us." }),
        chunk({}, "stop"),
        "data: [DONE]\n\n",
      ].join("");
      return new Response(stream, { headers: { "content-type": "text/event-stream" } });
    },
  });
  t.after(() => server.stop(true));

  await withKeys({ OPENAI_COMPATIBLE_API_KEY_DEEPSEEK: KEY }, async () => {
    const env = { ...process.env, OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK: `${server.url}v1` };
    const { runtime } = await runtimeFor(t, env);
    const model = runtime.getModel(PROVIDER, MODEL);
    const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
    const messages = [
      { role: "user", content: "read T1", timestamp: 1 },
      {
        role: "assistant",
        content: [
          { type: "thinking", thinking: "Look T1 up.", thinkingSignature: "reasoning" },
          { type: "toolCall", id: "call_1", name: "lookup", arguments: { qid: "Q00" } },
        ],
        api: "openai-completions",
        provider: PROVIDER,
        model: MODEL,
        usage,
        stopReason: "toolUse",
        timestamp: 2,
      },
      { role: "toolResult", toolCallId: "call_1", toolName: "lookup", content: [{ type: "text", text: "42 us" }], isError: false, timestamp: 3 },
    ];
    const answer = await runtime.complete(model, { messages }, { maxTokens: 32000 });

    assert.equal(requests.length, 1);
    const { authorization, body } = requests[0];
    assert.equal(authorization, `Bearer ${KEY}`);
    assert.equal(body.model, MODEL);
    assert.equal(body.max_tokens, 32000);
    for (const field of ["max_completion_tokens", "reasoning_effort", "thinking", "store"]) {
      assert.equal(field in body, false, field);
    }
    const replayed = body.messages.find((message) => message.tool_calls);
    assert.equal(replayed.reasoning, "Look T1 up.");
    assert.equal(replayed.tool_calls[0].function.name, "lookup");
    assert.deepEqual(body.messages.at(-1), { role: "tool", content: "42 us", tool_call_id: "call_1" });

    // Thinking streamed in delta.reasoning becomes a thinking block that is replayed as such.
    assert.equal(answer.stopReason, "stop");
    assert.deepEqual(
      answer.content.map((block) => [block.type, block.thinking ?? block.text, block.thinkingSignature]),
      [
        ["thinking", "Check T1 first.", "reasoning"],
        ["text", "T1 is 42 us.", undefined],
      ],
    );
  });
});

test("chat models without a configured key are unavailable, in declared order", async (t) => {
  const env = (extra = {}) => ({ OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK: BASE_URL, ...extra });
  const ids = (list) => list.map(({ provider, name }) => `${provider}/${name}`);
  const flags = (list) => Object.fromEntries(list.map((m) => [`${m.provider}/${m.name}`, m.available]));

  const none = await withKeys({}, () => availability(t, env()));
  assert.deepEqual(ids(none), [
    "openai/gpt-6-sol",
    "openai-compatible-chat/qwen3.8-flash-next",
    "anthropic/claude-opus-5-5",
    `${PROVIDER}/${MODEL}`,
  ]);
  assert.ok(none.every((model) => model.available === false));

  // Empty and whitespace-only keys count as missing.
  const blank = await withKeys(
    { OPENAI_API_KEY: "   ", ANTHROPIC_API_KEY: "", OPENAI_COMPATIBLE_API_KEY_DEEPSEEK: " \t" },
    () => availability(t, env()),
  );
  assert.ok(blank.every((model) => model.available === false));

  const some = await withKeys(
    { ANTHROPIC_API_KEY: "anthropic-placeholder", OPENAI_COMPATIBLE_API_KEY_DEEPSEEK: KEY },
    () => availability(t, env()),
  );
  assert.deepEqual(flags(some), {
    "openai/gpt-6-sol": false,
    "openai-compatible-chat/qwen3.8-flash-next": false,
    "anthropic/claude-opus-5-5": true,
    [`${PROVIDER}/${MODEL}`]: true,
  });
  assert.equal(JSON.stringify(some).includes(KEY), false);

  // A keyless local endpoint stays available through compose's placeholder key.
  const all = await withKeys(
    { OPENAI_API_KEY: "openai-placeholder", OPENAI_COMPATIBLE_API_KEY_CHAT: "openai-compatible" },
    () => availability(t, env({ OPENAI_COMPATIBLE_BASE_URL_CHAT: "http://127.0.0.1:9/v1" })),
  );
  assert.deepEqual(flags(all), {
    "openai/gpt-6-sol": true,
    "openai-compatible-chat/qwen3.8-flash-next": true,
    "anthropic/claude-opus-5-5": false,
    [`${PROVIDER}/${MODEL}`]: false,
  });
});

test("availability names chat.yaml's providers, maps aliases, and drops duplicates", () => {
  const yaml = `chat_models:
  - provider: bedrock
    name: jp.anthropic.claude-sonnet-4-6
  - provider: openai
    name: gpt-6-sol
  - provider: openai
    name: gpt-6-sol
  - name: missing-provider
`;
  assert.deepEqual(chatModelAvailability(yaml, new Set(["amazon-bedrock/jp.anthropic.claude-sonnet-4-6"])), [
    { provider: "bedrock", name: "jp.anthropic.claude-sonnet-4-6", available: true },
    { provider: "openai", name: "gpt-6-sol", available: false },
  ]);
});
