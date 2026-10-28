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

/** Match the client release flow while keeping each pi package's own version line. */
export function releaseVersion({ name, base, tags, event, ref, runId, attempt }) {
  if (!PACKAGES.includes(name) || !stable.test(base)) throw new Error("Invalid package or base version");
  const prefix = `${name}/v`;
  const versions = tags.filter((tag) => tag.startsWith(prefix))
    .map((tag) => tag.slice(prefix.length)).filter((version) => stable.test(version));
  const latest = [base, ...versions].sort(compare).at(-1);
  if (ref.startsWith(`refs/tags/${prefix}`)) {
    const version = ref.slice(`refs/tags/${prefix}`.length);
    if (!stable.test(version) || compare(version, latest) < 0) throw new Error("Invalid or superseded release tag");
    return { version, channel: "latest" };
  }
  if (event === "push" && ref === "refs/heads/develop") {
    if (!/^[1-9]\d*$/.test(runId) || !/^[1-9]\d*$/.test(attempt)) throw new Error("Missing CI run identity");
    const [major, minor, patch] = latest.split(".").map(Number);
    // GitHub run IDs do not restart when moving to a new repository. The attempt
    // makes a retry publishable even after one matrix member already succeeded.
    return { version: `${major}.${minor}.${patch + 1}-beta.${runId}.${attempt}`, channel: "beta" };
  }
  return { version: base, channel: "check" };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const name = process.argv[2];
  if (!PACKAGES.includes(name)) throw new Error("Unknown package");
  const path = `packages/${name}/package.json`;
  const manifest = pinClientDependency(
    JSON.parse(readFileSync(path, "utf8")), process.env.QDASH_CLIENT_VERSION,
  );
  const result = releaseVersion({
    name, base: manifest.version,
    tags: execFileSync("git", ["tag", "--list", `${name}/v*`], { encoding: "utf8" }).trim().split("\n"),
    event: process.env.GITHUB_EVENT_NAME, ref: process.env.GITHUB_REF ?? "",
    runId: process.env.GITHUB_RUN_ID, attempt: process.env.GITHUB_RUN_ATTEMPT,
  });
  manifest.version = result.version;
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`${manifest.name}@${result.version} (${result.channel})`);
}
