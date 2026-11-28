import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { pinClientDependency, pypiRelease, qdashRelease, releasePipeline } from "./client-release.mjs";

const input = { tags: ["v1.9.9", "v1.9.20", "v1.9.21-beta.1"], ref: "refs/heads/develop", event: "push", build: "1271" };
test("develop clients share one QDash beta in npm and PEP 440 spelling", () => {
  assert.deepEqual(qdashRelease(input), { version: "1.9.21-beta.1271", python: "1.9.21b1271", channel: "beta" });
  // A rerun of the same commit keeps its version, so publication can skip it.
  assert.deepEqual(qdashRelease({ ...input }), qdashRelease(input));
  for (const build of [undefined, "", "0", "01", "12a"]) {
    assert.throws(() => qdashRelease({ ...input, build }));
  }
  assert.equal(qdashRelease({ ...input, tags: [] }).python, "0.0.1b1271");
});
test("a QDash tag pushed before a later run moves the base, so one run computes it once", () => {
  // Release tags live on main, not develop, so the version reads every v* tag in the
  // checkout. The Python client therefore never recomputes it: it takes pypiRelease.
  const later = qdashRelease({ ...input, tags: [...input.tags, "v1.9.21"] });
  assert.deepEqual(later, { version: "1.9.22-beta.1271", python: "1.9.22b1271", channel: "beta" });
});
test("QDash release tags publish the same stable version for every client", () => {
  assert.deepEqual(qdashRelease({ ...input, ref: "refs/tags/v1.9.21" }), { version: "1.9.21", python: "1.9.21", channel: "latest" });
  for (const version of ["1.9.19", "1.9.21-beta.1", "01.9.21", "0.0.0"]) {
    assert.throws(() => qdashRelease({ ...input, ref: `refs/tags/v${version}` }));
  }
});
test("PRs, other branches, and branch dispatches only validate", () => {
  for (const [event, ref] of [["pull_request", "refs/pull/1/merge"], ["workflow_dispatch", "refs/heads/develop"], ["push", "refs/heads/main"]]) {
    assert.equal(qdashRelease({ ...input, event, ref }).channel, "check");
  }
  // Former independent pi tags no longer publish a client snapshot.
  for (const ref of ["refs/tags/pi-qdash/v0.1.11", "refs/tags/pi-qcaleval/v0.0.2"]) {
    assert.equal(qdashRelease({ ...input, ref }).channel, "check");
  }
});
test("packing pins only pi-qdash to the exact matching client artifact", () => {
  const manifest = { dependencies: { "@oqtopus-team/qdash-client": "workspace:*" } };
  const version = qdashRelease(input).version;
  assert.equal(pinClientDependency(manifest, version).dependencies["@oqtopus-team/qdash-client"], version);
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-client"], "workspace:*");
  for (const bad of [undefined, "0.0.0", "workspace:*", "file:../../clients/typescript", "^1.9.21", "beta", "1.2.3\ninjected"]) {
    assert.throws(() => pinClientDependency(manifest, bad));
  }
  assert.deepEqual(pinClientDependency({ name: "pi-qcaleval" }, undefined), { name: "pi-qcaleval" });
});
const repository = "oqtopus-team/qdash";
const sha = "0123456789abcdef0123456789abcdef01234567";
const other = "f".repeat(40);
const run = (overrides = {}) => ({
  id: 4242, run_attempt: 1, event: "push", head_branch: "develop", head_sha: sha, path: releasePipeline,
  repository: { full_name: repository }, head_repository: { full_name: repository }, ...overrides,
});
const record = (result, overrides = {}) => ({
  sha, ref: "refs/heads/develop", run_id: "4242", channel: result.channel, version: result.version, python: result.python,
  ...overrides,
});
// The remote as pypiRelease sees it: tag v1.9.21 on main at `sha`, which is also on develop.
const remote = ({ tags = { "v1.9.21": sha }, branches = ["main", "develop"], main = [sha], develop = [sha] } = {}) => ({
  tagCommit: (name) => tags[name] ?? null,
  branchExists: (name) => branches.includes(name),
  isAncestor: (commit, branch) => ({ main, develop })[branch].includes(commit),
});
const beta = () => ({ run: run(), repository, record: record(qdashRelease(input)), git: remote() });
const stable = () => ({
  run: run({ head_branch: "v1.9.21" }), repository,
  record: record(qdashRelease({ ...input, ref: "refs/tags/v1.9.21" }), { ref: "refs/tags/v1.9.21" }), git: remote(),
});
test("PyPI publishes exactly the version a trusted TypeScript run computed", () => {
  assert.deepEqual(pypiRelease(beta()), { version: "1.9.21b1271", channel: "beta" });
  assert.deepEqual(pypiRelease(stable()), { version: "1.9.21", channel: "latest" });
  // A manual retry on the tag is the same stable release.
  assert.deepEqual(pypiRelease({ ...stable(), run: run({ head_branch: "v1.9.21", event: "workflow_dispatch" }) }).channel, "latest");
  // Even after a new QDash tag, a record keeps the version its own run computed.
  const moved = qdashRelease({ ...input, tags: [...input.tags, "v1.9.21"] });
  assert.equal(pypiRelease({ ...beta(), record: record(moved) }).version, "1.9.22b1271");
  // An earlier develop commit is still trusted after develop moves on.
  assert.equal(pypiRelease({ ...beta(), git: remote({ develop: [other, sha] }) }).channel, "beta");
});
test("PyPI refuses a run that is not a trusted release source", () => {
  const cases = {
    "fork run": { ...beta(), run: run({ head_repository: { full_name: "attacker/qdash" } }) },
    "other repository": { ...beta(), repository: "attacker/qdash" },
    "pull request run": { ...beta(), run: run({ event: "pull_request" }) },
    "other workflow with the pipeline's name": { ...beta(), run: run({ path: ".github/workflows/evil.yml" }) },
    "manual develop run": { ...beta(), run: run({ event: "workflow_dispatch" }) },
    "develop commit not on develop": { ...beta(), git: remote({ develop: [other] }) },
    "beta from another branch": { ...beta(), run: run({ head_branch: "main" }) },
    "beta from a tag ref": { ...beta(), record: record(qdashRelease(input), { ref: "refs/tags/v1.9.21" }) },
    // The reported bypass: a manual run on a branch named like a tag.
    "manual run on a v-prefixed branch": {
      ...stable(), run: run({ head_branch: "v1.9.22", event: "workflow_dispatch" }),
      record: record(qdashRelease({ ...input, ref: "refs/tags/v1.9.22" }), { ref: "refs/tags/v1.9.22" }),
    },
    "branch shadowing the tag": { ...stable(), git: remote({ branches: ["main", "develop", "v1.9.21"] }) },
    "tag on another commit": { ...stable(), git: remote({ tags: { "v1.9.21": other } }) },
    "tag not on main": { ...stable(), git: remote({ main: [other] }) },
    "stable record from a branch ref": { ...stable(), record: { ...stable().record, ref: "refs/heads/v1.9.21" } },
    "stable from develop": { ...stable(), run: run() },
    "non-QDash tag name": { ...stable(), run: run({ head_branch: "v1.9.21-rc" }) },
  };
  for (const [name, args] of Object.entries(cases)) assert.throws(() => pypiRelease(args), /Refusing/, name);
});
test("PyPI refuses a record from another commit, run, ref, channel, or spelling", () => {
  const b = beta().record;
  const s = stable().record;
  for (const [release, base] of [
    [{ ...b, sha: other }, beta], [{ ...b, run_id: "4243" }, beta], [{ ...b, run_id: 4242 }, beta],
    [{ ...b, python: "1.9.21b1272" }, beta], [{ ...b, python: "1.9.21b01271" }, beta],
    [{ ...b, version: "1.9.21-beta.1271.1" }, beta], [{ ...b, channel: "check" }, beta],
    // Channel spoofing: a develop record cannot claim the stable channel.
    [{ ...b, channel: "latest" }, beta], [{ ...b, channel: "latest", version: "1.9.21", python: "1.9.21" }, beta],
    [{ ...s, version: "1.9.22", python: "1.9.22" }, stable], [{ ...s, python: "1.9.21b1" }, stable],
    [{ ...s, channel: "beta" }, stable], [{ ...b, extra: "x" }, beta], [undefined, beta], [[], beta], ["{}", beta],
  ]) {
    assert.throws(() => pypiRelease({ ...base(), record: release }), /Refusing/, JSON.stringify(release));
  }
  const { ref: _ref, ...missing } = b;
  assert.throws(() => pypiRelease({ ...beta(), record: missing }), /Refusing/);
});

