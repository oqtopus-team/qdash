import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Run against an npm install of the tarball outside the monorepo. This catches
// missing published files and imports that only resolve inside our workspace.
const [consumer, name] = process.argv.slice(2);
const packages = {
  "pi-qdash": ["@oqtopus-team/pi-qdash", "qdash_build_qcal_evidence", "qdash"],
  "pi-qcaleval": ["@oqtopus-team/pi-qcaleval", "qcal_evaluate", "qcaleval"],
};
assert.ok(Object.hasOwn(packages, name), "Unknown package");
const [packageName, tool, skill] = packages[name];
const root = join(consumer, "node_modules", packageName);
const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
assert.equal(manifest.name, packageName);
for (const version of Object.values(manifest.dependencies ?? {})) {
  assert.ok(!/^(workspace:|file:|link:)/.test(version), "Published dependencies must resolve outside the workspace");
}
if (name === "pi-qdash") {
  const client = JSON.parse(readFileSync(join(consumer, "node_modules/@oqtopus-team/qdash-client/package.json"), "utf8"));
  assert.equal(manifest.dependencies["@oqtopus-team/qdash-client"], client.version);
  assert.notEqual(client.version, "0.0.0");
}
assert.ok(existsSync(join(root, "LICENSE")));
assert.ok(existsSync(join(root, "skills", skill, "SKILL.md")));
const tools = new Map();
for (const entry of manifest.pi.extensions) {
  const { default: extension } = await import(pathToFileURL(join(root, entry)).href);
  extension({ registerTool: (tool) => tools.set(tool.name, tool), registerCommand() {}, on() {} });
}
assert.ok(tools.has(tool), `${tool} must be registered by the installed tarball`);
console.log(`${packageName}@${manifest.version}: standalone artifact verified`);
