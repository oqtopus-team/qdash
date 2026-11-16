import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { parse } from "yaml";

import {
  COPILOT_PROFILE_ENV,
  CopilotProfileError,
  PROFILE_MODEL_FIELDS,
  resolveCopilotModelFiles,
  selectedCopilotProfile,
  validateCopilotProfileDocument,
} from "../src/copilot-profile.ts";
import { writeModelsConfig } from "../src/models-config.ts";

const REPO_COPILOT = new URL("../../config/copilot/", import.meta.url);
// The cases the API's tests/qdash/common/config/test_copilot_profile.py checks too.
const CASES = JSON.parse(
  readFileSync(new URL("../../tests/data/copilot_profile_cases.json", import.meta.url), "utf8"),
);

const ENDPOINTS = {
  OPENAI_COMPATIBLE_BASE_URL_CHAT: "http://chat.invalid/v1",
  OPENAI_COMPATIBLE_BASE_URL_EVALUATION: "http://evaluation.invalid/v1",
  // The endpoint of the shared cases' model entries.
  OPENAI_COMPATIBLE_BASE_URL_SITE: "http://site.invalid/v1",
};

const chat = (name) =>
  `chat_models:\n  - provider: openai-compatible-chat\n    name: ${name}\n    api_style: completion\n    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT\n`;
const evaluation = (name) =>
  `evaluation_models:\n  - provider: openai-compatible-evaluation\n    name: ${name}\n    api_style: completion\n    base_url: env:OPENAI_COMPATIBLE_BASE_URL_EVALUATION\n`;

