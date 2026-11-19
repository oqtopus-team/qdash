import mermaid from "mermaid";
import { beforeEach, describe, expect, it } from "vitest";

import { renderMermaid, resetMermaidCache } from "@/lib/chatMermaid";

beforeEach(() => resetMermaidCache());

// Uses the real Mermaid: its config handling is what keeps a diagram from loosening it.
describe("renderMermaid config", () => {
  it("ignores directives that try to loosen the locked settings", async () => {
    // jsdom cannot lay out SVG, so the render itself may fail; the config is
    // already applied by then.
    await renderMermaid(
      '%%{init: {"securityLevel": "loose", "suppressErrorRendering": false, "startOnLoad": true, "secure": []}}%%\ngraph TD\n  A-->B',
      "default",
      { links: "keep" },
    );
    expect(mermaid.mermaidAPI.getConfig()).toMatchObject({
      securityLevel: "strict",
      suppressErrorRendering: true,
      startOnLoad: false,
    });
  });

  it("does not carry a diagram's directives into the next render", async () => {
    await renderMermaid('%%{init: {"theme": "forest"}}%%\ngraph TD\n  A-->B', "default", {
      links: "keep",
    });
    expect(mermaid.mermaidAPI.getConfig().theme).toBe("forest");

    await renderMermaid("graph TD\n  C-->D", "neutral");
    expect(mermaid.mermaidAPI.getConfig()).toMatchObject({
      theme: "neutral",
      securityLevel: "strict",
    });
  });
});
