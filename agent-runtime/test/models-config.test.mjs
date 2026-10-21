import assert from "node:assert/strict";
import { test } from "node:test";

import { buildModelsConfig } from "../src/models-config.ts";

const YAML = `
chat_models:
  - provider: openai-compatible-local
    name: gemma4:31b
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_LOCAL
    api_key_env: OPENAI_COMPATIBLE_API_KEY_LOCAL
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

const EVALUATION_YAML = `
evaluation_models:
  - provider: openai-compatible-local
    name: nvidia/Gemma-4-31B-IT-NVFP4
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_LOCAL
    api_key_env: OPENAI_COMPATIBLE_API_KEY_LOCAL
    keep_alive: 30m
    temperature: 1.0
    top_p: 0.95
    top_k: 64
    max_output_tokens: 4096
  - provider: openai-compatible-local
    name: gemma4:31b
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_LOCAL
    api_key_env: OPENAI_COMPATIBLE_API_KEY_LOCAL
    keep_alive: 30m
    max_output_tokens: 2048
  - provider: openai
    name: gpt-5.4
    api_style: responses
    temperature: 0.1
    max_output_tokens: 8192
`;

const env = { OPENAI_COMPATIBLE_BASE_URL_LOCAL: "http://ollama:11434/v1" };

const OPENAI_COMPATIBLE_YAML = `
chat_models:
  - provider: openai-compatible-chat
    name: qwen3.8-flash-next
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT
    api_key_env: OPENAI_COMPATIBLE_API_KEY_CHAT
    num_ctx: 65536
    max_output_tokens: 16384
    temperature: 0.7
    top_p: 0.8
    top_k: 20
    sampling_params:
      min_p: 0
      presence_penalty: 1.5
      repetition_penalty: 1
    sampling_params_by_thinking_level:
      high:
        temperature: 1
        top_p: 0.95
        top_k: 20
        min_p: 0
        presence_penalty: 0
        repetition_penalty: 1
        reasoning_effort: xhigh
    reasoning_effort: high
`;

test("a model with base_url becomes a provider definition", () => {
  const { providers } = buildModelsConfig(YAML, undefined, env);
  assert.deepEqual(providers["openai-compatible-local"], {
    baseUrl: "http://ollama:11434/v1",
    api: "openai-completions",
    apiKey: "$OPENAI_COMPATIBLE_API_KEY_LOCAL",
    compat: {
      supportsStore: false,
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      maxTokensField: "max_tokens",
    },
    models: [
      {
        id: "gemma4:31b",
        contextWindow: 131072,
        maxTokens: 4096,
        input: ["text", "image"],
        samplingParams: { temperature: 1, top_p: 0.95, top_k: 64 },
      },
    ],
  });
});

test("OpenAI-compatible Qwen models preserve Pi 1.0 sampling and thinking settings", () => {
  const { providers } = buildModelsConfig(OPENAI_COMPATIBLE_YAML, undefined, {
    OPENAI_COMPATIBLE_BASE_URL_CHAT: "https://gateway.example/model/v1",
  });
  assert.deepEqual(providers["openai-compatible-chat"], {
    baseUrl: "https://gateway.example/model/v1",
    api: "openai-completions",
    apiKey: "$OPENAI_COMPATIBLE_API_KEY_CHAT",
    compat: {
      supportsStore: false,
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      maxTokensField: "max_tokens",
      thinkingFormat: "qwen-chat-template",
    },
    models: [
      {
        id: "qwen3.8-flash-next",
        contextWindow: 65536,
        maxTokens: 16384,
        reasoning: true,
        input: ["text", "image"],
        samplingParams: {
          min_p: 0,
          presence_penalty: 1.5,
          repetition_penalty: 1,
          temperature: 0.7,
          top_p: 0.8,
          top_k: 20,
        },
        samplingParamsByThinkingLevel: {
          high: {
            temperature: 1,
            top_p: 0.95,
            top_k: 20,
            min_p: 0,
            presence_penalty: 0,
            repetition_penalty: 1,
            reasoning_effort: "xhigh",
          },
        },
      },
    ],
  });
});

test("suffixed OpenAI-compatible providers keep endpoints separate", () => {
  const evaluationYaml = `
evaluation_models:
  - provider: openai-compatible-evaluation
    name: evaluator
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_EVALUATION
    api_key_env: OPENAI_COMPATIBLE_API_KEY_EVALUATION
`;
  const { providers } = buildModelsConfig(OPENAI_COMPATIBLE_YAML, evaluationYaml, {
    OPENAI_COMPATIBLE_BASE_URL_CHAT: "https://chat.example/v1",
    OPENAI_COMPATIBLE_BASE_URL_EVALUATION: "https://evaluation.example/v1",
  });

  assert.equal(providers["openai-compatible-chat"].baseUrl, "https://chat.example/v1");
  assert.equal(
    providers["openai-compatible-evaluation"].baseUrl,
    "https://evaluation.example/v1",
  );
  assert.equal(
    providers["openai-compatible-evaluation"].compat.maxTokensField,
    "max_tokens",
  );
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
  assert.equal(providers["openai-compatible-local"], undefined);
});

test("a base_url path is passed through without adding /v1", () => {
  const { providers } = buildModelsConfig(YAML, undefined, {
    OPENAI_COMPATIBLE_BASE_URL_LOCAL: "http://ollama:11434",
  });
  assert.equal(providers["openai-compatible-local"].baseUrl, "http://ollama:11434");
});

test("trailing slashes are removed from a canonical base_url", () => {
  const { providers } = buildModelsConfig(YAML, undefined, {
    OPENAI_COMPATIBLE_BASE_URL_LOCAL: "http://ollama:11434/v1/",
  });
  assert.equal(providers["openai-compatible-local"].baseUrl, "http://ollama:11434/v1");
});

test("evaluation models are merged into the same providers as chat models", () => {
  const { providers } = buildModelsConfig(YAML, EVALUATION_YAML, env);
  assert.deepEqual(
    providers["openai-compatible-local"].models.map((model) => model.id),
    ["gemma4:31b", "nvidia/Gemma-4-31B-IT-NVFP4"],
  );
});

test("keep_alive rides along in samplingParams so ollama keeps the VLM resident", () => {
  const { providers } = buildModelsConfig(YAML, EVALUATION_YAML, env);
  const evaluationModel = providers["openai-compatible-local"].models.find(
    (model) => model.id === "nvidia/Gemma-4-31B-IT-NVFP4",
  );
  assert.deepEqual(evaluationModel.samplingParams, {
    temperature: 1,
    top_p: 0.95,
    top_k: 64,
    keep_alive: "30m",
  });
});

test("locally hosted models are declared image-capable", () => {
  // Pi defaults an unstated `input` to text-only and then drops image content
  // while building the request, so figure analysis would silently lose its figures.
  const { providers } = buildModelsConfig(YAML, EVALUATION_YAML, env);
  for (const model of providers["openai-compatible-local"].models) {
    assert.deepEqual(model.input, ["text", "image"]);
  }
});

test("a model declared in both files keeps the chat definition", () => {
  const { providers } = buildModelsConfig(YAML, EVALUATION_YAML, env);
  const shared = providers["openai-compatible-local"].models.find(
    (model) => model.id === "gemma4:31b",
  );
  assert.equal(shared.maxTokens, 4096);
  assert.deepEqual(providers.openai.modelOverrides["gpt-5.4"], {
    maxTokens: 4096,
    samplingParams: { temperature: 0.7 },
  });
});
