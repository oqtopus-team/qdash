import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const stable = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const compare = (a, b) => {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] - right[i];
  return 0;
};

/** A client snapshot belongs to this workflow run, never to whichever beta is newest. */
export function clientRelease({ tags, ref, event, runId, attempt }) {
  const latest = tags.filter((tag) => /^v/.test(tag) && stable.test(tag.slice(1)))
    .map((tag) => tag.slice(1)).sort(compare).at(-1) ?? "0.0.0";
  if (ref.startsWith("refs/tags/v")) {
    const version = ref.slice("refs/tags/v".length);
    if (!stable.test(version) || version === "0.0.0" || compare(version, latest) < 0) {
      throw new Error("Invalid or superseded client release tag");
    }
    return { version, channel: "latest" };
  }
  if (!/^[1-9]\d*$/.test(runId) || !/^[1-9]\d*$/.test(attempt)) {
    throw new Error("Missing CI run identity");
  }
  const [major, minor, patch] = latest.split(".").map(Number);
  const prefix = "refs/tags/pi-qdash/v";
  const forPi = ref.startsWith(prefix);
  if (forPi && !stable.test(ref.slice(prefix.length))) {
    throw new Error("Invalid pi-qdash release tag");
  }
  const channel = forPi ? "pi" : event === "push" && ref === "refs/heads/develop" ? "beta" : "check";
  const suffix = forPi ? "pi" : "beta";
  return { version: `${major}.${minor}.${patch + 1}-${suffix}.${runId}.${attempt}`, channel };
}

/** npm cannot resolve workspace:* or the client's source placeholder 0.0.0. */
export function pinClientDependency(manifest, version) {
  if (!manifest.dependencies?.["@oqtopus-team/qdash-client"]) return manifest;
  if (typeof version !== "string" || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*)?$/.test(version) || version === "0.0.0") {
    throw new Error("An exact built client version is required before packing pi-qdash");
  }
  return { ...manifest, dependencies: { ...manifest.dependencies, "@oqtopus-team/qdash-client": version } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = clientRelease({
    tags: execFileSync("git", ["tag", "--list", "v*"], { encoding: "utf8" }).trim().split("\n"),
    ref: process.env.GITHUB_REF ?? "", event: process.env.GITHUB_EVENT_NAME,
    runId: process.env.GITHUB_RUN_ID, attempt: process.env.GITHUB_RUN_ATTEMPT,
  });
  const path = "clients/typescript/package.json";
  const manifest = JSON.parse(readFileSync(path, "utf8"));
  manifest.version = result.version;
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT, `version=${result.version}\nchannel=${result.channel}\n`);
  }
  console.log(`${manifest.name}@${result.version} (${result.channel})`);
}
