import { existsSync, lstatSync, mkdtempSync, readFileSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { parse as parseToml } from "smol-toml";
import { beforeEach, describe, expect, it } from "vitest";

import { renderConfig, runCli, tomlKey, tomlString } from "../src/config-init.js";
import { QDashConfig } from "../src/index.js";

const SECRET = "s3cret-token-value";
const testdata = (name: string) => readFileSync(new URL(`../../testdata/${name}`, import.meta.url), "utf8");
// The file both SDKs' `qdash config init` writes without options.
const DEFAULT_FILE = testdata("config_init_default.toml");
// The file both SDKs write for TOKEN_ENV_ARGV.
const TOKEN_ENV_FILE = testdata("config_init_token_env.toml");
const TOKEN_ENV_ARGV = ["--profile", "lab", "--base-url", "https://qdash.example/api", "--project-id", "p1", "--api-token-env", "QDASH_LAB_TOKEN"];
// Every profile key of config.toml (the profile fields of config.ts).
const PROFILE_KEYS = [
  "api_token", "api_token_env", "base_url", "cf_access_client_id", "cf_access_client_secret", "password_env",
  "project_id", "proxy", "read_attempts", "timeout_sec", "user_agent", "username", "verify_tls",
];

/** The profile table `name` of a config file. */
function profileTable(text: string, name: string): Record<string, unknown> {
  const table = (parseToml(text) as Record<string, Record<string, unknown> | undefined>)[name];
  if (table === undefined) throw new Error(`no profile ${name}`);
  return table;
}

/** The settings of the commented-out `key = value` lines, each parsed as TOML. */
function commentedSettings(text: string): Record<string, unknown> {
  const settings: Record<string, unknown> = {};
  for (const line of text.split("\n")) {
    if (/^# [a-z_]+ = /.test(line)) Object.assign(settings, parseToml(line.slice(2)));
  }
  return settings;
}
const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as {
  bin: Record<string, string>;
  scripts: Record<string, string>;
};

let dir: string;
let out: string[];
let err: string[];
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "qdash-sdk-init-"));
  out = [];
  err = [];
});

function run(argv: string[], env: Record<string, string> = { XDG_CONFIG_HOME: join(dir, "xdg") }): number {
  return runCli(argv, { env, stdout: (line) => out.push(line), stderr: (line) => err.push(line) });
}

