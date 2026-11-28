import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";
import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

import {
  defaultChatModel,
  exitStatus,
  expandTilde,
  forwardSignals,
  modelOptions,
  overlayEnv,
  parseDotenv,
  prepareLocalCli,
  referencedEnvNames,
  relayStdin,
  selectModel,
  stdinMode,
} from "../src/local-cli.ts";
import { buildModelsConfig } from "../src/models-config.ts";

const CHAT_YAML = `
chat_models:
  - provider: openai-compatible-chat
    name: qwen-test
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT
    api_key_env: OPENAI_COMPATIBLE_API_KEY_CHAT
    reasoning_effort: medium
  - provider: bedrock
    name: jp.anthropic.claude-sonnet-4-6
`;
const EVALUATION_YAML = `
evaluation_models:
  - provider: openai-compatible-evaluation
    name: vlm-test
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_EVALUATION
    api_key_env: OPENAI_COMPATIBLE_API_KEY_EVALUATION
`;

test("parseDotenv reads values without evaluating shell code", () => {
  const { values, invalidLines } = parseDotenv(
    [
      "# comment",
      "export A=plain # trailing comment",
      "B='literal $A $(touch /tmp/x)'",
      'C="line\\nbreak ${A}"',
      "D=${MISSING:-fallback}",
      "E=$(whoami)",
      "not a line",
      "F=",
    ].join("\n"),
  );
  assert.deepEqual(values, {
    A: "plain",
    B: "literal $A $(touch /tmp/x)",
    C: "line\nbreak plain",
    D: "fallback",
    E: "$(whoami)",
    F: "",
  });
  assert.deepEqual(invalidLines, [7]);
});

test("parseDotenv lets the shell win inside interpolation, even with an empty value", () => {
  const { values } = parseDotenv(
    ["HOST=file", "URL=https://${HOST}", "EMPTY=file", "E=[${EMPTY}]", "F=only-file", "G=$F"].join("\n"),
    { HOST: "shell", EMPTY: "" },
  );
  assert.equal(values.URL, "https://shell");
  assert.equal(values.E, "[]");
  assert.equal(values.G, "only-file");
});

test("parseDotenv keeps escaped dollars and backslashes literal in double quotes", () => {
  const { values, invalidLines } = parseDotenv(
    [
      "TOKEN=expanded",
      String.raw`KEY="abc\$TOKEN"`,
      String.raw`BRACED="abc\${TOKEN}"`,
      String.raw`SLASH="a\\$TOKEN"`,
      String.raw`OTHER="a\qb\"c"`,
      String.raw`UNQUOTED=a\$TOKEN`,
      "SINGLE='abc$TOKEN'",
      "LONE=cost $ 5",
    ].join("\n"),
  );
  assert.deepEqual(invalidLines, []);
  assert.equal(values.KEY, "abc$TOKEN");
  assert.equal(values.BRACED, "abc${TOKEN}");
  assert.equal(values.SLASH, "a\\expanded");
  assert.equal(values.OTHER, 'a\\qb"c');
  // Unquoted values keep backslashes, so the reference still expands.
  assert.equal(values.UNQUOTED, "a\\expanded");
  assert.equal(values.SINGLE, "abc$TOKEN");
  assert.equal(values.LONE, "cost $ 5");
});

test("parseDotenv distinguishes ${A-default} from ${A:-default}", () => {
  const lines = ["DASH=${A-fallback}", "COLON=${A:-fallback}"].join("\n");
  assert.deepEqual(parseDotenv(lines, { A: "" }).values, { DASH: "", COLON: "fallback" });
  assert.deepEqual(parseDotenv(lines, {}).values, { DASH: "fallback", COLON: "fallback" });
  assert.deepEqual(parseDotenv(`A=\n${lines}`, {}).values, { A: "", DASH: "", COLON: "fallback" });
  assert.deepEqual(parseDotenv(lines, { A: "set" }).values, { DASH: "set", COLON: "set" });
});

