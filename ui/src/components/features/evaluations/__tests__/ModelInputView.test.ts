import { describe, expect, it } from "vitest";

import { modelInputParts } from "../ModelInputView";

const fig = (sha256: string, path?: string) => ({
  sha256,
  mime_type: "image/png",
  bytes: 10,
  ...(path ? { path } : {}),
});

describe("modelInputParts", () => {
  it("puts each example figure, then the figure to judge, where the prompt marked it", () => {
    const parts = modelInputParts(
      {
        prompt: [
          "Reference for this experiment:",
          "## Experiment: CheckT1",
          "",
          "Example 1 of 1:",
          "[figure]",
          "Diagnosis of example 1:",
          "Outcome: suboptimal",
          "Experiment context:",
          "ctx",
          "[figure]",
        ].join("\n"),
        figures: [fig("query")],
        examples: [
          {
            id: "short-t1",
            title: "Short T1",
            outcome: "suboptimal",
            figures: [fig("ex", "examples/figures/t1.png")],
          },
        ],
      },
      ["/calib/fig/CheckT1_5_0.png"],
    );

    expect(parts.map((part) => part.type)).toEqual(["text", "figure", "text", "figure"]);
    expect(parts[0]).toEqual({
      type: "text",
      text: "Reference for this experiment:\n## Experiment: CheckT1\n\nExample 1 of 1:",
    });
    const example = parts[1].type === "figure" ? parts[1].slot : null;
    expect(example).toMatchObject({
      kind: "example",
      exampleIndex: 0,
      path: "examples/figures/t1.png",
      sha256: "ex",
    });
    const query = parts[3].type === "figure" ? parts[3].slot : null;
    expect(query).toMatchObject({
      kind: "query",
      index: 0,
      path: "/calib/fig/CheckT1_5_0.png",
      sha256: "query",
    });
  });

  it("a zero-shot prompt is its text then the figure to judge", () => {
    const parts = modelInputParts(
      { prompt: "Experiment context:\nctx\n[figure]", figures: [fig("q")], examples: [] },
      [],
    );
    expect(parts.map((part) => part.type)).toEqual(["text", "figure"]);
    expect(parts[1].type === "figure" && parts[1].slot?.path).toBeNull();
  });

  it("a marker the record cannot match stays an unnamed slot; no marker means no figure", () => {
    const parts = modelInputParts(
      { prompt: "a\n[figure]\nb\n[figure]", figures: [fig("q")], examples: [] },
      ["p"],
    );
    expect(
      parts
        .filter((part) => part.type === "figure")
        .map((part) => part.type === "figure" && part.slot?.kind),
    ).toEqual(["query", undefined]);
  });

  it("a record from before figure markers gets its figures after the text, where they were sent", () => {
    const parts = modelInputParts(
      { prompt: "Experiment context:\nctx", figures: [fig("q1"), fig("q2")], examples: [] },
      ["a.png", "b.png"],
    );
    expect(parts.map((part) => part.type)).toEqual(["text", "figure", "figure"]);
    expect(parts[2].type === "figure" && parts[2].slot?.path).toBe("b.png");
  });
});
