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

/**
 * One QDash version for every client language. Stable versions come from QDash's
 * vX.Y.Z tag. Other builds use the next QDash patch and the commit's first-parent
 * build number. QDash tags live on main and are not reachable from develop, so the
 * base reads every vX.Y.Z tag in the checkout and a later run of the same commit can
 * get a later base. The TypeScript pipeline therefore computes the version once per
 * run and hands it to the Python workflow through a release artifact (pypiRelease).
 */
export function qdashRelease({ tags, ref, event, build }) {
  const latest = tags.filter((tag) => /^v/.test(tag) && stable.test(tag.slice(1)))
    .map((tag) => tag.slice(1)).sort(compare).at(-1) ?? "0.0.0";
  if (ref.startsWith("refs/tags/v")) {
    const version = ref.slice("refs/tags/v".length);
    if (!stable.test(version) || version === "0.0.0" || compare(version, latest) < 0) {
      throw new Error("Invalid or superseded client release tag");
    }
    return { version, python: version, channel: "latest" };
  }
  if (!/^[1-9]\d*$/.test(String(build))) throw new Error("Missing commit build number");
  const [major, minor, patch] = latest.split(".").map(Number);
  const next = `${major}.${minor}.${patch + 1}`;
  const channel = event === "push" && ref === "refs/heads/develop" ? "beta" : "check";
  // npm SemVer and PyPI PEP 440 spell the same prerelease differently.
  return { version: `${next}-beta.${build}`, python: `${next}b${build}`, channel };
}

const pep440Beta = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)b([1-9]\d*)$/;
const qdashTag = /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const commitSha = /^[0-9a-f]{40}$/;
export const releasePipeline = ".github/workflows/publish-typescript-packages.yml";
const recordKeys = ["channel", "python", "ref", "run_id", "sha", "version"];

/**
 * Decide whether a completed TypeScript pipeline run may publish to PyPI, and return
 * the PyPI version. publish-qdash-client.yml runs this from the default branch before it
 * checks out or executes any code from the triggering commit.
 *
 * workflow_run.head_branch is a short ref name that does not say whether it names a
 * branch or a tag, and the triggering run may come from any branch or tag in the
 * repository, so neither the name nor the record is trusted on its own. A publication
 * is accepted only when the triggering commit is already trusted:
 * - stable: an exact refs/tags/vX.Y.Z on the remote resolves to the commit, the commit
 *   is on main, and no branch with the tag's name exists;
 * - beta: a push to develop whose commit is on develop.
 * The record is the artifact of that run, written by the pipeline at that commit, and
 * must name the same commit, ref, run, and version.
 *
 * `git` answers questions about the remote: tagCommit(name) returns the commit that
 * refs/tags/<name> peels to, or null; branchExists(name); isAncestor(sha, branch).
 */
export function pypiRelease({ run, repository, record, git }) {
  const fail = (reason) => { throw new Error(`Refusing PyPI release: ${reason}`); };
  if (!run || typeof repository !== "string" || !repository) fail("missing workflow_run event");
  if (run.repository?.full_name !== repository || run.head_repository?.full_name !== repository) {
    fail("run is not from this repository");
  }
  const path = String(run.path);
  if (path !== releasePipeline && !path.startsWith(`${releasePipeline}@`)) fail("run is not the release pipeline");
  const runId = String(run.id);
  if (!/^[1-9]\d*$/.test(runId)) fail("run has no ID");
  const headSha = String(run.head_sha);
  if (!commitSha.test(headSha)) fail("run has no commit");
  const headBranch = String(run.head_branch);

  if (!record || typeof record !== "object" || Array.isArray(record)
    || Object.keys(record).sort().join() !== recordKeys.join()
    || recordKeys.some((key) => typeof record[key] !== "string")) {
    fail("malformed release record");
  }
  const { sha, ref, run_id: recordRun, channel, version, python } = record;
  if (sha !== headSha || recordRun !== runId) fail("record belongs to another commit or run");

  if (channel === "latest") {
    if (run.event !== "push" && run.event !== "workflow_dispatch") fail("stable release from an unexpected event");
    if (!qdashTag.test(headBranch) || ref !== `refs/tags/${headBranch}`) fail("stable release is not from a QDash tag");
    if (version !== headBranch.slice(1) || python !== version) fail("stable record does not match its tag");
    if (git.branchExists(headBranch)) fail(`a branch shadows tag ${headBranch}`);
    if (git.tagCommit(headBranch) !== headSha) fail(`tag ${headBranch} does not point to the run's commit`);
    if (!git.isAncestor(headSha, "main")) fail(`tag ${headBranch} is not on main`);
  } else if (channel === "beta") {
    if (run.event !== "push" || headBranch !== "develop" || ref !== "refs/heads/develop") {
      fail("beta release is not a push to develop");
    }
    const match = pep440Beta.exec(python);
    if (!match || version !== `${match[1]}.${match[2]}.${match[3]}-beta.${match[4]}`) {
      fail("beta record versions do not match");
    }
    if (!git.isAncestor(headSha, "develop")) fail("commit is not on develop");
  } else {
    fail("record has no PyPI channel");
  }
  return { version: python, channel };
}

