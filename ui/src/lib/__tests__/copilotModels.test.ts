import { describe, expect, it } from "vitest";

import {
  buildChatModelOptions,
  buildEvaluationModelOptions,
  buildPlanModelOptions,
  isPlanModel,
  providerLabel,
  resolveChatModelOption,
  unavailablePlanOption,
} from "../copilotModels";

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

describe("ChatGPT plan models", () => {
  it("offers only models the runtime can run, keyed by provider and slug", () => {
    const options = buildPlanModelOptions([
      { slug: "gpt-6.1-sol", display_name: "GPT-6.1 Sol", supported: true },
      { slug: "legacy", display_name: "Legacy", supported: false },
    ]);
    expect(options).toEqual([
      {
        key: "model:chatgpt:gpt-6.1-sol",
        label: "GPT-6.1 Sol",
        model: { provider: "chatgpt", name: "gpt-6.1-sol" },
        resolvedModel: { provider: "chatgpt", name: "gpt-6.1-sol" },
        reasoningEffort: null,
      },
    ]);
    expect(isPlanModel(options[0].model)).toBe(true);
    expect(providerLabel("chatgpt")).toBe("ChatGPT plan");
    expect(providerLabel("openai-compatible")).toBe("openai-compatible");
  });

  it("keeps an unavailable ChatGPT choice explicit and ignores other keys", () => {
    expect(unavailablePlanOption("model:chatgpt:gpt-6.1-sol")).toMatchObject({
      unavailable: true,
      model: { provider: "chatgpt", name: "gpt-6.1-sol" },
    });
    expect(unavailablePlanOption("model:openai-compatible:qwen")).toBeNull();
    expect(unavailablePlanOption("default")).toBeNull();
  });
});
