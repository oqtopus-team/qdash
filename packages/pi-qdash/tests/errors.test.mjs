// The error message and HTTP status the tools read from a failure. Each caller keeps its own
// status policy: the agent-loop and session-end tools read only the SDK's statusCode, the
// pipeline tools fall back to status, and the paused-session check lets a present status win.
import assert from "node:assert/strict";
import test from "node:test";

import { pausedSessionConflict } from "../.test-dist/lib/agent-loop.js";
import { errorText, sdkStatusCode, statusCodeOrStatus } from "../.test-dist/lib/errors.js";

test("a failure's text is an Error's message, else the value as text", () => {
  assert.equal(errorText(new Error("boom")), "boom");
  assert.equal(errorText("plain"), "plain");
  assert.equal(errorText(404), "404");
});

test("the SDK status code ignores a status field", () => {
  assert.equal(sdkStatusCode(Object.assign(new Error("x"), { statusCode: 404 })), 404);
  assert.equal(sdkStatusCode({ status: 503 }), undefined);
  assert.equal(sdkStatusCode({ statusCode: 409, status: 500 }), 409);
  assert.equal(sdkStatusCode({ statusCode: "404" }), undefined);
  assert.equal(sdkStatusCode(null), undefined);
  assert.equal(sdkStatusCode(undefined), undefined);
});

test("the pipeline status prefers statusCode and falls back to a numeric status", () => {
  assert.equal(statusCodeOrStatus({ statusCode: 404 }), 404);
  assert.equal(statusCodeOrStatus({ status: 503 }), 503);
  assert.equal(statusCodeOrStatus({ statusCode: 409, status: 500 }), 409);
  assert.equal(statusCodeOrStatus({ statusCode: "409", status: 500 }), 500);
  assert.equal(statusCodeOrStatus({ statusCode: "404" }), undefined);
  assert.equal(statusCodeOrStatus(null), undefined);
  assert.equal(statusCodeOrStatus("404"), undefined);
});

test("the paused-session check reads a present status before statusCode", async () => {
  const failing = (fields) => ({
    async listAgentSessions() { throw Object.assign(new Error("list failed"), fields); },
  });
  const predates = /cannot list agent sessions \(HTTP (\d+);/;
  const unknown = /could not tell whether one of your agent sessions on chip 64Qv3 is paused for an expert \(list failed\)/;
  const conflict = (fields) => pausedSessionConflict(failing(fields), "64Qv3", ["0"]);

  assert.match(await conflict({ statusCode: 404 }), predates);
  // A status alone counts, unlike in the agent-loop and session-end tools.
  assert.equal((await conflict({ status: 405 })).match(predates)[1], "405");
  // Both present: status wins, even over a statusCode that would be read as unsupported.
  assert.equal((await conflict({ status: 404, statusCode: 500 })).match(predates)[1], "404");
  assert.match(await conflict({ status: 500, statusCode: 404 }), unknown);
  // A present non-numeric status hides a numeric statusCode.
  assert.match(await conflict({ status: "failed", statusCode: 404 }), unknown);
  assert.match(await conflict({ status: null, statusCode: 404 }), predates);
});
