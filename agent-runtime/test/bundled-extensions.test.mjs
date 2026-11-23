import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { DefaultResourceLoader } from "@earendil-works/pi-coding-agent";
import { parse } from "yaml";
import {
  ALLOWED_TOOL_NAMES,
  ALLOWLISTED_PACKAGES,
  DEFERRED_TOOL_NAMES,
  NESTED_READ_TOOL_NAMES,
  REVIEWED_WRITE_TOOL_NAMES,
  SESSION_GRANTED_WRITE_TOOL_NAMES,
} from "../src/allowed-tools.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";
import {
  bundledExtensions, bundledSourceVersion, createBundledResourceLoader, extensionPackage,
  trustedBundleRoots,
} from "../src/bundled-extensions.ts";

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
    const bundled = bundledExtensions(packagesDir);
    const paths = bundled.map(({ path }) => path);
    const loader = createBundledResourceLoader({ cwd: dir, agentDir: join(dir, "agent"), bundled });
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
    for (const name of SESSION_GRANTED_WRITE_TOOL_NAMES) assert.ok(names.includes(name), name);
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
    const roots = trustedBundleRoots(bundled, ALLOWLISTED_PACKAGES);
    assert.deepEqual(roots, [join(packagesDir, "pi-qcaleval")]);
    const adapted = buildQDashExtension(extensions, {}, dir, { toolArgs: {} }, roots);
    const toolNames = adapted.extension.tools.map(({ name }) => name);
    assert.ok(toolNames.includes("qcal_evaluate"));
    assert.ok(toolNames.includes("qdash_build_qcal_evidence"));
    assert.ok(toolNames.includes("qdash_create_forum_post"));
    // Session-granted writes are offered, model-only, and replayed (their keys come from the call id).
    for (const name of SESSION_GRANTED_WRITE_TOOL_NAMES) {
      const tool = adapted.extension.tools.find((entry) => entry.name === name);
      assert.ok(tool, name);
      assert.deepEqual(tool.callers, ["model"], name);
      assert.doesNotMatch(tool.description, /must approve before it runs/, name);
    }
    const extra = names.find((name) => name.startsWith("qdash_") && !ALLOWED_TOOL_NAMES.includes(name) && !REVIEWED_WRITE_TOOL_NAMES.includes(name) && !SESSION_GRANTED_WRITE_TOOL_NAMES.includes(name));
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
    const info = extensionPackage(evaluator.path, paths);
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
    const bundled = bundledExtensions(packagesDir);
    const loader = createBundledResourceLoader({ cwd: dir, agentDir: join(dir, "agent"), bundled });
    await loader.reload();
    const tools = new Set(loader.getExtensions().extensions.flatMap(({ tools }) => [...tools.keys()]));
    const offered = new Set([...ALLOWED_TOOL_NAMES, ...REVIEWED_WRITE_TOOL_NAMES, ...SESSION_GRANTED_WRITE_TOOL_NAMES]);
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
      // The budgeted ZX90 search that composes the two-qubit chain with ordinary pipelines.
      "qdash-zx90-optimization",
      "qdash-characterization",
      // The ordering check those skills defer to after Configure or ConfigureAll.
      "qdash-rabi-after-configure",
      // The model-driven loop that runs those skills' tasks inside an agent session.
      "qdash-agent-calibration",
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

/**
 * A stale pi package: a copy of pi-qdash with an extra tool and skill, as an
 * old development checkout or installed package would carry.
 */
function writeStalePackage(root, name) {
  mkdirSync(join(root, "extensions"), { recursive: true });
  mkdirSync(join(root, "skills", "stale-skill"), { recursive: true });
  writeFileSync(join(root, "package.json"), JSON.stringify({
    name, version: "0.0.1", type: "module",
    pi: { extensions: ["./extensions/stale.ts"], skills: ["./skills"] },
  }));
  writeFileSync(join(root, "extensions", "stale.ts"), staleExtension("stale_injected_tool"));
  writeFileSync(join(root, "skills", "stale-skill", "SKILL.md"), staleSkill("stale-skill"));
}

const staleExtension = (tool) => `export default function (pi) {
  pi.registerTool({
    name: ${JSON.stringify(tool)}, label: "Stale", description: "Stale tool",
    parameters: { type: "object", properties: {} },
    execute: async () => ({ content: [{ type: "text", text: "stale" }], details: {} }),
  });
}
`;

const staleSkill = (name) => `---\nname: ${name}\ndescription: Stale ${name} skill.\n---\n\nStale instructions.\n`;

/**
 * Every place pi would look for packages, extensions, and skills on its own:
 * the settings packages of the agent and working directories, and their
 * auto-discovered extensions/ and skills/ directories. The legacy
 * agent-runtime/extensions/ mount held such packages under /app/extensions.
 */
