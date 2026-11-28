/**
 * SDK configuration: `QDASH_*` variables, or a profile of the TOML config file shared with the
 * Python SDK (`$XDG_CONFIG_HOME/qdash/config.toml`, else `~/.config/qdash/config.toml`).
 *
 * The file and its keys are the Python SDK's, snake_case on disk. Each profile is a top-level
 * table; the optional root `default_profile` names the profile used when none is given:
 *
 * ```toml
 * default_profile = "lab"
 *
 * [lab]
 * base_url = "https://qdash.example/api"
 * api_token_env = "QDASH_LAB_TOKEN"
 * project_id = "p1"
 * timeout_sec = 30
 * read_attempts = 3
 * ```
 *
 * `qdash config init` writes such a file. The `config.ini` file of `@oqtopus-team/qdash-client` is still read when no `config.toml`
 * exists, or when given explicitly, with a deprecation warning of this SDK only.
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { extname, join } from "node:path";

import ini from "ini";
import { parse as parseToml, TomlError } from "smol-toml";

import { QDashConfigError } from "./errors.js";

export const DEFAULT_PROFILE = "default";
/** The `code` of the warning emitted when the SDK reads a deprecated INI config file. */
export const INI_CONFIG_DEPRECATION_CODE = "QDASH_SDK_INI_CONFIG";

type Environment = Readonly<Record<string, string | undefined>>;

export interface QDashConfigOptions {
  /** The API root, such as `https://qdash.example/api`; a trailing slash is removed. */
  baseUrl: string;
  apiToken?: string;
  /** Sign in with this user and the password in the environment variable `passwordEnv`. */
  username?: string;
  passwordEnv?: string;
  /** Sent as `X-Project-Id` on every request; without it the server uses the user's default project. */
  projectId?: string;
  /** Cloudflare Access service-token headers. */
  cfAccessClientId?: string;
  cfAccessClientSecret?: string;
  /** Seconds each request may take (default 30). */
  timeoutSec?: number;
  /**
   * Verify TLS certificates (default true). Turning it off, like `proxy`, needs a custom
   * `fetch` (session option) that applies it; the built-in fetch cannot.
   */
  verifyTls?: boolean;
  proxy?: string;
  userAgent?: string;
  /**
   * How often the SDK sends a read (GET) in total after a transport error or a transient status
   * (default 3, at least 1). Writes are sent once.
   */
  readAttempts?: number;
}

const OPTION_KEYS: ReadonlySet<string> = new Set([
  "baseUrl",
  "apiToken",
  "username",
  "passwordEnv",
  "projectId",
  "cfAccessClientId",
  "cfAccessClientSecret",
  "timeoutSec",
  "verifyTls",
  "proxy",
  "userAgent",
  "readAttempts",
]);
const STRING_OPTIONS = [
  "apiToken",
  "username",
  "passwordEnv",
  "projectId",
  "cfAccessClientId",
  "cfAccessClientSecret",
  "proxy",
  "userAgent",
] as const;

// Profile keys of config.toml: the config fields in snake_case, plus api_token_env.
const TOML_KEYS = {
  base_url: "baseUrl",
  api_token: "apiToken",
  username: "username",
  password_env: "passwordEnv",
  project_id: "projectId",
  cf_access_client_id: "cfAccessClientId",
  cf_access_client_secret: "cfAccessClientSecret",
  proxy: "proxy",
  user_agent: "userAgent",
  timeout_sec: "timeoutSec",
  verify_tls: "verifyTls",
  read_attempts: "readAttempts",
} as const satisfies Record<string, keyof QDashConfigOptions>;
const TOML_STRING_KEYS = new Set([
  "base_url",
  "api_token",
  "api_token_env",
  "username",
  "password_env",
  "project_id",
  "cf_access_client_id",
  "cf_access_client_secret",
  "proxy",
  "user_agent",
]);
const TOML_PROFILE_KEYS = new Set([...TOML_STRING_KEYS, "timeout_sec", "verify_tls", "read_attempts"]);
// Root keys of config.toml that are not profile tables. "profiles" held the profiles of the
// earlier [profiles.<name>] layout; it stays reserved so that layout fails with a migration hint.
const DEFAULT_PROFILE_KEY = "default_profile";
const LEGACY_PROFILES_KEY = "profiles";
/** Root keys of `config.toml` that cannot name a profile. */
export const RESERVED_PROFILE_NAMES: ReadonlySet<string> = new Set([DEFAULT_PROFILE_KEY, LEGACY_PROFILES_KEY]);

