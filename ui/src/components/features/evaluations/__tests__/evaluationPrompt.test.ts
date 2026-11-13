import { describe, expect, it } from "vitest";

import type { EvaluationInputModel, EvaluationItem } from "@/schemas";

import {
  promptProfile,
  promptSummary,
  rangeLabel,
  referenceLabel,
  systemPromptLabel,
} from "../evaluationPrompt";

/** Builds an evaluation item with an optional recorded input. */
function item(input: Partial<EvaluationInputModel> | null, qid = "Q1"): EvaluationItem {
  return {
    evaluation_id: `ev_${qid}`,
    run_id: "evr_a",
    task_id: `task-${qid}`,
    task_name: "CheckT1",
    qid,
    execution_id: "exec-1",
    figure_path: [],
    json_figure_path: [],
    status: "completed",
    requested_at: "2026-10-11T07:00:00Z",
    input: input ? { context: "Task: CheckT1", figures: [], ...input } : undefined,
  };
}

const figure = { sha256: "f".repeat(64), mime_type: "image/png", bytes: 10 };

describe("evaluationPrompt", () => {
  it("summarises what one prompt was made of, in order", () => {
    expect(
      promptSummary({
        system_prompt: "You are...",
        knowledge_chars: 1534,
        examples: [{ id: "e1", title: "good", outcome: "expected", figures: [figure] }],
        figures: [figure],
        question: "Is the fit trustworthy?",
      }),
    ).toBe("system prompt · reference 1534 chars · 1 labeled example · 1 figure · question");
    expect(promptSummary({ figures: [figure, figure] })).toBe(
      "system prompt not recorded · no reference · 2 figures",
    );
  });

  it("tells a run whose evaluations all saw the same ingredients", () => {
    const shared = {
      system_prompt: "SYSTEM",
      knowledge_chars: 1534,
      knowledge_sha256: "abcdef0123456789",
      figures: [figure],
    };
    const profile = promptProfile([item(shared, "Q1"), item(shared, "Q2"), item(null, "Q3")]);
    expect(profile.recorded).toBe(2);
    expect(profile.systemPrompt).toBe("SYSTEM");
    expect(profile.reference).toEqual({ chars: 1534, sha256: "abcdef0123456789" });
    expect(referenceLabel(profile)).toBe("1534 chars · abcdef01");
    expect(systemPromptLabel(profile)).toBe("6 chars");
    expect(rangeLabel(profile.figures)).toBe("1");
    expect(rangeLabel(profile.examples)).toBe("0");
    expect(profile.question).toBeNull();
  });

  it("flags ingredients that varied, as they can when Copilot is in the loop", () => {
    const profile = promptProfile([
      item({
        system_prompt: "S1",
        knowledge_chars: 1534,
        knowledge_sha256: "aaaa",
        figures: [figure],
      }),
      item({ system_prompt: "S1", figures: [figure, figure] }, "Q2"),
      item({ knowledge_chars: 393, knowledge_sha256: "bbbb", figures: [figure] }, "Q3"),
    ]);
    // Q3 has no system prompt, which is a variant of its own.
    expect(profile.systemPromptVariants).toBe(2);
    expect(profile.systemPrompt).toBeNull();
    expect(systemPromptLabel(profile)).toBe("varies (2)");
    expect(profile.referenceVariants).toBe(3);
    expect(profile.reference).toBeNull();
    expect(referenceLabel(profile)).toBe("varies (3)");
    expect(rangeLabel(profile.figures)).toBe("1–2");
  });

  it("counts a missing question as a variant of its own", () => {
    const profile = promptProfile([item({ question: "Is it good?" }, "Q1"), item({}, "Q2")]);
    expect(profile.questionVariants).toBe(2);
    expect(profile.question).toBeNull();
    expect(promptProfile([item({ question: "Q?" })]).question).toBe("Q?");
  });

  it("keeps the known size when a reference has no hash", () => {
    const profile = promptProfile([item({ knowledge_chars: 42 })]);
    expect(profile.reference).toEqual({ chars: 42, sha256: null });
    expect(referenceLabel(profile)).toBe("42 chars · hash unknown");
    expect(referenceLabel(promptProfile([item({})]))).toBe("none");
  });

  it("says when nothing was recorded", () => {
    const profile = promptProfile([item({ figures: [] })]);
    expect(referenceLabel(profile)).toBe("none");
    expect(systemPromptLabel(profile)).toBe("not recorded");
    expect(referenceLabel(promptProfile([]))).toBe("-");
  });
});
