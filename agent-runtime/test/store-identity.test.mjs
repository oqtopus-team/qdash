import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  claimStore,
  fenceSteer,
  generationFile,
  removeStore,
  steerFenceFile,
  steerFenced,
  workspaceMarker,
} from "../src/store-identity.ts";

function withDir(run) {
  const dir = mkdtempSync(join(tmpdir(), "store-identity-"));
  try {
    run(join(dir, "store.sqlite"));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** A store file, as SQLite would create it on open. */
function create(path) {
  writeFileSync(path, "db");
  writeFileSync(`${path}-wal`, "wal");
}

test("a new store takes the generation of the request that creates it", () => {
  withDir((path) => {
    assert.equal(claimStore(path, "G1", false), "absent");
    assert.equal(existsSync(generationFile(path)), false);
    assert.equal(claimStore(path, "G1", true), "ok");
    create(path);
    assert.equal(claimStore(path, "G1", false), "ok");
    // Another incarnation's request, or a legacy one, never reaches it.
    assert.equal(claimStore(path, "G0", true), "stale");
    assert.equal(claimStore(path, undefined, true), "stale");
  });
});

test("a stale removal after the chat was created again removes nothing", () => {
  withDir((path) => {
    claimStore(path, "G1", true);
    create(path);
    writeFileSync(workspaceMarker(path), "");
    fenceSteer(path, "root", "p\0s1");
    assert.deepEqual(removeStore(path, "G1"), { outcome: "removed", hadWorkspace: true });
    for (const file of [path, `${path}-wal`, workspaceMarker(path), steerFenceFile(path)]) {
      assert.equal(existsSync(file), false, file);
    }
    // A removal retried with the same generation finds nothing to remove.
    assert.equal(removeStore(path, "G1").outcome, "absent");
    // A request of the removed generation still on its way cannot recreate it.
    assert.equal(claimStore(path, "G1", true), "stale");
    assert.equal(existsSync(path), false);

    // The chat is created again: a new generation.
    assert.equal(claimStore(path, "G2", true), "ok");
    create(path);
    // The first removal's request arrives late: the new store stays.
    assert.deepEqual(removeStore(path, "G1"), { outcome: "stale", hadWorkspace: false });
    assert.deepEqual(removeStore(path, undefined), { outcome: "stale", hadWorkspace: false });
    assert.equal(readFileSync(path, "utf8"), "db");
    assert.equal(claimStore(path, "G2", false), "ok");
  });
});

test("a removal confirmed before the store was ever created still retires its generation", () => {
  withDir((path) => {
    assert.equal(removeStore(path, "G1").outcome, "absent");
    // The chat request of that generation arrives after the removal: refused.
    assert.equal(claimStore(path, "G1", true), "stale");
    assert.equal(claimStore(path, "G2", true), "ok");
  });
});

test("a legacy store is adopted by the first request that names a generation", () => {
  withDir((path) => {
    assert.equal(claimStore(path, undefined, true), "ok");
    create(path);
    assert.equal(existsSync(generationFile(path)), false);
    assert.equal(claimStore(path, undefined, false), "ok");
    assert.equal(claimStore(path, "G1", false), "ok");
    assert.equal(claimStore(path, undefined, false), "stale");
    assert.equal(removeStore(path, undefined).outcome, "stale");
    assert.equal(removeStore(path, "G1").outcome, "removed");
  });
  withDir((path) => {
    // A legacy store removed by a request that names a generation.
    create(path);
    assert.equal(removeStore(path, "G1").outcome, "removed");
    assert.equal(claimStore(path, "G1", true), "stale");
  });
});

test("a removal that died after retiring its generation is finished by a retry", () => {
  withDir((path) => {
    claimStore(path, "G1", true);
    create(path);
    // As `removeStore` leaves it when the process dies right after retiring G1.
    writeFileSync(generationFile(path), JSON.stringify({ retired: ["G1"] }));
    // Nothing of G1 reopens the half-removed store meanwhile.
    assert.equal(claimStore(path, "G1", true), "stale");
    assert.equal(removeStore(path, "G1").outcome, "removed");
    assert.equal(existsSync(path), false);
  });
});

test("a steer fence holds per conversation and store, and goes with the store", () => {
  withDir((path) => {
    assert.equal(steerFenced(path, "root", "p\0s1"), false);
    fenceSteer(path, "root", "p\0s1");
    fenceSteer(path, "root", "p\0s1");
    assert.equal(steerFenced(path, "root", "p\0s1"), true);
    assert.equal(steerFenced(path, "7", "p\0s1"), false);
    assert.equal(steerFenced(path, "root", "p\0s10"), false);
    assert.equal(steerFenced(path, "root", "q\0s1"), false);
    // Fenced before the store exists (a lookup before the first turn opened it): kept when it is created.
    claimStore(path, "G1", true);
    create(path);
    assert.equal(steerFenced(path, "root", "p\0s1"), true);
    removeStore(path, "G1");
    assert.equal(steerFenced(path, "root", "p\0s1"), false);
  });
});
