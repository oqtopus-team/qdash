import assert from "node:assert/strict";
import { test } from "node:test";
import { releaseVersion } from "./pi-package-release.mjs";

const input = {
  name: "pi-qdash", base: "0.1.10", tags: ["v9.0.0", "pi-qcaleval/v2.0.0", "pi-qdash/v0.1.12"],
  event: "push", ref: "refs/heads/develop", runId: "12345678", attempt: "1",
};
test("beta follows only this package's stable tags and has a migration-safe run identity", () => {
  assert.deepEqual(releaseVersion(input), { version: "0.1.13-beta.12345678.1", channel: "beta" });
  assert.equal(releaseVersion({ ...input, tags: [], attempt: "2" }).version, "0.1.11-beta.12345678.2");
});
test("stable tags publish one package without following QDash's release version", () => {
  assert.deepEqual(releaseVersion({ ...input, ref: "refs/tags/pi-qdash/v0.2.0" }), { version: "0.2.0", channel: "latest" });
  assert.equal(releaseVersion({ ...input, ref: "refs/tags/pi-qcaleval/v0.2.0" }).channel, "check");
  assert.equal(releaseVersion({ ...input, ref: "refs/tags/v9.0.0" }).channel, "check");
});
test("PRs and branch dispatches only validate; a tagged dispatch can retry a release", () => {
  assert.equal(releaseVersion({ ...input, event: "pull_request", ref: "refs/pull/1/merge" }).channel, "check");
  assert.equal(releaseVersion({ ...input, event: "workflow_dispatch" }).channel, "check");
  assert.equal(releaseVersion({ ...input, event: "workflow_dispatch", ref: "refs/tags/pi-qdash/v0.1.12" }).channel, "latest");
});
test("malformed or older stable tags cannot move latest backwards", () => {
  for (const tag of ["0.1.11", "1.2.3-beta.1", "01.2.3", "1.2.3/inject", "garbage"]) {
    assert.throws(() => releaseVersion({ ...input, ref: `refs/tags/pi-qdash/v${tag}` }));
  }
  assert.throws(() => releaseVersion({ ...input, runId: undefined }));
});
