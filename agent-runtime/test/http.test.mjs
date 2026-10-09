import assert from "node:assert/strict";
import { test } from "node:test";

import { hasBearerToken, readJsonBody, RequestError } from "../src/http.ts";

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
