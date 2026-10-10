import assert from "node:assert/strict";
import { test } from "node:test";

import { readFile } from "node:fs/promises";
import { SharedRuntime, sessionStorageName } from "../src/runtime.ts";

test("durable storage names are stable for one user session", () => {
  assert.equal(sessionStorageName("alice", "session-1"), sessionStorageName("alice", "session-1"));
});

test("the same browser session id is isolated between users", () => {
  assert.notEqual(sessionStorageName("alice", "shared"), sessionStorageName("bob", "shared"));
});

test("storage names cannot contain caller-controlled path segments", () => {
  assert.match(sessionStorageName("../alice", "../../session"), /^[a-f0-9]{64}\.sqlite$/);
});

test("failure to open a harness removes its temporary credentials", async (t) => {
  const previous = process.env.QDASH_BASE_URL;
  process.env.QDASH_BASE_URL = "http://localhost:5715";
  t.after(() =>
    previous === undefined
      ? delete process.env.QDASH_BASE_URL
      : (process.env.QDASH_BASE_URL = previous),
  );
  let configPath;
  const runtime = new SharedRuntime(
    { getModel: () => ({ contextWindow: 8192, maxTokens: 1024 }) },
    (connection) => {
      configPath = connection.toolArgs.configPath;
      throw new Error("registry unavailable");
    },
    [],
    {},
  );
  await assert.rejects(
    runtime.openSession(
      { ownerId: "alice", sessionId: "s1", provider: "test", modelName: "test" },
      { accessToken: "alice-token" },
    ),
    /registry unavailable/,
  );
  await assert.rejects(readFile(configPath), { code: "ENOENT" });
});