test("parseDotenv reports text after a closing quote and unsupported forms by line number", () => {
  const { values, invalidLines } = parseDotenv(
    [
      'A="abc"garbage',
      "B='abc'garbage",
      'C="abc"  # comment',
      "D='abc'\t",
      'E="unterminated',
      "F=${G:?required}",
      "H=${UNCLOSED",
      'I="abc"#tight',
    ].join("\n"),
  );
  assert.deepEqual(values, { C: "abc", D: "abc", I: "abc" });
  assert.deepEqual(invalidLines, [1, 2, 5, 6, 7]);
});

test("referencedEnvNames lists the endpoints, keys and the shared Access token", () => {
  assert.deepEqual(referencedEnvNames(CHAT_YAML, EVALUATION_YAML).sort(), [
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
    "OPENAI_COMPATIBLE_API_KEY_CHAT",
    "OPENAI_COMPATIBLE_API_KEY_EVALUATION",
    "OPENAI_COMPATIBLE_BASE_URL_CHAT",
    "OPENAI_COMPATIBLE_BASE_URL_EVALUATION",
  ]);
});

test("overlayEnv keeps shell values, even empty ones, and takes only named variables", () => {
  const { env, loaded } = overlayEnv(
    { KEEP: "shell", EMPTY: "" },
    { KEEP: "file", EMPTY: "file", NEW: "file", UNRELATED_SECRET: "file" },
    ["KEEP", "EMPTY", "NEW", "ABSENT"],
  );
  assert.equal(env.KEEP, "shell");
  assert.equal(env.EMPTY, "");
  assert.equal(env.NEW, "file");
  assert.equal("UNRELATED_SECRET" in env, false);
  assert.deepEqual(loaded, ["NEW"]);
});

test("defaultChatModel uses the first chat model and refuses an unresolved endpoint", () => {
  const configured = buildModelsConfig(CHAT_YAML, undefined, {
    OPENAI_COMPATIBLE_BASE_URL_CHAT: "https://llm.example/v1",
  });
  assert.deepEqual(defaultChatModel(CHAT_YAML, configured), {
    model: "openai-compatible-chat/qwen-test",
    thinking: "medium",
  });
  const unresolved = buildModelsConfig(CHAT_YAML, undefined, {});
  assert.throws(() => defaultChatModel(CHAT_YAML, unresolved), /OPENAI_COMPATIBLE_BASE_URL_CHAT does not resolve/);
});

function checkout() {
  const root = mkdtempSync(join(tmpdir(), "pi-local-"));
  mkdirSync(join(root, "config/agent/profiles/lab"), { recursive: true });
  writeFileSync(join(root, "config/agent/config.yaml"), "language: {}\n");
  writeFileSync(join(root, "config/agent/chat.yaml"), CHAT_YAML);
  writeFileSync(join(root, "config/agent/evaluation.yaml"), EVALUATION_YAML);
  writeFileSync(
    join(root, "config/agent/profiles/lab/chat.yaml"),
    CHAT_YAML.replace("qwen-test", "lab-model"),
  );
  writeFileSync(join(root, "config/agent/profiles/lab/evaluation.yaml"), EVALUATION_YAML);
  writeFileSync(
    join(root, ".env"),
    [
      "OPENAI_COMPATIBLE_BASE_URL_CHAT=https://llm.example/v1/",
      "OPENAI_COMPATIBLE_API_KEY_CHAT=value-from-env-file",
      "MONGO_INITDB_ROOT_PASSWORD=unrelated-value",
    ].join("\n"),
  );
  return root;
}

