import { describe, expect, it } from "vitest";

import { buildEvaluationModelOptions } from "../copilotModels";

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
        label: "ising (openai-compatible-evaluation)",
        model: { provider: "openai-compatible-evaluation", name: "ising" },
        reasoningEffort: null,
      },
      {
        key: "evaluation-openai-compatible-chat:qwen",
        label: "qwen (openai-compatible-chat)",
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
