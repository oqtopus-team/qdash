/**
 * Where a pi-qdash tool call connects: the `QDASH_*` environment, a profile of the TOML config
 * file shared with the Python and TypeScript SDKs, or a profile of a legacy INI `config.ini`
 * (the format `@oqtopus-team/qdash-client` writes, and the Agent Runtime's private profile).
 * Every source is read by `@oqtopus-team/qdash-sdk` and connects through one SDK session.
 *
 * - `useEnv: true`, or neither `profile` nor `configPath` while `QDASH_BASE_URL` is set: the
 *   environment.
 * - An explicit `configPath` ending in `.toml` (any case): that TOML file.
 *   Any other explicit `configPath`: that legacy INI file, whatever its extension.
 * - No `configPath`: `$XDG_CONFIG_HOME/qdash/config.toml` (else `~/.config/qdash/config.toml`)
 *   when it exists, else the legacy `config.ini` next to it.
 *
 * Without `profile`, a TOML file selects its root `default_profile`, else `"default"`; an INI
 * file selects `"default"`. A TOML file is never skipped for the INI file: an unreadable or
 * invalid TOML file, or a missing profile in it, is an error.
 */
import { existsSync, readFileSync } from "node:fs";
import { extname } from "node:path";

import {
  DEFAULT_PROFILE,
  QDash,
  QDashConfig as SdkConfig,
  QDashConfigError,
  defaultConfigPath as sdkConfigPath,
  legacyConfigPath as legacyClientConfigPath,
  type QDashSessionOptions,
} from "@oqtopus-team/qdash-sdk";
import { parse as parseToml, TomlError } from "smol-toml";

import { QDashConnection } from "./qdash-connection.js";
import { errorText } from "./errors.js";

export interface ConnectionParams {
  useEnv?: boolean;
  profile?: string;
  configPath?: string;
}

type Environment = Readonly<Record<string, string | undefined>>;

export type ConfigFormat = "toml" | "ini";

/** The config file a profile is read from, and how. */
export interface ConfigFile {
  path: string;
  format: ConfigFormat;
  /** Whether the caller named the file rather than pi-qdash finding it. */
  explicit: boolean;
}

// Root keys of config.toml that are not profiles (see the SDK's RESERVED_PROFILE_NAMES).
const TOML_RESERVED = new Set(["default_profile", "profiles"]);

/** Whether a call reads `QDASH_*` variables rather than a profile file. */
export function shouldUseEnv(params: ConnectionParams, env: Environment = process.env): boolean {
  if (params.useEnv !== undefined) return params.useEnv;
  return !params.profile && !params.configPath && Boolean(env.QDASH_BASE_URL);
}

/** The config file `configPath` names, or the discovered one: config.toml, else config.ini. */
export function configFile(configPath: string | undefined, env: Environment = process.env): ConfigFile {
  if (configPath) {
    return { path: configPath, format: extname(configPath).toLowerCase() === ".toml" ? "toml" : "ini", explicit: true };
  }
  const toml = sdkConfigPath(env);
  if (existsSync(toml)) return { path: toml, format: "toml", explicit: false };
  return { path: legacyClientConfigPath(env), format: "ini", explicit: false };
}

/** The profiles of a config file, for display; never its values. */
export interface ConfigProfiles {
  path: string;
  format: ConfigFormat;
  exists: boolean;
  profiles: string[];
  /** The profile used when none is given. */
  defaultProfile: string;
  /** Why the file cannot be read or parsed; no values of the file. */
  error?: string;
}

function readTomlDocument(path: string): Record<string, unknown> {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (error) {
    throw new QDashConfigError(`Cannot read config file ${path}: ${(error as NodeJS.ErrnoException).code ?? "read failed"}`);
  }
  try {
    return parseToml(text) as Record<string, unknown>;
  } catch (error) {
    if (error instanceof TomlError) {
      // The parser's message ends with the offending lines, which may hold secrets.
      const reason = error.message.split("\n")[0]?.replace(/^Invalid TOML document:\s*/, "") ?? "parse error";
      throw new QDashConfigError(`Invalid TOML in config file ${path}: ${reason} (at line ${error.line}, column ${error.column})`);
    }
    throw new QDashConfigError(`Invalid TOML in config file ${path}.`);
  }
}

function isTable(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) && !(value instanceof Date);
}

