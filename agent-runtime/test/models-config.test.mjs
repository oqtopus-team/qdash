import assert from "node:assert/strict";
import { test } from "node:test";

import { buildModelsConfig } from "../src/models-config.ts";

const YAML = `
chat_models:
  - provider: ollama
    name: gemma4:31b
    api_style: completion
    base_url: env:OLLAMA_BASE_URL
    api_key_env: OLLAMA_API_KEY
    temperature: 1.0
    top_p: 0.95
    top_k: 64
    max_output_tokens: 4096
  - provider: openai
    name: gpt-5.4
    api_style: responses
    temperature: 0.7
    max_output_tokens: 4096
  - provider: bedrock
    name: jp.anthropic.claude-sonnet-4-6
    api_style: responses
    temperature: 0.7
`;

const REVIEW_YAML = `
analysis_models:
  - provider: ollama
    name: nvidia/Gemma-4-31B-IT-NVFP4
    api_style: completion
    base_url: env:OLLAMA_BASE_URL
    api_key_env: OLLAMA_API_KEY
    keep_alive: 30m
    temperature: 1.0
    top_p: 0.95
    top_k: 64
    max_output_tokens: 4096
  - provider: ollama
    name: gemma4:31b
    api_style: completion
    base_url: env:OLLAMA_BASE_URL
    api_key_env: OLLAMA_API_KEY
    keep_alive: 30m
    max_output_tokens: 2048
  - provider: openai
    name: gpt-5.4
    api_style: responses
    temperature: 0.1
    max_output_tokens: 8192
`;

const env = { OLLAMA_BASE_URL: "http://ollama:11434/v1" };

test("a model with base_url becomes a provider definition", () => {
  const { providers } = buildModelsConfig(YAML, undefined, env);
  assert.deepEqual(providers.ollama, {
    baseUrl: "http://ollama:11434/v1",
    api: "openai-completions",
    apiKey: "$OLLAMA_API_KEY",
    compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
    models: [
      {
        id: "gemma4:31b",
        contextWindow: 131072,
        maxTokens: 4096,
        samplingParams: { temperature: 1, top_p: 0.95, top_k: 64 },
      },
    ],
  });
});

test("a catalog model only gets overrides", () => {
  const { providers } = buildModelsConfig(YAML, undefined, env);
  assert.deepEqual(providers.openai, {
    modelOverrides: {
      "gpt-5.4": { maxTokens: 4096, samplingParams: { temperature: 0.7 } },
    },
  });
});

test("bedrock is renamed to pi's provider id", () => {
  const { providers } = buildModelsConfig(YAML, undefined, env);
  assert.ok(providers["amazon-bedrock"]);
  assert.equal(providers.bedrock, undefined);
});

test("an unresolvable base_url drops the model instead of writing a literal", () => {
  const { providers } = buildModelsConfig(YAML, undefined, {});
  assert.equal(providers.ollama, undefined);
});

test("review models are merged into the same providers as chat models", () => {
  const { providers } = buildModelsConfig(YAML, REVIEW_YAML, env);
  assert.deepEqual(
    providers.ollama.models.map((model) => model.id),
    ["gemma4:31b", "nvidia/Gemma-4-31B-IT-NVFP4"],
  );
});

test("keep_alive rides along in samplingParams so ollama keeps the VLM resident", () => {
  const { providers } = buildModelsConfig(YAML, REVIEW_YAML, env);
  const reviewModel = providers.ollama.models.find(
    (model) => model.id === "nvidia/Gemma-4-31B-IT-NVFP4",
  );
  assert.deepEqual(reviewModel.samplingParams, {
    temperature: 1,
    top_p: 0.95,
    top_k: 64,
    keep_alive: "30m",
  });
});

test("a model declared in both files keeps the chat definition", () => {
  const { providers } = buildModelsConfig(YAML, REVIEW_YAML, env);
  const shared = providers.ollama.models.find((model) => model.id === "gemma4:31b");
  assert.equal(shared.maxTokens, 4096);
  assert.deepEqual(providers.openai.modelOverrides["gpt-5.4"], {
    maxTokens: 4096,
    samplingParams: { temperature: 0.7 },
  });
});