/** Where and how a `QDash` session reaches the API. Immutable. */
export class QDashConfig {
  readonly baseUrl: string;
  readonly apiToken?: string;
  readonly username?: string;
  readonly passwordEnv?: string;
  readonly projectId?: string;
  readonly cfAccessClientId?: string;
  readonly cfAccessClientSecret?: string;
  readonly timeoutSec: number;
  readonly verifyTls: boolean;
  readonly proxy?: string;
  readonly userAgent?: string;
  readonly readAttempts: number;

  constructor(options: QDashConfigOptions) {
    const problems = configProblems(options);
    if (problems.length > 0) throw new QDashConfigError(`Invalid config values: ${problems.join(", ")}`);
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    for (const key of STRING_OPTIONS) {
      const value = options[key];
      if (value) (this as Record<string, unknown>)[key] = value;
    }
    this.timeoutSec = options.timeoutSec ?? 30;
    this.verifyTls = options.verifyTls ?? true;
    this.readAttempts = options.readAttempts ?? 3;
    Object.freeze(this);
  }

  /** A copy with `overrides` applied; this config is unchanged. */
  with(overrides: Partial<QDashConfigOptions>): QDashConfig {
    return new QDashConfig({ ...this.options(), ...overrides });
  }

  /** The options this config was built from, as a plain object. */
  options(): QDashConfigOptions {
    return Object.fromEntries(Object.entries(this).filter(([, value]) => value !== undefined)) as unknown as QDashConfigOptions;
  }

  /**
   * Read `QDASH_BASE_URL`, `QDASH_API_TOKEN`, `QDASH_USERNAME`, `QDASH_PASSWORD_ENV` (default
   * `QDASH_PASSWORD`), `QDASH_PROJECT_ID`, `QDASH_CF_ACCESS_CLIENT_ID`,
   * `QDASH_CF_ACCESS_CLIENT_SECRET`, `QDASH_TIMEOUT_SECONDS`, `QDASH_VERIFY_TLS`, `QDASH_PROXY`,
   * `QDASH_USER_AGENT` and `QDASH_RETRY_MAX_ATTEMPTS`.
   */
  static fromEnv(env: Environment = process.env): QDashConfig {
    const baseUrl = env.QDASH_BASE_URL;
    if (!baseUrl) throw new QDashConfigError("Environment variable QDASH_BASE_URL is required.");
    const options: Record<string, unknown> = { baseUrl, passwordEnv: env.QDASH_PASSWORD_ENV || "QDASH_PASSWORD" };
    const strings = {
      apiToken: "QDASH_API_TOKEN",
      username: "QDASH_USERNAME",
      projectId: "QDASH_PROJECT_ID",
      cfAccessClientId: "QDASH_CF_ACCESS_CLIENT_ID",
      cfAccessClientSecret: "QDASH_CF_ACCESS_CLIENT_SECRET",
      proxy: "QDASH_PROXY",
      userAgent: "QDASH_USER_AGENT",
    };
    for (const [key, variable] of Object.entries(strings)) {
      if (env[variable]) options[key] = env[variable];
    }
    const invalid: string[] = [];
    const number = (variable: string, key: string, integer: boolean) => {
      const raw = env[variable];
      if (!raw) return;
      const parsed = Number(raw.trim());
      if (raw.trim() === "" || !Number.isFinite(parsed) || (integer && !Number.isInteger(parsed))) invalid.push(variable);
      else options[key] = parsed;
    };
    number("QDASH_TIMEOUT_SECONDS", "timeoutSec", false);
    number("QDASH_RETRY_MAX_ATTEMPTS", "readAttempts", true);
    if (env.QDASH_VERIFY_TLS) {
      const parsed = parseBoolean(env.QDASH_VERIFY_TLS);
      if (parsed === undefined) invalid.push("QDASH_VERIFY_TLS");
      else options.verifyTls = parsed;
    }
    if (invalid.length === 0) invalid.push(...configProblems(options as unknown as QDashConfigOptions).map(envName));
    if (invalid.length > 0) {
      throw new QDashConfigError(`Invalid config values loaded from environment: ${invalid.join(", ")}`);
    }
    return new QDashConfig(options as unknown as QDashConfigOptions);
  }

