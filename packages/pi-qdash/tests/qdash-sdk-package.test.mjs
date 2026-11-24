import assert from "node:assert/strict";
import { readFileSync, realpathSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Resolved through each package's package.json exports and its built dist, as a
// published consumer would, not through a source alias.
import * as client from "@oqtopus-team/qdash-client";
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
    assert.notEqual(sdk[name], client[name], `${name} is the SDK's own class`);
  }
  assert.ok(new sdk.QDashNotFoundError("x") instanceof sdk.ApiError);
  const sdkRoot = root(pi, "@oqtopus-team/qdash-sdk");
  const manifest = JSON.parse(readFileSync(join(sdkRoot, "package.json"), "utf8"));
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-client"], undefined);
  assert.doesNotMatch(readFileSync(join(sdkRoot, "dist/index.js"), "utf8"), /from "@oqtopus-team\/qdash-client"/);
});

test("pi-qdash builds an SDK session from the client it resolved, with the same settings", async () => {
  const { sdkSession } = await import("../.test-dist/lib/sdk-session.js");
  const config = new client.QDashConfig({
    baseUrl: "https://qdash.example/api",
    apiToken: "t",
    projectId: "p",
    cfAccessClientId: "id",
    cfAccessClientSecret: "secret",
    timeoutSeconds: 12,
    retry: { maxAttempts: 2 },
  });
  const session = sdkSession(new client.QDashClient(config));
  assert.ok(session instanceof sdk.QDash);
  assert.deepEqual(session.config.options(), {
    baseUrl: "https://qdash.example/api",
    apiToken: "t",
    projectId: "p",
    cfAccessClientId: "id",
    cfAccessClientSecret: "secret",
    timeoutSec: 12,
    verifyTls: true,
    userAgent: config.userAgent,
    readAttempts: 2,
  });
  // The client and its configuration are unchanged.
  assert.equal(config.projectId, "p");
});

test("the client no longer exposes an SDK subpath", () => {
  const manifest = JSON.parse(readFileSync(join(root(pi, "@oqtopus-team/qdash-client"), "package.json"), "utf8"));
  assert.deepEqual(Object.keys(manifest.exports).sort(), [".", "./models", "./openapi"]);
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-sdk"], undefined);
});