// End-to-end through the CLI that publish-qdash-client.yml runs, against a real remote.
test("the --pypi CLI verifies refs and lineage on the real remote", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-release-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const env = {
    ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1",
    GIT_AUTHOR_NAME: "QDash", GIT_AUTHOR_EMAIL: "qdash@example.com",
    GIT_COMMITTER_NAME: "QDash", GIT_COMMITTER_EMAIL: "qdash@example.com",
  };
  const git = (cwd, ...args) => execFileSync("git", args, { cwd, env, encoding: "utf8" }).trim();
  const origin = join(dir, "origin.git");
  const work = join(dir, "work");
  git(dir, "init", "--quiet", "--bare", "-b", "main", origin);
  git(dir, "init", "--quiet", "-b", "main", work);
  git(work, "remote", "add", "origin", origin);
  const commit = (message) => { git(work, "commit", "--quiet", "--allow-empty", "-m", message); return git(work, "rev-parse", "HEAD"); };
  const released = commit("release");
  git(work, "tag", "-a", "v1.9.21", "-m", "QDash v1.9.21");
  git(work, "switch", "--quiet", "-c", "develop");
  const merged = commit("merged feature");
  commit("develop tip");
  git(work, "switch", "--quiet", "-c", "attacker");
  const attack = commit("modified release scripts");
  git(work, "push", "--quiet", "origin", "main", "develop", "refs/tags/v1.9.21");
  // The workflow's default-branch checkout is shallow.
  const trusted = join(dir, "trusted");
  git(dir, "clone", "--quiet", "--depth", "1", "--branch", "develop", `file://${origin}`, trusted);

  const cli = fileURLToPath(new URL("./client-release.mjs", import.meta.url));
  const verify = (runOverrides, recordValue) => {
    writeFileSync(join(dir, "event.json"), JSON.stringify({ workflow_run: run(runOverrides) }));
    writeFileSync(join(dir, "release.json"), typeof recordValue === "string" ? recordValue : JSON.stringify(recordValue));
    writeFileSync(join(dir, "output"), "");
    const result = spawnSync(process.execPath, [cli, "--pypi", join(dir, "release.json")], {
      cwd: trusted, encoding: "utf8",
      env: { ...env, GITHUB_EVENT_NAME: "workflow_run", GITHUB_EVENT_PATH: join(dir, "event.json"), GITHUB_REPOSITORY: repository, GITHUB_OUTPUT: join(dir, "output") },
    });
    return { ok: result.status === 0, output: readFileSync(join(dir, "output"), "utf8"), stderr: result.stderr };
  };
  const stableRecord = (commitSha, version) => ({ sha: commitSha, ref: `refs/tags/v${version}`, run_id: "4242", channel: "latest", version, python: version });
  const betaRecord = (commitSha) => ({ ...record(qdashRelease(input)), sha: commitSha });

  // Accepted: the annotated QDash tag on main, and an earlier develop commit.
  let result = verify({ head_branch: "v1.9.21", head_sha: released }, stableRecord(released, "1.9.21"));
  assert.ok(result.ok, result.stderr);
  assert.equal(result.output, "version=1.9.21\nchannel=latest\n");
  result = verify({ head_sha: merged }, betaRecord(merged));
  assert.ok(result.ok, result.stderr);
  assert.equal(result.output, "version=1.9.21b1271\nchannel=beta\n");

  // The reported bypass: a branch named v1.9.22 dispatched with a forged stable record.
  git(work, "push", "--quiet", "origin", "attacker:refs/heads/v1.9.22");
  result = verify({ event: "workflow_dispatch", head_branch: "v1.9.22", head_sha: attack }, stableRecord(attack, "1.9.22"));
  assert.ok(!result.ok);
  assert.match(result.stderr, /a branch shadows tag v1\.9\.22/);
  assert.equal(result.output, "");
  // The same run after the branch is deleted again, before this workflow verifies it.
  git(work, "push", "--quiet", "origin", "--delete", "refs/heads/v1.9.22");
  result = verify({ event: "workflow_dispatch", head_branch: "v1.9.22", head_sha: attack }, stableRecord(attack, "1.9.22"));
  assert.match(result.stderr, /tag v1\.9\.22 does not point/);
  // A branch named like the real tag, at the attacker's commit or at the tag's commit.
  git(work, "push", "--quiet", "origin", "attacker:refs/heads/v1.9.21");
  result = verify({ event: "workflow_dispatch", head_branch: "v1.9.21", head_sha: attack }, stableRecord(attack, "1.9.21"));
  assert.match(result.stderr, /a branch shadows tag v1\.9\.21/);
  git(work, "push", "--quiet", "--force", "origin", `${released}:refs/heads/v1.9.21`);
  result = verify({ head_branch: "v1.9.21", head_sha: released }, stableRecord(released, "1.9.21"));
  assert.match(result.stderr, /a branch shadows tag v1\.9\.21/);
  git(work, "push", "--quiet", "origin", "--delete", "refs/heads/v1.9.21");
  // A real QDash-shaped tag that is not on main, and a develop-named run off develop.
  git(work, "tag", "v1.9.23", attack);
  git(work, "push", "--quiet", "origin", "refs/tags/v1.9.23");
  result = verify({ head_branch: "v1.9.23", head_sha: attack }, stableRecord(attack, "1.9.23"));
  assert.match(result.stderr, /tag v1\.9\.23 is not on main/);
  result = verify({ head_sha: attack }, betaRecord(attack));
  assert.match(result.stderr, /commit is not on develop/);
  // Channel spoofing and malformed records never reach git.
  result = verify({ head_sha: merged }, { ...betaRecord(merged), channel: "latest" });
  assert.match(result.stderr, /Refusing/);
  result = verify({ head_sha: merged }, "not json");
  assert.match(result.stderr, /unreadable release record/);
});
const workflow = (file) => readFileSync(new URL(`../workflows/${file}`, import.meta.url), "utf8");
const triggers = (text) => text.slice(text.indexOf("\non:\n"), text.indexOf("\npermissions:"));
test("the Python workflow publishes only from the TypeScript pipeline's release record", () => {
  const python = workflow("publish-qdash-client.yml");
  const pipeline = workflow("publish-typescript-packages.yml");
  const client = workflow("publish-qdash-typescript-client.yml");
  const pipelineName = /^name: (.+)$/m.exec(pipeline)[1];
  const on = triggers(python);
  assert.match(on, new RegExp(`\\n  workflow_run:\\n    workflows: \\[${pipelineName}\\]\\n    types: \\[completed\\]`));
  // No direct push or tag trigger, so no second version computation can publish.
  assert.doesNotMatch(on, /\n  push:/);
  assert.match(python, /name: qdash-client-release\n\s+path: \$\{\{ runner\.temp \}\}\/release\n\s+run-id: \$\{\{ github\.event\.workflow_run\.id \}\}/);
  // Default-branch scripts verify the run before the triggering commit is checked out.
  const steps = python.slice(python.indexOf("\n  build:\n"), python.indexOf("\n  publish:\n"));
  const trusted = steps.indexOf("name: Checkout release scripts");
  const verify = steps.indexOf("name: Verify release source");
  const source = steps.indexOf("name: Checkout code");
  assert.ok(trusted >= 0 && trusted < verify && verify < source);
  assert.doesNotMatch(steps.slice(trusted, source), /workflow_run\.head_sha/);
  assert.match(steps.slice(verify, source), /working-directory: trusted\n\s+run: node \.github\/scripts\/client-release\.mjs --pypi/);
  assert.match(steps.slice(source), /ref: \$\{\{ github\.event\.workflow_run\.head_sha \|\| github\.sha \}\}/);
  assert.match(steps, /channel: \$\{\{ steps\.release\.outputs\.channel \}\}/);
  assert.match(steps, /SETUPTOOLS_SCM_PRETEND_VERSION: \$\{\{ steps\.release\.outputs\.version \|\| steps\.check\.outputs\.version \}\}/);
  const publish = python.slice(python.indexOf("\n  publish:\n"), python.indexOf("\n  publish-sdk:\n"));
  const publishSdk = python.slice(python.indexOf("\n  publish-sdk:\n"));
  for (const [job, dist] of [[publish, "qdash-client-dist"], [publishSdk, "qdash-sdk-dist"]]) {
    assert.match(job, /github\.event_name == 'workflow_run' &&/);
    assert.match(job, /pypa\/gh-action-pypi-publish@/);
    // Each publisher uploads only its own package, and no repository code runs there.
    assert.deepEqual([...job.matchAll(/^\s+name: (qdash-\S+-dist)$/gm)].map((m) => m[1]), [dist]);
    assert.doesNotMatch(job, /actions\/checkout@|\n\s+run:/);
  }
  // The SDK publishes after the client, so one release record lands as a pair.
  assert.match(publishSdk, /needs: \[build, publish\]/);
  // Both packages of one run carry the record's version; the self-contained SDK must not
  // depend on qdash-client, and its tests run without the client installed.
  assert.match(steps, /uv build --package qdash-client --out-dir dist\n\s+uv build --package qdash-sdk --out-dir dist/);
  assert.match(steps, /grep -i "\^Requires-Dist: qdash-client" sdk-metadata\.txt/);
  assert.match(steps, /uv run --package qdash-sdk pytest sdks\/python\/tests/);
  // The npm client and the record come from one build output in one reusable workflow run.
  assert.match(client, /python: \$\{\{ steps\.version\.outputs\.python \}\}/);
  const upload = client.slice(client.indexOf("- name: Publish package"));
  assert.ok(upload.indexOf("npm publish") < upload.indexOf("name: qdash-client-release"));
  assert.match(upload, /PYTHON_VERSION: \$\{\{ needs\.build\.outputs\.python \}\}/);
  assert.match(upload, /CLIENT_VERSION: \$\{\{ needs\.build\.outputs\.version \}\}/);
  assert.match(upload, /\{sha: \$sha, ref: \$ref, run_id: \$run_id, channel: \$channel, version: \$version, python: \$python\}/);
  // npm Trusted Publishing still sees publish-typescript-packages.yml as the caller.
  assert.match(pipeline, /uses: \.\/\.github\/workflows\/publish-qdash-typescript-client\.yml/);
  assert.doesNotMatch(triggers(client), /\n  (push|pull_request|workflow_dispatch):/);
});
test("the TypeScript pipeline runs for Python client and SDK changes so all betas publish together", () => {
  const on = triggers(workflow("publish-typescript-packages.yml"));
  const push = on.slice(on.indexOf("  push:\n")).split(/\n  (?=\S)/)[0];
  for (const path of ["clients/python/**", "sdks/python/**", "clients/typescript/**", "docs/oas/openapi.json", "pyproject.toml", "uv.lock", ".github/workflows/publish-qdash-client.yml"]) {
    assert.ok(push.includes(`- "${path}"`), path);
  }
  assert.match(push, /- "v\[0-9\]\+\.\[0-9\]\+\.\[0-9\]\+"/);
});
