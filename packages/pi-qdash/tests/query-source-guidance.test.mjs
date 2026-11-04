import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";

import qdashExtension from "../.test-dist/qdash.js";
import { looksLikeSourcePath, readSourceArguments } from "../.test-dist/lib/source-guidance.js";

const EXECUTOR = "qdash/workflow/engine/task/executor.py";

/** A QDash API whose config directory holds one file, named like a source root on purpose. */
async function fakeQDash(t, { fileContentStatus } = {}) {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    requests.push(`${url.pathname}${url.search}`);
    const send = (status, body) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    };
    if (url.pathname === "/files/tree") return send(200, [{ name: "qubex-config.yaml", path: "qubex-config.yaml", type: "file" }]);
    if (url.pathname === "/files/content") {
      const path = url.searchParams.get("path");
      if (fileContentStatus) return send(fileContentStatus, { detail: `config API failed with ${fileContentStatus}` });
      if (path === "qubex-config.yaml" || path === "qdash/chip.yaml") return send(200, { content: "chip_id: 64Qv3\n", path });
      if (path.startsWith("/")) return send(400, { detail: "Path outside allowed directory" });
      return send(404, { detail: `File not found: ${path}` });
    }
    if (url.pathname === "/copilot/source/file") {
      if (url.searchParams.get("path") !== EXECUTOR) return send(404, { detail: "Could not tell which source root the path belongs to; pass root" });
      return send(200, {
        root: "qdash",
        path: "workflow/engine/task/executor.py",
        start_line: 1,
        end_line: 2,
        total_lines: 900,
        content: "    1  \"\"\"Task executor.\"\"\"\n    2  from __future__ import annotations",
        truncated: false,
        revision: null,
      });
    }
    if (url.pathname === "/copilot/source/roots") return send(200, { roots: [], missing_dependencies: ["qubex"], execution_revision_recorded: false });
    return send(404, { detail: "unexpected" });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const previous = { QDASH_BASE_URL: process.env.QDASH_BASE_URL, QDASH_API_TOKEN: process.env.QDASH_API_TOKEN };
  process.env.QDASH_BASE_URL = `http://127.0.0.1:${server.address().port}`;
  process.env.QDASH_API_TOKEN = "test-token";
  t.after(() => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  const tools = new Map();
  qdashExtension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on() {}, appendEntry() {} });
  const run = (name, params) => tools.get(name).execute("t", { useEnv: true, ...params });
  return { tools, requests, run };
}

test("the user's file_content request for source names the qdash_read_source call to make", async (t) => {
  const { run, requests } = await fakeQDash(t);
  const result = await run("qdash_query", { action: "file_content", path: EXECUTOR });
  const text = result.content[0].text;
  assert.deepEqual(requests, [`/files/content?path=${encodeURIComponent(EXECUTOR)}`]);
  assert.match(text, /not a config file \(config file API: 404 \/files\/content: File not found/);
  assert.match(text, /serve only the calibration config directory/);
  assert.match(text, /Do not retry file_content for source/);
  assert.ok(text.includes(`qdash_read_source {"path":"${EXECUTOR}"}`));
  assert.equal(result.details.misdirected, true);

  // Following the guidance through the registered source tool reads the file.
  const read = await run("qdash_read_source", JSON.parse(text.match(/qdash_read_source (\{.*\})/)[1]));
  assert.match(read.content[0].text, /^qdash:workflow\/engine\/task\/executor\.py lines 1-2 of 900 \(revision unknown\)/);
  assert.match(read.content[0].text, /Task executor/);
});

test("a traceback path rejected by the config API also gets source guidance", async (t) => {
  const { run } = await fakeQDash(t);
  const text = (await run("qdash_query", { action: "file_content", path: "/app/qdash/workflow/engine/task/executor.py" })).content[0].text;
  assert.match(text, /config file API: 400 \/files\/content: Path outside allowed directory/);
  assert.ok(text.includes('qdash_read_source {"path":"/app/qdash/workflow/engine/task/executor.py"}'));
});

test("config file_content reads are unchanged, including a config path named qdash", async (t) => {
  const { run } = await fakeQDash(t);
  for (const path of ["qubex-config.yaml", "qdash/chip.yaml"]) {
    const result = await run("qdash_query", { action: "file_content", path });
    assert.equal(result.details.misdirected, undefined);
    assert.equal(JSON.parse(result.content[0].text).content, "chip_id: 64Qv3\n");
  }
});

test("a missing config file that is not source still fails as before", async (t) => {
  const { run } = await fakeQDash(t);
  await assert.rejects(run("qdash_query", { action: "file_content", path: "missing.yaml" }), /File not found: missing\.yaml/);
});

for (const status of [403, 500]) {
  test(`HTTP ${status} from the config API is not turned into guidance`, async (t) => {
    const { run } = await fakeQDash(t, { fileContentStatus: status });
    await assert.rejects(run("qdash_query", { action: "file_content", path: EXECUTOR }), new RegExp(`config API failed with ${status}`));
  });
}

test("the user's files_tree request with a source path is not silently answered with the config tree", async (t) => {
  const { run, requests } = await fakeQDash(t);
  const result = await run("qdash_query", { action: "files_tree", path: "/app/qdash" });
  const text = result.content[0].text;
  assert.deepEqual(requests, []);
  assert.match(text, /files_tree does not take a path and cannot list `\/app\/qdash`/);
  assert.match(text, /Call files_tree without path to list the config directory/);
  assert.ok(text.includes('qdash_search_source {"root":"qdash","mode":"path","query":".py"}'));
  assert.match(text, /qdash_list_source_roots/);
  assert.equal(result.details.misdirected, true);
});

test("files_tree without a path still lists the config directory", async (t) => {
  const { run, requests } = await fakeQDash(t);
  const result = await run("qdash_query", { action: "files_tree" });
  assert.deepEqual(requests, ["/files/tree"]);
  assert.equal(JSON.parse(result.content[0].text)[0].name, "qubex-config.yaml");
});

test("the query tool tells the model which tool reads source", async (t) => {
  const { tools } = await fakeQDash(t);
  const query = tools.get("qdash_query");
  assert.match(query.parameters.properties.path.description, /calibration config directory\. Not source code; read QDash or qubex source with qdash_read_source\. files_tree takes no path/);
  assert.ok(query.promptGuidelines.some((line) => line.includes("files_tree and file_content cover only the calibration config directory")
    && line.includes(`qdash_read_source {"path":"${EXECUTOR}"}`)));
  for (const name of ["qdash_list_source_roots", "qdash_search_source", "qdash_read_source"]) assert.ok(tools.has(name), name);
});

test("source path recognition and read arguments", () => {
  for (const path of [EXECUTOR, "/app/qdash", "workflow/engine/x.py", "lib/python3.11/site-packages/qubex/y.yaml", "qubex/z"]) {
    assert.ok(looksLikeSourcePath(path), path);
  }
  for (const path of ["qubex-config.yaml", "64Qv3/params/qubit.yaml", "", undefined]) assert.ok(!looksLikeSourcePath(path), String(path));
  assert.deepEqual(readSourceArguments(EXECUTOR), { path: EXECUTOR });
  assert.deepEqual(readSourceArguments("workflow/engine/x.py"), { root: "qdash", path: "workflow/engine/x.py" });
});