  /**
   * Read `profile` of a config file.
   *
   * Without `path`, read `defaultConfigPath()` (`config.toml`); only when that file does not
   * exist, read the deprecated `legacyConfigPath()` (`config.ini`). An explicit `path` is read
   * as TOML (`.toml`) or deprecated INI (`.ini`), with no fallback. Without `profile`, use the
   * TOML `default_profile`, else `"default"`. An `api_token_env` of the selected profile is
   * read from `options.env` (default `process.env`). Reading an INI file emits a
   * `DeprecationWarning` with code `QDASH_SDK_INI_CONFIG`.
   */
  static async fromFile(
    profile?: string,
    path?: string,
    options: { env?: Environment } = {},
  ): Promise<QDashConfig> {
    return loadConfig(profile, path, options.env ?? process.env);
  }

  /** Read a legacy INI profile at an explicit path, including files without an extension. */
  static async fromIniFile(path: string, profile?: string): Promise<QDashConfig> {
    const configPath = expandUser(path);
    const file = readText(configPath);
    if (file.kind === "missing") throw new QDashConfigError(`Config file not found: ${configPath}`);
    return fromIni(file.text, profile);
  }
}

function envName(field: string): string {
  const names: Record<string, string> = {
    baseUrl: "QDASH_BASE_URL",
    timeoutSec: "QDASH_TIMEOUT_SECONDS",
    readAttempts: "QDASH_RETRY_MAX_ATTEMPTS",
  };
  return names[field] ?? field;
}

/** Field names of `options` that are invalid; never their values. */
function configProblems(options: QDashConfigOptions): string[] {
  if (options === null || typeof options !== "object") return ["options"];
  const raw = options as unknown as Record<string, unknown>;
  const problems = Object.keys(raw).filter((key) => !OPTION_KEYS.has(key) && raw[key] !== undefined);
  // Like the Python SDK, the URL is not parsed here; a malformed one fails on the first request.
  if (typeof raw.baseUrl !== "string" || !raw.baseUrl) problems.push("baseUrl");
  for (const key of STRING_OPTIONS) {
    if (raw[key] !== undefined && typeof raw[key] !== "string") problems.push(key);
  }
  const timeout = raw.timeoutSec;
  if (timeout !== undefined && !(typeof timeout === "number" && Number.isFinite(timeout) && timeout > 0)) {
    problems.push("timeoutSec");
  }
  const attempts = raw.readAttempts;
  if (attempts !== undefined && !(typeof attempts === "number" && Number.isSafeInteger(attempts) && attempts >= 1)) {
    problems.push("readAttempts");
  }
  if (raw.verifyTls !== undefined && typeof raw.verifyTls !== "boolean") problems.push("verifyTls");
  return problems;
}

function parseBoolean(value: string): boolean | undefined {
  const lowered = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(lowered)) return true;
  if (["0", "false", "no", "off"].includes(lowered)) return false;
  return undefined;
}

function configDir(env: Environment): string {
  return env.XDG_CONFIG_HOME ? join(env.XDG_CONFIG_HOME, "qdash") : join(homedir(), ".config", "qdash");
}

/** `$XDG_CONFIG_HOME/qdash/config.toml`, else `~/.config/qdash/config.toml`. */
export function defaultConfigPath(env: Environment = process.env): string {
  return join(configDir(env), "config.toml");
}

/** The deprecated `config.ini` next to `defaultConfigPath()`. */
export function legacyConfigPath(env: Environment = process.env): string {
  return join(configDir(env), "config.ini");
}

/** `path` with a leading `~` or `~/` replaced by the home directory. */
export function expandUser(path: string): string {
  return path === "~" || path.startsWith("~/") ? join(homedir(), path.slice(1)) : path;
}

type Read = { kind: "ok"; text: string } | { kind: "missing" };

function readText(path: string): Read {
  let bytes: Buffer;
  try {
    bytes = readFileSync(path);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return { kind: "missing" };
    throw new QDashConfigError(`Cannot read config file ${path}: ${code ?? "read failed"}`);
  }
  try {
    return { kind: "ok", text: new TextDecoder("utf-8", { fatal: true }).decode(bytes) };
  } catch {
    throw new QDashConfigError(`Config file ${path} is not valid UTF-8.`);
  }
}

