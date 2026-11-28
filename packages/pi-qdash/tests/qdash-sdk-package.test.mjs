import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Resolved through each package's package.json exports and its built dist, as a
// published consumer would, not through a source alias.
import * as sdk from "@oqtopus-team/qdash-sdk";

// Node ignores import.meta.resolve's parent argument without a flag, so follow
// node_modules directly: the workspace links each package to its checkout.
const root = (from, name) => realpathSync(join(from, "node_modules", name));
const pi = fileURLToPath(new URL("..", import.meta.url));

test("the SDK is self-contained: its own errors and generated client, no dependency on the client", () => {
  for (const name of ["QDash", "QDashConfig", "QDashApiClient", "QDashApi", "Chip", "CalibrationRun", "Pipelines", "PipelineRun", "Workflows", "Workflow", "WorkflowRun", "Run", "runStatus", "sweep", "qubitTargets", "muxTargets", "customOneQubit", "calibrationSpec"]) {
    assert.ok(name in sdk, `${name} must be exported from @oqtopus-team/qdash-sdk`);
  }
  for (const name of ["QDashApiError", "QDashAuthError", "QDashConfigError", "QDashConflictError", "QDashNotFoundError", "QDashTimeoutError", "QDashTransportError", "QDashValidationError"]) {
    assert.equal(typeof sdk[name], "function", `${name} must be exported`);
  }
  assert.ok(new sdk.QDashNotFoundError("x") instanceof sdk.ApiError);
  const sdkRoot = root(pi, "@oqtopus-team/qdash-sdk");
  const manifest = JSON.parse(readFileSync(join(sdkRoot, "package.json"), "utf8"));
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-client"], undefined);
  assert.doesNotMatch(readFileSync(join(sdkRoot, "dist/index.js"), "utf8"), /from "@oqtopus-team\/qdash-client"/);
});

test("the SDK publishes its calibration builders as @oqtopus-team/qdash-sdk/calibration, with no runtime imports", async () => {
  const calibration = await import("@oqtopus-team/qdash-sdk/calibration");
  for (const name of ["taskCall", "qubitTargets", "muxTargets", "couplingTargets", "customOneQubit", "customTwoQubit", "calibrationStep", "calibrationSpec", "sweep", "calibrationDefinitionsSource"]) {
    assert.ok(name in calibration, `${name} must be exported from @oqtopus-team/qdash-sdk/calibration`);
    // The same functions as the package root.
    assert.equal(calibration[name], sdk[name], name);
  }
  for (const name of ["QDash", "QDashConfig", "QDashApiClient"]) assert.equal(name in calibration, false, name);
  // Follow the entry's whole static import graph in the built dist: relative chunks only, and
  // none of them imports a package, a Node built-in, or the SDK's HTTP and config code.
  const dist = join(root(pi, "@oqtopus-team/qdash-sdk"), "dist");
  const seen = new Set();
  const visit = (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    const source = readFileSync(join(dist, file), "utf8");
    assert.doesNotMatch(source, /\bfetch\(|process\.env|node:|readFileSync/, file);
    for (const [, specifier] of source.matchAll(/(?:^|\n)\s*(?:import|export)\s[^"']*?["']([^"']+)["']/g)) {
      assert.match(specifier, /^\.\/[\w-]+\.js$/, `${file} imports ${specifier}`);
      visit(specifier.slice(2));
    }
  };
  visit("calibration.js");
  assert.ok(seen.size >= 2);
});

test("pi-qdash depends on the SDK only: the client is neither a dependency nor resolvable", () => {
  const manifest = JSON.parse(readFileSync(join(pi, "package.json"), "utf8"));
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-client"], undefined);
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-sdk"], "workspace:*");
  assert.throws(() => root(pi, "@oqtopus-team/qdash-client"), { code: "ENOENT" });
});

test("the extension's own sources import nothing from the client", () => {
  const sources = execFileSync("git", ["ls-files", "extensions"], { cwd: pi, encoding: "utf8" }).split("\n").filter((path) => path.endsWith(".ts"));
  const untracked = execFileSync("git", ["ls-files", "--others", "--exclude-standard", "extensions"], { cwd: pi, encoding: "utf8" }).split("\n").filter((path) => path.endsWith(".ts"));
  assert.ok(sources.length + untracked.length > 10);
  for (const path of [...sources, ...untracked]) {
    assert.doesNotMatch(readFileSync(join(pi, path), "utf8"), /from "@oqtopus-team\/qdash-client/, path);
  }
});

test("pi-qdash builds its SDK sessions from the connection's session, with the same settings", async () => {
  const { sdkSession, sdkSessionFactory } = await import("../.test-dist/lib/sdk-session.js");
  const { QDashConnection } = await import("../.test-dist/lib/qdash-connection.js");
  const options = {
    baseUrl: "https://qdash.example/api",
    apiToken: "t",
    projectId: "p",
    cfAccessClientId: "id",
    cfAccessClientSecret: "secret",
    timeoutSec: 12,
    readAttempts: 2,
  };
  const connection = new QDashConnection(new sdk.QDash(options));
  // The default shares the connection's session: one fetch, one sign-in, one project.
  assert.equal(sdkSession(connection), connection.qdash);
  const session = sdkSessionFactory({ fetch: async () => new Response("{}") })(connection);
  assert.ok(session instanceof sdk.QDash);
  assert.notEqual(session, connection.qdash);
  assert.deepEqual(session.config.options(), { ...options, verifyTls: true });
});
