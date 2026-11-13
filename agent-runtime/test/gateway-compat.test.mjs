import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { buildModelsConfig } from "../src/models-config.ts";

/** A replayed turn whose assistant message holds only a tool call, then no tools offered. */
const HISTORY = [
  { role: "user", content: "read T1", timestamp: 1 },
  {
    role: "assistant",
    content: [{ type: "toolCall", id: "call_1", name: "lookup", arguments: { qid: "Q00" } }],
    api: "openai-completions",
    provider: "openai-compatible-chat",
    model: "gateway",
    usage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: "toolUse",
    timestamp: 2,
  },
  {
    role: "toolResult",
    toolCallId: "call_1",
    toolName: "lookup",
    content: [{ type: "text", text: "42 us" }],
    isError: false,
    timestamp: 3,
  },
  { role: "user", content: "summarize", timestamp: 4 },
];

/** Load chat.yaml through Pi's own models.json validation and capture one request body per model. */
async function requestBodies(t, chatModels, models) {
  const bodies = [];
  const server = Bun.serve({
    port: 0,
    hostname: "127.0.0.1",
    async fetch(request) {
      bodies.push(await request.json());
      return Response.json({ error: { message: "Request captured", type: "test" } }, { status: 400 });
    },
  });
  t.after(() => server.stop(true));
  const directory = mkdtempSync(join(tmpdir(), "gateway-compat-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const env = { OPENAI_COMPATIBLE_BASE_URL_CHAT: `${server.url}v1`, OPENAI_COMPATIBLE_API_KEY_CHAT: "key" };
  const modelsPath = join(directory, "models.json");
  writeFileSync(modelsPath, JSON.stringify(buildModelsConfig(`chat_models:\n${chatModels}`, undefined, env)));
  const runtime = await ModelRuntime.create({
    modelsPath,
    authPath: join(directory, "auth.json"),
    modelsStorePath: join(directory, "models-store.json"),
  });
  assert.equal(runtime.getError(), undefined, "Pi accepts the generated models.json");
  for (const name of models) {
    const model = runtime.getModel("openai-compatible-chat", name);
    assert.ok(model, name);
    await runtime.complete(model, { messages: HISTORY }, { env, maxTokens: 1, sessionId: "conversation-1" });
  }
  assert.equal(bodies.length, models.length);
  return bodies;
}

const entry = (name, extra = "") => `  - provider: openai-compatible-chat
    name: ${name}
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT
    api_key_env: OPENAI_COMPATIBLE_API_KEY_CHAT
${extra}`;

test("Pi sends opted-in gateway compat on the completions request and defaults elsewhere", async (t) => {
  const [gateway, plain] = await requestBodies(
    t,
    entry(
      "gateway",
      `    prompt_cache_key_mode: enabled
    requires_non_null_assistant_content: true
    requires_tools_with_tool_history: true
`,
    ) + entry("plain"),
    ["gateway", "plain"],
  );

  const toolCallMessage = (body) => body.messages.find((message) => message.tool_calls);
  assert.equal(gateway.prompt_cache_key, "conversation-1");
  assert.equal(toolCallMessage(gateway).content, "");
  assert.deepEqual(gateway.tools, []);

  // Pi's defaults for a custom endpoint: no cache key, null content, no empty tools array.
  assert.equal("prompt_cache_key" in plain, false);
  assert.equal(toolCallMessage(plain).content, null);
  assert.equal("tools" in plain, false);
});

test("an explicit false keeps Pi's default request shape", async (t) => {
  const [body] = await requestBodies(
    t,
    entry(
      "explicit",
      `    prompt_cache_key_mode: disabled
    requires_non_null_assistant_content: false
    requires_tools_with_tool_history: false
`,
    ),
    ["explicit"],
  );
  assert.equal("prompt_cache_key" in body, false);
  assert.equal(body.messages.find((message) => message.tool_calls).content, null);
  assert.equal("tools" in body, false);
});
