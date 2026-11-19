import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { pinClientDependency } from "./client-release.mjs";

export const PACKAGES = ["pi-qdash", "pi-qcaleval"];
const stable = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const compare = (a, b) => {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] - right[i];
  return 0;
};

/**
 * pi packages follow QDash's version line, like both clients. The client job of the
 * same run computes the QDash version once (client-release.mjs) and passes it here, so
 * the packages never read tags themselves. A QDash vX.Y.Z run releases X.Y.Z. develop
 * keeps the run-identity beta suffix on the next QDash patch: the attempt makes a retry
 * publishable after one matrix member already succeeded.
 */
export function releaseVersion({ name, clientVersion, event, ref, runId, attempt }) {
  if (!PACKAGES.includes(name)) throw new Error("Unknown package");
  const match = /^((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))(-beta\.[1-9]\d*)?$/.exec(String(clientVersion));
  if (!match || match[1] === "0.0.0") throw new Error("A QDash client version from this run is required");
  if (ref.startsWith("refs/tags/v")) {
    if (match[5] || ref !== `refs/tags/v${clientVersion}`) throw new Error("Client version does not match the QDash tag");
    return { version: clientVersion, channel: "latest" };
  }
  if (event === "push" && ref === "refs/heads/develop") {
    if (!match[5]) throw new Error("develop requires a QDash beta client version");
    if (!/^[1-9]\d*$/.test(runId) || !/^[1-9]\d*$/.test(attempt)) throw new Error("Missing CI run identity");
    return { version: `${match[1]}-beta.${runId}.${attempt}`, channel: "beta" };
  }
  return { version: clientVersion, channel: "check" };
}

/**
 * Pick the npm dist-tag for a built tarball, or null to skip publication. A QDash
 * vX.Y.Z run publishes X.Y.Z as latest; a rerun finds it published and skips it.
 */
export function publishTag({ name, ref, version, published = [], latest }) {
  if (!PACKAGES.includes(name)) throw new Error("Unknown package");
  if (ref === "refs/heads/develop") return published.includes(version) ? null : "beta";
  if (!ref.startsWith("refs/tags/v")) return null;
  if (!stable.test(version) || ref !== `refs/tags/v${version}`) throw new Error("Tarball version does not match the QDash tag");
  if (published.includes(version)) return null;
  if (typeof latest === "string" && stable.test(latest) && compare(version, latest) < 0) {
    throw new Error(`Refusing to move latest back from ${latest} to ${version}`);
  }
  return "latest";
}

async function registryState(spec) {
  const response = await fetch(`https://registry.npmjs.org/${spec.replace("/", "%2f")}`);
  if (response.status === 404) return { published: [], latest: undefined };
  if (!response.ok) throw new Error(`npm registry returned ${response.status}`);
  const body = await response.json();
  return { published: Object.keys(body.versions ?? {}), latest: body["dist-tags"]?.latest };
}

const main = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (main && process.argv[2] === "--publish-tag") {
  // Usage: --publish-tag <package> <tarball>; prints the dist-tag or nothing to skip.
  const name = process.argv[3];
  const manifest = JSON.parse(execFileSync("tar", ["-xOzf", process.argv[4], "package/package.json"], { encoding: "utf8" }));
  const ref = process.env.GITHUB_REF ?? "";
  const state = ref === "refs/heads/develop" || ref.startsWith("refs/tags/v")
    ? await registryState(manifest.name) : {};
  console.log(publishTag({ name, ref, version: manifest.version, ...state }) ?? "");
} else if (main) {
  const name = process.argv[2];
  if (!PACKAGES.includes(name)) throw new Error("Unknown package");
  const path = `packages/${name}/package.json`;
  const clientVersion = process.env.QDASH_CLIENT_VERSION;
  const manifest = pinClientDependency(JSON.parse(readFileSync(path, "utf8")), clientVersion);
  const result = releaseVersion({
    name, clientVersion,
    event: process.env.GITHUB_EVENT_NAME, ref: process.env.GITHUB_REF ?? "",
    runId: process.env.GITHUB_RUN_ID, attempt: process.env.GITHUB_RUN_ATTEMPT,
  });
  manifest.version = result.version;
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`${manifest.name}@${result.version} (${result.channel})`);
}
