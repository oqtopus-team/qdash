import { describe, expect, it } from "vitest";

import { escapeRawHtml } from "@/lib/chatMarkdown";
import { balanceHighlightedLines } from "@/lib/highlight";

describe("escapeRawHtml", () => {
  it("escapes tags, comments and declarations in text", () => {
    expect(escapeRawHtml("a <b>bold</b> <!-- note --> <?php ?>")).toBe(
      "a \\<b>bold\\</b> \\<!-- note --> \\<?php ?>",
    );
  });

  it("leaves comparisons, autolinks and escaped brackets as they are", () => {
    const md = "x < 5 and 3<4, <https://a.example/x> <me@a.example> \\<b>";
    expect(escapeRawHtml(md)).toBe(md);
  });

  it("leaves code spans, fences, indented code and math untouched", () => {
    const md = [
      "Use ``a `<b>` c`` and `<i>`.",
      "",
      "```html\n<div>\n```",
      "",
      "    <pre>indented</pre>",
      "",
      "> ~~~\n> <span>\n> ~~~",
      "",
      "$a<b>c$ and $$\n<x>\n$$",
    ].join("\n");
    expect(escapeRawHtml(md)).toBe(md);
  });

  it("escapes tags in an indented list continuation", () => {
    expect(escapeRawHtml("- item\n\n    <b>more</b>")).toBe("- item\n\n    \\<b>more\\</b>");
  });

  it("keeps the tail of an unclosed code span while streaming", () => {
    expect(escapeRawHtml("Run `<cmd", { streaming: true })).toBe("Run `<cmd");
    expect(escapeRawHtml("Run `<cmd")).toBe("Run `\\<cmd");
  });

  it("keeps an angle-bracket link destination", () => {
    const md = "[doc](</path with space>)";
    expect(escapeRawHtml(md)).toBe(md);
  });
});

describe("balanceHighlightedLines", () => {
  it("closes and reopens spans at line breaks", () => {
    expect(balanceHighlightedLines('<span class="s">"a\nb"</span>\nc')).toBe(
      '<span class="s">"a</span>\n<span class="s">b"</span>\nc',
    );
  });
});