/** List the profiles of the config file `configPath` names, or of the discovered one. */
export function configProfiles(configPath?: string, env: Environment = process.env): ConfigProfiles {
  const file = configFile(configPath, env);
  const base = { path: file.path, format: file.format, defaultProfile: DEFAULT_PROFILE };
  if (!existsSync(file.path)) return { ...base, exists: false, profiles: [] };
  if (file.format === "ini") {
    try {
      const contents = readFileSync(file.path, "utf8");
      return { ...base, exists: true, profiles: [...contents.matchAll(/^\s*\[([^\]]+)]\s*$/gm)].map((m) => m[1]) };
    } catch (error) {
      return { ...base, exists: true, profiles: [], error: `Cannot read config file ${file.path}: ${(error as NodeJS.ErrnoException).code ?? "read failed"}` };
    }
  }
  try {
    const document = readTomlDocument(file.path);
    const profiles = Object.keys(document).filter((key) => !TOML_RESERVED.has(key) && isTable(document[key]));
    const selected = document.default_profile;
    return { ...base, exists: true, profiles, defaultProfile: typeof selected === "string" && selected ? selected : DEFAULT_PROFILE };
  } catch (error) {
    return { ...base, exists: true, profiles: [], error: errorText(error) };
  }
}

/** The profile a file-backed call selects: `profile`, else the file's default. */
export function selectedProfile(params: ConnectionParams, env: Environment = process.env): string {
  if (params.profile) return params.profile;
  const file = configFile(params.configPath, env);
  if (file.format === "ini" || !existsSync(file.path)) return DEFAULT_PROFILE;
  return configProfiles(params.configPath, env).defaultProfile;
}

/** A label of where a call connects, such as `env` or `profile:lab`; no values. */
export function connectionSource(params: ConnectionParams, env: Environment = process.env): string {
  return shouldUseEnv(params, env) ? "env" : `profile:${selectedProfile(params, env)}`;
}

/** The SDK config of a TOML profile, with a hint when a legacy INI profile is shadowed. */
async function tomlConfig(file: ConfigFile, profile: string | undefined, env: Environment): Promise<SdkConfig> {
  try {
    return await SdkConfig.fromFile(profile, file.path, { env });
  } catch (error) {
    const message = errorText(error);
    const legacy = legacyClientConfigPath(env);
    if (!file.explicit && message.startsWith("Config profile not found") && existsSync(legacy)) {
      throw new QDashConfigError(
        `${message} in ${file.path}. The legacy ${legacy} is not read while ${file.path} exists; ` +
          "add the profile to config.toml, or pass configPath to use the INI file.",
        { cause: error },
      );
    }
    throw error;
  }
}

/** The SDK config a tool call connects with (see the module comment). */
export async function connectionConfig(params: ConnectionParams, env: Environment = process.env): Promise<SdkConfig> {
  if (shouldUseEnv(params, env)) return SdkConfig.fromEnv(env);
  const file = configFile(params.configPath, env);
  if (file.format === "toml") return tomlConfig(file, params.profile, env);
  return SdkConfig.fromIniFile(file.path, params.profile ?? DEFAULT_PROFILE);
}

/**
 * The connection a tool call uses: one SDK session for the call's config. `options` reach the
 * session (a host's own fetch for a proxy or custom TLS, test responses); the password of a
 * username/password profile is read from `env`.
 */
export async function connectClient(
  params: ConnectionParams,
  env: Environment = process.env,
  options: Omit<QDashSessionOptions, "env"> = {},
): Promise<QDashConnection> {
  const config = await connectionConfig(params, env);
  try {
    // The SDK parses the URL on the first request; pi-qdash refuses it before any request.
    try {
      new URL(config.baseUrl);
    } catch (cause) {
      throw new QDashConfigError("baseUrl must be a valid URL", { cause });
    }
    return new QDashConnection(new QDash(config, { ...options, env }));
  } catch (error) {
    if (shouldUseEnv(params, env)) throw error;
    const file = configFile(params.configPath, env);
    if (file.format !== "toml") throw error;
    // The SDK's messages name fields, never values.
    const name = params.profile ?? configProfiles(file.path, env).defaultProfile;
    const message = errorText(error);
    throw new QDashConfigError(`Profile '${name}' in config file ${file.path} cannot be used by pi-qdash: ${message}`, { cause: error });
  }
}

/** The `profile` parameter of the connection-taking tools. */
export const PROFILE_DESCRIPTION =
  "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise the config file's default profile " +
  "(config.toml default_profile, else 'default').";

/** The `configPath` parameter of the connection-taking tools. */
export const CONFIG_PATH_DESCRIPTION =
  "Optional path to a QDash config file: a .toml file shared with the QDash SDKs, or a legacy INI config.ini.";
