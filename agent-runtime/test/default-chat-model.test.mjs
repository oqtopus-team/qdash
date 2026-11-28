import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { streamSimple as anthropicStream } from "@earendil-works/pi-ai/api/anthropic-messages";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

import { buildModelsConfig, missingCredentialMessage, NATIVE_API_KEY_ENV, supportedThinkingLevel } from "../src/models-config.ts";

// The committed default chat model, resolved the way the runtime resolves it: models.json
// built from config/agent/*.yaml, then pi's bundled catalog. Offline: no model is called,
// no catalog is fetched, and the key is a placeholder that is never sent anywhere.
const CONFIG = new URL("../../config/agent/", import.meta.url);
const chatYaml = readFileSync(new URL("chat.yaml", CONFIG), "utf8");
const evaluationYaml = readFileSync(new URL("evaluation.yaml", CONFIG), "utf8");

async function runtimeWith(env) {
  const dir = mkdtempSync(join(tmpdir(), "default-chat-model-"));
  const models = buildModelsConfig(chatYaml, evaluationYaml, env);
  writeFileSync(join(dir, "models.json"), JSON.stringify(models));
  const runtime = await ModelRuntime.create({
    modelsPath: join(dir, "models.json"),
    authPath: join(dir, "auth.json"),
    refreshOnCreate: false,
  });
  return { runtime, models, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

test("the default chat model is GPT-6 Sol on OpenAI's own Responses API, from the bundled catalog", async () => {
  const saved = process.env.OPENAI_API_KEY;
  delete process.env.OPENAI_API_KEY;
  const { runtime, models, cleanup } = await runtimeWith({});
  try {
    // No endpoint and no sampling of its own: models.json defines nothing for it.
    assert.equal(models.providers.openai?.modelOverrides?.["gpt-6-sol"], undefined);
    assert.equal(models.providers.openai?.baseUrl, undefined);
    const model = runtime.getModel("openai", "gpt-6-sol");
    assert.ok(model, "gpt-6-sol is in the pinned pi-ai catalog");
    assert.equal(model.id, "gpt-6-sol");
    assert.equal(model.provider, "openai");
    assert.equal(model.api, "openai-responses");
    assert.equal(model.baseUrl, "https://api.openai.com/v1");
    assert.equal(model.reasoning, true);
    // render_ui's arguments are sampled against strict schemas on this model.
    assert.equal(model.compat?.supportsStrictMode, true);
    assert.equal(model.thinkingLevelMap?.medium, "medium");
  } finally {
    cleanup();
    if (saved !== undefined) process.env.OPENAI_API_KEY = saved;
  }
});

test("a chat on a native OpenAI model without OPENAI_API_KEY is refused with what to set", async () => {
  assert.equal(NATIVE_API_KEY_ENV.openai, "OPENAI_API_KEY");
  const saved = process.env.OPENAI_API_KEY;
  try {
    delete process.env.OPENAI_API_KEY;
    let { runtime, cleanup } = await runtimeWith({});
    const missing = (await runtime.checkAuth("openai")) === undefined;
    cleanup();
    assert.equal(missing, true);
    const message = missingCredentialMessage("openai", "gpt-6-sol", !missing);
    assert.match(message, /^openai\/gpt-6-sol needs OPENAI_API_KEY in the agent runtime's environment/);
    assert.match(message, /Set OPENAI_API_KEY in \.env and recreate the agent-runtime container, or choose another model\./);

    // With the variable set, the catalog provider is authenticated from it.
    process.env.OPENAI_API_KEY = "placeholder-not-a-key";
    ({ runtime, cleanup } = await runtimeWith({}));
    const auth = await runtime.checkAuth("openai");
    cleanup();
    assert.equal(auth?.source, "OPENAI_API_KEY");
    assert.equal(missingCredentialMessage("openai", "gpt-6-sol", true), undefined);
  } finally {
    if (saved === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = saved;
  }
  // Endpoints with their own key (Qwen through openai-compatible-chat) are not checked here.
  assert.equal(missingCredentialMessage("openai-compatible-chat", "qwen3.8-flash-next", false), undefined);
});

// Anthropic's key variables, cleared so a developer's own environment cannot leak into a test.
const ANTHROPIC_ENV = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN"];
function withoutAnthropicEnv() {
  const saved = Object.fromEntries(ANTHROPIC_ENV.map((name) => [name, process.env[name]]));
  for (const name of ANTHROPIC_ENV) delete process.env[name];
  return () => {
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  };
}

test("Claude Opus 5.5 is offered on Anthropic's own Messages API, from the bundled catalog", async () => {
  const restore = withoutAnthropicEnv();
  const { runtime, models, cleanup } = await runtimeWith({});
  try {
    // GPT-6 Sol stays the default; Qwen and Opus are the other choices.
    assert.match(chatYaml, /chat_models:\n(?:\s*#.*\n)*\s*- provider: openai\n\s*name: gpt-6-sol/);
    assert.equal(models.providers.anthropic, undefined, "no endpoint, sampling, or limits of its own");
    const model = runtime.getModel("anthropic", "claude-opus-5-5");
    assert.ok(model, "claude-opus-5-5 is in the pinned pi-ai catalog");
    assert.equal(model.provider, "anthropic");
    assert.equal(model.api, "anthropic-messages");
    assert.equal(model.baseUrl, "https://api.anthropic.com");
    assert.equal(model.compat?.forceAdaptiveThinking, true);
    assert.equal(model.compat?.supportsTemperature, false);
    assert.equal(model.compat?.supportsStrictTools, true);
    // Bedrock's ID of the same model is never used for it.
    assert.equal(runtime.getModel("amazon-bedrock", "claude-opus-5-5"), undefined);

    // Its thinking is always on: Off and Minimal run at Low, the rest as asked; unset stays unset.
    assert.equal(supportedThinkingLevel(model, "off"), "low");
    assert.equal(supportedThinkingLevel(model, "minimal"), "low");
    for (const level of ["low", "medium", "high"]) assert.equal(supportedThinkingLevel(model, level), level);
    assert.equal(supportedThinkingLevel(model, undefined), undefined);
    // GPT-6 Sol can turn thinking off, so Off stays Off there.
    assert.equal(supportedThinkingLevel(runtime.getModel("openai", "gpt-6-sol"), "off"), "off");

    // The request pi builds for it: adaptive thinking at the turn's effort, no temperature, the
    // exact model ID. Built offline: the base URL is a closed local port and the key a placeholder.
    const offline = { ...model, baseUrl: "http://127.0.0.1:9" };
    for (const level of ["low", "medium"]) {
      let payload;
      const events = anthropicStream(
        offline,
        { messages: [{ role: "user", content: "hi", timestamp: 0 }], tools: [] },
        { apiKey: "placeholder-not-a-key", reasoning: level, temperature: 0.7, onPayload: (body) => (payload = body) },
      );
      for await (const _event of events) {
        // Drained; the request itself fails to connect.
      }
      assert.equal(payload.model, "claude-opus-5-5");
      assert.equal(payload.thinking.type, "adaptive");
      assert.equal(payload.temperature, undefined);
      assert.equal(payload.top_p, undefined);
      assert.equal(payload.top_k, undefined);
      assert.deepEqual(payload.messages.at(-1).output_config, { effort: level });
      assert.doesNotMatch(JSON.stringify(payload), /placeholder-not-a-key/);
    }
  } finally {
    cleanup();
    restore();
  }
});

test("a chat on Claude Opus 5.5 without ANTHROPIC_API_KEY is refused with what to set", async () => {
  assert.equal(NATIVE_API_KEY_ENV.anthropic, "ANTHROPIC_API_KEY");
  const restore = withoutAnthropicEnv();
  try {
    let { runtime, cleanup } = await runtimeWith({});
    const missing = (await runtime.checkAuth("anthropic")) === undefined;
    cleanup();
    assert.equal(missing, true);
    assert.match(
      missingCredentialMessage("anthropic", "claude-opus-5-5", !missing),
      /^anthropic\/claude-opus-5-5 needs ANTHROPIC_API_KEY in the agent runtime's environment, and it is not set\. Set ANTHROPIC_API_KEY in \.env/,
    );
    process.env.ANTHROPIC_API_KEY = "placeholder-not-a-key";
    ({ runtime, cleanup } = await runtimeWith({}));
    const auth = await runtime.checkAuth("anthropic");
    cleanup();
    assert.equal(auth?.source, "ANTHROPIC_API_KEY");
    // The status names the variable, never its value.
    assert.doesNotMatch(JSON.stringify(auth), /placeholder-not-a-key/);
  } finally {
    restore();
  }
});
