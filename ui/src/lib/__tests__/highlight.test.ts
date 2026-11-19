import { renderHook, cleanup } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

type HighlightModule = typeof import("@/lib/highlight");

/** A fresh copy of the module, so each test starts before Highlights has loaded. */
async function freshModule(): Promise<HighlightModule> {
  vi.resetModules();
  return import("@/lib/highlight");
}

/** The text a browser shows for highlighted HTML. */
function textOf(html: string): string {
  const element = document.createElement("code");
  element.innerHTML = html;
  return element.textContent ?? "";
}

function cssColors(html: string): string[] {
  return [...html.matchAll(/color:var\((--qd-code-[a-z-]+)\)/g)].map((match) => match[1]);
}

afterEach(() => {
  cleanup();
  vi.doUnmock("@pierre/highlights");
  vi.doUnmock("@pierre/diffs");
  vi.restoreAllMocks();
});

describe("highlightCode before Highlights loads", () => {
  it("uses highlight.js for its languages and plain text otherwise", async () => {
    const { highlightCode } = await freshModule();
    expect(highlightCode("x = 1  # note", "python")).toContain('class="hljs-comment"');
    expect(highlightCode("x", "zig")).toBeNull();
    expect(highlightCode("x", undefined)).toBeNull();
  });
});

describe("highlightCode with Highlights", () => {
  it("loads Highlights and colors tokens with the DaisyUI palette variables", async () => {
    const { highlightCode, loadHighlights } = await freshModule();
    await expect(loadHighlights()).resolves.toBe(true);

    const html = highlightCode('def run(q):\n    return "T1"  # done', "python")!;
    expect(html).not.toContain("hljs");
    expect(html).toContain(
      '<span style="color:var(--qd-code-keyword);font-weight:500">def </span>',
    );
    expect(html).toContain('<span style="color:var(--qd-code-string)">"T1"');
    expect(html).toContain("color:var(--qd-code-comment);font-style:italic");
    expect(textOf(html)).toBe('def run(q):\n    return "T1"  # done');
  });

  it("highlights QDash's common languages and their aliases", async () => {
    const { highlightCode, loadHighlights } = await freshModule();
    await loadHighlights();
    const samples: [string, string, string][] = [
      ["python", "py", "import numpy"],
      ["yaml", "yml", "qubit: Q00\nshots: 1024"],
      ["json", "jsonc", '{"t1": 25.3, "ok": true}'],
      ["sql", "sql", "SELECT * FROM task WHERE id = 1;"],
      ["bash", "sh", 'echo "$HOME" | grep q # x'],
      ["bash", "zsh", "export A=1"],
      ["bash", "console", "task check  # all checks"],
      ["typescript", "ts", "const t: number = 1;"],
      ["typescript", "tsx", "const a = <A b={1} />;"],
      ["javascript", "js", "let a = 1; // n"],
      ["markdown", "md", "# Title\n**bold** `code`"],
      ["toml", "toml", 'name = "qdash"'],
    ];
    for (const [language, alias, code] of samples) {
      for (const name of [language, alias, alias.toUpperCase()]) {
        const html = highlightCode(code, name);
        expect(html, name).not.toBeNull();
        expect(html, name).not.toContain("hljs");
        expect(textOf(html!), name).toBe(code);
      }
      // Each sample has at least one token colored beyond the foreground.
      const colors = cssColors(highlightCode(code, language)!);
      expect(
        colors.some((color) => color !== "--qd-code-foreground"),
        language,
      ).toBe(true);
    }
  });

  it("returns null for unknown languages", async () => {
    const { highlightCode, loadHighlights } = await freshModule();
    await loadHighlights();
    expect(highlightCode("x", "not-a-language")).toBeNull();
    expect(highlightCode("x", "")).toBeNull();
  });

  it("escapes HTML in the source", async () => {
    const { highlightCode, loadHighlights } = await freshModule();
    await loadHighlights();
    const code = "s = \"<script>alert(1)</script>\" & '<img onerror=x>'";
    const html = highlightCode(code, "python")!;
    expect(html).not.toMatch(/<script|<img/);
    expect(html).toContain("&lt;script&gt;");
    expect(textOf(html)).toBe(code);
    const plain = highlightCode("<b>&amp;</b>", "plain")!;
    expect(plain).toContain("&lt;b&gt;&amp;amp;&lt;/b&gt;");
  });

  it("gives the Words plugin balanced lines for multi-line strings and comments", async () => {
    const { getChatCodePlugin, loadHighlights } = await freshModule();
    const before = getChatCodePlugin();
    await loadHighlights();
    const plugin = getChatCodePlugin();
    expect(plugin).not.toBe(before);

    const code = 'x = """first\nsecond"""\n/* not a comment in python */\n';
    const html = plugin.highlight({
      code,
      language: "python",
      isIncomplete: false,
    })!;
    for (const line of html.split("\n")) {
      expect(line.match(/<span/g)?.length ?? 0).toBe(line.match(/<\/span>/g)?.length ?? 0);
    }
    // Both lines of the string keep the string color.
    const lines = html.split("\n");
    expect(lines[0]).toContain("--qd-code-string");
    expect(lines[1]).toContain("--qd-code-string");
    expect(textOf(html)).toBe(code);
  });

  it("streams an open fence through a Words session line by line", async () => {
    const { getChatCodePlugin, loadHighlights } = await freshModule();
    await loadHighlights();
    const session = getChatCodePlugin().createSession!();
    const first = session.highlightLines!({
      code: "x = 1\ny = 2\n",
      language: "py",
      isIncomplete: true,
    })!;
    expect(first.html).toContain("--qd-code-number");
    const next = session.highlightLines!({
      code: "x = 1\ny = 2\nz = 'three'\n",
      language: "py",
      isIncomplete: true,
    })!;
    // Finished lines are kept; highlighting resumes at the last line with content.
    expect(next.firstLine).toBe(1);
    expect(next.html).toContain("--qd-code-string");
    expect(textOf(next.fullHtml)).toBe("x = 1\ny = 2\nz = 'three'\n");
    expect(
      session.highlightLines!({
        code: "x",
        language: "nope",
        isIncomplete: true,
      }),
    ).toBeNull();
    session.dispose();
  });
});

