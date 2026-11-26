import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { pinClientDependency, qdashRelease } from "./client-release.mjs";
import { releaseVersion } from "./pi-package-release.mjs";
import { CLIENT, SDK, SDK_DEPENDENCIES, sdkManifest, sdkPublishTag } from "./sdk-package-release.mjs";

const tags = ["v1.10.1", "v1.10.2"];
// The client job of the same run computes this; the SDK never reads tags itself.
const client = (ref, event = "push") => qdashRelease({ tags, ref, event, build: "1278" }).version;
const source = () => JSON.parse(readFileSync(new URL("../../sdks/typescript/package.json", import.meta.url), "utf8"));
const workflow = readFileSync(new URL("../workflows/publish-typescript-packages.yml", import.meta.url), "utf8");
const job = (name) => workflow.slice(workflow.indexOf(`\n  ${name}:\n`)).split(/\n  (?=[a-z-]+:\n)/)[1];

test("the source SDK is self-contained: its own runtime libraries, no client, the placeholder version", () => {
  const manifest = source();
  assert.equal(manifest.name, SDK);
  assert.equal(manifest.version, "0.0.0");
  assert.deepEqual(Object.keys(manifest.dependencies).sort(), [...SDK_DEPENDENCIES].sort());
  assert.equal(manifest.dependencies[CLIENT], undefined);
  // The package root, and the calibration builders on their own: no HTTP, config, or Node code.
  assert.deepEqual(Object.keys(manifest.exports), [".", "./calibration"]);
  const clientManifest = JSON.parse(readFileSync(new URL("../../clients/typescript/package.json", import.meta.url), "utf8"));
  assert.equal(clientManifest.dependencies[SDK], undefined, "the client must not depend on the SDK");
  assert.equal(clientManifest.exports["./sdk"], undefined);
});

test("a QDash tag packs the SDK as X.Y.Z, its dependencies unchanged", () => {
  const version = client("refs/tags/v1.10.3");
  const packed = sdkManifest(source(), version);
  assert.equal(packed.version, "1.10.3");
  assert.deepEqual(packed.dependencies, source().dependencies);
});

test("develop packs the SDK at the client's beta version", () => {
  const version = client("refs/heads/develop");
  assert.equal(version, "1.10.3-beta.1278");
  const packed = sdkManifest(source(), version);
  assert.equal(packed.version, version);
  assert.equal(packed.dependencies[CLIENT], undefined);
});

test("packing refuses a missing version, a client dependency and unexpected dependencies", () => {
  for (const bad of [undefined, "0.0.0", "workspace:*", "^1.10.3", "1.10.3\ninjected"]) {
    assert.throws(() => sdkManifest(source(), bad));
  }
  const dependencies = source().dependencies;
  assert.throws(() => sdkManifest({ ...source(), name: "@oqtopus-team/pi-qdash" }, "1.10.3"));
  assert.throws(() => sdkManifest({ ...source(), dependencies: { ...dependencies, [CLIENT]: "workspace:*" } }, "1.10.3"), /must not depend/);
  assert.throws(() => sdkManifest({ ...source(), peerDependencies: { [CLIENT]: "*" } }, "1.10.3"), /must not depend/);
  assert.throws(() => sdkManifest({ ...source(), dependencies: { ...dependencies, axios: "^1" } }, "1.10.3"));
  assert.throws(() => sdkManifest({ ...source(), dependencies: {} }, "1.10.3"));
  assert.throws(() => sdkManifest({ ...source(), dependencies: { ...dependencies, ini: "workspace:*" } }, "1.10.3"));
});

test("pi-qdash pins the SDK of the same run and adds no client", () => {
  const clientVersion = client("refs/heads/develop");
  const manifest = { name: "@oqtopus-team/pi-qdash", dependencies: { [SDK]: "workspace:*" } };
  const pinned = pinClientDependency(manifest, clientVersion);
  assert.deepEqual(pinned.dependencies, { [SDK]: clientVersion });
  // A package that still depends on both, such as an older pi-qdash, gets both pinned.
  assert.deepEqual(pinClientDependency({ dependencies: { [CLIENT]: "workspace:*", [SDK]: "workspace:*" } }, clientVersion).dependencies, { [CLIENT]: clientVersion, [SDK]: clientVersion });
  // pi-qdash's own version keeps the run identity; its dependencies keep the shared version.
  assert.equal(releaseVersion({ name: "pi-qdash", clientVersion, ref: "refs/heads/develop", event: "push", runId: "9", attempt: "1" }).version, "1.10.3-beta.9.1");
});

