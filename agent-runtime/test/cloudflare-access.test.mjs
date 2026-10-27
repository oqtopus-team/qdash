import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { buildModelsConfig } from "../src/models-config.ts";

for (const apiStyle of ["completion", "responses"]) {
  test(`Pi sends Access and origin authentication over ${apiStyle} for chat and evaluation`, async (t) => {
    const requests = [];
    const server = Bun.serve({
      port: 0,
      hostname: "127.0.0.1",
      fetch(request) {
        requests.push({ url: request.url, headers: request.headers });
        // Stop after request capture; no model server or external credentials are needed.
        return Response.json({ error: { message: "Request captured", type: "test" } }, { status: 401 });
      },
    });
    t.after(() => server.stop(true));
    const directory = mkdtempSync(join(tmpdir(), "cloudflare-models-"));
    t.after(() => rmSync(directory, { recursive: true, force: true }));
    const env = {
      CF_ACCESS_CLIENT_ID: "shared-client.access",
      CF_ACCESS_CLIENT_SECRET: "shared-secret",
    };
    const yaml = (kind, suffix) => {
      env[`OPENAI_COMPATIBLE_BASE_URL_${suffix}`] = `${server.url}v1`;
      // Evaluation exercises Access-only authentication without an origin API key.
      if (suffix === "CHAT") env[`OPENAI_COMPATIBLE_API_KEY_${suffix}`] = "origin-key";
      return `${kind}_models:
  - provider: openai-compatible-${kind}
    name: test-model
    api_style: ${apiStyle}
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_${suffix}
    api_key_env: OPENAI_COMPATIBLE_API_KEY_${suffix}
`;
    };
    const chat = yaml("chat", "CHAT");
    const evaluation = yaml("evaluation", "EVALUATION");
    const modelsPath = join(directory, "models.json");
    writeFileSync(modelsPath, JSON.stringify(buildModelsConfig(chat, evaluation, env)));
    const runtime = await ModelRuntime.create({
      modelsPath,
      authPath: join(directory, "auth.json"),
      modelsStorePath: join(directory, "models-store.json"),
    });
    assert.equal(runtime.getError(), undefined);
    for (const kind of ["chat", "evaluation"]) {
      const model = runtime.getModel(`openai-compatible-${kind}`, "test-model");
      assert.ok(model);
      const auth = await runtime.getAuth(model, { env });
      assert.equal(auth.auth.headers["CF-Access-Client-Id"], "shared-client.access");
      await runtime.complete(model, {
        messages: [{ role: "user", content: "test", timestamp: Date.now() }],
      }, { env, maxTokens: 1 });
      const request = requests.at(-1);
      assert.ok(request);
      assert.equal(request.headers.get("CF-Access-Client-Id"), "shared-client.access");
      assert.equal(request.headers.get("CF-Access-Client-Secret"), "shared-secret");
      assert.equal(request.headers.get("Authorization"), `Bearer ${kind === "chat" ? "origin-key" : "openai-compatible"}`);
      assert.equal(new URL(request.url).pathname, apiStyle === "responses" ? "/v1/responses" : "/v1/chat/completions");
    }
    assert.equal(requests.length, 2);
  });
}
