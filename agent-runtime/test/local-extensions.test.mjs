import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  buildLocalToolGuide,
  isInstalledPackage,
  isLocalExtension,
  isTrustedExtension,
  localToolNames,
  describeExtensionError,
  discoverExtensionCheckouts,
  trustedCheckoutRoots,
  withoutReplacedInstalls,
} from "../src/local-extensions.ts";

test("checkouts are the package directories with a pi manifest under the mount", () => {
  const dir = mkdtempSync(join(tmpdir(), "qdash-extensions-"));
  try {
    const pkg = (name, manifest) => {
      mkdirSync(join(dir, name), { recursive: true });
      if (manifest !== undefined) writeFileSync(join(dir, name, "package.json"), manifest);
    };
    pkg("pi-qcaleval", JSON.stringify({ name: "@x/pi-qcaleval", pi: { extensions: ["./extensions/q.ts"] } }));
    pkg("pi-other", JSON.stringify({ name: "@x/pi-other", pi: {} }));
    pkg("plain-package", JSON.stringify({ name: "no-pi-manifest" }));
    pkg("broken", "{not json");
    pkg("no-manifest");
    writeFileSync(join(dir, "README.md"), "a file, not a checkout");

    assert.deepEqual(discoverExtensionCheckouts(dir), [
      { path: join(dir, "pi-other"), name: "@x/pi-other" },
      { path: join(dir, "pi-qcaleval"), name: "@x/pi-qcaleval" },
    ]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a missing or empty extensions directory yields no checkouts", () => {
  assert.deepEqual(discoverExtensionCheckouts("/nonexistent/qdash-extensions"), []);
  const dir = mkdtempSync(join(tmpdir(), "qdash-extensions-empty-"));
  try {
    assert.deepEqual(discoverExtensionCheckouts(dir), []);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("an extension is local only when its file sits under a checkout root", () => {
  const roots = ["/app/extensions/pi-qcaleval"];
  assert.equal(isLocalExtension("/app/extensions/pi-qcaleval/extensions/qcaleval.ts", roots), true);
  assert.equal(isLocalExtension("/app/extensions/pi-qcaleval", roots), true);
  // A sibling directory sharing the prefix is not inside the root.
  assert.equal(isLocalExtension("/app/extensions/pi-qcaleval-old/extensions/x.ts", roots), false);
  assert.equal(isLocalExtension("/app/.pi-agent/packages/pi-qdash/extensions/qdash.ts", roots), false);
});

test("only tools defined by local checkouts are collected", () => {
  const extensions = [
    {
      path: "/app/.pi-agent/packages/pi-qdash/extensions/qdash.ts",
      tools: new Map([["qdash_get_default_chip", {}]]),
    },
    {
      path: "/app/extensions/pi-qcaleval/extensions/qcaleval.ts",
      tools: new Map([
        ["qcal_evaluate", {}],
        ["qcal_list_models", {}],
      ]),
    },
    { path: "/app/extensions/pi-qcaleval/extensions/helpers.ts" },
  ];
  assert.deepEqual(localToolNames(extensions, []), []);
  assert.deepEqual(localToolNames(extensions, ["/app/extensions/pi-qcaleval"]), [
    "qcal_evaluate",
    "qcal_list_models",
  ]);
});

test("local tools describe themselves to the model through their pi guidelines", () => {
  const extensions = [
    {
      path: "/app/.pi-agent/packages/pi-qdash/extensions/qdash.ts",
      tools: new Map([["qdash_get_figure", { definition: { description: "Fetch a figure" } }]]),
    },
    {
      path: "/app/extensions/pi-qcaleval/extensions/qcaleval.ts",
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
  const roots = ["/app/extensions/pi-qcaleval"];
  assert.equal(buildLocalToolGuide(extensions, [], new Set(["qcal_evaluate"])), null);
  assert.equal(
    buildLocalToolGuide(extensions, roots, new Set(["qcal_evaluate"])),
    [
      "- `qcal_evaluate`: Diagnose a calibration plot",
      "  - Use it for every figure.",
      "  - Pass the task name as context.",
    ].join("\n"),
  );
});

test("an installed package is trusted by its name under pi's node_modules", () => {
  const packages = ["@orangekame3/pi-qcaleval"];
  const installed = "/app/.pi-agent/npm/node_modules/@orangekame3/pi-qcaleval/extensions/qcaleval.ts";
  assert.equal(isInstalledPackage(installed, packages), true);
  assert.equal(isInstalledPackage(installed, []), false);
  // The pinned pi-qdash package and look-alike names are not covered.
  assert.equal(
    isInstalledPackage("/app/.pi-agent/npm/node_modules/@oqtopus-team/pi-qdash/extensions/qdash.ts", packages),
    false,
  );
  assert.equal(
    isInstalledPackage("/app/.pi-agent/npm/node_modules/@orangekame3/pi-qcaleval-fork/extensions/x.ts", packages),
    false,
  );
  // A checkout root or a trusted package both qualify.
  assert.equal(isTrustedExtension(installed, [], packages), true);
  assert.equal(isTrustedExtension("/app/extensions/dev/extensions/x.ts", ["/app/extensions/dev"], packages), true);
  assert.equal(isTrustedExtension("/app/extensions/dev/extensions/x.ts", [], packages), false);

  const extensions = [
    { path: installed, tools: new Map([["qcal_evaluate", { definition: { description: "d" } }]]) },
  ];
  assert.deepEqual(localToolNames(extensions, [], packages), ["qcal_evaluate"]);
  assert.deepEqual(localToolNames(extensions, [], []), []);
  assert.equal(buildLocalToolGuide(extensions, [], new Set(["qcal_evaluate"]), packages), "- `qcal_evaluate`: d");
});

test("checkouts of allowlisted packages load but are not trusted as a whole", () => {
  const checkouts = [
    { path: "/app/extensions/pi-qcaleval", name: "@orangekame3/pi-qcaleval" },
    { path: "/app/extensions/pi-qdash", name: "@oqtopus-team/pi-qdash" },
    { path: "/app/extensions/anonymous", name: null },
  ];
  assert.deepEqual(trustedCheckoutRoots(checkouts, ["@oqtopus-team/pi-qdash"]), [
    "/app/extensions/pi-qcaleval",
    "/app/extensions/anonymous",
  ]);
  assert.deepEqual(trustedCheckoutRoots(checkouts, []).length, 3);
});

test("an installed copy rejected in favour of a checkout is reported as a replacement", () => {
  const checkouts = ["/app/extensions/pi-qcaleval"];
  const installed = "/app/.pi-agent/npm/node_modules/@orangekame3/pi-qcaleval/extensions/qcaleval.ts";
  assert.deepEqual(
    describeExtensionError(
      installed,
      'Tool "qcal_evaluate" conflicts with /app/extensions/pi-qcaleval/extensions/qcaleval.ts',
      checkouts,
    ),
    {
      level: "info",
      message: `[agent-runtime] local checkout /app/extensions/pi-qcaleval/extensions/qcaleval.ts replaces installed ${installed}`,
    },
  );
  // A conflict between two checkouts, or any other failure, stays an error.
  assert.equal(
    describeExtensionError("/app/extensions/pi-qcaleval/extensions/b.ts", 'Tool "x" conflicts with /app/extensions/pi-qcaleval/extensions/a.ts', checkouts).level,
    "error",
  );
  assert.equal(describeExtensionError(installed, "Extension path does not exist", checkouts).level, "error");
});

test("an installed copy is dropped when a checkout of the same package is present", () => {
  const checkouts = [
    { path: "/app/extensions/pi-qdash", name: "@oqtopus-team/pi-qdash" },
    { path: "/app/extensions/unnamed", name: null },
  ];
  const checkout = { path: "/app/extensions/pi-qdash/extensions/qdash.ts" };
  const installed = { path: "/app/.pi-agent/npm/node_modules/@oqtopus-team/pi-qdash/extensions/qdash.ts" };
  const other = { path: "/app/.pi-agent/npm/node_modules/@orangekame3/pi-qcaleval/extensions/qcaleval.ts" };
  // pi lists the checkout first and the rejected installed copy after it.
  assert.deepEqual(withoutReplacedInstalls([checkout, installed, other], checkouts), [checkout, other]);
  // Without a checkout of that package, the installed copy stays.
  assert.deepEqual(withoutReplacedInstalls([installed, other], []), [installed, other]);
});