function writeStaleSources(dir) {
  const legacy = join(dir, "legacy-extensions", "pi-qdash");
  writeStalePackage(legacy, "@oqtopus-team/pi-qdash");
  const agentDir = join(dir, "agent");
  const cwd = join(dir, "workspace");
  for (const [base, label] of [[agentDir, "agent"], [join(cwd, ".pi"), "project"]]) {
    mkdirSync(join(base, "extensions"), { recursive: true });
    mkdirSync(join(base, "skills", `${label}-skill`), { recursive: true });
    writeFileSync(join(base, "settings.json"), JSON.stringify({ packages: [legacy] }));
    writeFileSync(join(base, "extensions", `${label}.ts`), staleExtension(`${label}_dir_tool`));
    writeFileSync(join(base, "skills", `${label}-skill`, "SKILL.md"), staleSkill(`${label}-skill`));
  }
  return { agentDir, cwd };
}

const STALE_TOOLS = ["stale_injected_tool", "agent_dir_tool", "project_dir_tool"];
const STALE_SKILLS = ["stale-skill", "agent-skill", "project-skill"];

test("stale packages, settings, and discovered resources cannot replace or extend the bundled set", async () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-stale-"));
  try {
    const { agentDir, cwd } = writeStaleSources(dir);
    const bundled = bundledExtensions(packagesDir);

    // Control: pi's default loader does pick these up, so the fixture is a real threat.
    const plain = new DefaultResourceLoader({ cwd, agentDir, additionalExtensionPaths: bundled.map(({ path }) => path) });
    await plain.reload();
    const plainTools = plain.getExtensions().extensions.flatMap(({ tools }) => [...tools.keys()]);
    const plainSkills = plain.getSkills().skills.map(({ name }) => name);
    assert.ok(plainTools.includes("stale_injected_tool") && plainTools.includes("agent_dir_tool"), plainTools.join());
    assert.ok(plainSkills.includes("stale-skill") && plainSkills.includes("agent-skill"), plainSkills.join());

    const loader = createBundledResourceLoader({ cwd, agentDir, bundled });
    await loader.reload();
    assert.deepEqual(loader.getExtensions().errors, []);
    const extensions = loader.getExtensions().extensions;
    // Every extension file comes from a bundled package of this checkout.
    for (const { path } of extensions) {
      assert.ok(bundled.some((pkg) => path.startsWith(pkg.path + sep)), path);
    }
    const tools = extensions.flatMap(({ tools }) => [...tools.keys()]);
    for (const name of STALE_TOOLS) assert.ok(!tools.includes(name), name);
    for (const name of [...ALLOWED_TOOL_NAMES, "qcal_evaluate"]) assert.ok(tools.includes(name), name);
    const skills = loader.getSkills().skills;
    for (const { name, filePath } of skills) {
      assert.ok(!STALE_SKILLS.includes(name), name);
      assert.ok(bundled.some((pkg) => filePath.startsWith(pkg.path + sep)), filePath);
    }
    for (const name of ["qdash", "qcaleval", "qdash-metric-scripts"]) {
      assert.ok(skills.some((skill) => skill.name === name), name);
    }
    // The trust boundary is unchanged: only pi-qcaleval is trusted as a whole,
    // and pi-qdash's unreviewed tools stay out of the adapted extension.
    const roots = trustedBundleRoots(bundled, ALLOWLISTED_PACKAGES);
    assert.deepEqual(roots, [join(packagesDir, "pi-qcaleval")]);
    const adapted = buildQDashExtension(extensions, {}, cwd, { toolArgs: {} }, roots);
    const offered = adapted.extension.tools.map(({ name }) => name);
    for (const name of STALE_TOOLS) assert.ok(!offered.includes(name), name);
    assert.deepEqual(adapted.nestedTools.sort(), [...NESTED_READ_TOOL_NAMES].sort());
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the runtime builds its loader from the bundled packages only", () => {
  const source = readFileSync(new URL("../src/runtime.ts", import.meta.url), "utf8");
  assert.match(source, /createBundledResourceLoader\(\{ cwd: WORK_DIR, agentDir: AGENT_DIR, bundled: BUNDLED \}\)/);
  assert.doesNotMatch(source, /new DefaultResourceLoader|\/app\/extensions/);
});

test("compose mounts no extension directory into the Agent Runtime", () => {
  const compose = parse(readFileSync(new URL("../../compose.yaml", import.meta.url), "utf8"));
  const volumes = compose.services["agent-runtime"].volumes;
  assert.ok(volumes.length > 0);
  for (const volume of volumes) {
    const target = typeof volume === "string" ? volume.split(":")[1] : volume.target;
    assert.ok(!/^\/app\/(extensions|packages)(\/|$)/.test(target), volume);
  }
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
