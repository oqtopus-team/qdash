import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderMermaid, resetMermaidCache } from "@/lib/chatMermaid";

type Call = { kind: "initialize"; config: Record<string, unknown> } | { kind: "render" };

const mermaid = vi.hoisted(() => ({
  calls: [] as Call[],
  rendering: 0,
  overlapped: false,
  initialize: vi.fn(),
  render: vi.fn(),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

const SRC_DIR = resolve(__dirname, "../..");
const SKIPPED_DIRS = new Set(["client", "schemas", "node_modules", "__tests__"]);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      return SKIPPED_DIRS.has(entry.name) ? [] : sourceFiles(join(dir, entry.name));
    }
    return /\.tsx?$/.test(entry.name) ? [join(dir, entry.name)] : [];
  });
}

beforeEach(() => {
  resetMermaidCache();
  mermaid.calls = [];
  mermaid.rendering = 0;
  mermaid.overlapped = false;
  mermaid.initialize.mockReset();
  mermaid.initialize.mockImplementation((config: Record<string, unknown>) => {
    mermaid.calls.push({ kind: "initialize", config });
  });
  mermaid.render.mockReset();
  mermaid.render.mockImplementation(async (_id: string, source: string) => {
    mermaid.calls.push({ kind: "render" });
    if (mermaid.rendering > 0) mermaid.overlapped = true;
    mermaid.rendering += 1;
    // Yield so a concurrent caller would get a chance to interleave.
    await new Promise((resolve) => setTimeout(resolve, 5));
    mermaid.rendering -= 1;
    return {
      svg: `<svg><a href="https://example.com" onclick="alert(1)"><text>${source}</text></a></svg>`,
    };
  });
});

describe("renderMermaid", () => {
  it("serializes interleaved chat and non-chat renders, each under its own strict config", async () => {
    const results = await Promise.all([
      renderMermaid("graph TD\n A-->B", "default", { links: "keep" }),
      renderMermaid("graph TD\n C-->D", "neutral"),
      renderMermaid("graph TD\n E-->F", "default", { links: "keep" }),
      renderMermaid("graph TD\n G-->H", "dark"),
    ]);

    expect(mermaid.overlapped).toBe(false);
    // Every render is directly preceded by the initialize for that render's theme.
    expect(
      mermaid.calls.map((call) => (call.kind === "render" ? "render" : call.config.theme)),
    ).toEqual(["default", "render", "neutral", "render", "default", "render", "dark", "render"]);
    for (const call of mermaid.calls) {
      if (call.kind !== "initialize") continue;
      expect(call.config).toMatchObject({
        securityLevel: "strict",
        startOnLoad: false,
        suppressErrorRendering: true,
      });
    }
    expect(results.every((result) => result.status === "ok")).toBe(true);
  });

  it("initializes before every render, even when the config has not changed", async () => {
    await renderMermaid("graph TD\n A-->B", "neutral");
    await renderMermaid("graph TD\n C-->D", "neutral");
    expect(mermaid.initialize).toHaveBeenCalledTimes(2);
    expect(mermaid.render).toHaveBeenCalledTimes(2);
  });

  it("strips link targets for chat and keeps them elsewhere, removing handlers in both", async () => {
    const chat = await renderMermaid("graph TD\n A-->B", "neutral");
    const other = await renderMermaid("graph TD\n A-->B", "default", {
      links: "keep",
    });
    if (chat.status !== "ok" || other.status !== "ok") throw new Error("render failed");

    expect(chat.svg).not.toContain("href");
    expect(other.svg).toContain('href="https://example.com"');
    expect(chat.svg).not.toContain("onclick");
    expect(other.svg).not.toContain("onclick");
  });

  it("caches chat and non-chat results separately", async () => {
    await renderMermaid("graph TD\n A-->B", "default");
    await renderMermaid("graph TD\n A-->B", "default", { links: "keep" });
    await renderMermaid("graph TD\n A-->B", "default", { links: "keep" });
    expect(mermaid.render).toHaveBeenCalledTimes(2);
  });

  it("reports a failed render and keeps the queue going", async () => {
    mermaid.render.mockRejectedValueOnce(new Error("Parse error on line 2"));
    const [failed, next] = await Promise.all([
      renderMermaid("graph TD\n A--", "default", { links: "keep" }),
      renderMermaid("graph TD\n A-->B", "neutral"),
    ]);
    expect(failed).toEqual({
      status: "error",
      message: "Parse error on line 2",
    });
    expect(next.status).toBe("ok");
  });

  it("is the only module that loads Mermaid", () => {
    const loaders = sourceFiles(SRC_DIR)
      .filter((file) => /(from|import\()\s*["']mermaid["']/.test(readFileSync(file, "utf8")))
      .map((file) => relative(SRC_DIR, file));
    expect(loaders).toEqual(["lib/chatMermaid.ts"]);
  });
});
