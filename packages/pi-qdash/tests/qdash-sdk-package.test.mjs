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

test("pi-qdash and the SDK share one client, so errors keep their identity", () => {
  for (const name of ["QDash", "Chip", "CalibrationRun", "Pipelines", "PipelineRun", "Workflows", "Workflow", "WorkflowRun", "runStatus", "sweep", "qubitTargets", "muxTargets", "customOneQubit", "calibrationSpec"]) {
    assert.ok(name in sdk, `${name} must be exported from @oqtopus-team/qdash-sdk`);
  }
  for (const name of ["QDashApiError", "QDashAuthError", "QDashConfigError", "QDashNotFoundError", "QDashTimeoutError", "QDashTransportError", "QDashValidationError"]) {
    assert.equal(sdk[name], client[name], `${name} must be the client's class`);
  }
  const clientRoot = root(pi, "@oqtopus-team/qdash-client");
  assert.equal(root(root(pi, "@oqtopus-team/qdash-sdk"), "@oqtopus-team/qdash-client"), clientRoot);
  assert.equal(realpathSync(fileURLToPath(import.meta.resolve("@oqtopus-team/qdash-client"))), join(clientRoot, "dist/index.js"));

  const base = new client.QDashClient(new client.QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "t" }));
  const scoped = new sdk.QDash(base, { projectId: "p" });
  assert.ok(scoped.client instanceof client.QDashClient);
  assert.equal(base.config.projectId, undefined);
  // Without a project the session uses the client as given; the server's default applies.
  assert.equal(new sdk.QDash(base).client, base);
});

test("the client no longer exposes an SDK subpath", () => {
  const manifest = JSON.parse(readFileSync(join(root(pi, "@oqtopus-team/qdash-client"), "package.json"), "utf8"));
  assert.deepEqual(Object.keys(manifest.exports).sort(), [".", "./models", "./openapi"]);
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-sdk"], undefined);
});
