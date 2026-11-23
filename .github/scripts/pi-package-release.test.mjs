import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { pinClientDependency, qdashRelease } from "./client-release.mjs";
import { PACKAGES, publishTag, releaseVersion } from "./pi-package-release.mjs";

const tags = ["v1.10.1", "v1.10.2"];
const run = { event: "push", runId: "12345678", attempt: "1" };
// The client job of the same run computes this; the packages never read tags themselves.
const client = (ref, event = "push") => qdashRelease({ tags, ref, event, build: "1278" }).version;

test("a QDash tag releases both pi packages and the client at the same X.Y.Z", () => {
  const ref = "refs/tags/v1.10.3";
  const clientVersion = client(ref);
  assert.equal(clientVersion, "1.10.3");
  for (const name of PACKAGES) {
    assert.deepEqual(releaseVersion({ name, clientVersion, ref, ...run }), { version: "1.10.3", channel: "latest" });
  }
  // A manual retry on the tag releases the same version.
  assert.deepEqual(
    releaseVersion({ name: "pi-qdash", clientVersion, ref, ...run, event: "workflow_dispatch", attempt: "2" }),
    { version: "1.10.3", channel: "latest" },
  );
});

test("a QDash tag packs pi-qdash with the stable client it releases", () => {
  const ref = "refs/tags/v1.10.3";
  const clientVersion = client(ref);
  const manifest = { name: "@oqtopus-team/pi-qdash", version: "0.1.10", dependencies: { "@oqtopus-team/qdash-client": "workspace:*" } };
  const packed = { ...pinClientDependency(manifest, clientVersion), version: releaseVersion({ name: "pi-qdash", clientVersion, ref, ...run }).version };
  assert.equal(packed.version, "1.10.3");
  assert.equal(packed.dependencies["@oqtopus-team/qdash-client"], "1.10.3");
});

test("a QDash tag refuses a client version from another computation", () => {
  for (const clientVersion of ["1.10.4", "1.10.3-beta.1278", undefined, "0.0.0", "1.10.3\ninjected"]) {
    assert.throws(() => releaseVersion({ name: "pi-qdash", clientVersion, ref: "refs/tags/v1.10.3", ...run }));
  }
  assert.throws(() => releaseVersion({ name: "pi-other", clientVersion: "1.10.3", ref: "refs/tags/v1.10.3", ...run }));
});

test("develop betas keep the run identity on the next QDash patch", () => {
  const clientVersion = client("refs/heads/develop");
  assert.equal(clientVersion, "1.10.3-beta.1278");
  for (const name of PACKAGES) {
    assert.deepEqual(releaseVersion({ name, clientVersion, ref: "refs/heads/develop", ...run }), { version: "1.10.3-beta.12345678.1", channel: "beta" });
  }
  // A retry attempt republishes under a new version after one package already succeeded.
  assert.equal(releaseVersion({ name: "pi-qcaleval", clientVersion, ref: "refs/heads/develop", ...run, attempt: "2" }).version, "1.10.3-beta.12345678.2");
  assert.throws(() => releaseVersion({ name: "pi-qdash", clientVersion, ref: "refs/heads/develop", ...run, runId: undefined }));
  assert.throws(() => releaseVersion({ name: "pi-qdash", clientVersion: "1.10.3", ref: "refs/heads/develop", ...run }));
});

test("PRs, dispatches on branches, and old package tags only validate", () => {
  for (const [event, ref] of [["pull_request", "refs/pull/1/merge"], ["workflow_dispatch", "refs/heads/develop"], ["push", "refs/tags/pi-qdash/v0.1.12"]]) {
    const clientVersion = client(ref, event);
    assert.deepEqual(releaseVersion({ name: "pi-qdash", clientVersion, ref, ...run, event }), { version: clientVersion, channel: "check" });
  }
});

