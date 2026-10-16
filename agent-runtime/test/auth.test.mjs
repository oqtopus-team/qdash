import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname } from "node:path";
import { test } from "node:test";
import qdashExtension from "@oqtopus-team/pi-qdash/extensions/qdash.ts";
import { createQDashConnection, requestQDashAuth } from "../src/auth.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";
import { buildPythonTool } from "../src/python-tool.ts";

function installedTools() {
  const tools = new Map();
  qdashExtension({
    registerTool: (definition) => tools.set(definition.name, { definition }),
    registerCommand() {},
    on() {},
  });
  return [{ tools }];
}

function setEnvironment(t, values) {
  const previous = Object.keys(values).map((key) => [key, process.env[key]]);
  Object.assign(process.env, values);
  t.after(() =>
    previous.forEach(([key, value]) =>
      value === undefined ? delete process.env[key] : (process.env[key] = value),
    ),
  );
}

test("missing user credentials never fall back to an ambient administrator token", async (t) => {
  setEnvironment(t, { QDASH_API_TOKEN: "ambient-admin" });
  assert.throws(() => requestQDashAuth({}), /user token is required/);
  assert.throws(() => requestQDashAuth({ "x-qdash-token": ["a", "b"] }), /user token is required/);
  await assert.rejects(createQDashConnection({ accessToken: "" }), /user token is required/);
});

test("real pi-qdash reads, approved writes and Python calls keep concurrent users isolated", async (t) => {
  const requests = [];
  let denyWrites = false;
  const server = createServer(async (req, res) => {
    for await (const _chunk of req) {
      /* drain */
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
    requests.push({
      token: req.headers.authorization,
      project: req.headers["x-project-id"],
      path: req.url,
      method: req.method,
    });
    if (denyWrites && req.method === "POST") {
      res.writeHead(403, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "Insufficient permissions" }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ chips: [], total: 0, id: "post-1", output: "ok" }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  setEnvironment(t, {
    QDASH_BASE_URL: `http://127.0.0.1:${server.address().port}`,
    QDASH_API_TOKEN: "ambient-admin",
    QDASH_PROJECT_ID: "ambient-project",
  });
  const connections = await Promise.all(
    ["alice", "bob"].map((user) =>
      createQDashConnection({
        accessToken: `${user}-token`,
        projectId: `${user}-project`,
      }),
    ),
  );
  t.after(() => Promise.all(connections.map((connection) => connection.close())));
  assert.notEqual(connections[0].toolArgs.configPath, connections[1].toolArgs.configPath);
  for (const connection of connections) {
    assert.equal((await stat(connection.toolArgs.configPath)).mode & 0o777, 0o600);
    assert.equal((await stat(dirname(connection.toolArgs.configPath))).mode & 0o777, 0o700);
  }
  const extensions = installedTools();
  const context = { abortSignal: new AbortController().signal };
  const results = await Promise.all(
    connections.map(async (connection) => {
      const { extension, writeTools } = buildQDashExtension(
        extensions,
        {},
        "/tmp",
        connection,
        true,
      );
      const read = extension.tools.find((tool) => tool.name === "qdash_list_chips");
      for (const tool of extension.tools) {
        for (const hidden of ["configPath", "profile", "useEnv", "confirmWrite"]) {
          assert.equal(hidden in tool.parameters.properties, false);
        }
      }
      // Old durable entries or a model may still supply connection overrides.
      const override = {
        configPath: "/nonexistent/admin.ini",
        profile: "admin",
        useEnv: true,
      };
      const readResult = await read.execute(override, { callId: "read" }, context);
      assert.equal(readResult.isError, undefined);
      const write = extension.tools.find((tool) => tool.name === "qdash_create_forum_post");
      const requested = await write.execute(
        {
          ...override,
          title: "Question",
          content: "Details",
          confirmWrite: true,
        },
        { callId: "write" },
        context,
      );
      assert.equal(requested.details.approval.args.configPath, undefined);
      await writeTools.runApproved({
        ...requested.details.approval,
        args: { ...requested.details.approval.args, ...override },
      });
      await buildPythonTool(connection).execute({ code: "result = {'output': 'ok'}" }, {}, context);
      return [readResult, requested];
    }),
  );
  for (const user of ["alice", "bob"]) {
    const own = requests.filter((request) => request.token === `Bearer ${user}-token`);
    assert.equal(own.length, 3);
    assert.ok(own.every((request) => request.project === `${user}-project`));
    assert.equal(own.filter((request) => request.method === "POST").length, 2);
  }
  assert.equal(requests.length, 6);
  assert.equal(process.env.QDASH_API_TOKEN, "ambient-admin");
  assert.equal(process.env.QDASH_PROJECT_ID, "ambient-project");
  assert.ok(!JSON.stringify(results).includes("alice-token"));
  assert.ok(!JSON.stringify(results).includes("bob-token"));
  denyWrites = true;
  const { writeTools } = buildQDashExtension(extensions, {}, "/tmp", connections[1], true);
  await assert.rejects(
    writeTools.runApproved({
      id: "denied",
      tool: "qdash_create_forum_post",
      label: "Create post",
      args: { title: "Question", content: "Details" },
    }),
    /403|Insufficient permissions/,
  );
  assert.equal(requests.length, 7);
  assert.equal(requests.at(-1).token, "Bearer bob-token");

  const noProject = await createQDashConnection({ accessToken: "alice-token" });
  try {
    const { extension } = buildQDashExtension(extensions, {}, "/tmp", noProject);
    await extension.tools
      .find((tool) => tool.name === "qdash_list_chips")
      .execute({}, { callId: "read" }, context);
    assert.equal(requests.at(-1).project, undefined);
  } finally {
    await noProject.close();
  }
  for (const connection of connections) {
    await connection.close();
    await assert.rejects(readFile(connection.toolArgs.configPath), {
      code: "ENOENT",
    });
  }
});
