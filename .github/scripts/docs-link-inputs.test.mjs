import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { main, selectLinkInputs } from "./docs-link-inputs.mjs";

const tracked = ["docs/index.md", "docs/reference/pi-qdash.md", "docs/public/logo.svg"];

function select(eventName, changed, exists = () => true) {
  return selectLinkInputs({
    eventName,
    changedFiles: () => changed,
    trackedFiles: () => tracked,
    exists,
  });
}

test("a pull request that changes pages checks only those pages", () => {
  assert.deepEqual(select("pull_request", ["docs/reference/pi-qdash.md", "docs/public/logo.svg"]), {
    scope: "changed",
    files: ["docs/reference/pi-qdash.md"],
  });
});

test("a pull request without page changes checks the complete page set", () => {
  assert.deepEqual(select("pull_request", []), {
    scope: "full",
    files: ["docs/index.md", "docs/reference/pi-qdash.md"],
  });
});

test("scheduled and manual runs check the complete page set", () => {
  for (const eventName of ["schedule", "workflow_dispatch"]) {
    const changedFiles = () => assert.fail("changed files must not be read");
    const result = selectLinkInputs({
      eventName,
      changedFiles,
      trackedFiles: () => tracked,
      exists: () => true,
    });
    assert.equal(result.scope, "full");
  }
});

test("an empty complete page set fails", () => {
  assert.throws(
    () =>
      selectLinkInputs({
        eventName: "schedule",
        changedFiles: () => [],
        trackedFiles: () => [],
        exists: () => true,
      }),
    /No tracked Markdown files/,
  );
});

test("a selected file that does not exist fails", () => {
  assert.throws(
    () => select("pull_request", ["docs/missing.md"], (path) => path !== "docs/missing.md"),
    /do not exist: docs\/missing\.md/,
  );
});

test("a pull request run without commit SHAs fails", () => {
  const errors = [];
  const status = main(["inputs"], {
    env: { GITHUB_EVENT_NAME: "pull_request" },
    writeFile: () => assert.fail("inputs must not be written"),
    error: (line) => errors.push(line),
  });
  assert.equal(status, 1);
  assert.match(errors.join("\n"), /BASE_SHA and HEAD_SHA/);
});

function gitIn(dir, ...args) {
  const result = spawnSync("git", args, { cwd: dir, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}

test("main selects changed pages from a real git range and reports the scope", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "docs-link-inputs-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  gitIn(dir, "init", "--quiet");
  gitIn(dir, "config", "user.email", "test@example.com");
  gitIn(dir, "config", "user.name", "Test");
  gitIn(dir, "config", "commit.gpgsign", "false");
  mkdirSync(join(dir, "docs/reference"), { recursive: true });
  writeFileSync(join(dir, "docs/index.md"), "# Home\n");
  writeFileSync(join(dir, "docs/reference/old.md"), "# Old\n");
  gitIn(dir, "add", ".");
  gitIn(dir, "commit", "--quiet", "-m", "base");
  const base = gitIn(dir, "rev-parse", "HEAD");
  // A link-free page change and a non-ASCII file name, which git quotes without -z.
  writeFileSync(join(dir, "docs/reference/old.md"), "# Old\n\nNo links here.\n");
  writeFileSync(join(dir, "docs/reference/日本語.md"), "# Page\n");
  gitIn(dir, "rm", "--quiet", "docs/index.md");
  gitIn(dir, "add", ".");
  gitIn(dir, "commit", "--quiet", "-m", "head");
  const head = gitIn(dir, "rev-parse", "HEAD");

  const inputs = join(dir, "inputs");
  const output = join(dir, "github-output");
  const status = main([inputs], {
    env: {
      GITHUB_EVENT_NAME: "pull_request",
      BASE_SHA: base,
      HEAD_SHA: head,
      GITHUB_OUTPUT: output,
    },
    spawn: (command, args, options) => spawnSync(command, args, { ...options, cwd: dir }),
    exists: (path) => existsSync(join(dir, path)),
    log: () => {},
  });

  assert.equal(status, 0);
  assert.equal(readFileSync(inputs, "utf8"), "docs/reference/old.md\ndocs/reference/日本語.md\n");
  assert.equal(readFileSync(output, "utf8"), "scope=changed\n");
});
