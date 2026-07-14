import { chmod, mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

import ini from "ini";

import { QDashConfigError } from "./errors.js";

export interface QDashRetryConfig {
  maxAttempts: number;
  baseDelaySeconds: number;
  maxDelaySeconds: number;
}

export interface QDashConfigOptions {
  baseUrl: string;
  username?: string;
  passwordEnv?: string;
  apiToken?: string;
  projectId?: string;
  cfAccessClientId?: string;
  cfAccessClientSecret?: string;
  timeoutSeconds?: number;
  verifyTls?: boolean;
  proxy?: string;
  userAgent?: string;
  retry?: Partial<QDashRetryConfig>;
}

type Environment = Record<string, string | undefined>;

const DEFAULT_RETRY: QDashRetryConfig = {
  maxAttempts: 3,
  baseDelaySeconds: 0.2,
  maxDelaySeconds: 5,
};

function optional(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function positiveNumber(value: unknown, name: string, fallback: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new QDashConfigError(`${name} must be a positive number`);
  }
  return parsed;
}

function nonNegativeNumber(value: unknown, name: string, fallback: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new QDashConfigError(`${name} must be a non-negative number`);
  }
  return parsed;
}

function booleanValue(value: unknown, name: string, fallback: boolean): boolean {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (["1", "true", "yes", "on"].includes(value.toLowerCase())) return true;
    if (["0", "false", "no", "off"].includes(value.toLowerCase())) return false;
  }
  throw new QDashConfigError(`${name} must be a boolean`);
}

export function defaultConfigPath(env: Environment = process.env): string {
  return env.XDG_CONFIG_HOME
    ? join(env.XDG_CONFIG_HOME, "qdash", "config.ini")
    : join(homedir(), ".config", "qdash", "config.ini");
}

export class QDashConfig {
  readonly baseUrl: string;
  readonly username?: string;
  readonly passwordEnv?: string;
  readonly apiToken?: string;
  readonly projectId?: string;
  readonly cfAccessClientId?: string;
  readonly cfAccessClientSecret?: string;
  readonly timeoutSeconds: number;
  readonly verifyTls: boolean;
  readonly proxy?: string;
  readonly userAgent: string;
  readonly retry: QDashRetryConfig;

  constructor(options: QDashConfigOptions) {
    const baseUrl = options.baseUrl?.replace(/\/+$/, "");
    if (!baseUrl) throw new QDashConfigError("baseUrl is required");
    try {
      new URL(baseUrl);
    } catch (cause) {
      throw new QDashConfigError("baseUrl must be a valid URL", { cause });
    }

    this.baseUrl = baseUrl;
    this.username = optional(options.username);
    this.passwordEnv = optional(options.passwordEnv);
    this.apiToken = optional(options.apiToken);
    this.projectId = optional(options.projectId);
    this.cfAccessClientId = optional(options.cfAccessClientId);
    this.cfAccessClientSecret = optional(options.cfAccessClientSecret);
    this.timeoutSeconds = positiveNumber(options.timeoutSeconds, "timeoutSeconds", 30);
    this.verifyTls = options.verifyTls ?? true;
    this.proxy = optional(options.proxy);
    this.userAgent = optional(options.userAgent) ?? "qdash-client-ts/dev";
    this.retry = {
      maxAttempts: positiveNumber(
        options.retry?.maxAttempts,
        "retry.maxAttempts",
        DEFAULT_RETRY.maxAttempts,
      ),
      baseDelaySeconds: nonNegativeNumber(
        options.retry?.baseDelaySeconds,
        "retry.baseDelaySeconds",
        DEFAULT_RETRY.baseDelaySeconds,
      ),
      maxDelaySeconds: nonNegativeNumber(
        options.retry?.maxDelaySeconds,
        "retry.maxDelaySeconds",
        DEFAULT_RETRY.maxDelaySeconds,
      ),
    };
  }

