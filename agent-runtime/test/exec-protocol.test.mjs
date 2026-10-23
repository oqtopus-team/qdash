import assert from "node:assert/strict";
import { test } from "node:test";

import { ownerUid, parseHello, UID_BASE, UID_SPAN, workspaceName } from "../exec/protocol.ts";
import { execConfigFromEnv, workspacePath } from "../src/exec-env.ts";

test("a hello is accepted only in the exact shape the relay sends", () => {
  const token = "0123456789abcdef0123456789abcdef";
  const hello = parseHello(JSON.stringify({ owner: "alice", argv: ["serve", "--token", token] }));
  assert.deepEqual(hello, { owner: "alice", argv: ["serve", "--token", token] });
  for (const bad of [
    "not json",
    "[]",
    JSON.stringify({ owner: "", argv: ["serve", "--token", token] }),
    JSON.stringify({ owner: "alice", argv: ["serve", "--token", "nothex"] }),
    JSON.stringify({ owner: "alice", argv: ["serve", "--token", token, "--extra"] }),
    JSON.stringify({ owner: "alice", argv: ["sh", "-c", token] }),
    JSON.stringify({ owner: "a".repeat(257), argv: ["serve", "--token", token] }),
  ]) {
    assert.equal(parseHello(bad), undefined, bad);
  }
});

test("workspace names are filename-safe, stable, and distinct for distinct ids", () => {
  assert.match(workspaceName("alice"), /^alice-[0-9a-f]{12}$/);
  assert.equal(workspaceName("alice"), workspaceName("alice"));
  assert.notEqual(workspaceName("alice"), workspaceName("alice "));
  assert.match(workspaceName("../etc/passwd"), /^_+etc_passwd-[0-9a-f]{12}$/);
  assert.match(workspaceName("x".repeat(100)), /^x{32}-[0-9a-f]{12}$/);
  assert.match(workspaceName("日本語"), /^_-[0-9a-f]{12}$/);
  assert.equal(workspacePath("/workspace", "alice", "s1"), `/workspace/${workspaceName("alice")}/${workspaceName("s1")}`);
});

test("owner uids are stable and stay inside the reserved range", () => {
  const uid = ownerUid("alice");
  assert.equal(uid, ownerUid("alice"));
  assert.ok(uid >= UID_BASE && uid < UID_BASE + UID_SPAN);
  assert.notEqual(uid, ownerUid("bob"));
});

test("hash collisions get a different available uid and exhaustion fails closed", () => {
  const first = ownerUid("user79");
  assert.equal(first, ownerUid("user974"));
  assert.notEqual(first, ownerUid("user974", new Set([first])));
  const full = new Set(Array.from({ length: UID_SPAN }, (_, i) => UID_BASE + i));
  assert.throws(() => ownerUid("alice", full), /exhausted/);
});

test("the workspace is configured only when a Unix socket is set", () => {
  assert.equal(execConfigFromEnv({}), undefined);
  assert.deepEqual(execConfigFromEnv({ AGENT_EXEC_SOCKET: "/run/agent-exec/exec.sock" }), {
    socketPath: "/run/agent-exec/exec.sock",
    workspaceRoot: "/workspace",
  });
  assert.equal(execConfigFromEnv({ AGENT_EXEC_HOST: "old-tcp-host" }), undefined);
});
