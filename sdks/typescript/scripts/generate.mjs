#!/usr/bin/env node
/**
 * Generate src/_generated from docs/oas/openapi.json with Fern's TypeScript SDK generator.
 *
 * The generator runs in local mode with the CLI version pinned in fern/fern.config.json and
 * the generator version pinned in fern/generators.yml. It needs Node.js (npx) and Docker; no
 * Fern account or token. Only the TypeScript sources are kept; they are never edited by hand.
 *
 * --check regenerates into a temporary tree and fails when the committed tree differs.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SDK_ROOT = fileURLToPath(new URL("..", import.meta.url));
const FERN_DIR = join(SDK_ROOT, "fern");
// generators.yml writes the Fern output here; build/ is ignored by git.
const FERN_OUTPUT = join(SDK_ROOT, "build", "fern-typescript");
const TARGET = join(SDK_ROOT, "src", "_generated");
const FERN_GROUP = "typescript-sdk";

function files(root) {
  const found = new Map();
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      const rel = relative(root, path).split(sep).join("/");
      if (statSync(path).isDirectory()) {
        // .fern/ holds run metadata, not package sources.
        if (name !== ".fern") walk(path);
      } else if (name.endsWith(".ts")) {
        found.set(rel, readFileSync(path));
      }
    }
  };
  if (existsSync(root)) walk(root);
  return found;
}

function runFern() {
  const version = JSON.parse(readFileSync(join(FERN_DIR, "fern.config.json"), "utf8")).version;
  rmSync(FERN_OUTPUT, { recursive: true, force: true });
  const npx = process.platform === "win32" ? "npx.cmd" : "npx";
  const result = spawnSync(npx, ["--yes", `fern-api@${version}`, "generate", "--group", FERN_GROUP, "--local", "--force"], {
    cwd: FERN_DIR,
    encoding: "utf8",
  });
  if (result.error || result.status !== 0) {
    process.stderr.write(`${result.stdout ?? ""}${result.stderr ?? ""}${result.error ? `${result.error.message}\n` : ""}`);
    throw new Error("Fern generation failed (are npx and Docker available, and is Docker running?)");
  }
  const generated = files(FERN_OUTPUT);
  if (generated.size === 0) throw new Error(`Fern wrote no TypeScript sources to ${FERN_OUTPUT}`);
  return generated;
}

function write(generated, target) {
  rmSync(target, { recursive: true, force: true });
  for (const [name, content] of generated) {
    const path = join(target, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
}

function differences(expected, actual) {
  const changed = [...expected.keys()].filter((name) => !actual.has(name) || !actual.get(name).equals(expected.get(name)));
  changed.push(...[...actual.keys()].filter((name) => !expected.has(name)));
  return changed.sort();
}

const check = process.argv.includes("--check");
const generated = runFern();
if (!check) {
  write(generated, TARGET);
} else {
  const scratch = mkdtempSync(join(tmpdir(), "qdash-sdk-ts-"));
  try {
    write(generated, scratch);
    const changed = differences(files(scratch), files(TARGET));
    if (changed.length > 0) {
      const listed = changed.slice(0, 20).map((name) => `\n  ${name}`).join("");
      const more = changed.length > 20 ? `\n  ... and ${changed.length - 20} more` : "";
      console.error(`sdks/typescript/src/_generated is stale; run: task generate-typescript-sdk${listed}${more}`);
      process.exitCode = 1;
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}