  static fromEnv(env: Environment = process.env): QDashConfig {
    const baseUrl = env.QDASH_BASE_URL;
    if (!baseUrl) {
      throw new QDashConfigError("Environment variable QDASH_BASE_URL is required");
    }
    return new QDashConfig({
      baseUrl,
      ...(optional(env.QDASH_USERNAME) ? { username: env.QDASH_USERNAME } : {}),
      passwordEnv: env.QDASH_PASSWORD_ENV ?? "QDASH_PASSWORD",
      ...(optional(env.QDASH_API_TOKEN) ? { apiToken: env.QDASH_API_TOKEN } : {}),
      ...(optional(env.QDASH_PROJECT_ID) ? { projectId: env.QDASH_PROJECT_ID } : {}),
      ...(optional(env.QDASH_CF_ACCESS_CLIENT_ID)
        ? { cfAccessClientId: env.QDASH_CF_ACCESS_CLIENT_ID }
        : {}),
      ...(optional(env.QDASH_CF_ACCESS_CLIENT_SECRET)
        ? { cfAccessClientSecret: env.QDASH_CF_ACCESS_CLIENT_SECRET }
        : {}),
      timeoutSeconds: positiveNumber(env.QDASH_TIMEOUT_SECONDS, "QDASH_TIMEOUT_SECONDS", 30),
      verifyTls: booleanValue(env.QDASH_VERIFY_TLS, "QDASH_VERIFY_TLS", true),
      ...(optional(env.QDASH_PROXY) ? { proxy: env.QDASH_PROXY } : {}),
      userAgent: env.QDASH_USER_AGENT ?? "qdash-client-ts/dev",
      retry: {
        maxAttempts: positiveNumber(
          env.QDASH_RETRY_MAX_ATTEMPTS,
          "QDASH_RETRY_MAX_ATTEMPTS",
          3,
        ),
        baseDelaySeconds: nonNegativeNumber(
          env.QDASH_RETRY_BACKOFF_SECONDS,
          "QDASH_RETRY_BACKOFF_SECONDS",
          0.2,
        ),
        maxDelaySeconds: nonNegativeNumber(
          env.QDASH_RETRY_MAX_BACKOFF_SECONDS,
          "QDASH_RETRY_MAX_BACKOFF_SECONDS",
          5,
        ),
      },
    });
  }

  static async fromFile(profile = "default", path = defaultConfigPath()): Promise<QDashConfig> {
    let contents: string;
    try {
      contents = await readFile(path, "utf8");
    } catch (cause) {
      throw new QDashConfigError(`Config file not found: ${path}`, { cause });
    }
    const section = ini.parse(contents)[profile] as Record<string, unknown> | undefined;
    if (!section) throw new QDashConfigError(`Config profile not found: ${profile}`);

    const baseUrl = optional(section.base_url);
    if (!baseUrl) throw new QDashConfigError(`base_url is required in profile '${profile}'`);
    return new QDashConfig({
      baseUrl,
      ...(optional(section.username) ? { username: String(section.username) } : {}),
      ...(optional(section.password_env) ? { passwordEnv: String(section.password_env) } : {}),
      ...(optional(section.api_token) ? { apiToken: String(section.api_token) } : {}),
      ...(optional(section.project_id) ? { projectId: String(section.project_id) } : {}),
      ...(optional(section.cf_access_client_id)
        ? { cfAccessClientId: String(section.cf_access_client_id) }
        : {}),
      ...(optional(section.cf_access_client_secret)
        ? { cfAccessClientSecret: String(section.cf_access_client_secret) }
        : {}),
      timeoutSeconds: positiveNumber(
        section.timeout_seconds ?? section.timeout_sec,
        "timeout_seconds",
        30,
      ),
      verifyTls: booleanValue(section.verify_tls, "verify_tls", true),
      ...(optional(section.proxy) ? { proxy: String(section.proxy) } : {}),
      userAgent: optional(section.user_agent) ?? "qdash-client-ts/dev",
      retry: {
        maxAttempts: positiveNumber(section.retry_max_attempts, "retry_max_attempts", 3),
        baseDelaySeconds: nonNegativeNumber(
          section.retry_backoff_seconds ?? section.retry_base_delay_sec,
          "retry_backoff_seconds",
          0.2,
        ),
        maxDelaySeconds: nonNegativeNumber(
          section.retry_max_backoff_seconds ?? section.retry_max_delay_sec,
          "retry_max_backoff_seconds",
          5,
        ),
      },
    });
  }

  async save(profile = "default", path = defaultConfigPath()): Promise<string> {
    let parsed: Record<string, unknown> = {};
    try {
      parsed = ini.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    } catch (cause) {
      if ((cause as NodeJS.ErrnoException).code !== "ENOENT") throw cause;
    }
    parsed[profile] = {
      base_url: this.baseUrl,
      ...(this.username ? { username: this.username } : {}),
      ...(this.passwordEnv ? { password_env: this.passwordEnv } : {}),
      ...(this.apiToken ? { api_token: this.apiToken } : {}),
      ...(this.projectId ? { project_id: this.projectId } : {}),
      ...(this.cfAccessClientId ? { cf_access_client_id: this.cfAccessClientId } : {}),
      ...(this.cfAccessClientSecret
        ? { cf_access_client_secret: this.cfAccessClientSecret }
        : {}),
      timeout_seconds: this.timeoutSeconds,
      verify_tls: this.verifyTls,
      ...(this.proxy ? { proxy: this.proxy } : {}),
      user_agent: this.userAgent,
      retry_max_attempts: this.retry.maxAttempts,
      retry_backoff_seconds: this.retry.baseDelaySeconds,
      retry_max_backoff_seconds: this.retry.maxDelaySeconds,
    };
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, ini.stringify(parsed), { encoding: "utf8", mode: 0o600 });
    await chmod(path, 0o600);
    return path;
  }
}
