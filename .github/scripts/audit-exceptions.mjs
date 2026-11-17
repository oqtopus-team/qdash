// Runs `bun audit` with time-limited advisory exceptions.
//
// Usage: node .github/scripts/audit-exceptions.mjs -- <audit command...>
//
// Each exception becomes Bun's native `--ignore=<GHSA>` flag, which ignores one exact
// advisory and still fails on every other advisory and on registry errors. The wrapper
// refuses to run the audit once any exception has expired, so an exception is never
// renewed silently.
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const DAY_MS = 24 * 60 * 60 * 1000;
const MAX_EXCEPTION_DAYS = 14;
const GHSA_ID = /^GHSA(-[23456789cfghjmpqrvwx]{4}){3}$/;

export const AUDIT_EXCEPTIONS = [
  {
    id: "GHSA-fc5q-39xc-vjpf",
    package: "picomatch",
    url: "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
    approved: "2026-11-18T00:00:00Z",
    expires: "2026-12-02T00:00:00Z",
    owner: "QDash repository maintainers",
    reason:
      "No patched picomatch release exists. The UI reaches picomatch only through dev tooling " +
      "(Knip, Vite, Vitest) whose glob patterns come from checked-in configuration.",
    removeWhen:
      "A patched picomatch release is installed, or picomatch starts receiving patterns " +
      "from users, requests, or other untrusted input.",
  },
];

function parseTime(value, field, id) {
  const time = Date.parse(value);
  if (typeof value !== "string" || Number.isNaN(time)) {
    throw new Error(`audit exception ${id}: invalid ${field} ${JSON.stringify(value)}`);
  }
  return time;
}

// Returns the `--ignore` flags for the exceptions, or throws when any exception is malformed,
// expired, or longer than the maximum window.
export function ignoreArgs(exceptions, now) {
  if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
    throw new Error("audit exceptions: invalid current time");
  }
  return exceptions.map((exception) => {
    const { id } = exception;
    if (typeof id !== "string" || !GHSA_ID.test(id)) {
      throw new Error(`audit exception: invalid GHSA ID ${JSON.stringify(id)}`);
    }
    for (const field of ["package", "url", "owner", "reason", "removeWhen"]) {
      if (typeof exception[field] !== "string" || exception[field].trim() === "") {
        throw new Error(`audit exception ${id}: missing ${field}`);
      }
    }
    const approved = parseTime(exception.approved, "approved", id);
    const expires = parseTime(exception.expires, "expires", id);
    if (expires <= approved || expires - approved > MAX_EXCEPTION_DAYS * DAY_MS) {
      throw new Error(
        `audit exception ${id}: expiry must be within ${MAX_EXCEPTION_DAYS} days of approval`,
      );
    }
    if (now.getTime() >= expires) {
      throw new Error(
        `audit exception ${id} (${exception.package}) expired at ${exception.expires}. ` +
          `Remove it when: ${exception.removeWhen} ` +
          `Otherwise reassess the risk and record a new approval. See ${exception.url}`,
      );
    }
    return `--ignore=${id}`;
  });
}

export function main(
  argv,
  { exceptions = AUDIT_EXCEPTIONS, now = new Date(), spawn = spawnSync, log = console.error } = {},
) {
  const separator = argv.indexOf("--");
  const command = separator === -1 ? [] : argv.slice(separator + 1);
  if (command.length === 0) {
    log("usage: audit-exceptions.mjs -- <audit command...>");
    return 2;
  }
  let flags;
  try {
    flags = ignoreArgs(exceptions, now);
  } catch (error) {
    log(error.message);
    return 1;
  }
  for (const exception of exceptions) {
    log(`Ignoring ${exception.id} (${exception.package}) until ${exception.expires}`);
  }
  const result = spawn(command[0], [...command.slice(1), ...flags], { stdio: "inherit" });
  if (result.error) {
    log(`audit command failed to start: ${result.error.message}`);
    return 1;
  }
  // A signal-terminated or otherwise status-less audit counts as a failure.
  return typeof result.status === "number" ? result.status : 1;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  process.exitCode = main(process.argv.slice(2));
}