test("prepareLocalCli writes key references only into an isolated agent dir", () => {
  const root = checkout();
  const plan = prepareLocalCli(["-p", "hello"], {}, root);
  assert.equal(plan.agentDir, join(root, ".pi-local/agent"));
  assert.equal(plan.env.PI_CODING_AGENT_DIR, plan.agentDir);
  const models = readFileSync(join(plan.agentDir, "models.json"), "utf8");
  assert.doesNotMatch(models, /value-from-env-file/);
  assert.match(models, /"apiKey": "\$OPENAI_COMPATIBLE_API_KEY_CHAT"/);
  assert.equal(plan.env.OPENAI_COMPATIBLE_API_KEY_CHAT, "value-from-env-file");
  assert.equal("MONGO_INITDB_ROOT_PASSWORD" in plan.env, false);
  assert.deepEqual(plan.args, [
    "-e",
    join(root, "packages/pi-qdash"),
    "--model",
    "openai-compatible-chat/qwen-test",
    "--thinking",
    "medium",
    "-p",
    "hello",
  ]);
});

test("prepareLocalCli keeps the caller's model, thinking and agent dir choices", () => {
  const root = checkout();
  const plan = prepareLocalCli(
    ["--model", "openai-compatible-chat/other", "--thinking", "high", "--agent-dir", join(root, "elsewhere")],
    { PI_CODING_AGENT_DIR: join(root, "from-shell") },
    root,
  );
  assert.equal(plan.agentDir, join(root, "elsewhere"));
  assert.deepEqual(plan.args.slice(2), ["--model", "openai-compatible-chat/other", "--thinking", "high"]);
});

test("modelOptions reads pi's separate-value flags and rejects the = form", () => {
  assert.deepEqual(modelOptions(["--provider", "p", "--model", "m", "--thinking", "low", "-p", "hi"]), {
    provider: "p",
    model: "m",
    thinking: "low",
  });
  assert.deepEqual(modelOptions(["-p", "--", "--model", "m"]), {});
  assert.throws(() => modelOptions(["--model=m"]), /separate arguments/);
  assert.throws(() => modelOptions(["--thinking"]), /needs a value/);
});

test("selectModel lets --model bypass an unresolved default and its thinking level", () => {
  const unresolved = buildModelsConfig(CHAT_YAML, undefined, {});
  assert.deepEqual(selectModel(["--model", "bedrock/jp.anthropic.claude-sonnet-4-6"], CHAT_YAML, unresolved), {
    model: "bedrock/jp.anthropic.claude-sonnet-4-6",
    source: "argument",
    args: [],
  });
  assert.deepEqual(
    selectModel(["--provider", "bedrock", "--model", "jp.anthropic.claude-sonnet-4-6"], CHAT_YAML, unresolved),
    { model: "bedrock/jp.anthropic.claude-sonnet-4-6", source: "argument", args: [] },
  );
  assert.throws(() => selectModel([], CHAT_YAML, unresolved), /does not resolve/);
  assert.throws(() => selectModel(["--provider", "bedrock"], CHAT_YAML, unresolved), /--provider needs --model/);

  const configured = buildModelsConfig(CHAT_YAML, undefined, {
    OPENAI_COMPATIBLE_BASE_URL_CHAT: "https://llm.example/v1",
  });
  // Another model keeps pi's thinking default; the default model keeps its level.
  assert.deepEqual(selectModel(["--model", "bedrock/x"], CHAT_YAML, configured).args, []);
  assert.deepEqual(selectModel(["--model", "openai-compatible-chat/qwen-test"], CHAT_YAML, configured).args, [
    "--thinking",
    "medium",
  ]);
  assert.deepEqual(
    selectModel(["--model", "openai-compatible-chat/qwen-test", "--thinking", "low"], CHAT_YAML, configured).args,
    [],
  );
  assert.deepEqual(selectModel(["--thinking", "low"], CHAT_YAML, configured).args, [
    "--model",
    "openai-compatible-chat/qwen-test",
  ]);
});

