// Selects the Markdown files that the documentation workflow passes to lychee.
//
// Usage: node .github/scripts/docs-link-inputs.mjs <output-file>
//
// Environment: GITHUB_EVENT_NAME, BASE_SHA and HEAD_SHA (pull requests), and GITHUB_OUTPUT.
//
// A pull request that changes documentation pages checks only those pages, so the selection
// can legitimately contain no links. Every other run, and a pull request that changes only the
// workflow or lychee configuration, checks the complete page set, where finding no links means
// the inputs are misconfigured. The script writes `scope=changed` or `scope=full` to
// GITHUB_OUTPUT so the workflow can require links only for the complete set.
import { spawnSync } from "node:child_process";
import { appendFileSync, existsSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const DOCS_DIR = "docs";

export function isDocsMarkdown(path) {
  return path.startsWith(`${DOCS_DIR}/`) && path.endsWith(".md");
}

// NUL-separated output keeps non-ASCII paths unquoted (core.quotePath).
function splitNul(output) {
  return output.split("\0").filter((path) => path !== "");
}

export function selectLinkInputs({ eventName, changedFiles, trackedFiles, exists }) {
  let scope = "full";
  let files = [];
  if (eventName === "pull_request") {
    files = changedFiles().filter(isDocsMarkdown);
    if (files.length > 0) {
      scope = "changed";
    }
  }
  if (scope === "full") {
    files = trackedFiles().filter(isDocsMarkdown);
    if (files.length === 0) {
      throw new Error(`No tracked Markdown files were found under ${DOCS_DIR}/.`);
    }
  }
  const missing = files.filter((path) => !exists(path));
  if (missing.length > 0) {
    throw new Error(`Selected link-check inputs do not exist: ${missing.join(", ")}`);
  }
  return { scope, files };
}

function git(args, spawn) {
  const result = spawn("git", args, { encoding: "utf8" });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${result.stderr.trim()}`);
  }
  return splitNul(result.stdout);
}

export function main(
  argv,
  {
    env = process.env,
    spawn = spawnSync,
    exists = existsSync,
    writeFile = writeFileSync,
    appendFile = appendFileSync,
    log = console.log,
    error = console.error,
  } = {},
) {
  const [outputFile] = argv;
  if (!outputFile) {
    error("Usage: node .github/scripts/docs-link-inputs.mjs <output-file>");
    return 2;
  }
  const eventName = env.GITHUB_EVENT_NAME ?? "";
  try {
    const { scope, files } = selectLinkInputs({
      eventName,
      changedFiles: () => {
        if (!env.BASE_SHA || !env.HEAD_SHA) {
          throw new Error("BASE_SHA and HEAD_SHA are required for pull_request runs.");
        }
        const range = [env.BASE_SHA, env.HEAD_SHA];
        return git(
          ["diff", "--name-only", "-z", "--diff-filter=ACMR", ...range, "--", DOCS_DIR],
          spawn,
        );
      },
      trackedFiles: () => git(["ls-files", "-z", "--", DOCS_DIR], spawn),
      exists,
    });
    writeFile(outputFile, `${files.join("\n")}\n`);
    if (env.GITHUB_OUTPUT) {
      appendFile(env.GITHUB_OUTPUT, `scope=${scope}\n`);
    }
    log(`Selected ${files.length} Markdown file(s) for the ${scope} link check.`);
    return 0;
  } catch (cause) {
    error(cause instanceof Error ? cause.message : String(cause));
    return 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  process.exitCode = main(process.argv.slice(2));
}