test("publication: develop betas, tag releases, reruns skip, and nothing else publishes", () => {
  const beta = sdkManifest(source(), "1.10.3-beta.1278");
  const stable = sdkManifest(source(), "1.10.3");
  assert.equal(sdkPublishTag({ ref: "refs/heads/develop", manifest: beta }), "beta");
  assert.equal(sdkPublishTag({ ref: "refs/heads/develop", manifest: beta, published: [beta.version] }), null);
  assert.throws(() => sdkPublishTag({ ref: "refs/heads/develop", manifest: stable }));
  assert.equal(sdkPublishTag({ ref: "refs/tags/v1.10.3", manifest: stable, published: [], latest: undefined }), "latest");
  assert.equal(sdkPublishTag({ ref: "refs/tags/v1.10.3", manifest: stable, published: ["1.10.3"], latest: "1.10.3" }), null);
  assert.throws(() => sdkPublishTag({ ref: "refs/tags/v1.10.3", manifest: stable, published: ["1.10.4"], latest: "1.10.4" }));
  assert.throws(() => sdkPublishTag({ ref: "refs/tags/v1.10.4", manifest: stable }));
  assert.throws(() => sdkPublishTag({ ref: "refs/tags/v1.10.3", manifest: beta }));
  for (const ref of ["refs/pull/1/merge", "refs/heads/main", "refs/heads/feature"]) {
    assert.equal(sdkPublishTag({ ref, manifest: beta }), null);
  }
  // A tarball that depends on the client never publishes.
  assert.throws(() => sdkPublishTag({ ref: "refs/heads/develop", manifest: { ...beta, dependencies: { ...beta.dependencies, [CLIENT]: beta.version } } }));
});

test("the CLI writes the packed manifest from QDASH_CLIENT_VERSION", () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "sdk-release-")));
  for (const dir of ["sdks/typescript", ".github/scripts"]) mkdirSync(join(root, dir), { recursive: true });
  for (const file of ["sdk-package-release.mjs", "pi-package-release.mjs", "client-release.mjs"]) {
    writeFileSync(join(root, ".github/scripts", file), readFileSync(new URL(`./${file}`, import.meta.url)));
  }
  const path = join(root, "sdks/typescript/package.json");
  writeFileSync(path, JSON.stringify(source()));
  execFileSync("node", [join(root, ".github/scripts/sdk-package-release.mjs")], {
    cwd: root, env: { ...process.env, QDASH_CLIENT_VERSION: "1.10.3-beta.1278" },
  });
  const packed = JSON.parse(readFileSync(path, "utf8"));
  assert.equal(packed.version, "1.10.3-beta.1278");
  assert.deepEqual(packed.dependencies, source().dependencies);
});

test("the pipeline releases client, then SDK, then pi packages, from one client version", () => {
  const sdk = job("sdk");
  const publishSdk = job("publish-sdk");
  const build = job("build");
  const publish = job("publish");
  assert.match(sdk, /needs: client\n/);
  assert.match(sdk, /QDASH_CLIENT_VERSION: \$\{\{ needs\.client\.outputs\.version \}\}/);
  // The SDK builds, checks and installs without the client.
  assert.doesNotMatch(sdk, /build:client|qdash-typescript-client-dist/);
  assert.match(sdk, /node sdks\/typescript\/scripts\/generate\.mjs --check/);
  assert.match(sdk, /node \.github\/scripts\/sdk-package-smoke\.mjs/);
  assert.match(publishSdk, /needs: \[client, sdk\]/);
  assert.match(publishSdk, /id-token: write/);
  assert.match(publishSdk, /--publish-tag/);
  assert.match(build, /needs: \[client, sdk\]/);
  // The pi packages build, test and install with the SDK only; the client is neither built nor installed.
  assert.match(build, /run: bun run build:sdk\n/);
  assert.doesNotMatch(build, /build:client|qdash-typescript-client-dist|client-dist/);
  assert.match(build, /name: qdash-typescript-sdk-dist/);
  assert.match(publish, /needs: \[client, publish-sdk, build\]/);
  for (const path of ["sdks/typescript/**", ".github/scripts/sdk-package-*"]) {
    assert.equal(workflow.split(`- "${path}"`).length - 1, 2, `${path} must trigger PR and push runs`);
  }
});