test("prepareLocalCli runs an explicit model when the default endpoint is unset", () => {
  const root = checkout();
  writeFileSync(join(root, ".env"), "OPENAI_COMPATIBLE_API_KEY_CHAT=value-from-env-file\n");
  const plan = prepareLocalCli(["--model", "bedrock/jp.anthropic.claude-sonnet-4-6", "-p", "hi"], {}, root);
  assert.equal(plan.model, "bedrock/jp.anthropic.claude-sonnet-4-6");
  assert.equal(plan.modelSource, "argument");
  assert.deepEqual(plan.args.slice(2), ["--model", "bedrock/jp.anthropic.claude-sonnet-4-6", "-p", "hi"]);
  assert.throws(() => prepareLocalCli(["-p", "hi"], {}, root), /does not resolve/);
});

test("prepareLocalCli passes launcher-looking text after -- to pi", () => {
  const root = checkout();
  const plan = prepareLocalCli(["-p", "--", "--agent-dir", "x"], {}, root);
  assert.equal(plan.agentDir, join(root, ".pi-local/agent"));
  assert.deepEqual(plan.args.slice(-4), ["-p", "--", "--agent-dir", "x"]);
});

test("prepareLocalCli selects a profile named in .env", () => {
  const root = checkout();
  writeFileSync(join(root, ".env"), `${readFileSync(join(root, ".env"), "utf8")}\nQDASH_AGENT_PROFILE=lab\n`);
  const plan = prepareLocalCli([], {}, root);
  assert.equal(plan.profile, "lab");
  assert.equal(plan.model, "openai-compatible-chat/lab-model");
});

test("prepareLocalCli accepts the legacy QDASH_COPILOT_PROFILE and refuses a conflicting pair", () => {
  const root = checkout();
  const base = readFileSync(join(root, ".env"), "utf8");
  writeFileSync(join(root, ".env"), `${base}\nQDASH_COPILOT_PROFILE=lab\n`);
  assert.equal(prepareLocalCli([], {}, root).profile, "lab");
  // The shell's new name and the file's legacy name are compared, not layered.
  assert.throws(
    () => prepareLocalCli([], { QDASH_AGENT_PROFILE: "other" }, root),
    /conflicts with the legacy QDASH_COPILOT_PROFILE/,
  );
});

test("expandTilde resolves ~ and ~/ against the home directory", () => {
  const home = homedir();
  assert.equal(expandTilde("~"), home);
  assert.equal(expandTilde("~/custom/agent"), join(home, "custom/agent"));
  assert.equal(expandTilde("/abs/path"), "/abs/path");
  assert.equal(expandTilde("rel/path"), "rel/path");
});

test("prepareLocalCli refuses the global pi agent dir", () => {
  const root = checkout();
  for (const dir of [join(homedir(), ".pi/agent"), "~/.pi/agent"]) {
    assert.throws(
      () => prepareLocalCli(["--agent-dir", dir], {}, root),
      /global pi agent dir/,
    );
  }
  const expandedRelative = prepareLocalCli(["--agent-dir", resolve(root, "custom")], {}, root);
  assert.equal(expandedRelative.agentDir, resolve(root, "custom"));
});


test("model selection respects values consumed by pi options", () => {
  for (const flag of ["--system-prompt", "--append-system-prompt", "--api-key", "--name", "-n", "--session", "--extension", "-e", "--skill", "--prompt-template", "--theme"]) {
    assert.deepEqual(modelOptions([flag, "--model", "hello"]), {}, flag);
    assert.deepEqual(modelOptions([flag, "--model=hello"]), {}, flag);
  }
  const plan = prepareLocalCli(["--system-prompt", "--model", "hello"], {}, checkout());
  assert.equal(plan.modelSource, "default");
  assert.equal(plan.model, "openai-compatible-chat/qwen-test");
});

