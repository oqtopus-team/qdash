import { describe, expect, it } from "vitest";

import { normalizeMathDelimiters } from "../ChatMarkdown";

describe("normalizeMathDelimiters", () => {
  it("rewrites inline \\( \\) math to dollars", () => {
    expect(normalizeMathDelimiters("T1 is \\(T_1 = 45\\,\\mu s\\).")).toBe(
      "T1 is $T_1 = 45\\,\\mu s$.",
    );
  });

  it("rewrites \\[ \\] math to a display block", () => {
    expect(normalizeMathDelimiters("Fit:\\[ y = e^{-t/T_1} \\]done")).toBe(
      "Fit:\n$$\ny = e^{-t/T_1}\n$$\ndone",
    );
  });

  it("leaves code spans and fences untouched", () => {
    const md = "`\\(x\\)` and\n```python\nprint('\\[a\\]')\n```\n";
    expect(normalizeMathDelimiters(md)).toBe(md);
  });

  it("leaves an unterminated fence untouched while streaming", () => {
    const md = "```python\nre.match(r'\\(\\d+\\)', s)";
    expect(normalizeMathDelimiters(md)).toBe(md);
  });
});