/** Answer pypiRelease's questions with the remote `origin` of the repository at `cwd`. */
export function remoteGit(cwd = process.cwd()) {
  const run = (...args) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  const lines = (...refs) => run("ls-remote", "origin", ...refs).split("\n").filter(Boolean)
    .map((line) => line.split("\t"));
  return {
    tagCommit(name) {
      const refs = new Map(lines(`refs/tags/${name}`, `refs/tags/${name}^{}`).map(([sha, ref]) => [ref, sha]));
      return refs.get(`refs/tags/${name}^{}`) ?? refs.get(`refs/tags/${name}`) ?? null;
    },
    // ls-remote matches patterns against ref tails, so compare full names.
    branchExists: (name) => lines(`refs/heads/${name}`).some(([, ref]) => ref === `refs/heads/${name}`),
    isAncestor(sha, branch) {
      const local = `refs/qdash-release/${branch}`;
      // A shallow checkout cannot walk history, so fetch the branch's full history.
      const unshallow = run("rev-parse", "--is-shallow-repository") === "true" ? ["--unshallow"] : [];
      run("fetch", "--quiet", "--no-tags", ...unshallow, "origin", `+refs/heads/${branch}:${local}`);
      try {
        run("merge-base", "--is-ancestor", sha, local);
        return true;
      } catch {
        // Not an ancestor, or the commit is unknown because it is on no fetched branch.
        return false;
      }
    },
  };
}

/**
 * The npm libraries that release with QDash's version: the client and the self-contained SDK.
 * Every one of them carries the run's exact client version.
 */
export const QDASH_LIBRARIES = ["@oqtopus-team/qdash-client", "@oqtopus-team/qdash-sdk"];

/**
 * npm cannot resolve workspace:* or the source placeholder 0.0.0, so pin each QDash
 * library a manifest depends on to the exact version this run built. The SDK takes the
 * client's version, so one version pins both.
 */
export function pinClientDependency(manifest, version) {
  const names = QDASH_LIBRARIES.filter((name) => manifest.dependencies?.[name]);
  if (names.length === 0) return manifest;
  if (typeof version !== "string" || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*)?$/.test(version) || version === "0.0.0") {
    throw new Error(`An exact built client version is required before packing ${manifest.name ?? "a package"}`);
  }
  const dependencies = { ...manifest.dependencies };
  for (const name of names) dependencies[name] = version;
  return { ...manifest, dependencies };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const git = (...args) => execFileSync("git", args, { encoding: "utf8" }).trim();
  const input = () => ({
    tags: git("tag", "--list", "v*").split("\n"),
    ref: process.env.GITHUB_REF ?? "", event: process.env.GITHUB_EVENT_NAME,
    build: git("rev-list", "--count", "--first-parent", "HEAD"),
  });
  let output;
  if (process.argv[2] === "--pypi") {
    // Usage: --pypi <release.json>, from a default-branch checkout in the workflow_run
    // triggered by the TypeScript pipeline, before the triggering commit is checked out.
    const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"));
    if (process.env.GITHUB_EVENT_NAME !== "workflow_run") throw new Error("--pypi requires a workflow_run event");
    let record;
    try {
      record = JSON.parse(readFileSync(process.argv[3], "utf8"));
    } catch {
      throw new Error("Refusing PyPI release: unreadable release record");
    }
    output = pypiRelease({ run: event.workflow_run, repository: process.env.GITHUB_REPOSITORY, record, git: remoteGit() });
    console.log(`qdash-client==${output.version} (${output.channel})`);
  } else if (process.argv[2] === "--python") {
    // Validation builds only: publication always takes the version from the release record.
    const result = qdashRelease(input());
    output = { version: result.python, channel: "check" };
    console.log(`qdash-client==${result.python} (check)`);
  } else {
    output = qdashRelease(input());
    const path = "clients/typescript/package.json";
    const manifest = JSON.parse(readFileSync(path, "utf8"));
    manifest.version = output.version;
    writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
    console.log(`${manifest.name}@${output.version} (${output.channel})`);
  }
  if (process.env.GITHUB_OUTPUT) {
    const python = output.python ? `python=${output.python}\n` : "";
    appendFileSync(process.env.GITHUB_OUTPUT, `version=${output.version}\nchannel=${output.channel}\n${python}`);
  }
}