test("launcher options and delimiters used as pi option values remain untouched", () => {
  const root = checkout();
  const input = ["--system-prompt", "--env-file", "hello", "--append-system-prompt", "--agent-dir"];
  const plan = prepareLocalCli(input, {}, root);
  assert.deepEqual(plan.args.slice(-input.length), input);
  assert.equal(plan.agentDir, join(root, ".pi-local/agent"));
  const afterConsumedDelimiter = prepareLocalCli(["--system-prompt", "--", "--agent-dir", join(root, "isolated")], {}, root);
  assert.equal(afterConsumedDelimiter.agentDir, join(root, "isolated"));
});

test("prepareLocalCli consumes --wait-stdin only as a launcher option", () => {
  const root = checkout();
  const plan = prepareLocalCli(["--wait-stdin", "-p", "hi"], {}, root);
  assert.equal(plan.waitForStdin, true);
  assert.ok(!plan.args.includes("--wait-stdin"));
  const message = prepareLocalCli(["-p", "--", "--wait-stdin"], {}, root);
  assert.equal(message.waitForStdin, false);
  assert.deepEqual(message.args.slice(-3), ["-p", "--", "--wait-stdin"]);
});

test("stdinMode bounds an open pipe only when the arguments already carry a prompt", () => {
  assert.equal(stdinMode(["-p", "hi"], true, false), "grace");
  assert.equal(stdinMode(["--mode", "json", "hi"], true, false), "grace");
  assert.equal(stdinMode(["-p", "@notes.md"], true, false), "grace");
  // Terminal, file or /dev/null: pi reads it directly.
  assert.equal(stdinMode(["-p", "hi"], false, false), "inherit");
  // The piped input is the prompt, RPC streams stdin, or the caller asked to wait.
  assert.equal(stdinMode(["-p"], true, false), "inherit");
  assert.equal(stdinMode(["--mode", "rpc"], true, false), "inherit");
  assert.equal(stdinMode(["-p", "hi"], true, true), "inherit");
  // A flag value is not a prompt.
  assert.equal(stdinMode(["-p", "--model", "a/b"], true, false), "inherit");
});

// pi reads a piped stdin to EOF before its first event. This child does the same,
// so an open pipe that never writes stalls it unless the relay closes its stdin.
const READS_STDIN_TO_EOF = `let d = ""; process.stdin.on("data", (c) => (d += c)); process.stdin.on("end", () => { process.stdout.write("started:" + d.length); });`;

function runRelayedChild(feed, graceMs) {
  const child = spawn(process.execPath, ["-e", READS_STDIN_TO_EOF], { stdio: ["pipe", "pipe", "inherit"] });
  const input = new PassThrough();
  let idle = false;
  relayStdin(input, child.stdin, graceMs, () => {
    idle = true;
  });
  feed(input);
  return new Promise((resolve, reject) => {
    let out = "";
    child.stdout.on("data", (c) => (out += c));
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("child still waiting for stdin"));
    }, 10_000);
    child.on("close", () => {
      clearTimeout(timer);
      input.destroy();
      resolve({ out, idle });
    });
  });
}

test("relayStdin starts a stdin-reading child when the pipe stays open and silent", async () => {
  const started = Date.now();
  const { out, idle } = await runRelayedChild(() => {}, 100);
  assert.equal(out, "started:0");
  assert.equal(idle, true);
  assert.ok(Date.now() - started < 5_000);
});

test("relayStdin forwards input that starts within the grace period to EOF", async () => {
  const { out, idle } = await runRelayedChild((input) => {
    input.write("abc");
    // Later chunks arrive after the grace period and still count.
    setTimeout(() => input.end("def"), 300);
  }, 100);
  assert.equal(out, "started:6");
  assert.equal(idle, false);
});

test("forwardSignals passes stop signals to pi and exitStatus reports them", () => {
  const sent = [];
  const target = new EventEmitter();
  forwardSignals({ kill: (signal) => sent.push(signal) }, target);
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) target.emit(signal);
  assert.deepEqual(sent, ["SIGINT", "SIGTERM", "SIGHUP"]);
  assert.equal(exitStatus(3, null), 3);
  assert.equal(exitStatus(null, "SIGTERM"), 143);
});
