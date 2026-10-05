import assert from "node:assert/strict";
import { test } from "node:test";

import { sessionStorageName } from "../src/runtime.ts";

test("durable storage names are stable for one user session", () => {
  assert.equal(sessionStorageName("alice", "session-1"), sessionStorageName("alice", "session-1"));
});

test("the same browser session id is isolated between users", () => {
  assert.notEqual(sessionStorageName("alice", "shared"), sessionStorageName("bob", "shared"));
});

test("storage names cannot contain caller-controlled path segments", () => {
  assert.match(sessionStorageName("../alice", "../../session"), /^[a-f0-9]{64}\.sqlite$/);
});
