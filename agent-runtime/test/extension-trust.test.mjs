import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  buildLocalToolGuide,
  describeBundledExtensions,
  extensionPackage,
  isTrustedExtension,
  localToolNames,
  trustedBundleRoots,
} from "../src/bundled-extensions.ts";

const QCALEVAL = "/app/packages/pi-qcaleval";
const QDASH = "/app/packages/pi-qdash";

test("an extension is trusted only when its file sits under a trusted root", () => {
  const roots = [QCALEVAL];
  assert.equal(isTrustedExtension(`${QCALEVAL}/extensions/qcaleval.ts`, roots), true);
  assert.equal(isTrustedExtension(QCALEVAL, roots), true);
  // A sibling directory sharing the prefix is not inside the root.
  assert.equal(isTrustedExtension("/app/packages/pi-qcaleval-old/extensions/x.ts", roots), false);
  assert.equal(isTrustedExtension(`${QDASH}/extensions/qdash.ts`, roots), false);
  // An installed copy of the same package is not trusted by its name.
  assert.equal(
    isTrustedExtension("/app/.pi-agent/npm/node_modules/@oqtopus-team/pi-qcaleval/extensions/qcaleval.ts", roots),
    false,
  );
});

test("only tools defined under trusted roots are collected", () => {
  const extensions = [
    { path: `${QDASH}/extensions/qdash.ts`, tools: new Map([["qdash_get_default_chip", {}]]) },
    {
      path: `${QCALEVAL}/extensions/qcaleval.ts`,
      tools: new Map([
        ["qcal_evaluate", {}],
        ["qcal_list_models", {}],
      ]),
    },
    { path: `${QCALEVAL}/extensions/helpers.ts` },
  ];
  assert.deepEqual(localToolNames(extensions, []), []);
  assert.deepEqual(localToolNames(extensions, [QCALEVAL]), ["qcal_evaluate", "qcal_list_models"]);
});

test("trusted tools describe themselves to the model through their pi guidelines", () => {
  const extensions = [
    {
      path: `${QDASH}/extensions/qdash.ts`,
      tools: new Map([["qdash_get_figure", { definition: { description: "Fetch a figure" } }]]),
    },
    {
      path: `${QCALEVAL}/extensions/qcaleval.ts`,
      tools: new Map([
        [
          "qcal_evaluate",
          {
            definition: {
              description: "Long description",
              promptSnippet: "Diagnose a calibration plot",
              promptGuidelines: ["Use it for every figure.", "Pass the task name as context."],
            },
          },
        ],
        ["qcal_disabled", { definition: { description: "Not enabled" } }],
      ]),
    },
  ];
  assert.equal(buildLocalToolGuide(extensions, [], new Set(["qcal_evaluate"])), null);
  assert.equal(
    buildLocalToolGuide(extensions, [QCALEVAL], new Set(["qcal_evaluate"])),
    [
      "- `qcal_evaluate`: Diagnose a calibration plot",
      "  - Use it for every figure.",
      "  - Pass the task name as context.",
    ].join("\n"),
  );
});

test("bundled packages of allowlisted names load but are not trusted as a whole", () => {
  const bundled = [
    { path: QCALEVAL, name: "@oqtopus-team/pi-qcaleval" },
    { path: QDASH, name: "@oqtopus-team/pi-qdash" },
  ];
  assert.deepEqual(trustedBundleRoots(bundled, ["@oqtopus-team/pi-qdash"]), [QCALEVAL]);
  assert.deepEqual(trustedBundleRoots(bundled, []), [QCALEVAL, QDASH]);
});

test("an extension's package is read from the nearest manifest, with a source hash when bundled", () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-extensions-"));
  try {
    const pkg = (root, version) => {
      mkdirSync(join(root, "extensions"), { recursive: true });
      writeFileSync(join(root, "package.json"), JSON.stringify({ name: "@oqtopus-team/pi-qcaleval", version, pi: {} }));
      const file = join(root, "extensions", "qcaleval.ts");
      writeFileSync(file, "");
      return file;
    };
    const bundled = join(dir, "packages", "pi-qcaleval");
    const bundledFile = pkg(bundled, "0.0.1");
    const info = extensionPackage(bundledFile, [bundled]);
    assert.equal(info.name, "@oqtopus-team/pi-qcaleval");
    assert.equal(info.source, "package");
    assert.match(info.version, /^0\.0\.1\+source\.[0-9a-f]{16}$/);

    const installedFile = pkg(join(dir, "node_modules", "@oqtopus-team", "pi-qcaleval"), "0.0.2-beta.5");
    assert.deepEqual(extensionPackage(installedFile, [bundled]), {
      name: "@oqtopus-team/pi-qcaleval",
      version: "0.0.2-beta.5",
      source: "package",
    });

    assert.equal(extensionPackage(join(dir, "stray.ts"), [bundled]), undefined);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the startup diagnostics name each bundled package's source version, trust, tools, and skills", () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-diagnostics-"));
  try {
    const qdash = join(dir, "packages", "pi-qdash");
    const qcaleval = join(dir, "packages", "pi-qcaleval");
    for (const [root, name] of [[qdash, "@oqtopus-team/pi-qdash"], [qcaleval, "@oqtopus-team/pi-qcaleval"]]) {
      mkdirSync(join(root, "extensions"), { recursive: true });
      writeFileSync(join(root, "package.json"), JSON.stringify({ name, version: "1.2.3", pi: {} }));
    }
    const bundled = [{ path: qdash, name: "@oqtopus-team/pi-qdash" }, { path: qcaleval, name: "@oqtopus-team/pi-qcaleval" }];
    const lines = describeBundledExtensions(
      bundled,
      [qcaleval],
      [
        { path: join(qdash, "extensions", "qdash.ts"), tools: new Map([["qdash_a", {}], ["qdash_b", {}]]) },
        { path: join(qcaleval, "extensions", "qcaleval.ts"), tools: new Map([["qcal_evaluate", {}]]) },
      ],
      [{ name: "qdash", filePath: join(qdash, "skills", "qdash", "SKILL.md") }],
    );
    assert.equal(lines.length, 2);
    assert.match(
      lines[0],
      new RegExp(`^\\[agent-runtime\\] bundled extension @oqtopus-team/pi-qdash@1\\.2\\.3\\+source\\.[0-9a-f]{16} \\(${qdash}, allowlisted\\): 2 tools, skills: qdash$`),
    );
    assert.match(lines[1], /pi-qcaleval@1\.2\.3\+source\.[0-9a-f]{16} .*, trusted\): 1 tools, skills: none$/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
