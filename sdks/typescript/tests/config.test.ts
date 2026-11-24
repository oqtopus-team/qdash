import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  INI_CONFIG_DEPRECATION_CODE,
  QDash,
  QDashConfig,
  QDashConfigError,
  defaultConfigPath,
  legacyConfigPath,
} from "../src/index.js";

interface Case {
  name: string;
  toml: string;
  profile?: string;
  env?: Record<string, string>;
  expected?: Record<string, unknown>;
  error?: string;
}

const shared = JSON.parse(readFileSync(new URL("../../testdata/config_profiles.json", import.meta.url), "utf8")) as {
  defaults: Record<string, unknown>;
  valid: Case[];
  invalid: Case[];
  secret: string;
};

const SNAKE: Record<string, string> = {
  baseUrl: "base_url",
  apiToken: "api_token",
  username: "username",
  passwordEnv: "password_env",
  projectId: "project_id",
  cfAccessClientId: "cf_access_client_id",
  cfAccessClientSecret: "cf_access_client_secret",
  timeoutSec: "timeout_sec",
  verifyTls: "verify_tls",
  proxy: "proxy",
  userAgent: "user_agent",
  readAttempts: "read_attempts",
};

/** A config's fields in snake_case with every unset one as null, as the Python model dumps them. */
function dumped(config: QDashConfig): Record<string, unknown> {
  const out: Record<string, unknown> = Object.fromEntries(Object.values(SNAKE).map((key) => [key, null]));
  for (const [field, value] of Object.entries(config.options())) out[SNAKE[field]!] = value;
  return out;
}

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "qdash-sdk-config-"));
});
afterEach(() => {
  vi.restoreAllMocks();
});

function file(name: string, text: string | Buffer): string {
  const path = join(dir, name);
  writeFileSync(path, text);
  return path;
}

