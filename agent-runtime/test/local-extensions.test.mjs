import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isLocalExtension,
  localToolNames,
  parseExtensionPaths,
} from "../src/local-extensions.ts";

test("extension paths come from a colon- or comma-separated list", () => {
  const cwd = "/app/workspace";
  assert.deepEqual(parseExtensionPaths(undefined, cwd), []);
  assert.deepEqual(parseExtensionPaths("  ", cwd), []);
  assert.deepEqual(parseExtensionPaths("/app/extensions/pi-qcaleval", cwd), [
    "/app/extensions/pi-qcaleval",
  ]);
  assert.deepEqual(
    parseExtensionPaths("/app/extensions/a:/app/extensions/b, /app/extensions/a", cwd),
    ["/app/extensions/a", "/app/extensions/b"],
  );
});

test("relative extension paths resolve against the loader cwd, as pi does", () => {
  assert.deepEqual(parseExtensionPaths("../extensions/pi-qcaleval", "/app/workspace"), [
    "/app/extensions/pi-qcaleval",
  ]);
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
