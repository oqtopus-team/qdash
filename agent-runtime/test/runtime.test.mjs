import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { readFile } from "node:fs/promises";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { SharedRuntime, sessionStorageName, warnModelsJsonError } from "../src/runtime.ts";

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

import { chatSystemPromptOf } from "../src/runtime.ts";

test("the system prompt shown in Settings is QDash's text plus the user's tagged section", () => {
  const shown = chatSystemPromptOf("You are QDash Agent.", ["run_python", "ask_user"], "  Use tables. ");
  assert.equal(shown.system_prompt, "You are QDash Agent.");
  assert.match(shown.user_preferences, /^<user-preferences>\n[\s\S]*Use tables\.\n<\/user-preferences>$/);
  assert.deepEqual(shown.tools, ["ask_user", "run_python"]);
  assert.equal(chatSystemPromptOf("x", [], "   ").user_preferences, null);
});

test("warnModelsJsonError reports startup models.json errors and stays silent when valid", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-models-err-"));
  try {
    const modelsPath = join(dir, "models.json");
    const authPath = join(dir, "auth.json");
    writeFileSync(modelsPath, "{not valid json", "utf8");
    const brokenRuntime = await ModelRuntime.create({ modelsPath, authPath, refreshOnCreate: false });
    const warnings = [];
    const error = warnModelsJsonError(brokenRuntime, (message) => warnings.push(message));
    assert.ok(error);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /^\[agent-runtime\] models\.json error: /);

    writeFileSync(modelsPath, JSON.stringify({ providers: {} }), "utf8");
    const validRuntime = await ModelRuntime.create({ modelsPath, authPath, refreshOnCreate: false });
    const cleanWarnings = [];
    assert.equal(warnModelsJsonError(validRuntime, (message) => cleanWarnings.push(message)), undefined);
    assert.deepEqual(cleanWarnings, []);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