describe("config.toml cases shared with the Python SDK", () => {
  it.each(shared.valid.map((entry) => [entry.name, entry] as const))("%s", async (_name, entry) => {
    const path = file("config.toml", entry.toml);
    const config = await QDashConfig.fromFile(entry.profile, path, { env: entry.env ?? {} });
    expect(dumped(config)).toEqual({ ...shared.defaults, ...entry.expected });
  });

  it.each(shared.invalid.map((entry) => [entry.name, entry] as const))("%s", async (_name, entry) => {
    const path = file("config.toml", entry.toml);
    const error = await QDashConfig.fromFile(entry.profile, path, { env: entry.env ?? {} }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(QDashConfigError);
    const message = (error as Error).message;
    expect(message).toMatch(new RegExp(entry.error!));
    expect(message).not.toContain(shared.secret);
    expect((error as Error).cause).toBeUndefined();
  });
});

describe("config file discovery", () => {
  const toml = '[profiles.default]\nbase_url = "http://toml.local"\napi_token = "t"\n';
  const ini = "[default]\nbase_url = http://ini.local\napi_token = i\ntimeout_seconds = 7\nretry_max_attempts = 2\nverify_tls = false\n";

  it("follows XDG_CONFIG_HOME, else ~/.config/qdash", () => {
    expect(defaultConfigPath({ XDG_CONFIG_HOME: "/x" })).toBe("/x/qdash/config.toml");
    expect(legacyConfigPath({ XDG_CONFIG_HOME: "/x" })).toBe("/x/qdash/config.ini");
    expect(defaultConfigPath({})).toMatch(/\.config[/\\]qdash[/\\]config\.toml$/);
  });

  it("prefers config.toml and never merges or warns about the INI beside it", async () => {
    mkdirSync(join(dir, "qdash"));
    file("qdash/config.toml", toml);
    file("qdash/config.ini", ini);
    const warn = vi.spyOn(process, "emitWarning").mockImplementation(() => {});
    const config = await QDashConfig.fromFile(undefined, undefined, { env: { XDG_CONFIG_HOME: dir } });
    expect(config.baseUrl).toBe("http://toml.local");
    expect(config.timeoutSec).toBe(30);
    expect(warn).not.toHaveBeenCalled();
  });

  it("falls back to config.ini only without config.toml, with a deprecation of the SDK", async () => {
    mkdirSync(join(dir, "qdash"));
    file("qdash/config.ini", ini);
    const warn = vi.spyOn(process, "emitWarning").mockImplementation(() => {});
    const config = await QDashConfig.fromFile(undefined, undefined, { env: { XDG_CONFIG_HOME: dir } });
    expect(config.options()).toEqual({
      baseUrl: "http://ini.local",
      apiToken: "i",
      timeoutSec: 7,
      readAttempts: 2,
      verifyTls: false,
    });
    expect(warn).toHaveBeenCalledTimes(1);
    const [message, options] = warn.mock.calls[0]!;
    expect(options).toEqual({ type: "DeprecationWarning", code: INI_CONFIG_DEPRECATION_CODE });
    expect(String(message)).toMatch(/deprecated in @oqtopus-team\/qdash-sdk/);
    expect(String(message)).toMatch(/qdash-client keeps using config\.ini/);
    expect(String(message)).not.toContain("api_token = i");
  });

  it("does not fall back on an invalid config.toml or a missing TOML profile", async () => {
    mkdirSync(join(dir, "qdash"));
    file("qdash/config.ini", ini);
    file("qdash/config.toml", "[profiles.default\n");
    const env = { XDG_CONFIG_HOME: dir };
    await expect(QDashConfig.fromFile(undefined, undefined, { env })).rejects.toThrow(/Invalid TOML/);
    file("qdash/config.toml", toml);
    await expect(QDashConfig.fromFile("lab", undefined, { env })).rejects.toThrow(/Config profile not found: lab/);
  });

  it("reports the TOML path when neither file exists", async () => {
    await expect(QDashConfig.fromFile(undefined, undefined, { env: { XDG_CONFIG_HOME: dir } })).rejects.toThrow(
      `Config file not found: ${join(dir, "qdash", "config.toml")}`,
    );
  });

  it("reads an explicit path by its extension, with no fallback", async () => {
    const warn = vi.spyOn(process, "emitWarning").mockImplementation(() => {});
    const iniPath = file("legacy.ini", ini);
    expect((await QDashConfig.fromFile(undefined, iniPath)).baseUrl).toBe("http://ini.local");
    expect(warn).toHaveBeenCalledTimes(1);
    await expect(QDashConfig.fromFile("missing", iniPath)).rejects.toThrow(/Config profile not found: missing/);
    await expect(QDashConfig.fromFile(undefined, join(dir, "absent.toml"))).rejects.toThrow(/Config file not found/);
    for (const name of ["config.yaml", "config", "config.json"]) {
      await expect(QDashConfig.fromFile(undefined, file(name, toml))).rejects.toThrow(/Unsupported config file extension/);
    }
  });

  it("rejects invalid INI values without echoing them", async () => {
    vi.spyOn(process, "emitWarning").mockImplementation(() => {});
    const path = file("bad.ini", `[default]\nbase_url = http://x\napi_token = ${shared.secret}\nverify_tls = maybe\n`);
    const error = await QDashConfig.fromFile(undefined, path).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(QDashConfigError);
    expect((error as Error).message).toBe("Invalid config values in profile 'default'.");
  });

  it("reports unreadable and non-UTF-8 files", async () => {
    mkdirSync(join(dir, "dir.toml"));
    await expect(QDashConfig.fromFile(undefined, join(dir, "dir.toml"))).rejects.toThrow(/Cannot read config file/);
    await expect(QDashConfig.fromFile(undefined, file("bad.toml", Buffer.from([0xff, 0xfe])))).rejects.toThrow(/not valid UTF-8/);
  });

  it("builds a session from a profile, its project overridable", async () => {
    const path = file("config.toml", '[profiles.lab]\nbase_url = "http://lab.local"\napi_token = "t"\nproject_id = "p1"\n');
    const qdash = await QDash.fromProfile("lab", path);
    expect(qdash.projectId).toBe("p1");
    expect((await QDash.fromProfile("lab", path, { projectId: "p2" })).projectId).toBe("p2");
  });
});

describe("QDashConfig", () => {
  it("reads QDASH_* variables and rejects invalid ones by name only", () => {
    const config = QDashConfig.fromEnv({
      QDASH_BASE_URL: "https://qdash.example/api/",
      QDASH_API_TOKEN: "t",
      QDASH_PROJECT_ID: "p",
      QDASH_TIMEOUT_SECONDS: "12.5",
      QDASH_RETRY_MAX_ATTEMPTS: "5",
      QDASH_VERIFY_TLS: "false",
      QDASH_CF_ACCESS_CLIENT_ID: "id",
      QDASH_CF_ACCESS_CLIENT_SECRET: "secret",
    });
    expect(config.options()).toEqual({
      baseUrl: "https://qdash.example/api",
      apiToken: "t",
      passwordEnv: "QDASH_PASSWORD",
      projectId: "p",
      cfAccessClientId: "id",
      cfAccessClientSecret: "secret",
      timeoutSec: 12.5,
      verifyTls: false,
      readAttempts: 5,
    });
    expect(() => QDashConfig.fromEnv({})).toThrow(/QDASH_BASE_URL is required/);
    for (const [name, value] of [
      ["QDASH_TIMEOUT_SECONDS", "0"],
      ["QDASH_TIMEOUT_SECONDS", "soon"],
      ["QDASH_RETRY_MAX_ATTEMPTS", "1.5"],
      ["QDASH_VERIFY_TLS", "maybe"],
    ]) {
      expect(() => QDashConfig.fromEnv({ QDASH_BASE_URL: "http://x", [name!]: value })).toThrow(
        `Invalid config values loaded from environment: ${name}`,
      );
    }
  });

  it("is frozen, rejects unknown options and copies with overrides", () => {
    const config = new QDashConfig({ baseUrl: "http://x", apiToken: "t" });
    expect(Object.isFrozen(config)).toBe(true);
    expect(config.with({ projectId: "p" }).projectId).toBe("p");
    expect(config.projectId).toBeUndefined();
    expect(() => new QDashConfig({ baseUrl: "http://x", timeoutSeconds: 3 } as never)).toThrow(/timeoutSeconds/);
    expect(() => new QDashConfig({ baseUrl: "http://x", readAttempts: 0 })).toThrow(/readAttempts/);
    expect(() => new QDashConfig({ baseUrl: "" })).toThrow(/baseUrl/);
  });

  it("refuses proxy or TLS overrides the built-in fetch would silently ignore", () => {
    for (const options of [{ proxy: "http://proxy:3128" }, { verifyTls: false }]) {
      const config = { baseUrl: "http://x", apiToken: "t", ...options };
      expect(() => new QDash(config)).toThrow(/need a custom fetch/);
      expect(() => new QDash(config, { fetch: async () => new Response("{}") })).not.toThrow();
    }
  });

  it("needs authentication before anything is sent", () => {
    expect(() => new QDash({ baseUrl: "http://x" })).toThrow(/No authentication configured/);
    expect(() => new QDash({ baseUrl: "http://x", username: "alice" })).toThrow(/password_env is required/);
    expect(() => new QDash({ baseUrl: "http://x", username: "alice", passwordEnv: "PW" })).not.toThrow();
  });
});
