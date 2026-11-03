import assert from "node:assert/strict";
import { test } from "node:test";
import { clientRelease, pinClientDependency } from "./client-release.mjs";

const input = { tags: ["v1.9.9", "v1.9.20", "v1.9.21-beta.1", "pi-qdash/v9.0.0"], ref: "refs/heads/develop", event: "push", runId: "12345", attempt: "1" };
test("develop publishes an exact client beta without following pi or prerelease tags", () => {
  assert.deepEqual(clientRelease(input), { version: "1.9.21-beta.12345.1", channel: "beta" });
  assert.equal(clientRelease({ ...input, attempt: "2" }).version, "1.9.21-beta.12345.2");
});
test("a pi-qdash release publishes its own client snapshot without moving latest or beta", () => {
  assert.deepEqual(clientRelease({ ...input, ref: "refs/tags/pi-qdash/v0.1.11" }), { version: "1.9.21-pi.12345.1", channel: "pi" });
  assert.equal(clientRelease({ ...input, ref: "refs/tags/pi-qcaleval/v0.0.2" }).channel, "check");
  assert.throws(() => clientRelease({ ...input, ref: "refs/tags/pi-qdash/vgarbage" }));
});
test("QDash release tags keep the stable client version line", () => {
  assert.deepEqual(clientRelease({ ...input, ref: "refs/tags/v1.9.21" }), { version: "1.9.21", channel: "latest" });
  for (const version of ["1.9.19", "1.9.21-beta.1", "01.9.21", "0.0.0"]) {
    assert.throws(() => clientRelease({ ...input, ref: `refs/tags/v${version}` }));
  }
});
test("PRs and branch dispatches build unique versions without publication", () => {
  for (const event of ["pull_request", "workflow_dispatch"]) {
    assert.equal(clientRelease({ ...input, event }).channel, "check");
  }
  assert.throws(() => clientRelease({ ...input, runId: undefined }));
});
test("packing pins only pi-qdash to the exact matching client artifact", () => {
  const manifest = { dependencies: { "@oqtopus-team/qdash-client": "workspace:*" } };
  const version = clientRelease(input).version;
  assert.equal(pinClientDependency(manifest, version).dependencies["@oqtopus-team/qdash-client"], version);
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-client"], "workspace:*");
  for (const bad of [undefined, "0.0.0", "workspace:*", "file:../../clients/typescript", "^1.9.21", "beta", "1.2.3\ninjected"]) {
    assert.throws(() => pinClientDependency(manifest, bad));
  }
  assert.deepEqual(pinClientDependency({ name: "pi-qcaleval" }, undefined), { name: "pi-qcaleval" });
});