function loadConfig(profile: string | undefined, path: string | undefined, env: Environment): QDashConfig {
  if (profile !== undefined && typeof profile !== "string") throw new QDashConfigError("Config profile must be a string.");
  if (path === undefined) {
    const tomlPath = defaultConfigPath(env);
    const toml = readText(tomlPath);
    if (toml.kind === "ok") return fromToml(tomlPath, toml.text, profile, env);
    const iniPath = legacyConfigPath(env);
    const legacy = readText(iniPath);
    if (legacy.kind === "ok") {
      warnIni(iniPath, env);
      return fromIni(legacy.text, profile);
    }
    throw new QDashConfigError(`Config file not found: ${tomlPath}`);
  }
  if (typeof path !== "string") throw new QDashConfigError("Config path must be a string.");
  const configPath = expandUser(path);
  const suffix = extname(configPath).toLowerCase();
  if (suffix !== ".toml" && suffix !== ".ini") {
    throw new QDashConfigError(
      `Unsupported config file extension '${suffix || "(none)"}' for ${configPath}: use a .toml file (.ini is deprecated).`,
    );
  }
  const read = readText(configPath);
  if (read.kind === "missing") throw new QDashConfigError(`Config file not found: ${configPath}`);
  if (suffix === ".toml") return fromToml(configPath, read.text, profile, env);
  warnIni(configPath, env);
  return fromIni(read.text, profile);
}

function warnIni(path: string, env: Environment): void {
  process.emitWarning(
    `@oqtopus-team/qdash-sdk read the INI config file ${path}. Reading INI config files is deprecated ` +
      `in @oqtopus-team/qdash-sdk; move the profiles to ${defaultConfigPath(env)} as top-level ` +
      "[<name>] tables (TOML); `qdash config init` creates a starting file. @oqtopus-team/qdash-client keeps using config.ini; this deprecation applies to " +
      "@oqtopus-team/qdash-sdk only.",
    { type: "DeprecationWarning", code: INI_CONFIG_DEPRECATION_CODE },
  );
}

/** The profile section of a qdash-client `config.ini`; keys keep their INI meaning. */
function fromIni(text: string, profile: string | undefined): QDashConfig {
  const selected = profile ?? DEFAULT_PROFILE;
  const parsed = ini.parse(text) as Record<string, unknown>;
  const section = Object.hasOwn(parsed, selected) ? parsed[selected] : undefined;
  if (!isTable(section)) throw new QDashConfigError(`Config profile not found: ${selected}`);
  const value = (key: string): string | undefined => {
    const raw = section[key];
    if (raw === undefined || raw === null || raw === "") return undefined;
    return typeof raw === "string" ? raw : String(raw);
  };
  const options: Record<string, unknown> = {};
  for (const key of ["base_url", "api_token", "username", "password_env", "project_id", "cf_access_client_id", "cf_access_client_secret", "proxy", "user_agent"] as const) {
    const found = value(key);
    if (found !== undefined) options[TOML_KEYS[key]] = found;
  }
  const invalid = (): never => {
    throw new QDashConfigError(`Invalid config values in profile '${selected}'.`);
  };
  const timeout = value("timeout_sec") ?? value("timeout_seconds");
  if (timeout !== undefined) {
    const parsed = Number(timeout.trim());
    if (timeout.trim() === "" || Number.isNaN(parsed)) invalid();
    options.timeoutSec = parsed;
  }
  const attempts = value("retry_max_attempts");
  if (attempts !== undefined) {
    if (!/^\s*[+-]?\d+\s*$/.test(attempts)) invalid();
    options.readAttempts = Number(attempts.trim());
  }
  const verify = value("verify_tls");
  if (verify !== undefined) {
    const parsed = parseBoolean(verify);
    if (parsed === undefined) invalid();
    options.verifyTls = parsed;
  }
  if (!options.baseUrl) invalid();
  if (configProblems(options as unknown as QDashConfigOptions).length > 0) invalid();
  return new QDashConfig(options as unknown as QDashConfigOptions);
}

