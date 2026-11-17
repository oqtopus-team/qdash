import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { AUDIT_EXCEPTIONS, ignoreArgs, main } from "./audit-exceptions.mjs";

const exception = {
  id: "GHSA-fc5q-39xc-vjpf",
  package: "picomatch",
  url: "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
  approved: "2026-11-18T00:00:00Z",
  expires: "2026-12-02T00:00:00Z",
  owner: "QDash repository maintainers",
  reason: "reason",
  removeWhen: "a patched release is installed.",
};
const before = new Date("2026-12-01T23:59:59Z");
const atExpiry = new Date("2026-12-02T00:00:00Z");

// Runs main() against a stand-in audit that exits with `code` and records its arguments.
// The trailing "--" keeps Node from parsing the appended --ignore flag as its own option.
function run(code, options) {
  const calls = [];
  const logs = [];
  const status = main(["--", process.execPath, "-e", `process.exit(${code})`, "--"], {
    exceptions: [exception],
    now: before,
    log: (line) => logs.push(line),
    spawn: (command, args, spawnOptions) => {
      calls.push([command, ...args]);
      return spawnSync(command, args, spawnOptions);
    },
    ...options,
  });
  return { status, calls, logs };
}

test("the checked-in exception is valid while it is active", () => {
  assert.deepEqual(ignoreArgs(AUDIT_EXCEPTIONS, before), ["--ignore=GHSA-fc5q-39xc-vjpf"]);
});

test("an active exception adds only its exact GHSA ignore and passes a clean audit", () => {
  const { status, calls } = run(0);
  assert.equal(status, 0);
  assert.deepEqual(calls[0].slice(-2), ["--", "--ignore=GHSA-fc5q-39xc-vjpf"]);
  assert.equal(calls[0].filter((arg) => arg.startsWith("--ignore")).length, 1);
});

test("other advisories and registry errors keep the audit's nonzero exit", () => {
  // Bun exits 1 for remaining advisories and for failed registry requests.
  assert.equal(run(1).status, 1);
  assert.equal(run(3).status, 3);
});

test("an expired exception fails closed without running the audit", () => {
  for (const now of [atExpiry, new Date("2027-01-01T00:00:00Z")]) {
    const { status, calls, logs } = run(0, { now });
    assert.equal(status, 1);
    assert.equal(calls.length, 0);
    assert.match(logs.join("\n"), /GHSA-fc5q-39xc-vjpf \(picomatch\) expired at 2026-12-02/);
  }
});

test("malformed exceptions fail closed", () => {
  const malformed = [
    { ...exception, id: "CVE-2026-0001" },
    { ...exception, id: "picomatch" },
    { ...exception, package: "" },
    { ...exception, reason: undefined },
    { ...exception, expires: "soon" },
    { ...exception, expires: "2026-12-03T00:00:00Z" },
    { ...exception, expires: exception.approved },
  ];
  for (const bad of malformed) {
    const { status, calls } = run(0, { exceptions: [bad] });
    assert.equal(status, 1, JSON.stringify(bad));
    assert.equal(calls.length, 0);
  }
  assert.throws(() => ignoreArgs([exception], new Date("invalid")));
});

test("a missing command, failed start, or signal fails", () => {
  assert.equal(main([], { log: () => {} }), 2);
  const start = main(["--", "/nonexistent/audit"], {
    exceptions: [exception],
    now: before,
    log: () => {},
  });
  assert.equal(start, 1);
  const signal = main(["--", "audit"], {
    exceptions: [exception],
    now: before,
    log: () => {},
    spawn: () => ({ status: null, signal: "SIGTERM" }),
  });
  assert.equal(signal, 1);
});
