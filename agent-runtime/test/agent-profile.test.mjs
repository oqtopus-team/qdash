import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { parse } from "yaml";

import {
  AGENT_PROFILE_ENV,
  AgentProfileError,
  PROFILE_MODEL_FIELDS,
  resolveAgentConfigPaths,
  resolveAgentModelFiles,
  selectedAgentProfile,
  validateAgentProfileDocument,
} from "../src/agent-profile.ts";
import { loadLanguageConfig } from "../src/config.ts";
import { writeModelsConfig } from "../src/models-config.ts";

const REPO_AGENT = new URL("../../config/agent/", import.meta.url);
// The cases the API's tests/qdash/common/config/test_agent_profile.py checks too.
const CASES = JSON.parse(
  readFileSync(new URL("../../tests/data/agent_profile_cases.json", import.meta.url), "utf8"),
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

/** A config/agent directory with default files and a `site` profile. */
function fixture() {
  const root = mkdtempSync(join(tmpdir(), "agent-profile-"));
  const agent = join(root, "agent");
  write(join(agent, "config.yaml"), "enabled: true\n");
  write(join(agent, "chat.yaml"), chat("default-chat"));
  write(join(agent, "evaluation.yaml"), evaluation("default-eval"));
  write(join(agent, "profiles", "site", "chat.yaml"), chat("site-chat"));
  write(join(agent, "profiles", "site", "evaluation.yaml"), evaluation("site-eval"));
  return {
    root,
    agent,
    configPath: join(agent, "config.yaml"),
    cleanup: () => rmSync(root, { recursive: true, force: true }),
  };
}

/** Generate models.json the way SharedRuntime.create does and list provider/model ids. */
function generate(env, configPath, outDir) {
  const files = resolveAgentModelFiles(env, configPath);
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
      const env = value === undefined ? {} : { [AGENT_PROFILE_ENV]: value };
      assert.deepEqual(resolveAgentModelFiles(env, dir.configPath), {
        chatPath: join(dir.agent, "chat.yaml"),
        evaluationPath: join(dir.agent, "evaluation.yaml"),
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

for (const testCase of CASES.renamed_env) {
  test(`renamed profile variable: ${JSON.stringify(testCase.env)}`, () => {
    const warnings = [];
    const select = () => selectedAgentProfile(testCase.env, (message) => warnings.push(message));
    if (testCase.error) {
      assert.throws(select, (error) => error instanceof AgentProfileError && error.message.includes(testCase.error));
    } else {
      assert.equal(select(), testCase.profile ?? undefined);
    }
  });
}

test("AGENT_CONFIG_PATH and its legacy name COPILOT_CONFIG_PATH name config.yaml", () => {
  const dir = fixture();
  try {
    const warnings = [];
    const resolve = (env) => resolveAgentConfigPaths(env, dir.root, (message) => warnings.push(message));
    assert.deepEqual(resolve({}), {
      configPath: join(dir.agent, "config.yaml"),
      classifierPath: join(dir.agent, "classifier.yaml"),
    });
    assert.equal(resolve({ AGENT_CONFIG_PATH: "" }).configPath, join(dir.agent, "config.yaml"));
    assert.equal(resolve({ AGENT_CONFIG_PATH: "/new/config.yaml" }).configPath, "/new/config.yaml");
    assert.deepEqual(warnings, []);
    // A caller-supplied legacy path is used as given, not rewritten to agent/.
    assert.equal(
      resolve({ COPILOT_CONFIG_PATH: "/app/config/copilot/config.yaml" }).configPath,
      "/app/config/copilot/config.yaml",
    );
    assert.match(warnings.join("\n"), /COPILOT_CONFIG_PATH is deprecated/);
    assert.equal(
      resolve({ AGENT_CONFIG_PATH: "/same.yaml", COPILOT_CONFIG_PATH: "/same.yaml" }).configPath,
      "/same.yaml",
    );
    assert.throws(
      () => resolve({ AGENT_CONFIG_PATH: "/new.yaml", COPILOT_CONFIG_PATH: "/old.yaml" }),
      /AGENT_CONFIG_PATH="\/new.yaml" conflicts with the legacy COPILOT_CONFIG_PATH/,
    );
    assert.equal(resolve({ CLASSIFIER_CONFIG_PATH: "/c.yaml" }).classifierPath, "/c.yaml");
  } finally {
    dir.cleanup();
  }
});

for (const testCase of CASES.config_paths) {
  test(`config paths (${testCase.layout ?? "agent"}): ${JSON.stringify(testCase.env)}`, () => {
    // The API's test_config_paths_select_the_files_the_runtime_reads checks the same cases.
    const root = mkdtempSync(join(tmpdir(), "agent-config-paths-"));
    const warnings = [];
    const consoleWarn = console.warn;
    console.warn = (...args) => warnings.push(args.join(" "));
    try {
      for (const [relative, content] of Object.entries(CASES.config_path_files)) {
        write(join(root, relative), content);
      }
      if (testCase.layout === "legacy") {
        renameSync(join(root, "config", "agent"), join(root, "config", "copilot"));
      }
      const env = Object.fromEntries(
        Object.entries(testCase.env).map(([name, value]) => [name, value.replaceAll("{root}", root)]),
      );
      // Resolve and load the way SharedRuntime.create does.
      const load = () => {
        const { configPath } = resolveAgentConfigPaths(env, join(root, "config"), (message) =>
          warnings.push(message),
        );
        const { responseLanguage } = loadLanguageConfig(configPath);
        return { responseLanguage, models: generate(env, configPath, root) };
      };
      if (testCase.error) {
        assert.throws(load, (error) => error instanceof AgentProfileError && error.message.includes(testCase.error));
        return;
      }
      const { responseLanguage, models } = load();
      assert.equal(responseLanguage, testCase.language);
      assert.deepEqual(models, [
        ...testCase.chat.map((name) => `openai-compatible-chat/${name}`),
        ...testCase.evaluation.map((name) => `openai-compatible-evaluation/${name}`),
      ]);
      if (testCase.warning) assert.match(warnings.join("\n"), new RegExp(testCase.warning));
    } finally {
      console.warn = consoleWarn;
      rmSync(root, { recursive: true, force: true });
    }
  });
}

test("a configuration root with only the legacy copilot directory is read from there", () => {
  const dir = fixture();
  try {
    const legacy = join(dir.root, "copilot");
    cpSync(dir.agent, legacy, { recursive: true });
    rmSync(dir.agent, { recursive: true });
    const warnings = [];
    const paths = resolveAgentConfigPaths({}, dir.root, (message) => warnings.push(message));
    assert.deepEqual(paths, {
      configPath: join(legacy, "config.yaml"),
      classifierPath: join(legacy, "classifier.yaml"),
    });
    assert.match(warnings.join("\n"), /copilot is deprecated/);
    assert.equal(resolveAgentModelFiles({}, paths.configPath).chatPath, join(legacy, "chat.yaml"));
  } finally {
    dir.cleanup();
  }
});

test("a profile left under the legacy copilot directory is named in the error", () => {
  const dir = fixture();
  try {
    write(join(dir.root, "copilot", "profiles", "lab", "chat.yaml"), chat("lab-chat"));
    assert.throws(
      () => resolveAgentModelFiles({ [AGENT_PROFILE_ENV]: "lab" }, dir.configPath),
      /not found: .* move .*copilot\/profiles\/lab there/,
    );
  } finally {
    dir.cleanup();
  }
});

test("the default files keep a missing evaluation.yaml optional", () => {
  const dir = fixture();
  try {
    unlinkSync(join(dir.agent, "evaluation.yaml"));
    assert.deepEqual(generate({}, dir.configPath, dir.root), ["openai-compatible-chat/default-chat"]);
  } finally {
    dir.cleanup();
  }
});

test("a named profile replaces both model files", () => {
  const dir = fixture();
  try {
    const env = { [AGENT_PROFILE_ENV]: "site" };
    assert.deepEqual(resolveAgentModelFiles(env, dir.configPath), {
      profile: "site",
      chatPath: join(dir.agent, "profiles", "site", "chat.yaml"),
      evaluationPath: join(dir.agent, "profiles", "site", "evaluation.yaml"),
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
    write(join(dir.agent, "profiles", "split", "chat.yaml"), chat("split-chat"));
    write(join(dir.agent, "profiles", "split", "evaluation.yaml"), "evaluation_models: []\n");
    assert.deepEqual(generate({ [AGENT_PROFILE_ENV]: "split" }, dir.configPath, dir.root), [
      "openai-compatible-chat/split-chat",
    ]);
  } finally {
    dir.cleanup();
  }
});

test("*.local.yaml files are read neither by default nor in a profile", () => {
  const dir = fixture();
  try {
    write(join(dir.agent, "chat.local.yaml"), chat("local-chat"));
    write(join(dir.agent, "evaluation.local.yaml"), evaluation("local-eval"));
    write(join(dir.agent, "profiles", "site", "chat.local.yaml"), chat("site-local-chat"));
    write(join(dir.agent, "profiles", "site", "evaluation.local.yaml"), evaluation("site-local"));
    assert.deepEqual(generate({}, dir.configPath, dir.root), [
      "openai-compatible-chat/default-chat",
      "openai-compatible-evaluation/default-eval",
    ]);
    assert.deepEqual(generate({ [AGENT_PROFILE_ENV]: "site" }, dir.configPath, dir.root), [
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
      () => resolveAgentModelFiles({ [AGENT_PROFILE_ENV]: "osaka" }, dir.configPath),
      (error) => error instanceof AgentProfileError && /"osaka" not found/.test(error.message),
    );
  } finally {
    dir.cleanup();
  }
});

for (const missing of ["chat.yaml", "evaluation.yaml"]) {
  test(`a profile without ${missing} fails`, () => {
    const dir = fixture();
    try {
      unlinkSync(join(dir.agent, "profiles", "site", missing));
      assert.throws(
        () => resolveAgentModelFiles({ [AGENT_PROFILE_ENV]: "site" }, dir.configPath),
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
    write(join(dir.agent, "profiles", "site", "evaluation.yaml"), "evaluation_models: [\n");
    assert.throws(
      () => generate({ [AGENT_PROFILE_ENV]: "site" }, dir.configPath, dir.root),
      (error) =>
        error instanceof AgentProfileError && /cannot read Agent profile file/.test(error.message),
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
        resolveAgentModelFiles(
          { [AGENT_PROFILE_ENV]: "site", CHAT_CONFIG_PATH: "/elsewhere/chat.yaml" },
          dir.configPath,
        ),
      /conflicts with CHAT_CONFIG_PATH/,
    );
    // Without a profile the overrides still apply as before.
    assert.equal(
      resolveAgentModelFiles({ CHAT_CONFIG_PATH: "/elsewhere/chat.yaml" }, dir.configPath).chatPath,
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
        () => resolveAgentModelFiles({ [AGENT_PROFILE_ENV]: name }, dir.configPath),
        (error) => error instanceof AgentProfileError && /not a valid profile name/.test(error.message),
      );
    } finally {
      dir.cleanup();
    }
  });
}

test("valid profile names are accepted", () => {
  for (const name of CASES.valid_names) {
    assert.equal(selectedAgentProfile({ [AGENT_PROFILE_ENV]: name }), name);
  }
});

test("a profile directory that links out of profiles/ is refused", () => {
  const dir = fixture();
  try {
    const outside = join(dir.root, "outside");
    write(join(outside, "chat.yaml"), chat("outside-chat"));
    write(join(outside, "evaluation.yaml"), evaluation("outside-eval"));
    symlinkSync(outside, join(dir.agent, "profiles", "escape"), "dir");
    assert.throws(
      () => resolveAgentModelFiles({ [AGENT_PROFILE_ENV]: "escape" }, dir.configPath),
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
      validateAgentProfileDocument(doc.kind, data, `${doc.kind}.yaml`);
    } else {
      assert.throws(
        () => validateAgentProfileDocument(doc.kind, data, `${doc.kind}.yaml`),
        (error) => error instanceof AgentProfileError && error.message.includes(doc.error),
      );
    }
    // The same document through the generator.
    const dir = fixture();
    try {
      write(join(dir.agent, "profiles", "site", `${doc.kind}.yaml`), doc.yaml);
      const run = () => generate({ [AGENT_PROFILE_ENV]: "site" }, dir.configPath, dir.root);
      if (doc.valid) run();
      else {
        assert.throws(
          run,
          (error) => error instanceof AgentProfileError && error.message.includes(doc.error),
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
      write(join(dir.agent, "profiles", "site", `${doc.kind}.yaml`), doc.yaml);
      assert.throws(
        () => generate({ [AGENT_PROFILE_ENV]: "site" }, dir.configPath, dir.root),
        (error) =>
          error instanceof AgentProfileError && /cannot read Agent profile file/.test(error.message),
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
      const chatPath = join(dir.agent, "profiles", "site", "chat.yaml");
      write(chatPath, `${chat("site-chat")}    max_output_tokens: ${value}\n`);
      assert.throws(
        () => generate({ [AGENT_PROFILE_ENV]: "site" }, dir.configPath, dir.root),
        (error) =>
          error instanceof AgentProfileError &&
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
    write(join(dir.agent, "chat.yaml"), `${chat("default-chat")}    max_output_tokens: lots\n    unknown_key: 1\n`);
    const { path } = writeModelsConfig(
      resolveAgentModelFiles({}, dir.configPath),
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
    write(join(dir.agent, "profiles", "site", "chat.yaml"), full.yaml);
    const env = { [AGENT_PROFILE_ENV]: "site" };
    const files = resolveAgentModelFiles(env, dir.configPath);
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

test("the committed oqtopus profile serves Qwen for chat and evaluation", () => {
  const root = mkdtempSync(join(tmpdir(), "agent-oqtopus-"));
  try {
    const agent = join(root, "agent");
    cpSync(REPO_AGENT, agent, { recursive: true });
    const env = { [AGENT_PROFILE_ENV]: "oqtopus" };
    const files = resolveAgentModelFiles(env, join(agent, "config.yaml"));
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
        ["Qwen/Qwen3.8-27B"],
      );
      // The profile sets no reasoning_effort, so the Qwen chat-template
      // thinking format, which applies only to reasoning models, stays off.
      const [model] = entry.models;
      assert.equal(model.reasoning, undefined);
      assert.equal(model.compat?.thinkingFormat, undefined);
      assert.equal(model.contextWindow, 131072);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("the committed default files are what an unset profile generates from", () => {
  const configPath = new URL("config.yaml", REPO_AGENT).pathname;
  const files = resolveAgentModelFiles({}, configPath);
  const ids = (yaml, key) => parse(yaml)[key].map((model) => model.name);
  assert.deepEqual(
    ids(readFileSync(files.chatPath, "utf8"), "chat_models"),
    ids(readFileSync(new URL("chat.yaml", REPO_AGENT), "utf8"), "chat_models"),
  );
  assert.deepEqual(
    ids(readFileSync(files.evaluationPath, "utf8"), "evaluation_models"),
    ids(readFileSync(new URL("evaluation.yaml", REPO_AGENT), "utf8"), "evaluation_models"),
  );
});
