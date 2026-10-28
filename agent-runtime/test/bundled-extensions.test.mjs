import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { DefaultResourceLoader } from "@earendil-works/pi-coding-agent";
import { ALLOWED_TOOL_NAMES, ALLOWLISTED_PACKAGES, REVIEWED_WRITE_TOOL_NAMES } from "../src/allowed-tools.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";
import {
  bundledExtensionCheckouts, bundledSourceVersion, extensionPackage,
  trustedCheckoutRoots, withExtensionOverrides,
} from "../src/local-extensions.ts";

const packagesDir = fileURLToPath(new URL("../../packages/", import.meta.url));

test("bundled packages load tools and skills offline, retaining the pi-qdash allowlist", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-bundled-"));
  try {
    const bundled = bundledExtensionCheckouts(packagesDir);
    const paths = bundled.map(({ path }) => path);
    const loader = new DefaultResourceLoader({
      cwd: dir, agentDir: join(dir, "agent"), additionalExtensionPaths: paths,
    });
    await loader.reload();
    assert.deepEqual(loader.getExtensions().errors, []);
    const extensions = loader.getExtensions().extensions;
    const names = extensions.flatMap(({ tools }) => [...tools.keys()]);
    assert.ok(names.includes("qdash_build_qcal_evidence"));
    assert.ok(names.includes("qcal_evaluate"));
    const skills = loader.getSkills().skills.map(({ name }) => name);
    assert.ok(skills.includes("qdash"));
    assert.ok(skills.includes("qcaleval"));
    const roots = trustedCheckoutRoots(bundled, ALLOWLISTED_PACKAGES);
    assert.deepEqual(roots, [join(packagesDir, "pi-qcaleval")]);
    const adapted = buildQDashExtension(extensions, {}, dir, { toolArgs: {} }, roots);
    const toolNames = adapted.extension.tools.map(({ name }) => name);
    assert.ok(toolNames.includes("qcal_evaluate"));
    assert.ok(toolNames.includes("qdash_build_qcal_evidence"));
    assert.ok(toolNames.includes("qdash_create_forum_post"));
    const extra = names.find((name) => name.startsWith("qdash_") && !ALLOWED_TOOL_NAMES.includes(name) && !REVIEWED_WRITE_TOOL_NAMES.includes(name));
    assert.ok(extra);
    assert.ok(!toolNames.includes(extra));
    const evaluator = extensions.find(({ tools }) => tools.has("qcal_evaluate"));
    const info = extensionPackage(evaluator.path, paths, paths);
    assert.equal(info.source, "package");
    assert.match(info.version, /^\d+\.\d+\.\d+\+source\.[0-9a-f]{16}$/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a mounted override replaces only its matching bundled package and skills", () => {
  const bundled = bundledExtensionCheckouts(packagesDir);
  const override = { name: "@oqtopus-team/pi-qdash", path: "/app/extensions/pi-qdash" };
  const selected = withExtensionOverrides(bundled, [override]);
  assert.deepEqual(selected, [override, bundled[1]]);
  assert.deepEqual(trustedCheckoutRoots(selected, ALLOWLISTED_PACKAGES), [bundled[1].path]);
});

test("source identity changes for code, skills, and locked dependencies without git", () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-source-"));
  try {
    const root = join(dir, "packages", "test");
    mkdirSync(join(root, "extensions"), { recursive: true });
    mkdirSync(join(root, "skills"), { recursive: true });
    writeFileSync(join(root, "package.json"), '{"version":"1.0.0"}');
    const version = () => bundledSourceVersion(root, "1.0.0");
    const initial = version();
    assert.equal(version(), initial);
    writeFileSync(join(root, "extensions", "index.ts"), "export default 1;");
    const code = version();
    assert.notEqual(code, initial);
    writeFileSync(join(root, "skills", "SKILL.md"), "new instructions");
    const skill = version();
    assert.notEqual(skill, code);
    writeFileSync(join(dir, "bun.lock"), "new dependencies");
    assert.notEqual(version(), skill);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
