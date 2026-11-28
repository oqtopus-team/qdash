import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { registryState } from "./pi-package-release.mjs";

export const SDK = "@oqtopus-team/qdash-sdk";
export const CLIENT = "@oqtopus-team/qdash-client";
export const SDK_MANIFEST = "sdks/typescript/package.json";
// The SDK's own runtime dependencies; it carries its generated API client and never the client.
export const SDK_DEPENDENCIES = ["ini", "smol-toml"];
const exact = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*)?$/;
const stable = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const beta = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.[1-9]\d*$/;
const compare = (a, b) => {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] - right[i];
  return 0;
};

/**
 * The TypeScript SDK releases at exactly the client version of the same run, like the Python
 * qdash-sdk beside qdash-client. It is self-contained: it must not depend on the client, and
 * its dependencies are its own runtime libraries, unchanged.
 * The client job computes the version once (client-release.mjs); this never reads tags.
 */
export function sdkManifest(manifest, clientVersion) {
  if (manifest.name !== SDK) throw new Error(`Expected the ${SDK} manifest`);
  checkDependencies(manifest);
  if (typeof clientVersion !== "string" || !exact.test(clientVersion) || clientVersion === "0.0.0") {
    throw new Error(`An exact built client version is required before packing ${SDK}`);
  }
  return { ...manifest, version: clientVersion };
}

function checkDependencies(manifest) {
  const dependencies = Object.keys(manifest.dependencies ?? {}).sort();
  if (manifest.dependencies?.[CLIENT] !== undefined || manifest.peerDependencies?.[CLIENT] !== undefined) {
    throw new Error(`${SDK} must not depend on ${CLIENT}`);
  }
  if (dependencies.join() !== [...SDK_DEPENDENCIES].sort().join()) {
    throw new Error(`${SDK} must depend on ${SDK_DEPENDENCIES.join(", ")} only`);
  }
  for (const [name, range] of Object.entries(manifest.dependencies)) {
    if (/^(workspace:|file:|link:)/.test(range)) throw new Error(`${name} must resolve outside the workspace`);
  }
}

/**
 * Pick the npm dist-tag for a built SDK tarball, or null to skip publication. The
 * tarball must not depend on the client. develop publishes the run's client beta
 * version; a QDash vX.Y.Z tag publishes X.Y.Z as latest. A rerun finds the version
 * published and skips it, as the client job does.
 */
export function sdkPublishTag({ ref, manifest, published = [], latest }) {
  const { version } = manifest;
  if (manifest.name !== SDK) throw new Error(`Expected the ${SDK} tarball`);
  checkDependencies(manifest);
  if (ref === "refs/heads/develop") {
    if (!beta.test(version)) throw new Error("develop publishes only a QDash beta version");
    return published.includes(version) ? null : "beta";
  }
  if (!ref.startsWith("refs/tags/v")) return null;
  if (!stable.test(version) || ref !== `refs/tags/v${version}`) throw new Error("Tarball version does not match the QDash tag");
  if (published.includes(version)) return null;
  if (typeof latest === "string" && stable.test(latest) && compare(version, latest) < 0) {
    throw new Error(`Refusing to move latest back from ${latest} to ${version}`);
  }
  return "latest";
}

const main = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (main && process.argv[2] === "--publish-tag") {
  // Usage: --publish-tag <tarball>; prints the dist-tag or nothing to skip.
  const manifest = JSON.parse(execFileSync("tar", ["-xOzf", process.argv[3], "package/package.json"], { encoding: "utf8" }));
  const ref = process.env.GITHUB_REF ?? "";
  const state = ref === "refs/heads/develop" || ref.startsWith("refs/tags/v") ? await registryState(SDK) : {};
  console.log(sdkPublishTag({ ref, manifest, ...state }) ?? "");
} else if (main) {
  const manifest = sdkManifest(JSON.parse(readFileSync(SDK_MANIFEST, "utf8")), process.env.QDASH_CLIENT_VERSION);
  writeFileSync(SDK_MANIFEST, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`${manifest.name}@${manifest.version} (self-contained, no ${CLIENT} dependency)`);
}
