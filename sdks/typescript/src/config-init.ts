/**
 * The `qdash` command of `@oqtopus-team/qdash-sdk`: `qdash config init` writes a starting
 * `config.toml`.
 *
 * The command makes no network request and never asks for an API token: the file holds an empty
 * `api_token` to fill in, or, with `--api-token-env`, names the environment variable that holds
 * the token. The `qdash` command of the Python SDK writes the same file for the same options.
 */
import { mkdirSync, openSync, writeSync, closeSync, unlinkSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { parseArgs } from "node:util";

import { defaultConfigPath, expandUser, RESERVED_PROFILE_NAMES } from "./config.js";

export const PROG = "qdash";
export const DEFAULT_INIT_PROFILE = "local";
export const DEFAULT_INIT_BASE_URL = "http://localhost:5714/api";
export const DEFAULT_INIT_TOKEN_ENV = "QDASH_LOCAL_TOKEN";

const EXIT_FAILURE = 1;
const EXIT_USAGE = 2;

const BARE_KEY = /^[A-Za-z0-9_-]+$/;
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
const TOML_ESCAPES: Record<string, string> = {
  '"': '\\"',
  "\\": "\\\\",
  "\b": "\\b",
  "\t": "\\t",
  "\n": "\\n",
  "\f": "\\f",
  "\r": "\\r",
};

type Environment = Readonly<Record<string, string | undefined>>;

export interface CliIo {
  env?: Environment;
  stdout?: (line: string) => void;
  stderr?: (line: string) => void;
}

/** An invalid option value; the message never carries the value itself. */
class UsageError extends Error {}

/** `value` as a TOML basic string. */
export function tomlString(value: string): string {
  let out = "";
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0;
    const escape = TOML_ESCAPES[char];
    if (escape !== undefined) out += escape;
    else if (code < 0x20 || code === 0x7f) out += `\\u${code.toString(16).toUpperCase().padStart(4, "0")}`;
    else out += char;
  }
  return `"${out}"`;
}

/** `name` as a TOML key: bare when it may be, else quoted (a dot never nests tables). */
export function tomlKey(name: string): string {
  return BARE_KEY.test(name) ? name : tomlString(name);
}

/**
 * The text of a new config file holding one profile, which is the default profile.
 *
 * Every profile key appears: the common ones set, the rest commented out with their use.
 * Without `apiTokenEnv` the profile holds an empty `api_token` to fill in; with it, the
 * profile reads the token from that environment variable instead.
 */
export function renderConfig(profile: string, baseUrl: string, apiTokenEnv?: string, projectId?: string): string {
  const lines = [
    "# QDash SDK configuration, created by `qdash config init`.",
    "# Each [<name>] table is a profile; default_profile selects one when none is given.",
    `default_profile = ${tomlString(profile)}`,
    "",
    `[${tomlKey(profile)}]`,
    `base_url = ${tomlString(baseUrl)}`,
    "",
    "# Authentication: set one of api_token, api_token_env, or username with password_env.",
  ];
  if (apiTokenEnv === undefined) {
    lines.push(
      "# Paste the token from Settings > API Token in QDash; empty means no token.",
      'api_token = ""',
      "# To keep the token out of this file, delete api_token and name the environment",
      "# variable that holds it:",
      `# api_token_env = ${tomlString(DEFAULT_INIT_TOKEN_ENV)}`,
      "# To sign in with a password instead, leave api_token empty and set:",
    );
  } else {
    lines.push(
      "# The API token is read from this environment variable, not stored in this file.",
      `api_token_env = ${tomlString(apiTokenEnv)}`,
      "# To store the token here instead, delete api_token_env and paste the token from",
      "# Settings > API Token in QDash:",
      '# api_token = "<token>"',
      "# To sign in with a password instead, delete api_token_env and set:",
    );
  }
  lines.push(
    '# username = "<username>"',
    '# password_env = "QDASH_PASSWORD"  # environment variable holding the password',
    "",
    "# Project sent as X-Project-Id; running tasks from the Python SDK needs it. Without it",
    "# the server uses your default project.",
    projectId === undefined ? '# project_id = "<project-id>"' : `project_id = ${tomlString(projectId)}`,
    "",
    "timeout_sec = 30  # seconds per request",
    "verify_tls = true",
    "read_attempts = 3  # tries of a read (GET) on a transient failure; writes are sent once",
    "# Proxy for API requests. In the TypeScript SDK, proxy and verify_tls = false need a",
    "# custom fetch (session option).",
    '# proxy = "http://proxy.example:8080"',
    "# User-Agent header for API requests:",
    '# user_agent = "my-tool/1.0"',
    "# Cloudflare Access service token, for a server behind Cloudflare Access:",
    '# cf_access_client_id = "<client-id>.access"',
    '# cf_access_client_secret = "<client-secret>"',
  );
  return `${lines.join("\n")}\n`;
}

/**
 * Create `path` with `text`; fail with `EEXIST` when anything, a symlink included, is there.
 * The `wx` flag makes the existence check and the creation one step and does not follow a
 * symlink at `path`. On POSIX the new file is readable by its owner only.
 */