function isTable(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function parseDocument(path: string, text: string): Record<string, unknown> {
  try {
    return parseToml(text, { integersAsBigInt: true }) as Record<string, unknown>;
  } catch (error) {
    if (error instanceof TomlError) {
      // The parser's message ends with the offending lines; keep only its reason and position.
      const reason = error.message.split("\n")[0]?.replace(/^Invalid TOML document:\s*/, "") ?? "parse error";
      throw new QDashConfigError(
        `Invalid TOML in config file ${path}: ${reason} (at line ${error.line}, column ${error.column})`,
      );
    }
    throw new QDashConfigError(`Invalid TOML in config file ${path}.`);
  }
}

function fromToml(path: string, text: string, profile: string | undefined, env: Environment): QDashConfig {
  const document = parseDocument(path, text);
  if (Object.hasOwn(document, LEGACY_PROFILES_KEY)) {
    throw new QDashConfigError(
      `Config file ${path} uses the removed [profiles.<name>] layout: move each [profiles.<name>] table ` +
        "to a top-level [<name>] table and keep default_profile at the top.",
    );
  }
  const defaultProfile = document[DEFAULT_PROFILE_KEY];
  if (defaultProfile !== undefined && (typeof defaultProfile !== "string" || !defaultProfile)) {
    throw new QDashConfigError(`default_profile in config file ${path} must be a non-empty string.`);
  }
  // Every other root key is a profile table; a root value holds a misplaced setting.
  const unknown = Object.keys(document)
    .filter((key) => key !== DEFAULT_PROFILE_KEY && !isTable(document[key]))
    .sort();
  if (unknown.length > 0) {
    throw new QDashConfigError(
      `Unknown top-level keys in config file ${path}: ${unknown.join(", ")}. Put profile settings under a [<name>] table.`,
    );
  }
  if (Object.hasOwn(document, "")) throw new QDashConfigError(`A profile in config file ${path} has an empty name.`);
  const selected = profile ?? (defaultProfile as string | undefined) ?? DEFAULT_PROFILE;
  if (RESERVED_PROFILE_NAMES.has(selected)) throw new QDashConfigError(`Config profile name '${selected}' is reserved.`);
  if (!Object.hasOwn(document, selected)) throw new QDashConfigError(`Config profile not found: ${selected}`);
  return profileConfig(selected, document[selected] as Record<string, unknown>, env);
}

/** Validate one `[<name>]` profile table; error messages never carry values. */
function profileConfig(profile: string, table: Record<string, unknown>, env: Environment): QDashConfig {
  const unknown = Object.keys(table).filter((key) => !TOML_PROFILE_KEYS.has(key)).sort();
  if (unknown.length > 0) throw new QDashConfigError(`Unknown keys in profile '${profile}': ${unknown.join(", ")}`);
  for (const key of [...TOML_STRING_KEYS].sort()) {
    if (key in table && typeof table[key] !== "string") {
      throw new QDashConfigError(`'${key}' in profile '${profile}' must be a string.`);
    }
  }
  if ("verify_tls" in table && typeof table.verify_tls !== "boolean") {
    throw new QDashConfigError(`'verify_tls' in profile '${profile}' must be a boolean.`);
  }
  const timeout = table.timeout_sec;
  if (timeout !== undefined && typeof timeout !== "number" && typeof timeout !== "bigint") {
    throw new QDashConfigError(`'timeout_sec' in profile '${profile}' must be a number.`);
  }
  const attempts = table.read_attempts;
  // Integers parse as bigint, so a float such as 3.0 is not an integer here, as in Python.
  if (attempts !== undefined && typeof attempts !== "bigint") {
    throw new QDashConfigError(`'read_attempts' in profile '${profile}' must be an integer.`);
  }

  // Empty strings mean unset, as in config.ini.
  const raw: Record<string, unknown> = Object.fromEntries(Object.entries(table).filter(([, value]) => value !== ""));
  if ("api_token_env" in table) {
    const variable = raw.api_token_env as string | undefined;
    delete raw.api_token_env;
    if (!variable) {
      throw new QDashConfigError(`'api_token_env' in profile '${profile}' must name an environment variable.`);
    }
    if (raw.api_token) {
      throw new QDashConfigError(`Profile '${profile}' sets both 'api_token' and 'api_token_env'; set one.`);
    }
    const token = env[variable];
    if (!token) {
      throw new QDashConfigError(
        `Environment variable ${variable} named by 'api_token_env' in profile '${profile}' is not set or empty.`,
      );
    }
    raw.api_token = token;
  }
  if (!("base_url" in raw)) throw new QDashConfigError(`'base_url' is required in profile '${profile}'.`);
  const options: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(raw)) {
    const field = TOML_KEYS[key as keyof typeof TOML_KEYS];
    options[field] = typeof value === "bigint" ? Number(value) : value;
  }
  const problems = configProblems(options as unknown as QDashConfigOptions);
  if (problems.length > 0) {
    const snake = Object.fromEntries(Object.entries(TOML_KEYS).map(([key, field]) => [field, key]));
    const fields = [...new Set(problems.map((field) => snake[field] ?? field))].sort();
    throw new QDashConfigError(`Invalid config values in profile '${profile}': ${fields.join(", ")}`);
  }
  return new QDashConfig(options as unknown as QDashConfigOptions);
}
