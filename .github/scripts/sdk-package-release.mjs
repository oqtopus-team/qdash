import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { pinClientDependency } from "./client-release.mjs";
import { registryState } from "./pi-package-release.mjs";

export const SDK = "@oqtopus-team/qdash-sdk";
export const CLIENT = "@oqtopus-team/qdash-client";
export const SDK_MANIFEST = "sdks/typescript/package.json";
const stable = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const beta = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.[1-9]\d*$/;
const compare = (a, b) => {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] - right[i];
  return 0;
};

/**
 * The TypeScript SDK releases at exactly the client version of the same run, and depends on
 * that client only, pinned to it.
 * The client job computes the version once (client-release.mjs); this never reads tags.
 */
export function sdkManifest(manifest, clientVersion) {
  if (manifest.name !== SDK) throw new Error(`Expected the ${SDK} manifest`);
  const dependencies = Object.keys(manifest.dependencies ?? {});
  if (dependencies.join() !== CLIENT) throw new Error(`${SDK} must depend on ${CLIENT} and nothing else`);
  return { ...pinClientDependency(manifest, clientVersion), version: clientVersion };
}

/**
 * Pick the npm dist-tag for a built SDK tarball, or null to skip publication. The
 * tarball must pin the client at its own version. develop publishes the run's client
 * beta version; a QDash vX.Y.Z tag publishes X.Y.Z as latest. A rerun finds the
 * version published and skips it, as the client job does.
 */
export function sdkPublishTag({ ref, manifest, published = [], latest }) {
  const { version } = manifest;
  if (manifest.name !== SDK) throw new Error(`Expected the ${SDK} tarball`);
  if (manifest.dependencies?.[CLIENT] !== version) throw new Error(`The tarball must pin ${CLIENT}@${version}`);
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
  console.log(`${manifest.name}@${manifest.version} (${CLIENT}@${manifest.dependencies[CLIENT]})`);
}