test("a QDash tag publishes X.Y.Z as latest once; a rerun skips it", () => {
  const release = { name: "pi-qdash", ref: "refs/tags/v1.10.3", version: "1.10.3" };
  // First QDash-numbered release after the independent 0.1.x line.
  assert.equal(publishTag({ ...release, published: ["0.1.10", "0.1.11-beta.44429038434.1"], latest: "0.1.10" }), "latest");
  assert.equal(publishTag({ ...release, published: [], latest: undefined }), "latest");
  // Rerun: npm already has 1.10.3, so the package is skipped instead of failing.
  assert.equal(publishTag({ ...release, published: ["0.1.10", "1.10.3"], latest: "1.10.3" }), null);
  // A superseded tag never moves latest backwards.
  assert.throws(() => publishTag({ ...release, published: ["1.10.4"], latest: "1.10.4" }));
  // The tarball must carry the tag's version.
  for (const version of ["0.1.11", "1.10.3-beta.1.1", "1.10.4"]) {
    assert.throws(() => publishTag({ ...release, version, published: [] }));
  }
});

test("develop publishes beta; PRs, other refs, and old package tags never publish", () => {
  assert.equal(publishTag({ name: "pi-qcaleval", ref: "refs/heads/develop", version: "1.10.3-beta.1.1" }), "beta");
  for (const ref of ["refs/tags/pi-qdash/v0.1.11", "refs/tags/pi-qcaleval/v0.1.11", "refs/pull/1/merge", "refs/heads/main"]) {
    assert.equal(publishTag({ name: "pi-qdash", ref, version: "0.1.11" }), null);
  }
});

test("retrying a beta publish skips the exact version in the existing tarball", () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "pi-beta-retry-")));
  mkdirSync(join(root, "package"));
  const version = "1.10.3-beta.12345678.1";
  writeFileSync(join(root, "package/package.json"), JSON.stringify({ name: "@oqtopus-team/pi-qdash", version }));
  const tarball = join(root, "package.tgz");
  execFileSync("tar", ["-czf", tarball, "-C", root, "package"]);
  const mock = join(root, "registry.mjs");
  for (const published of [false, true]) {
    writeFileSync(mock, `globalThis.fetch = async (url) => {
      if (url !== "https://registry.npmjs.org/@oqtopus-team%2fpi-qdash") throw new Error("Unexpected registry URL");
      return { ok: true, status: 200, json: async () => ({ versions: ${JSON.stringify(published ? { [version]: {} } : {})} }) };
    };`);
    const result = execFileSync("node", ["--import", mock, new URL("./pi-package-release.mjs", import.meta.url).pathname, "--publish-tag", "pi-qdash", tarball], {
      encoding: "utf8",
      env: { ...process.env, GITHUB_REF: "refs/heads/develop", GITHUB_RUN_ATTEMPT: "2" },
    });
    assert.equal(result.trim(), published ? "" : "beta");
  }
});

test("the CLI packs the manifest at the QDash tag version with the pinned client and SDK", () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "pi-release-")));
  for (const dir of ["packages/pi-qdash", ".github/scripts"]) mkdirSync(join(root, dir), { recursive: true });
  for (const file of ["pi-package-release.mjs", "client-release.mjs"]) {
    writeFileSync(join(root, ".github/scripts", file), readFileSync(new URL(`./${file}`, import.meta.url)));
  }
  const path = join(root, "packages/pi-qdash/package.json");
  writeFileSync(path, JSON.stringify({ name: "@oqtopus-team/pi-qdash", version: "0.1.10", dependencies: { "@oqtopus-team/qdash-client": "workspace:*", "@oqtopus-team/qdash-sdk": "workspace:*" } }));
  execFileSync("node", [join(root, ".github/scripts/pi-package-release.mjs"), "pi-qdash"], {
    cwd: root,
    env: { ...process.env, GITHUB_REF: "refs/tags/v1.10.3", GITHUB_EVENT_NAME: "push", QDASH_CLIENT_VERSION: "1.10.3", GITHUB_RUN_ID: "1", GITHUB_RUN_ATTEMPT: "1" },
  });
  const packed = JSON.parse(readFileSync(path, "utf8"));
  assert.equal(packed.version, "1.10.3");
  assert.equal(packed.dependencies["@oqtopus-team/qdash-client"], "1.10.3");
  assert.equal(packed.dependencies["@oqtopus-team/qdash-sdk"], "1.10.3");
});

test("the pipeline has no independent pi stable tags", () => {
  const pipeline = readFileSync(new URL("../workflows/publish-typescript-packages.yml", import.meta.url), "utf8");
  assert.doesNotMatch(pipeline, /pi-qdash\/v|pi-qcaleval\/v/);
  assert.match(pipeline, /QDASH_CLIENT_VERSION: \$\{\{ needs\.client\.outputs\.version \}\}/);
});
