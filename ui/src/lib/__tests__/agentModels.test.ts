import { describe, expect, it } from "vitest";

import {
  buildChatModelOptions,
  buildEvaluationModelOptions,
  resolveChatModelOption,
} from "../agentModels";

describe("buildChatModelOptions", () => {
  const qwen = { provider: "openai-compatible-chat", name: "qwen", reasoning_effort: "low" };
  const kimi = { provider: "openai-compatible-chat", name: "kimi" };

  it("labels the default with the model it resolves to and keys the rest by identity", () => {
    const options = buildChatModelOptions({ chat_models: [qwen, kimi, qwen], model: qwen });
    expect(options.map(({ key, label, model }) => ({ key, label, model }))).toEqual([
      { key: "default", label: "qwen", model: null },
      { key: "model:openai-compatible-chat:kimi", label: "kimi", model: kimi },
    ]);
    expect(options[0]).toMatchObject({ resolvedModel: qwen, reasoningEffort: "low" });
  });

  it("offers only the default before the config loads", () => {
    expect(buildChatModelOptions(null)).toEqual([
      expect.objectContaining({ key: "default", label: "Configured default", model: null }),
    ]);
  });

  it("resolves a removed choice to the default", () => {
    const options = buildChatModelOptions({ chat_models: [qwen] });
    expect(resolveChatModelOption(options, "model:openai-compatible-chat:kimi").key).toBe(
      "default",
    );
  });
});

describe("buildEvaluationModelOptions", () => {
  it("keeps configured order and removes invalid or duplicate models", () => {
    expect(
      buildEvaluationModelOptions({
        evaluation_models: [
          { provider: "openai-compatible-evaluation", name: "ising" },
          { provider: "openai-compatible-chat", name: "qwen", reasoning_effort: "medium" },
          { provider: "openai-compatible-evaluation", name: "ising" },
          { provider: "missing-name" },
        ],
      }),
    ).toEqual([
      {
        key: "evaluation-openai-compatible-evaluation:ising",
        label: "ising",
        model: { provider: "openai-compatible-evaluation", name: "ising" },
        reasoningEffort: null,
      },
      {
        key: "evaluation-openai-compatible-chat:qwen",
        label: "qwen",
        model: {
          provider: "openai-compatible-chat",
          name: "qwen",
          reasoning_effort: "medium",
        },
        reasoningEffort: "medium",
      },
    ]);
  });
});