export function writeNewFile(path: string, text: string): void {
  try {
    mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  } catch (error) {
    // A file where a parent directory belongs; the config file itself does not exist.
    if ((error as NodeJS.ErrnoException).code === "EEXIST") throw Object.assign(new Error("ENOTDIR"), { code: "ENOTDIR" });
    throw error;
  }
  const fd = openSync(path, "wx", 0o600);
  try {
    writeSync(fd, text, null, "utf8");
  } catch (error) {
    closeSync(fd);
    unlinkSync(path);
    throw error;
  }
  closeSync(fd);
}

function text(option: string, value: string): string {
  if (!value) throw new UsageError(`${option} must not be empty.`);
  if (/\p{Cs}/u.test(value)) throw new UsageError(`${option} must be valid Unicode text.`);
  return value;
}

const HELP = `usage: ${PROG} config init [--profile NAME] [--base-url URL] [--project-id ID]
                         [--api-token-env NAME] [--path FILE]

Create a new config.toml holding one profile, which becomes default_profile. An existing file
is never changed. No token is asked for: fill in api_token in the new file, or pass
--api-token-env to read the token from an environment variable. Every other profile key is
listed, commented out.

options:
  --profile NAME        default: ${DEFAULT_INIT_PROFILE}
  --base-url URL        default: ${DEFAULT_INIT_BASE_URL}
  --project-id ID       sent as X-Project-Id (default: none, commented out)
  --api-token-env NAME  read the API token from this environment variable instead of storing
                        it (default: an empty api_token to fill in)
  --path FILE           file to create (default: $XDG_CONFIG_HOME/qdash/config.toml)`;

/** Run `qdash` with `argv` (without the node and script paths); return the exit status. */
export function runCli(argv: readonly string[], io: CliIo = {}): number {
  const env = io.env ?? process.env;
  const stdout = io.stdout ?? ((line: string) => process.stdout.write(`${line}\n`));
  const stderr = io.stderr ?? ((line: string) => process.stderr.write(`${line}\n`));
  const fail = (message: string, status: number): number => {
    stderr(`${PROG}: error: ${message}`);
    return status;
  };

  let parsed;
  try {
    parsed = parseArgs({
      args: [...argv],
      allowPositionals: true,
      strict: true,
      options: {
        help: { type: "boolean", short: "h" },
        profile: { type: "string" },
        "base-url": { type: "string" },
        "project-id": { type: "string" },
        "api-token-env": { type: "string" },
        path: { type: "string" },
      },
    });
  } catch (error) {
    stderr(HELP);
    return fail((error as Error).message, EXIT_USAGE);
  }
  const { values, positionals } = parsed;
  if (values.help) {
    stdout(HELP);
    return 0;
  }
  if (positionals.length !== 2 || positionals[0] !== "config" || positionals[1] !== "init") {
    stderr(HELP);
    return fail("expected the command: config init", EXIT_USAGE);
  }

  const profile = values.profile ?? DEFAULT_INIT_PROFILE;
  const baseUrl = values["base-url"] ?? DEFAULT_INIT_BASE_URL;
  const projectId = values["project-id"];
  const apiTokenEnv = values["api-token-env"];
  let path: string;
  try {
    text("--profile", profile);
    if (RESERVED_PROFILE_NAMES.has(profile)) {
      throw new UsageError(`--profile must not be a reserved name (${[...RESERVED_PROFILE_NAMES].sort().join(", ")}).`);
    }
    text("--base-url", baseUrl);
    if (projectId !== undefined) text("--project-id", projectId);
    // A token pasted here by mistake would be written and printed, so only names pass.
    if (apiTokenEnv !== undefined && !ENV_NAME.test(apiTokenEnv)) {
      throw new UsageError(
        "--api-token-env must be an environment variable name (letters, digits and underscores, not starting with a digit).",
      );
    }
    if (values.path !== undefined) {
      text("--path", values.path);
      if (extname(values.path).toLowerCase() !== ".toml") throw new UsageError("--path must name a .toml file.");
      path = expandUser(values.path);
    } else {
      path = defaultConfigPath(env);
    }
  } catch (error) {
    if (error instanceof UsageError) return fail(error.message, EXIT_USAGE);
    throw error;
  }

  try {
    writeNewFile(path, renderConfig(profile, baseUrl, apiTokenEnv, projectId));
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "EEXIST") return fail(`${path} already exists; it was left unchanged. Edit it, or pass --path.`, EXIT_FAILURE);
    return fail(`cannot create ${path}: ${code ?? "write failed"}`, EXIT_FAILURE);
  }

  stdout(`Created ${path} with profile ${tomlKey(profile)} as default_profile.`);
  if (resolve(path) !== resolve(defaultConfigPath(env))) {
    stdout("This is not the default config path; pass this path when loading the profile.");
  }
  if (apiTokenEnv === undefined) {
    stdout(
      `Next: paste your QDash API token (Settings > API Token) into api_token in ${path}, or switch to api_token_env as the file describes.`,
    );
  } else {
    stdout(`Next: set ${apiTokenEnv} to your QDash API token, for example: export ${apiTokenEnv}=<token>`);
  }
  return 0;
}
