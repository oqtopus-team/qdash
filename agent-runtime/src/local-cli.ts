import { type ChildProcess, spawn } from "node:child_process";
import { existsSync, fstatSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { constants, homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { parseArgs } from "@earendil-works/pi-coding-agent";
import { parse } from "yaml";

import {
  AGENT_PROFILE_ENV,
  LEGACY_AGENT_PROFILE_ENV,
  readAgentModelYaml,
  resolveAgentConfigPaths,
  resolveAgentModelFiles,
} from "./agent-profile.ts";
import { buildModelsConfig, CF_ACCESS_ENV, PROVIDER_ALIASES, type ModelsConfig } from "./models-config.ts";

/**
 * Run the pi CLI from a QDash checkout with the Agent chat models.
 *
 * The models come from config/agent/chat.yaml and evaluation.yaml (or the
 * profile `QDASH_AGENT_PROFILE` selects), translated by the same
 * buildModelsConfig the agent runtime uses. Endpoint and key variables are read
 * from the checkout's `.env` without evaluating it as shell code. models.json
 * stores `$NAME` references only, so no secret is written to disk, and it goes
 * to an isolated agent directory so the global ~/.pi/agent stays untouched.
 *
 * This is a repository development helper; the published pi-qdash package does
 * not read `.env`.
 */

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

/** QDash reasoning_effort onto Pi thinking levels, as the API maps it for Agent chats. */
export const THINKING_LEVELS: Record<string, string> = {
  none: "off",
  minimal: "minimal",
  low: "low",
  medium: "medium",
  high: "high",
};

/** Variables taken from `.env` besides the ones a model names. */
const SELECTION_ENV = [AGENT_PROFILE_ENV, LEGACY_AGENT_PROFILE_ENV, "CHAT_CONFIG_PATH", "EVALUATION_CONFIG_PATH"];

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * Parse a subset of dotenv syntax as data, without running it.
 *
 * One `NAME=value` assignment per line, with an optional `export ` prefix.
 * Blank lines and lines starting with `#` are skipped.
 *
 * - Single quotes: the value is literal.
 * - Double quotes: `\n`, `\t`, `\r`, `\"`, `\\` and `\$` are escapes; any other
 *   backslash is kept. An unescaped `$` interpolates.
 * - Unquoted: surrounding whitespace and a ` #` comment are dropped; backslashes
 *   are kept and `$` interpolates.
 * - Interpolation: `$NAME`, `${NAME}`, `${NAME-default}` (default when unset) and
 *   `${NAME:-default}` (default when unset or empty). The default is literal
 *   text. `lookup` (the shell) wins over earlier lines of the file, and a name
 *   set to an empty string in `lookup` counts as set.
 * - After a closing quote only whitespace and a `#` comment may follow.
 *
 * A line outside this subset (no `=`, an unterminated quote, text after a
 * closing quote, another `${...}` form) is skipped and reported by line number
 * only, so no value reaches a diagnostic. Multi-line values are not supported.
 */
export function parseDotenv(
  text: string,
  lookup: NodeJS.ProcessEnv = {},
): { values: Record<string, string>; invalidLines: number[] } {
  const values: Record<string, string> = {};
  const invalidLines: number[] = [];
  const resolveName = (name: string): string | undefined =>
    Object.hasOwn(lookup, name) && lookup[name] !== undefined ? lookup[name] : values[name];
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (line === "" || line.startsWith("#")) continue;
    const match = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    const value = match ? parseValue(match[2], resolveName) : undefined;
    if (match === null || value === undefined) {
      invalidLines.push(index + 1);
      continue;
    }
    values[match[1]] = value;
  }
  return { values, invalidLines };
}

const DOUBLE_ESCAPES: Record<string, string> = { n: "\n", t: "\t", r: "\r", '"': '"', "\\": "\\", $: "$" };
const TRAILER = /^\s*(?:#.*)?$/;

/** One value after `=`, or undefined when it is outside the supported syntax. */
function parseValue(raw: string, resolveName: (name: string) => string | undefined): string | undefined {
  if (raw.startsWith("'")) {
    const end = raw.indexOf("'", 1);
    if (end < 0 || !TRAILER.test(raw.slice(end + 1))) return undefined;
    return raw.slice(1, end);
  }
  if (raw.startsWith('"')) {
    let out = "";
    for (let i = 1; i < raw.length; i += 1) {
      const ch = raw[i];
      if (ch === '"') return TRAILER.test(raw.slice(i + 1)) ? out : undefined;
      if (ch === "\\" && i + 1 < raw.length) {
        const next = raw[i + 1];
        out += DOUBLE_ESCAPES[next] ?? `\\${next}`;
        i += 1;
      } else if (ch === "$") {
        const expanded = expandAt(raw, i, resolveName);
        if (!expanded) return undefined;
        out += expanded.text;
        i = expanded.end - 1;
      } else {
        out += ch;
      }
    }
    return undefined; // unterminated
  }
  const body = raw.replace(/(?:^|\s+)#.*$/, "").trim();
  let out = "";
  for (let i = 0; i < body.length; i += 1) {
    if (body[i] !== "$") {
      out += body[i];
      continue;
    }
    const expanded = expandAt(body, i, resolveName);
    if (!expanded) return undefined;
    out += expanded.text;
    i = expanded.end - 1;
  }
  return out;
}

/**
 * Expand the reference starting at the `$` at `start`. Returns the text and the
 * index after the reference, `$` itself when no name follows, or undefined for
 * an unsupported or unterminated `${...}`.
 */
function expandAt(
  text: string,
  start: number,
  resolveName: (name: string) => string | undefined,
): { text: string; end: number } | undefined {
  const bare = /^\$([A-Za-z_][A-Za-z0-9_]*)/.exec(text.slice(start));
  if (bare) return { text: resolveName(bare[1]) ?? "", end: start + bare[0].length };
  if (text[start + 1] !== "{") return { text: "$", end: start + 1 };
  const close = text.indexOf("}", start + 2);
  if (close < 0) return undefined;
  const braced = /^([A-Za-z_][A-Za-z0-9_]*)(?:(:?-)(.*))?$/s.exec(text.slice(start + 2, close));
  if (!braced) return undefined;
  const [, name, operator, fallback] = braced;
  const resolved = resolveName(name);
  let result = resolved ?? "";
  if (operator === "-" && resolved === undefined) result = fallback;
  if (operator === ":-" && (resolved === undefined || resolved === "")) result = fallback;
  return { text: result, end: close + 1 };
}

/** The environment variables the chat and evaluation models read: endpoints, keys, Access token. */
export function referencedEnvNames(chatYaml: string, evaluationYaml: string | undefined): string[] {
  const names = new Set<string>();
  let usesEndpoint = false;
  for (const [text, key] of [
    [chatYaml, "chat_models"],
    [evaluationYaml, "evaluation_models"],
  ] as const) {
    if (!text) continue;
    const models = (parse(text) as Record<string, unknown> | null)?.[key];
    if (!Array.isArray(models)) continue;
    for (const model of models as Record<string, unknown>[]) {
      const baseUrl = model?.base_url;
      if (typeof baseUrl === "string" && baseUrl.startsWith("env:")) {
        usesEndpoint = true;
        if (ENV_NAME.test(baseUrl.slice(4))) names.add(baseUrl.slice(4));
      }
      const apiKeyEnv = model?.api_key_env;
      if (typeof apiKeyEnv === "string" && ENV_NAME.test(apiKeyEnv)) names.add(apiKeyEnv);
    }
  }
  if (usesEndpoint) {
    names.add(CF_ACCESS_ENV.clientId);
    names.add(CF_ACCESS_ENV.clientSecret);
  }
  return [...names];
}

/**
 * Add `names` from the file to the environment. A variable already set in the
 * shell wins, even when empty, so a one-off override needs no file edit.
 */
export function overlayEnv(
  base: NodeJS.ProcessEnv,
  file: Record<string, string>,
  names: Iterable<string>,
): { env: NodeJS.ProcessEnv; loaded: string[] } {
  const env: NodeJS.ProcessEnv = { ...base };
  const loaded: string[] = [];
  for (const name of names) {
    if (name in base || !(name in file)) continue;
    env[name] = file[name];
    loaded.push(name);
  }
  return { env, loaded };
}

/** The default chat model as `provider/id`, or an error naming what keeps it from resolving. */
export function defaultChatModel(
  chatYaml: string,
  config: ModelsConfig,
): { model: string; thinking?: string } {
  const models = (parse(chatYaml) as Record<string, unknown> | null)?.chat_models;
  const first = Array.isArray(models) ? (models[0] as Record<string, unknown>) : undefined;
  const provider = typeof first?.provider === "string" ? first.provider : undefined;
  const name = typeof first?.name === "string" ? first.name : undefined;
  if (!provider || !name) throw new Error("chat.yaml has no chat_models entry with provider and name");
  const providerId = PROVIDER_ALIASES[provider] ?? provider;
  if (typeof first?.base_url === "string" && !config.providers[providerId]?.models?.some((m) => m.id === name)) {
    throw new Error(
      `default chat model ${providerId}/${name} is not configured: ${first.base_url} does not resolve; set it in .env or the shell`,
    );
  }
  const effort = typeof first?.reasoning_effort === "string" ? first.reasoning_effort.toLowerCase() : undefined;
  const thinking = effort ? THINKING_LEVELS[effort] : undefined;
  return { model: `${providerId}/${name}`, ...(thinking ? { thinking } : {}) };
}

/** The model and thinking options the caller passed to pi, read the way pi reads them. */
export function modelOptions(args: readonly string[]): {
  model?: string;
  provider?: string;
  thinking?: string;
} {
  // Use pi's public parser so values of other flags are never reinterpreted.
  const parsed = parseArgs([...args]);
  for (const name of ["model", "provider", "thinking"] as const) {
    if (parsed.unknownFlags.has(name)) {
      throw new Error(parsed.unknownFlags.get(name) === true
        ? `--${name} needs a value`
        : `pass --${name} and its value as separate arguments`);
    }
  }
  const found: { model?: string; provider?: string; thinking?: string } = {};
  if (parsed.model !== undefined) found.model = parsed.model;
  if (parsed.provider !== undefined) found.provider = parsed.provider;
  if (parsed.thinking !== undefined) found.thinking = parsed.thinking;
  return found;
}

/**
 * The `--model` and `--thinking` arguments to add for the chat.yaml default.
 *
 * Without `--model` the first chat model starts, and an unresolved endpoint is
 * an error rather than a fallback. With `--model` the default is not required to
 * resolve. Its thinking level carries over only when `--model` names the same
 * `provider/id` without `--provider` or a `:<thinking>` suffix; another model
 * keeps pi's own thinking default unless `--thinking` is given.
 */
export function selectModel(
  piArgs: readonly string[],
  chatYaml: string,
  config: ModelsConfig,
): { model: string; source: "default" | "argument"; args: string[] } {
  const options = modelOptions(piArgs);
  if (options.provider !== undefined && options.model === undefined) {
    throw new Error("--provider needs --model");
  }
  if (options.model === undefined) {
    const { model, thinking } = defaultChatModel(chatYaml, config);
    const args = ["--model", model];
    if (thinking && options.thinking === undefined) args.push("--thinking", thinking);
    return { model, source: "default", args };
  }
  const explicit = options.provider === undefined ? options.model : `${options.provider}/${options.model}`;
  let inherited: string | undefined;
  if (options.thinking === undefined && options.provider === undefined) {
    try {
      const fallback = defaultChatModel(chatYaml, config);
      if (fallback.model === options.model) inherited = fallback.thinking;
    } catch {
      // The default does not need to resolve when another model is chosen.
    }
  }
  return { model: explicit, source: "argument", args: inherited ? ["--thinking", inherited] : [] };
}

export interface LocalCliPlan {
  agentDir: string;
  env: NodeJS.ProcessEnv;
  args: string[];
  loaded: string[];
  profile?: string;
  /** The model pi starts, and whether it is the chat.yaml default or `--model`. */
  model: string;
  modelSource: "default" | "argument";
  /** `--wait-stdin`: hand piped stdin to pi as is, however long it stays open. */
  waitForStdin: boolean;
}

/** Expand a leading `~` or `~/...` against the user's home directory, matching pi's `--agent-dir`. */
export function expandTilde(path: string): string {
  if (path === "~") return homedir();
  if (path.startsWith("~/") || path.startsWith("~\\")) return join(homedir(), path.slice(2));
  return path;
}

/**
 * Prepare a pi run: write models.json into `agentDir` and build the arguments.
 *
 * `--env-file <path>`, `--agent-dir <path>` and `--wait-stdin` are consumed
 * here; every other argument goes to pi. See selectModel for how `--model`, `--provider` and
 * `--thinking` interact with the chat.yaml default.
 */
export function prepareLocalCli(
  argv: readonly string[],
  baseEnv: NodeJS.ProcessEnv,
  repoRoot: string = REPO_ROOT,
): LocalCliPlan {
  let envFile = baseEnv.QDASH_ENV_FILE || join(repoRoot, ".env");
  // Not PI_CODING_AGENT_DIR: a shell that exports it for the global pi would
  // have its models.json replaced.
  let agentDir = join(repoRoot, ".pi-local", "agent");
  let waitForStdin = false;
  const piArgs: string[] = [];
  for (let i = 0; i < argv.length; i += 1) {
    // Ask pi whether this token is an option, rather than a preceding
    // option's value or message text after `--`.
    if (argv[i] === "--wait-stdin" && parseArgs([...piArgs, argv[i]]).unknownFlags.has("wait-stdin")) {
      waitForStdin = true;
    } else if ((argv[i] === "--env-file" || argv[i] === "--agent-dir") &&
        parseArgs([...piArgs, argv[i]]).unknownFlags.has(argv[i].slice(2))) {
      const value = argv[i + 1];
      if (!value) throw new Error(`${argv[i]} needs a path`);
      if (argv[i] === "--env-file") envFile = resolve(expandTilde(value));
      else agentDir = resolve(expandTilde(value));
      i += 1;
    } else {
      piArgs.push(argv[i]);
    }
  }

  if (resolve(agentDir) === resolve(homedir(), ".pi", "agent")) {
    throw new Error(`refusing to write models.json into the global pi agent dir ${agentDir}`);
  }

  let fileValues: Record<string, string> = {};
  if (existsSync(envFile)) {
    const parsed = parseDotenv(readFileSync(envFile, "utf8"), baseEnv);
    if (parsed.invalidLines.length > 0) {
      console.warn(`[pi-local] ignoring malformed .env lines: ${parsed.invalidLines.join(", ")}`);
    }
    fileValues = parsed.values;
  } else {
    console.warn(`[pi-local] ${envFile} not found; using the shell environment only`);
  }

  const selection = overlayEnv(baseEnv, fileValues, SELECTION_ENV);
  // AGENT_CONFIG_PATH (or the legacy COPILOT_CONFIG_PATH) comes from the shell only.
  const { configPath: agentConfigPath } = resolveAgentConfigPaths(baseEnv, join(repoRoot, "config"), (message) =>
    console.warn(`[pi-local] ${message}`),
  );
  const files = resolveAgentModelFiles(selection.env, agentConfigPath);
  const yaml = readAgentModelYaml(files);
  const { env, loaded } = overlayEnv(
    selection.env,
    fileValues,
    referencedEnvNames(yaml.chatYaml, yaml.evaluationYaml),
  );

  const config = buildModelsConfig(yaml.chatYaml, yaml.evaluationYaml, env);
  const selected = selectModel(piArgs, yaml.chatYaml, config);
  mkdirSync(agentDir, { recursive: true, mode: 0o700 });
  writeFileSync(join(agentDir, "models.json"), `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });

  const args = ["-e", join(repoRoot, "packages/pi-qdash"), ...selected.args, ...piArgs];
  env.PI_CODING_AGENT_DIR = agentDir;
  return {
    agentDir,
    env,
    args,
    loaded: [...selection.loaded, ...loaded],
    ...(files.profile ? { profile: files.profile } : {}),
    model: selected.model,
    modelSource: selected.source,
    waitForStdin,
  };
}

/** How long a piped stdin may stay silent before a run that has a prompt starts without it. */
export const STDIN_GRACE_MS = 2000;

/**
 * How pi gets the launcher's stdin.
 *
 * pi reads a non-TTY stdin to EOF before it writes its first event, even when
 * the prompt is an argument. A caller that holds a pipe open without writing to
 * it, such as an agent's command tool, then stalls pi with no output at all.
 *
 * - `inherit`: pi reads the launcher's stdin directly. Used for a terminal, a
 *   file or `/dev/null`, RPC mode, `--wait-stdin`, and a run whose only prompt
 *   is the piped input.
 * - `grace`: a pipe or socket while the arguments already carry a prompt. The
 *   launcher relays it, and when no byte arrives within STDIN_GRACE_MS it closes
 *   pi's stdin so the run starts without piped input.
 */
export function stdinMode(args: readonly string[], stdinIsPipe: boolean, waitForStdin: boolean): "inherit" | "grace" {
  if (!stdinIsPipe || waitForStdin) return "inherit";
  const parsed = parseArgs([...args]);
  if (parsed.mode === "rpc") return "inherit";
  return parsed.messages.length > 0 || parsed.fileArgs.length > 0 ? "grace" : "inherit";
}

/**
 * Copy `input` to `output`. When `input` neither sends a byte nor ends within
 * `graceMs`, stop reading it, end `output` and call `onIdle`. Once a byte
 * arrives the copy runs to EOF with no deadline.
 */
export function relayStdin(
  input: NodeJS.ReadableStream,
  output: NodeJS.WritableStream,
  graceMs: number,
  onIdle: () => void,
): void {
  // pi may exit before it reads everything; a closed pipe is not an error here.
  output.on("error", () => {});
  const timer = setTimeout(() => {
    input.unpipe(output);
    input.pause();
    output.end();
    onIdle();
  }, graceMs);
  input.once("data", () => clearTimeout(timer));
  input.once("end", () => clearTimeout(timer));
  input.pipe(output);
}

/**
 * Pass SIGINT, SIGTERM and SIGHUP on to `child`, so stopping the launcher stops
 * pi instead of leaving it to run the prompt unattended.
 */
export function forwardSignals(child: Pick<ChildProcess, "kill">, target: NodeJS.EventEmitter = process): void {
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"] as const) {
    target.on(signal, () => child.kill(signal));
  }
}

/** The launcher's exit status for pi's: its code, or 128 + the signal number. */
export function exitStatus(code: number | null, signal: NodeJS.Signals | null): number {
  if (code !== null) return code;
  return signal ? 128 + (constants.signals[signal] ?? 0) : 1;
}

function stdinIsPipe(): boolean {
  try {
    const stat = fstatSync(0);
    return stat.isFIFO() || stat.isSocket();
  } catch {
    return false;
  }
}

if (import.meta.main) {
  try {
    const plan = prepareLocalCli(process.argv.slice(2), process.env);
    // Names only, never values.
    console.warn(
      `[pi-local] models: ${plan.profile ? `profile ${plan.profile}` : "default"}, ${plan.modelSource === "default" ? "default" : "--model"} ${plan.model}; agent dir ${plan.agentDir}; from .env: ${plan.loaded.join(", ") || "none"}`,
    );
    const pi = join(REPO_ROOT, "agent-runtime/node_modules/.bin/pi");
    const mode = stdinMode(plan.args, stdinIsPipe(), plan.waitForStdin);
    const child = spawn(existsSync(pi) ? pi : "pi", plan.args, {
      stdio: [mode === "grace" ? "pipe" : "inherit", "inherit", "inherit"],
      env: plan.env,
    });
    forwardSignals(child);
    if (mode === "grace" && child.stdin) {
      relayStdin(process.stdin, child.stdin, STDIN_GRACE_MS, () => {
        console.warn(
          `[pi-local] stdin is an open pipe with no input after ${STDIN_GRACE_MS / 1000} s; starting without it. Pass --wait-stdin to wait for piped input, or </dev/null when there is none.`,
        );
      });
    }
    child.on("error", (error) => {
      console.error(`[pi-local] ${error.message}`);
      process.exit(1);
    });
    child.on("close", (code, signal) => process.exit(exitStatus(code, signal)));
  } catch (error) {
    console.error(`[pi-local] ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}
