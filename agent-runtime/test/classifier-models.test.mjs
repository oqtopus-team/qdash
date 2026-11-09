import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  classifierModelsFrom,
  configureClassifierModels,
  readClassifierConfig,
  selectClassifierModel,
} from "../src/classifier-models.ts";

function fakeRuntime({ providers = [], catalog = [], auth = [] } = {}) {
  const registered = [];
  return {
    registered,
    getProvider: (id) => (providers.includes(id) || registered.some((p) => p.id === id) ? {} : undefined),
    registerNativeProvider: (provider) => registered.push(provider),
    getModelOfType: (_type, provider, id) =>
      catalog.includes(`${provider}/${id}`) || registered.some((p) => p.id === provider) ? {} : undefined,
    hasConfiguredAuth: (provider) => auth.includes(provider),
  };
}
function capturedLog() {
  const lines = [];
  const push = (line) => lines.push(line);
  return { lines, log: { log: push, warn: push, error: push } };
}

const endpointEntry = `  - provider: system-one-classifier
    name: ZefanCai/Open-Jev-2B
    base_url: env:CLASSIFIER_BASE_URL
    api_key_env: CLASSIFIER_API_KEY
`;
const env = {
  CLASSIFIER_BASE_URL: "https://classifier.example/jev/v1",
  CLASSIFIER_API_KEY: "secret-token-value",
};

test("classifier_models: order, aliases, endpoints and errors", () => {
  assert.deepEqual(classifierModelsFrom(undefined), []);
  assert.deepEqual(classifierModelsFrom("# nothing\n"), []);
  assert.deepEqual(
    classifierModelsFrom(`classifier_models:\n${endpointEntry}  - provider: bedrock\n    name: m\n`),
    [
      {
        provider: "system-one-classifier",
        name: "ZefanCai/Open-Jev-2B",
        endpoint: { baseUrl: "env:CLASSIFIER_BASE_URL", apiKeyEnv: "CLASSIFIER_API_KEY" },
      },
      { provider: "amazon-bedrock", name: "m" },
    ],
  );
  const bad = (yaml, pattern) => assert.throws(() => classifierModelsFrom(`classifier_models:\n${yaml}`), pattern);
  bad("  - provider: typesafe\n", /classifier_models\[0\] needs `provider` and `name`/);
  bad("  - provider: t\n    name: m\n    api_key_env: K\n", /api_key_env needs base_url/);
  // An endpoint never takes a pi provider's id, so it cannot replace or fall through to one.
  bad(endpointEntry.replace("system-one-classifier", "typesafe"), /must be system-one or start with system-one-/);
  bad(endpointEntry.replace("    api_key_env: CLASSIFIER_API_KEY\n", ""), /api_key_env must name/);
  bad(endpointEntry.replace("env:CLASSIFIER_BASE_URL", "ftp://x"), /base_url must be env:NAME or an http\(s\) URL/);
  // A feature's thresholds do not belong to the model.
  bad(`${endpointEntry}    min_probability: 0.6\n`, /unknown keys min_probability/);
  bad(`${endpointEntry}${endpointEntry}`, /lists system-one-classifier\/ZefanCai\/Open-Jev-2B twice/);
  bad(`${endpointEntry}${endpointEntry.replace("Open-Jev-2B", "Other")}`, /names more than one endpoint/);
  assert.throws(() => classifierModelsFrom("classifier_models: {}\n"), /must be a list/);
});

test("declared models are set up without any feature, and secrets are never logged", () => {
  const runtime = fakeRuntime({ catalog: ["typesafe/jev-latest"], auth: ["typesafe"] });
  const { lines, log } = capturedLog();
  const models = configureClassifierModels(
    `classifier_models:\n${endpointEntry}  - provider: typesafe\n    name: jev-latest\n`,
    runtime,
    env,
    log,
  );
  assert.equal(models.declared.length, 2);
  assert.equal(models.unavailable.size, 0);
  assert.deepEqual(runtime.registered.map((p) => p.id), ["system-one-classifier"]);
  assert.ok(runtime.getModelOfType("classifier", "system-one-classifier", "ZefanCai/Open-Jev-2B"));
  assert.doesNotMatch(lines.join("\n"), /secret-token-value|classifier\.example/);
  // Any feature may pick a model: the first by default, or one it names.
  assert.equal(selectClassifierModel(models).model.provider, "system-one-classifier");
  assert.equal(selectClassifierModel(models, { provider: "typesafe", name: "jev-latest" }).model.name, "jev-latest");
});

test("an unusable model is reported, not registered, and never replaced by another provider", () => {
  const yaml = `classifier_models:\n${endpointEntry}`;
  const check = (runtime, environment, pattern) => {
    const { lines, log } = capturedLog();
    const models = configureClassifierModels(yaml, runtime, environment, log);
    assert.equal(runtime.registered.length, 0);
    assert.match(selectClassifierModel(models).error, pattern);
    assert.doesNotMatch(lines.join("\n"), /secret-token-value|classifier\.example/);
  };
  check(fakeRuntime(), { CLASSIFIER_BASE_URL: env.CLASSIFIER_BASE_URL }, /CLASSIFIER_API_KEY not set/);
  check(fakeRuntime(), { CLASSIFIER_API_KEY: "secret-token-value" }, /CLASSIFIER_BASE_URL not set/);
  // Half a Cloudflare Access token is an error, as for chat endpoints.
  check(fakeRuntime(), { ...env, CF_ACCESS_CLIENT_ID: "id" }, /Cloudflare Access requires both/);
  check(fakeRuntime({ providers: ["system-one-classifier"] }), env, /already exists/);

  const catalog = `classifier_models:\n  - provider: typesafe\n    name: jev-latest\n`;
  assert.match(
    selectClassifierModel(configureClassifierModels(catalog, fakeRuntime(), {}, capturedLog().log)).error,
    /not in the model catalog/,
  );
  assert.match(
    selectClassifierModel(
      configureClassifierModels(catalog, fakeRuntime({ catalog: ["typesafe/jev-latest"] }), {}, capturedLog().log),
    ).error,
    /no credentials for typesafe/,
  );
});

test("classifier.yaml is optional", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "classifier-config-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  assert.equal(readClassifierConfig(join(directory, "classifier.yaml")), undefined);
  const { lines, log } = capturedLog();
  const models = configureClassifierModels(undefined, fakeRuntime(), {}, log);
  assert.deepEqual(models.declared, []);
  assert.deepEqual(lines, []);
  writeFileSync(join(directory, "classifier.yaml"), "classifier_models: []\n");
  assert.equal(readClassifierConfig(join(directory, "classifier.yaml")), "classifier_models: []\n");
});