describe("qdash config init", () => {
  it("is the package's qdash executable", () => {
    expect(packageJson.bin).toEqual({ qdash: "./dist/cli.js" });
    expect(packageJson.scripts.build).toContain("src/cli.ts");
  });

  it("writes the default profile at the default path, owner-only", async () => {
    expect(run(["config", "init"])).toBe(0);
    const path = join(dir, "xdg", "qdash", "config.toml");
    expect(readFileSync(path, "utf8")).toBe(DEFAULT_FILE);
    if (process.platform !== "win32") expect(statSync(path).mode & 0o777).toBe(0o600);
    expect(out.join("\n")).toContain(`Created ${path} with profile local as default_profile.`);
    expect(out.join("\n")).toContain(`paste your QDash API token (Settings > API Token) into api_token in ${path}`);
    expect(out.join("\n")).not.toContain("export");
    expect(out.join("\n")).not.toContain("not the default config path");

    // The commented-out api_token_env is not read: the empty api_token means no token.
    const config = await QDashConfig.fromFile(undefined, undefined, {
      env: { XDG_CONFIG_HOME: join(dir, "xdg"), QDASH_LOCAL_TOKEN: SECRET },
    });
    expect(config.options()).toEqual({ baseUrl: "http://localhost:5714/api", timeoutSec: 30, verifyTls: true, readAttempts: 3 });
  });

  it("lists every profile key, setting only the common ones", () => {
    const active = profileTable(DEFAULT_FILE, "local");
    expect(active).toEqual({ base_url: "http://localhost:5714/api", api_token: "", timeout_sec: 30, verify_tls: true, read_attempts: 3 });
    const commented = commentedSettings(DEFAULT_FILE);
    expect(Object.keys(commented).filter((key) => key in active)).toEqual([]);
    expect([...Object.keys(commented), ...Object.keys(active)].sort()).toEqual(PROFILE_KEYS);
    for (const value of Object.values(commented)) expect(value).toMatch(/.+/);
    expect(commented.api_token_env).toBe("QDASH_LOCAL_TOKEN");
  });

  it("sets the named token variable and the project id when given", async () => {
    const path = join(dir, "config.toml");
    expect(run(["config", "init", ...TOKEN_ENV_ARGV, "--path", path])).toBe(0);
    const text = readFileSync(path, "utf8");
    expect(text).toBe(TOKEN_ENV_FILE);
    expect(out.join("\n")).toContain("Next: set QDASH_LAB_TOKEN to your QDash API token");
    expect(out.join("\n")).toContain("export QDASH_LAB_TOKEN=<token>");

    const active = profileTable(text, "lab");
    expect([active.api_token_env, active.project_id, "api_token" in active]).toEqual(["QDASH_LAB_TOKEN", "p1", false]);
    expect(text.split("project_id = ").length).toBe(2);
    const commented = commentedSettings(text);
    expect(Object.keys(commented).filter((key) => key in active)).toEqual([]);
    expect([...Object.keys(commented), ...Object.keys(active)].sort()).toEqual(PROFILE_KEYS);
    expect("api_token" in commented).toBe(true);

    const config = await QDashConfig.fromFile(undefined, path, { env: { QDASH_LAB_TOKEN: SECRET } });
    expect([config.apiToken, config.projectId, config.username]).toEqual([SECRET, "p1", undefined]);
  });

  it("writes custom values that read back, creating parent directories", async () => {
    const path = join(dir, "a", "b", "lab.toml");
    const argv = ["config", "init", "--profile", "lab", "--base-url", "https://qdash.example/api", "--project-id", "p1", "--api-token-env", "QDASH_LAB_TOKEN", "--path", path];
    expect(run(argv)).toBe(0);
    expect(out.join("\n")).toContain("not the default config path");
    expect(existsSync(join(dir, "xdg"))).toBe(false);
    const config = await QDashConfig.fromFile(undefined, path, { env: { QDASH_LAB_TOKEN: "t" } });
    expect([config.baseUrl, config.apiToken, config.projectId]).toEqual(["https://qdash.example/api", "t", "p1"]);
  });

  it.each(["lab.dev", 'quote " and \\ backslash', "tab\tnew\nline", "ünïcode 量子", "[x]", "del\x7f"])(
    "escapes the profile name %j",
    async (profile) => {
      const path = join(dir, "config.toml");
      const url = 'http://h/"\\\n';
      expect(run(["config", "init", "--profile", profile, "--base-url", url, "--path", path])).toBe(0);
      const document = parseToml(readFileSync(path, "utf8")) as Record<string, unknown>;
      expect(Object.keys(document).sort()).toEqual(["default_profile", profile].sort());
      expect(document.default_profile).toBe(profile);
      const env = { QDASH_LOCAL_TOKEN: "t" };
      expect((await QDashConfig.fromFile(undefined, path, { env })).baseUrl).toBe(url);
      expect((await QDashConfig.fromFile(profile, path, { env })).baseUrl).toBe(url);
    },
  );

  it("renders TOML like the Python SDK", () => {
    expect(tomlKey("local-1_A")).toBe("local-1_A");
    expect(tomlKey("a.b")).toBe('"a.b"');
    expect(tomlString('a"b\\c\x01\x7f\r')).toBe('"a\\"b\\\\c\\u0001\\u007F\\r"');
    expect(renderConfig("local", "http://localhost:5714/api")).toBe(DEFAULT_FILE);
    const text = renderConfig("p", "u", "E", "proj");
    expect(text).toContain('\napi_token_env = "E"\n');
    expect(text).toContain('\nproject_id = "proj"\n');
  });

  it.each([false, true])("refuses an existing file (symlink: %s)", (symlink) => {
    const path = join(dir, "config.toml");
    const target = join(dir, "target.toml");
    if (symlink) symlinkSync(target, path);
    else writeFileSync(path, "keep");
    expect(run(["config", "init", "--path", path])).toBe(1);
    expect(err.join("\n")).toContain("already exists; it was left unchanged");
    if (symlink) {
      expect(lstatSync(path).isSymbolicLink()).toBe(true);
      expect(existsSync(target)).toBe(false);
    } else {
      expect(readFileSync(path, "utf8")).toBe("keep");
    }
  });

  it("reports a path it cannot create", () => {
    writeFileSync(join(dir, "file"), "");
    expect(run(["config", "init", "--path", join(dir, "file", "config.toml")])).toBe(1);
    expect(err.join("\n")).toContain("cannot create");
    expect(err.join("\n")).not.toContain("already exists");
  });

  it.each([
    ["--profile", "", "--profile must not be empty"],
    ["--profile", "profiles", "reserved name"],
    ["--profile", "default_profile", "reserved name"],
    ["--profile", "bad\ud800", "valid Unicode"],
    ["--base-url", "", "--base-url must not be empty"],
    ["--project-id", "", "--project-id must not be empty"],
    ["--api-token-env", "", "environment variable name"],
    ["--api-token-env", `${SECRET}-x`, "environment variable name"],
    ["--api-token-env", "1ABC", "environment variable name"],
    ["--path", "config.json", "must name a .toml file"],
    ["--path", "", "--path must not be empty"],
  ])("rejects %s %j", (option, value, message) => {
    expect(run(["config", "init", option, value])).toBe(2);
    expect(err.join("\n")).toContain(message);
    expect(err.join("\n")).not.toContain(SECRET);
    expect(existsSync(join(dir, "xdg"))).toBe(false);
  });

  it.each([[[]], [["config"]], [["config", "init", "--bogus"]], [["other"]], [["config", "init", "extra"]]])(
    "exits 2 on usage %j",
    (argv) => {
      expect(run(argv)).toBe(2);
      expect(err.join("\n")).toContain("qdash: error:");
    },
  );

  it("prints help with exit 0", () => {
    expect(run(["config", "init", "--help"])).toBe(0);
    expect(out.join("\n")).toContain("usage: qdash config init");
  });
});
