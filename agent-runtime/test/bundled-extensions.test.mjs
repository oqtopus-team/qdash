import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { DefaultResourceLoader } from "@earendil-works/pi-coding-agent";
import {
  ALLOWED_TOOL_NAMES,
  ALLOWLISTED_PACKAGES,
  DEFERRED_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
} from "../src/allowed-tools.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";
import {
  bundledExtensionCheckouts, bundledSourceVersion, extensionPackage,
  trustedCheckoutRoots, withExtensionOverrides,
} from "../src/local-extensions.ts";

const packagesDir = fileURLToPath(new URL("../../packages/", import.meta.url));

test("pi-qdash resolves the client built from this checkout", () => {
  const client = import.meta.resolve(
    "@oqtopus-team/qdash-client",
    fileURLToPath(new URL("../../packages/pi-qdash/package.json", import.meta.url)),
  );
  assert.equal(
    realpathSync(fileURLToPath(client)),
    realpathSync(fileURLToPath(new URL("../../clients/typescript/dist/index.js", import.meta.url))),
  );
});

test("pi-qdash resolves the SDK built from this checkout, on the same client", () => {
  const pi = fileURLToPath(new URL("../../packages/pi-qdash/package.json", import.meta.url));
  const sdk = fileURLToPath(import.meta.resolve("@oqtopus-team/qdash-sdk", pi));
  assert.equal(
    realpathSync(sdk),
    realpathSync(fileURLToPath(new URL("../../sdks/typescript/dist/index.js", import.meta.url))),
  );
  assert.equal(
    realpathSync(fileURLToPath(import.meta.resolve("@oqtopus-team/qdash-client", sdk))),
    realpathSync(fileURLToPath(import.meta.resolve("@oqtopus-team/qdash-client", pi))),
  );
});

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
    // Timeseries data stays available; the removed TUI plot tool is not registered.
    assert.ok(names.includes("qdash_get_timeseries"));
    assert.ok(!names.includes("qdash_plot_timeseries"));
    // Every allowlisted read tool names a tool the bundled packages register.
    for (const name of ALLOWED_TOOL_NAMES) assert.ok(names.includes(name), name);
    const loadedSkills = loader.getSkills().skills;
    const skills = loadedSkills.map(({ name }) => name);
    assert.ok(skills.includes("qdash"));
    assert.ok(skills.includes("qcaleval"));
    // Dashboard authoring is a model-invocable skill whose references ship beside it.
    const metricScripts = loadedSkills.find(({ name }) => name === "qdash-metric-scripts");
    assert.ok(metricScripts, "qdash-metric-scripts skill loads");
    assert.ok(!metricScripts.disableModelInvocation);
    assert.match(metricScripts.description, /dashboard/);
    for (const reference of ["references/api.md", "references/templates.md"]) {
      assert.ok(existsSync(join(dirname(metricScripts.filePath), reference)), reference);
    }
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
    // Code Mode and deferred loading name real pi-qdash tools; scripts reach only the audited reads.
    for (const name of [...NESTED_READ_TOOL_NAMES, ...DEFERRED_TOOL_NAMES]) assert.ok(toolNames.includes(name), name);
    assert.deepEqual(adapted.nestedTools.sort(), [...NESTED_READ_TOOL_NAMES].sort());
    assert.deepEqual(adapted.deferredTools.sort(), [...DEFERRED_TOOL_NAMES].sort());
    for (const tool of adapted.extension.tools) {
      const nested = NESTED_READ_TOOL_NAMES.includes(tool.name);
      assert.deepEqual(tool.callers, nested ? ["model", "tools"] : ["model"], tool.name);
      assert.equal(tool.deferred === true, DEFERRED_TOOL_NAMES.includes(tool.name), tool.name);
    }
    const evaluator = extensions.find(({ tools }) => tools.has("qcal_evaluate"));
    const info = extensionPackage(evaluator.path, paths, paths);
    assert.equal(info.source, "package");
    assert.equal(info.name, "@oqtopus-team/pi-qcaleval");
    assert.match(info.version, /^\d+\.\d+\.\d+\+source\.[0-9a-f]{16}$/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("experiment-flow skills load in both hosts and name only tools the runtime offers", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-flow-skills-"));
  try {
    const bundled = bundledExtensionCheckouts(packagesDir);
    const loader = new DefaultResourceLoader({
      cwd: dir, agentDir: join(dir, "agent"), additionalExtensionPaths: bundled.map(({ path }) => path),
    });
    await loader.reload();
    const tools = new Set(loader.getExtensions().extensions.flatMap(({ tools }) => [...tools.keys()]));
    const offered = new Set([...ALLOWED_TOOL_NAMES, ...REVIEWED_WRITE_TOOL_NAMES]);
    const skills = loader.getSkills().skills;
    const names = new Set(skills.map(({ name }) => name));
    // The flow skills replace the retired calibration-agent and two-qubit diagnosis skills.
    for (const retired of ["qdash-calibration-agent", "qdash-two-qubit-calibration-diagnosis"]) {
      assert.ok(!names.has(retired), retired);
    }
    const flowSkills = [
      "qdash-chip-bringup",
      "qdash-one-qubit-calibration",
      "qdash-two-qubit-calibration",
      "qdash-characterization",
    ];
    for (const name of [...flowSkills, "qdash"]) {
      const skill = skills.find((entry) => entry.name === name);
      assert.ok(skill, `${name} loads`);
      assert.ok(!skill.disableModelInvocation, name);
      const text = readFileSync(skill.filePath, "utf8");
      // The general skill also covers pi-only tools and APIs; a flow skill must work in the web
      // Agent too, where read_skill returns only SKILL.md.
      if (name !== "qdash") {
        for (const [, tool] of text.matchAll(/`(qdash_[a-z0-9_]+)`/g)) {
          assert.ok(tools.has(tool), `${name} names unregistered tool ${tool}`);
          assert.ok(offered.has(tool), `${name} names ${tool}, which the runtime does not offer`);
        }
        assert.deepEqual(readdirSync(dirname(skill.filePath)), ["SKILL.md"], name);
      }
      for (const [, ref] of text.matchAll(/`(qdash-[a-z0-9-]+)`/g)) {
        assert.ok(names.has(ref), `${name} refers to missing skill ${ref}`);
      }
    }
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
