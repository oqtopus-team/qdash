import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { chmod, mkdir, mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { connect } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createCodingTools } from "@earendil-works/pi-durable/tools";
import { localDaemon } from "@earendil-works/pi-env";

import { integer, startExecServer, workspaceUid } from "../exec/server.ts";
import { ownerUid, workspaceName } from "../exec/protocol.ts";
import { ExecWorkspace, removeWorkspace, WORKSPACE_TOOL_NAMES } from "../src/exec-env.ts";

const daemon = localDaemon();
const canRun = process.platform === "linux" && existsSync(daemon);
// bun's node:test treats a test given both options and a `t` argument as callback style.
const live = canRun ? test : test.skip;

/** A server on a private Unix socket with a disposable workspace root. */
async function startServer(t, isolateUsers = false) {
  const root = await mkdtemp(join(tmpdir(), "agent-exec-"));
  if (isolateUsers) await chmod(root, 0o755);
  const logs = [];
  const server = await startExecServer({
    socketPath: join(root, "run", "exec.sock"),
    workspaceRoot: join(root, "workspace"),
    daemon,
    isolateUsers,
    log: (message) => logs.push(message),
  });
  t.after(async () => {
    await server.close();
    await rm(root, { recursive: true, force: true });
  });
  return { root, logs, config: { socketPath: server.socketPath, workspaceRoot: join(root, "workspace") } };
}

test("entries that are not owner directories do not block uid allocation", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "agent-exec-uids-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  // A stray file, and a directory owned outside the reserved range (this test's own uid).
  await writeFile(join(root, "README"), "");
  await mkdir(join(root, "lost+found"));
  assert.equal(workspaceUid(root, "alice"), ownerUid("alice"));
});

test("the socket group comes from the environment with a default for a blank value", () => {
  assert.equal(integer(undefined, 1000), 1000);
  assert.equal(integer("", 1000), 1000);
  assert.equal(integer("1234", 1000), 1234);
  assert.throws(() => integer("root", 1000), /non-negative integer/);
});

test("the coding tools are the four the workspace advertises", () => {
  const names = createCodingTools().tools.map((tool) => tool.name).sort();
  assert.deepEqual(names, [...WORKSPACE_TOOL_NAMES]);
});

live("a conversation gets its own directory and runs commands there through the relay", async (t) => {
  const { root, config, logs } = await startServer(t);
  const workspace = new ExecWorkspace(config, "alice", "session-1", (message) => logs.push(message));
  t.after(() => workspace.close());
  const env = await workspace.env();
  assert.equal(env.cwd, workspace.cwd);
  assert.ok(workspace.cwd.startsWith(root));

  let output = "";
  const run = await env.exec("pwd && echo \"$HOME\" && env | grep -c ^COPILOT_ || true", {
    onOutput: (text) => (output += text),
  }, BACKGROUND_CONTEXT);
  assert.ok(run.ok, JSON.stringify(run));
  assert.equal(run.value.exitCode, 0);
  const [cwd, home, inherited] = output.trim().split("\n");
  assert.equal(cwd, workspace.cwd);
  assert.equal(home, join(config.workspaceRoot, workspace.cwd.split("/").at(-2)));
  // The daemon's environment is the server's minimal one, never the runtime's.
  assert.equal(inherited, "0");

  const written = await env.writeFile(join(workspace.cwd, "data.csv"), "a,b\n1,2\n", BACKGROUND_CONTEXT);
  assert.ok(written.ok);
  assert.equal(await readFile(join(workspace.cwd, "data.csv"), "utf8"), "a,b\n1,2\n");
  const read = await env.readTextFile("data.csv", BACKGROUND_CONTEXT);
  assert.ok(read.ok && read.value === "a,b\n1,2\n");

  // Another conversation of the same owner shares the owner directory but not the session's.
  const sibling = new ExecWorkspace(config, "alice", "session-2", () => {});
  t.after(() => sibling.close());
  const siblingEnv = await sibling.env();
  assert.notEqual(siblingEnv.cwd, env.cwd);
  const missing = await siblingEnv.exists("data.csv", BACKGROUND_CONTEXT);
  assert.ok(missing.ok && missing.value === false);

  await removeWorkspace(config, "alice", "session-1", () => {});
  assert.equal(existsSync(join(workspace.cwd, "data.csv")), false);
  assert.ok(logs.some((line) => line.includes("daemon for alice-")));
});

live("the server closes a connection whose hello is not the relay's", async (t) => {
  const { config, logs } = await startServer(t);
  const closedBy = (line) =>
    new Promise((resolve) => {
      const socket = connect({ path: config.socketPath }, () => socket.write(line));
      socket.on("data", () => resolve("answered"));
      socket.on("close", () => resolve("closed"));
      socket.on("error", () => resolve("closed"));
    });
  assert.equal(await closedBy("not json\n"), "closed");
  assert.equal(await closedBy(`${JSON.stringify({ owner: "x", argv: ["sh", "-c", "id"] })}\n`), "closed");
  assert.equal(await closedBy("x".repeat(5000)), "closed");
  assert.equal(logs.filter((line) => line.includes("refused")).length, 3);
});

live("the socket and its parent exclude workspace users", async (t) => {
  const { root, config } = await startServer(t);
  assert.equal((await stat(config.socketPath)).mode & 0o777, 0o660);
  assert.equal((await stat(join(root, "run"))).mode & 0o777, 0o750);
});

const rootLive = canRun && process.getuid?.() === 0 ? test : test.skip;
rootLive("isolated users cannot impersonate owners or read a colliding owner's files", async (t) => {
  const { config } = await startServer(t, true);
  const first = new ExecWorkspace(config, "user79", "s1", () => {});
  const second = new ExecWorkspace(config, "user974", "s2", () => {});
  t.after(() => { first.close(); second.close(); });
  const firstEnv = await first.env();
  const secondEnv = await second.env();
  const secret = join(first.cwd, "private.txt");
  assert.ok((await firstEnv.writeFile(secret, "private", BACKGROUND_CONTEXT)).ok);
  assert.equal((await secondEnv.readTextFile(secret, BACKGROUND_CONTEXT)).ok, false);
  const firstUid = (await stat(join(config.workspaceRoot, workspaceName("user79")))).uid;
  const secondUid = (await stat(join(config.workspaceRoot, workspaceName("user974")))).uid;
  assert.notEqual(firstUid, secondUid);
  // No in-memory registry: reconnects and restarts recover the persisted uid.
  assert.equal(workspaceUid(config.workspaceRoot, "user974"), secondUid);
  let output = "";
  const probe = `const s = require("node:net").connect(${JSON.stringify(config.socketPath)}); s.on("connect", () => { console.log("connected"); s.destroy(); }); s.on("error", e => console.log(e.code));`;
  const binary = `'${process.execPath.replaceAll("'", "'\\''")}'`;
  const run = await secondEnv.exec(`${binary} -e '${probe}'`, { onOutput: text => output += text }, BACKGROUND_CONTEXT);
  assert.ok(run.ok);
  assert.match(output, /EACCES/);
});
