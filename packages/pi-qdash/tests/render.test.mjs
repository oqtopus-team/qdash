// Shared text helpers: the fitted boxes the figure and wiring tools print.
import assert from "node:assert/strict";
import test from "node:test";

import { figureAnalysisText } from "../.test-dist/lib/figure-analysis.js";
import { figureResultText, mediaTypeForPath } from "../.test-dist/lib/figures.js";
import { plainBox, simpleBox, stripAnsi } from "../.test-dist/lib/render.js";

/** The box figures.ts and figure-analysis.ts each drew before they shared `plainBox`. */
function previousPlainBox(title, body) {
  const rawLines = [` ${title} `, ...body];
  const width = Math.min(100, Math.max(...rawLines.map((line) => line.length), title.length + 4));
  const top = `╭${` ${title} `.padEnd(width, "─")}╮`;
  const bottom = `╰${"─".repeat(width)}╯`;
  return [top, ...body.map((line) => `│ ${line.padEnd(width - 2)} │`), bottom];
}

test("a plain box draws exactly as the figure tools did, never clipping a line", () => {
  for (const [title, body] of [
    ["T", []],
    ["T", ["ab", "abcdef"]],
    ["QDash Figure", ["path /fig/a.png", "type image/png", "size 12 bytes", "", '  {"data": []}']],
    ["QDash Figure Analysis", ["x".repeat(140), "short"]],
  ]) {
    assert.deepEqual(plainBox(title, body), previousPlainBox(title, body));
  }
  assert.equal(plainBox("T", ["x".repeat(140)])[1], `│ ${"x".repeat(140)} │`);
  // ANSI codes count toward a plain box's width, as they did; the wiring box leaves them out.
  const escaped = ["\u001b[31mred\u001b[0m line"];
  assert.deepEqual(plainBox("Fig", escaped), previousPlainBox("Fig", escaped));
  assert.notDeepEqual(plainBox("Fig", escaped), simpleBox("Fig", escaped));
});

test("a colored fitted box measures lines without their ANSI codes", () => {
  const colored = simpleBox("Wiring", ["\u001b[31mred\u001b[0m line"], true);
  assert.deepEqual(colored.map(stripAnsi), simpleBox("Wiring", ["red line"]));
  assert.ok(colored[0].includes("\u001b[1;36m Wiring \u001b[0m"));
});

test("the figure and figure-analysis texts keep their boxes", () => {
  const details = { tool: "qdash_get_figure", path: "/fig/a.png", mediaType: "image/png", sizeBytes: 12, taskId: "t-1" };
  assert.equal(
    figureResultText(details),
    previousPlainBox("QDash Figure", ["path /fig/a.png", "type image/png", "size 12 bytes", "task t-1"]).join("\n"),
  );
  assert.equal(
    figureAnalysisText({ path: "p.json", traceCount: 0, summaries: [], warnings: [] }),
    previousPlainBox("QDash Figure Analysis", ["path p.json", "traces 0", "", "Summaries", "", "Warnings", "  - none"]).join("\n"),
  );
});

test("a figure's media type follows its extension", () => {
  assert.equal(mediaTypeForPath("/a/B.JPEG"), "image/jpeg");
  assert.equal(mediaTypeForPath("/a/b.json"), "application/json");
  assert.equal(mediaTypeForPath("/a/b"), "application/octet-stream");
});