function write(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

/** A config/copilot directory with default files and a `site` profile. */
function fixture() {
  const root = mkdtempSync(join(tmpdir(), "copilot-profile-"));
  const copilot = join(root, "copilot");
  write(join(copilot, "config.yaml"), "enabled: true\n");
  write(join(copilot, "chat.yaml"), chat("default-chat"));
  write(join(copilot, "evaluation.yaml"), evaluation("default-eval"));
  write(join(copilot, "profiles", "site", "chat.yaml"), chat("site-chat"));
  write(join(copilot, "profiles", "site", "evaluation.yaml"), evaluation("site-eval"));
  return {
    root,
    copilot,
    configPath: join(copilot, "config.yaml"),
    cleanup: () => rmSync(root, { recursive: true, force: true }),
  };
}

/** Generate models.json the way SharedRuntime.create does and list provider/model ids. */
function generate(env, configPath, outDir) {
  const files = resolveCopilotModelFiles(env, configPath);
  const { path } = writeModelsConfig(files, join(outDir, "models.json"), { ...ENDPOINTS, ...env });
  const { providers } = JSON.parse(readFileSync(path, "utf8"));
  return Object.entries(providers).flatMap(([provider, entry]) =>
    (entry.models ?? []).map((model) => `${provider}/${model.id}`),
  );
}

for (const value of [undefined, ""]) {
  test(`an ${value === undefined ? "unset" : "empty"} profile reads the default files`, () => {
    const dir = fixture();
    try {
      const env = value === undefined ? {} : { [COPILOT_PROFILE_ENV]: value };
      assert.deepEqual(resolveCopilotModelFiles(env, dir.configPath), {
        chatPath: join(dir.copilot, "chat.yaml"),
        evaluationPath: join(dir.copilot, "evaluation.yaml"),
      });
      assert.deepEqual(generate(env, dir.configPath, dir.root), [
        "openai-compatible-chat/default-chat",
        "openai-compatible-evaluation/default-eval",
      ]);
    } finally {
      dir.cleanup();
    }
  });
}

test("the default files keep a missing evaluation.yaml optional", () => {
  const dir = fixture();
  try {
    unlinkSync(join(dir.copilot, "evaluation.yaml"));
    assert.deepEqual(generate({}, dir.configPath, dir.root), ["openai-compatible-chat/default-chat"]);
  } finally {
    dir.cleanup();
  }
});

test("a named profile replaces both model files", () => {
  const dir = fixture();
  try {
    const env = { [COPILOT_PROFILE_ENV]: "site" };
    assert.deepEqual(resolveCopilotModelFiles(env, dir.configPath), {
      profile: "site",
      chatPath: join(dir.copilot, "profiles", "site", "chat.yaml"),
      evaluationPath: join(dir.copilot, "profiles", "site", "evaluation.yaml"),
    });
    assert.deepEqual(generate(env, dir.configPath, dir.root), [
      "openai-compatible-chat/site-chat",
      "openai-compatible-evaluation/site-eval",
    ]);
  } finally {
    dir.cleanup();
  }
});

test("a profile's chat and evaluation lists are independent of the defaults", () => {
  const dir = fixture();
  try {
    write(join(dir.copilot, "profiles", "split", "chat.yaml"), chat("split-chat"));
    write(join(dir.copilot, "profiles", "split", "evaluation.yaml"), "evaluation_models: []\n");
    assert.deepEqual(generate({ [COPILOT_PROFILE_ENV]: "split" }, dir.configPath, dir.root), [
      "openai-compatible-chat/split-chat",
    ]);
  } finally {
    dir.cleanup();
  }
});

test("*.local.yaml files are read neither by default nor in a profile", () => {
  const dir = fixture();
  try {
    write(join(dir.copilot, "chat.local.yaml"), chat("local-chat"));
    write(join(dir.copilot, "evaluation.local.yaml"), evaluation("local-eval"));
    write(join(dir.copilot, "profiles", "site", "chat.local.yaml"), chat("site-local-chat"));
    write(join(dir.copilot, "profiles", "site", "evaluation.local.yaml"), evaluation("site-local"));
    assert.deepEqual(generate({}, dir.configPath, dir.root), [
      "openai-compatible-chat/default-chat",
      "openai-compatible-evaluation/default-eval",
    ]);
    assert.deepEqual(generate({ [COPILOT_PROFILE_ENV]: "site" }, dir.configPath, dir.root), [
      "openai-compatible-chat/site-chat",
      "openai-compatible-evaluation/site-eval",
    ]);
  } finally {
    dir.cleanup();
  }
});

test("a missing profile fails instead of falling back", () => {
  const dir = fixture();
  try {
    assert.throws(
      () => resolveCopilotModelFiles({ [COPILOT_PROFILE_ENV]: "osaka" }, dir.configPath),
      (error) => error instanceof CopilotProfileError && /"osaka" not found/.test(error.message),
    );
  } finally {
    dir.cleanup();
  }
});

for (const missing of ["chat.yaml", "evaluation.yaml"]) {
  test(`a profile without ${missing} fails`, () => {
    const dir = fixture();
    try {
      unlinkSync(join(dir.copilot, "profiles", "site", missing));
      assert.throws(
        () => resolveCopilotModelFiles({ [COPILOT_PROFILE_ENV]: "site" }, dir.configPath),
        new RegExp(`missing .*${missing.replace(".", "\\.")}`),
      );
    } finally {
      dir.cleanup();
    }
  });
}

test("a profile with malformed YAML fails before models.json is written", () => {
  const dir = fixture();
  try {
    write(join(dir.copilot, "profiles", "site", "evaluation.yaml"), "evaluation_models: [\n");
    assert.throws(
      () => generate({ [COPILOT_PROFILE_ENV]: "site" }, dir.configPath, dir.root),
      (error) =>
        error instanceof CopilotProfileError && /cannot read Copilot profile file/.test(error.message),
    );
    assert.throws(() => readFileSync(join(dir.root, "models.json")), { code: "ENOENT" });
  } finally {
    dir.cleanup();
  }
});

test("a profile conflicts with the CHAT_CONFIG_PATH and EVALUATION_CONFIG_PATH overrides", () => {
  const dir = fixture();
  try {
    assert.throws(
      () =>
        resolveCopilotModelFiles(
          { [COPILOT_PROFILE_ENV]: "site", CHAT_CONFIG_PATH: "/elsewhere/chat.yaml" },
          dir.configPath,
        ),
      /conflicts with CHAT_CONFIG_PATH/,
    );
    // Without a profile the overrides still apply as before.
    assert.equal(
      resolveCopilotModelFiles({ CHAT_CONFIG_PATH: "/elsewhere/chat.yaml" }, dir.configPath).chatPath,
      "/elsewhere/chat.yaml",
    );
  } finally {
    dir.cleanup();
  }
});

for (const name of CASES.invalid_names) {
  test(`profile name ${JSON.stringify(name)} is rejected`, () => {
    const dir = fixture();
    try {
      assert.throws(
        () => resolveCopilotModelFiles({ [COPILOT_PROFILE_ENV]: name }, dir.configPath),
        (error) => error instanceof CopilotProfileError && /not a valid profile name/.test(error.message),
      );
    } finally {
      dir.cleanup();
    }
  });
}

test("valid profile names are accepted", () => {
  for (const name of CASES.valid_names) {
    assert.equal(selectedCopilotProfile({ [COPILOT_PROFILE_ENV]: name }), name);
  }
});

test("a profile directory that links out of profiles/ is refused", () => {
  const dir = fixture();
  try {
    const outside = join(dir.root, "outside");
    write(join(outside, "chat.yaml"), chat("outside-chat"));
    write(join(outside, "evaluation.yaml"), evaluation("outside-eval"));
    symlinkSync(outside, join(dir.copilot, "profiles", "escape"), "dir");
    assert.throws(
      () => resolveCopilotModelFiles({ [COPILOT_PROFILE_ENV]: "escape" }, dir.configPath),
      /resolves outside/,
    );
  } finally {
    dir.cleanup();
  }
});

for (const doc of CASES.documents) {
  test(`${doc.kind}.yaml document: ${doc.error ?? "valid"}`, () => {
    const data = parse(doc.yaml);
    if (doc.valid) {
      validateCopilotProfileDocument(doc.kind, data, `${doc.kind}.yaml`);
    } else {
      assert.throws(
        () => validateCopilotProfileDocument(doc.kind, data, `${doc.kind}.yaml`),
        (error) => error instanceof CopilotProfileError && error.message.includes(doc.error),
      );
    }
    // The same document through the generator.
    const dir = fixture();
    try {
      write(join(dir.copilot, "profiles", "site", `${doc.kind}.yaml`), doc.yaml);
      const run = () => generate({ [COPILOT_PROFILE_ENV]: "site" }, dir.configPath, dir.root);
      if (doc.valid) run();
      else {
        assert.throws(
          run,
          (error) => error instanceof CopilotProfileError && error.message.includes(doc.error),
        );
        assert.throws(() => readFileSync(join(dir.root, "models.json")), { code: "ENOENT" });
      }
    } finally {
      dir.cleanup();
    }
  });
}

for (const doc of CASES.unreadable_documents) {
  test(`unreadable ${doc.kind}.yaml ${JSON.stringify(doc.yaml)} fails before models.json is written`, () => {
    const dir = fixture();
    try {
      write(join(dir.copilot, "profiles", "site", `${doc.kind}.yaml`), doc.yaml);
      assert.throws(
        () => generate({ [COPILOT_PROFILE_ENV]: "site" }, dir.configPath, dir.root),
        (error) =>
          error instanceof CopilotProfileError && /cannot read Copilot profile file/.test(error.message),
      );
      assert.throws(() => readFileSync(join(dir.root, "models.json")), { code: "ENOENT" });
    } finally {
      dir.cleanup();
    }
  });
}

test("the profile model fields match the shared cases", () => {
  assert.deepEqual([...PROFILE_MODEL_FIELDS].sort(), CASES.model_fields);
});

for (const value of ["lots", "'4096'", "true", "4096.5", "0"]) {
  test(`max_output_tokens: ${value} in a profile fails with its location`, () => {
    const dir = fixture();
    try {
      const chatPath = join(dir.copilot, "profiles", "site", "chat.yaml");
      write(chatPath, `${chat("site-chat")}    max_output_tokens: ${value}\n`);
      assert.throws(
        () => generate({ [COPILOT_PROFILE_ENV]: "site" }, dir.configPath, dir.root),
        (error) =>
          error instanceof CopilotProfileError &&
          error.message.includes(`${chatPath}: chat_models[0].max_output_tokens must be`),
      );
      assert.throws(() => readFileSync(join(dir.root, "models.json")), { code: "ENOENT" });
    } finally {
      dir.cleanup();
    }
  });
}

test("the default files are not checked field by field", () => {
  const dir = fixture();
  try {
    write(join(dir.copilot, "chat.yaml"), `${chat("default-chat")}    max_output_tokens: lots\n    unknown_key: 1\n`);
    const { path } = writeModelsConfig(
      resolveCopilotModelFiles({}, dir.configPath),
      join(dir.root, "models.json"),
      ENDPOINTS,
    );
    const model = JSON.parse(readFileSync(path, "utf8")).providers["openai-compatible-chat"].models[0];
    assert.equal(model.maxTokens, 4096);
  } finally {
    dir.cleanup();
  }
});

test("every generation field of a valid profile reaches models.json", () => {
  const full = CASES.documents.find((doc) => doc.yaml.includes("strict_tool_schemas"));
  assert.equal(full.valid, true);
  const dir = fixture();
  try {
    write(join(dir.copilot, "profiles", "site", "chat.yaml"), full.yaml);
    const env = { [COPILOT_PROFILE_ENV]: "site" };
    const files = resolveCopilotModelFiles(env, dir.configPath);
    const { path } = writeModelsConfig(files, join(dir.root, "models.json"), { ...ENDPOINTS, ...env });
    const provider = JSON.parse(readFileSync(path, "utf8")).providers["openai-compatible-site"];
    assert.equal(provider.api, "openai-completions");
    assert.equal(provider.baseUrl, "http://site.invalid/v1");
    assert.equal(provider.apiKey, "$OPENAI_COMPATIBLE_API_KEY_SITE");
    assert.deepEqual(provider.models[0], {
      id: "m",
      contextWindow: 65536,
      maxTokens: 8192,
      reasoning: true,
      compat: {
        supportsStrictMode: true,
        promptCacheKeyMode: "enabled",
        requiresNonNullAssistantContent: true,
        requiresToolsWithToolHistory: false,
      },
      input: ["text", "image"],
      samplingParams: { min_p: 0, presence_penalty: 1.5, temperature: 0, top_p: 1, top_k: -1, keep_alive: "30m" },
      samplingParamsByThinkingLevel: { low: { temperature: 1 }, xhigh: { top_p: 0.95 } },
    });
  } finally {
    dir.cleanup();
  }
});

test("the committed riken profile serves Kimi for chat and evaluation", () => {
  const root = mkdtempSync(join(tmpdir(), "copilot-riken-"));
  try {
    const copilot = join(root, "copilot");
    cpSync(REPO_COPILOT, copilot, { recursive: true });
    const env = { [COPILOT_PROFILE_ENV]: "riken" };
    const files = resolveCopilotModelFiles(env, join(copilot, "config.yaml"));
    const { path } = writeModelsConfig(files, join(root, "models.json"), ENDPOINTS);
    const { providers } = JSON.parse(readFileSync(path, "utf8"));

    assert.deepEqual(Object.keys(providers).sort(), [
      "openai-compatible-chat",
      "openai-compatible-evaluation",
    ]);
    for (const [provider, suffix] of [
      ["openai-compatible-chat", "CHAT"],
      ["openai-compatible-evaluation", "EVALUATION"],
    ]) {
      const entry = providers[provider];
      assert.equal(entry.api, "openai-completions");
      assert.equal(entry.baseUrl, ENDPOINTS[`OPENAI_COMPATIBLE_BASE_URL_${suffix}`]);
      // A reference to the key's variable, never a value.
      assert.equal(entry.apiKey, `$OPENAI_COMPATIBLE_API_KEY_${suffix}`);
      assert.deepEqual(
        entry.models.map((model) => model.id),
        ["moonshotai/Kimi-K3"],
      );
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("the committed default files are what an unset profile generates from", () => {
  const configPath = new URL("config.yaml", REPO_COPILOT).pathname;
  const files = resolveCopilotModelFiles({}, configPath);
  const ids = (yaml, key) => parse(yaml)[key].map((model) => model.name);
  assert.deepEqual(
    ids(readFileSync(files.chatPath, "utf8"), "chat_models"),
    ids(readFileSync(new URL("chat.yaml", REPO_COPILOT), "utf8"), "chat_models"),
  );
  assert.deepEqual(
    ids(readFileSync(files.evaluationPath, "utf8"), "evaluation_models"),
    ids(readFileSync(new URL("evaluation.yaml", REPO_COPILOT), "utf8"), "evaluation_models"),
  );
});
