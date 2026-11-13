import assert from "node:assert/strict";
import test from "node:test";

import { toFigureToolResult, toTextToolResult } from "../.test-dist/lib/results.js";

test("an image figure is returned to the model as image content after the text", () => {
  const result = toFigureToolResult(
    "figure summary",
    { base64: "AAAA", mediaType: "image/png" },
    { path: "a.png" },
    { tool: "qdash_get_figure" },
  );
  assert.deepEqual(result.content, [
    { type: "text", text: "figure summary" },
    { type: "image", data: "AAAA", mimeType: "image/png" },
  ]);
  assert.equal(result.details.tool, "qdash_get_figure");
  assert.deepEqual(result.details.data, { path: "a.png" });
});

test("a JSON figure or a missing image stays text-only", () => {
  const json = toFigureToolResult("json", { text: "{}", mediaType: "application/json" }, {}, {});
  assert.deepEqual(json.content, [{ type: "text", text: "json" }]);
  const missing = toFigureToolResult("none", { mediaType: "image/png" }, {}, {});
  assert.deepEqual(missing.content, toTextToolResult("none", {}, {}).content);
});
