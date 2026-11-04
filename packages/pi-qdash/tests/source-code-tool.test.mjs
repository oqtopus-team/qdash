import assert from "node:assert/strict";
import test from "node:test";

import { registerSourceCodeTools, searchMarkdown, sourceRootsMarkdown } from "../.test-dist/tools/source-code.js";

function registeredTools(client) {
  const tools = new Map();
  registerSourceCodeTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() { return client; },
  });
  return tools;
}

test("source tools are the three read-only source operations", () => {
  assert.deepEqual([...registeredTools({}).keys()], [
    "qdash_list_source_roots",
    "qdash_search_source",
    "qdash_read_source",
  ]);
});

test("roots state revisions and never claim a match with the execution", async () => {
  const tool = registeredTools({
    async listSourceRoots() {
      return {
        roots: [
          { name: "qdash", kind: "qdash", revision: "abc", revision_source: "git", dirty: true },
          { name: "qubex", kind: "dependency", version: "1.5.0" },
        ],
        missing_dependencies: ["qubecalib"],
        execution_revision_recorded: false,
      };
    },
  }).get("qdash_list_source_roots");
  const text = (await tool.execute("t", {})).content[0].text;
  assert.match(text, /qdash \(qdash\): revision abc \(from git\), with uncommitted local changes/);
  assert.match(text, /qubex \(dependency 1\.5\.0\): revision unknown/);
  assert.match(text, /Not available here: qubecalib/);
  assert.match(text, /cannot be shown to match/);
  assert.match(sourceRootsMarkdown({ roots: [] }), /No source is available/);
});

test("search forwards bounded options and lists root:path:line", async () => {
  const calls = [];
  const tool = registeredTools({
    async searchSource(options) {
      calls.push(options);
      return {
        query: options.query,
        mode: "content",
        matches: [{ root: "qdash", path: "workflow/engine/x.py", line: 12, text: "raise KeyError(qid)" }],
        truncated: true,
      };
    },
  }).get("qdash_search_source");
  const result = await tool.execute("t", { query: "KeyError", root: "qdash", pathPrefix: "workflow", limit: 5 });
  assert.deepEqual(calls, [{ query: "KeyError", root: "qdash", pathPrefix: "workflow", mode: undefined, caseSensitive: undefined, limit: 5 }]);
  assert.match(result.content[0].text, /- qdash:workflow\/engine\/x\.py:12 {2}raise KeyError\(qid\)/);
  assert.match(result.content[0].text, /stopped at the limit/);
});

test("read shows the range, revision and where to continue", async () => {
  const tool = registeredTools({
    async getSourceFile(options) {
      assert.deepEqual(options, { path: "/app/qdash/workflow/x.py", root: undefined, startLine: 1, endLine: undefined });
      return { root: "qdash", path: "workflow/x.py", start_line: 1, end_line: 400, total_lines: 900, content: "    1  import os", truncated: true, revision: null };
    },
  }).get("qdash_read_source");
  const text = (await tool.execute("t", { path: "/app/qdash/workflow/x.py", startLine: 1 })).content[0].text;
  assert.match(text, /^qdash:workflow\/x\.py lines 1-400 of 900 \(revision unknown\)/);
  assert.match(text, /read from line 401/);
});

test("a refused or missing file is reported, other errors propagate", async () => {
  const refusing = registeredTools({
    async getSourceFile() { const error = new Error("'.env' is not a readable source file"); error.statusCode = 403; throw error; },
    async searchSource() { const error = new Error("Unknown source root 'numpy'"); error.statusCode = 404; throw error; },
  });
  const read = await refusing.get("qdash_read_source").execute("t", { root: "qdash", path: ".env" });
  assert.match(read.content[0].text, /Source file unavailable: '\.env' is not a readable source file/);
  const search = await refusing.get("qdash_search_source").execute("t", { query: "x", root: "numpy" });
  assert.match(search.content[0].text, /Source search refused: Unknown source root/);

  const failing = registeredTools({
    async getSourceFile() { const error = new Error("server down"); error.statusCode = 503; throw error; },
  });
  await assert.rejects(failing.get("qdash_read_source").execute("t", { path: "x.py" }), /server down/);
});

for (const mode of ["content", "path"]) {
  test(`empty ${mode} search distinguishes incomplete and complete scans`, () => {
    const data = { query: "missing", mode, matches: [] };
    assert.match(searchMarkdown({ ...data, truncated: true }), /unsearched files may match/);
    assert.match(searchMarkdown({ ...data, truncated: true }), /Narrow root or pathPrefix/);
    assert.equal(searchMarkdown({ ...data, truncated: false }),
      `No ${mode === "path" ? "file paths" : "lines"} match \`missing\`.`);
  });
}
