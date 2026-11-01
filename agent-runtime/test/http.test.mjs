import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { hasBearerToken, readJsonBody, RequestError, runtimeToken } from "../src/http.ts";

async function* chunks(...values) {
  for (const value of values) yield Buffer.from(value);
}

test("readJsonBody parses a body split across chunks", async () => {
  assert.deepEqual(await readJsonBody(chunks('{"ok":', "true}"), 100), { ok: true });
});

test("readJsonBody rejects malformed JSON without exposing parser details", async () => {
  await assert.rejects(readJsonBody(chunks("{"), 100), (error) => {
    assert.ok(error instanceof RequestError);
    assert.equal(error.status, 400);
    assert.equal(error.message, "request body must be valid JSON");
    return true;
  });
});

test("readJsonBody rejects an oversized body while collecting chunks", async () => {
  await assert.rejects(readJsonBody(chunks("123", "456"), 5), (error) => {
    assert.ok(error instanceof RequestError);
    assert.equal(error.status, 413);
    return true;
  });
});

test("hasBearerToken requires the configured credential", () => {
  assert.equal(hasBearerToken(undefined, "secret"), false);
  assert.equal(hasBearerToken("Bearer wrong", "secret"), false);
  assert.equal(hasBearerToken("Bearer secret", undefined), false);
  assert.equal(hasBearerToken("Bearer secret", "secret"), true);
});


test("runtime credentials load from a file and fail closed when absent or empty", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "runtime-auth-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const path = join(directory, "token");
  const env = { AGENT_RUNTIME_TOKEN_FILE: path };
  assert.throws(() => runtimeToken(env));
  writeFileSync(path, "generated-secret\n");
  assert.equal(runtimeToken(env), "generated-secret");
  assert.equal(hasBearerToken("Bearer generated-secret", runtimeToken(env)), true);
  assert.equal(hasBearerToken("Bearer wrong", runtimeToken(env)), false);
  writeFileSync(path, "\n");
  assert.equal(hasBearerToken("Bearer ", runtimeToken(env)), false);
  assert.equal(runtimeToken({}), undefined);
  assert.equal(runtimeToken({ ...env, AGENT_RUNTIME_TOKEN: "explicit" }), "explicit");
});