describe("Highlights fallback", () => {
  it("keeps highlight.js where WebAssembly SIMD is unavailable", async () => {
    vi.doMock("@pierre/diffs", () => ({ canUseWASM: () => false }));
    const load = vi.fn();
    vi.doMock("@pierre/highlights", () => {
      load();
      return {};
    });
    const { highlightCode, loadHighlights, getChatCodePlugin } = await freshModule();
    await expect(loadHighlights()).resolves.toBe(false);
    expect(load).not.toHaveBeenCalled();
    expect(highlightCode("x = 1  # c", "python")).toContain("hljs-comment");
    expect(getChatCodePlugin().createSession).toBeUndefined();
  });

  it("keeps highlight.js when the WebAssembly module fails to initialize", async () => {
    vi.doMock("@pierre/highlights", () => {
      throw new WebAssembly.CompileError("WebAssembly.Module(): Wasm code generation disallowed");
    });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { highlightCode, loadHighlights } = await freshModule();
    await expect(loadHighlights()).resolves.toBe(false);
    expect(warn).toHaveBeenCalledWith(
      "Highlights is unavailable; using highlight.js for code.",
      expect.anything(),
    );
    expect(highlightCode("x = 1  # c", "python")).toContain("hljs-comment");
    // The failure is remembered: no retry on every mount.
    await expect(loadHighlights()).resolves.toBe(false);
    expect(warn).toHaveBeenCalledTimes(1);
  });
});

describe("Highlights palette", () => {
  it("defines every palette variable for chat prose and CodeBlock in globals.css", async () => {
    const { CODE_THEME, CODE_COLOR_PREFIX } = await freshModule();
    const css = readFileSync(resolve(__dirname, "../../app/globals.css"), "utf8");
    const block = /\.chat-prose,\s*\.qd-code\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    const defined = new Set([...block.matchAll(/(--qd-code-[a-z-]+):/g)].map((match) => match[1]));
    const used = new Set(
      Object.values(CODE_THEME.style.syntax ?? {}).map(
        (value) => CODE_COLOR_PREFIX + (typeof value === "string" ? value : value.color),
      ),
    );
    expect([...used].filter((name) => !defined.has(name))).toEqual([]);
    // Colors come from the DaisyUI theme, so switching theme recolors without highlighting again.
    expect(block).toContain("--qd-code-keyword: var(--color-primary)");
  });
});

it("does not load Highlights for prose until code appears", async () => {
  const canUseWASM = vi.fn(() => false);
  vi.doMock("@pierre/diffs", () => ({ canUseWASM }));
  const { useCodeHighlighter } = await freshModule();
  const { rerender } = renderHook(({ enabled }) => useCodeHighlighter(enabled), {
    initialProps: { enabled: false },
  });
  expect(canUseWASM).not.toHaveBeenCalled();
  rerender({ enabled: true });
  expect(canUseWASM).toHaveBeenCalledTimes(1);
});
