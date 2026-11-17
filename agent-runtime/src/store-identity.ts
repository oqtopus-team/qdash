/**
 * Files the runtime keeps beside a chat's SQLite store: which incarnation of
 * the store it is (its *generation*), and the steers a status lookup reported
 * as never sent.
 *
 * A store is named by owner and store session (see `sessionStorageName`), so a
 * chat deleted and then created again under the same ID gets a store at the
 * same path. QDash's API gives every incarnation its own generation and sends
 * it with every request about the store. The runtime records it beside the
 * store (`<store>.generation`) when the store is created, and checks it while
 * it holds the store (see server.ts), so a request about an older incarnation
 * never opens, stops, or deletes a newer one. Removing a store retires its
 * generation: the record stays, and a delayed request of a retired generation
 * cannot create the store again under the old identity.
 *
 * A store created before generations existed has no record. The first request
 * that names a generation adopts it; a request without one only reaches such
 * a legacy store.
 */

import { closeSync, existsSync, fsyncSync, openSync, readFileSync, renameSync, rmSync, writeSync } from "node:fs";

/** What the generation record holds: the store's current generation, and those removed before. */
interface GenerationRecord {
  current?: string;
  retired: string[];
}

/** At most this many retired generations are remembered per store path. */
const RETIRED_LIMIT = 100;

export function generationFile(storePath: string): string {
  return `${storePath}.generation`;
}

export function steerFenceFile(storePath: string): string {
  return `${storePath}.steer-fences`;
}

/** The file beside a session's store that says its workspace directory was created. */
export function workspaceMarker(storePath: string): string {
  return `${storePath}.workspace`;
}

function readRecord(storePath: string): GenerationRecord {
  const file = generationFile(storePath);
  if (!existsSync(file)) return { retired: [] };
  const parsed = JSON.parse(readFileSync(file, "utf8")) as Partial<GenerationRecord>;
  return {
    ...(typeof parsed.current === "string" ? { current: parsed.current } : {}),
    retired: Array.isArray(parsed.retired) ? parsed.retired.filter((g) => typeof g === "string") : [],
  };
}

/** Write a file durably: a synced temporary file renamed over the old one. */
function writeDurably(file: string, content: string): void {
  const tmp = `${file}.tmp`;
  const fd = openSync(tmp, "w");
  try {
    writeSync(fd, content);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tmp, file);
}

function writeRecord(storePath: string, record: GenerationRecord): void {
  writeDurably(
    generationFile(storePath),
    JSON.stringify({ ...record, retired: record.retired.slice(-RETIRED_LIMIT) }),
  );
}

/**
 * Whether a request of `generation` may use the store at `storePath`:
 * - `ok`: the store is that generation (adopted now, for a legacy store, or
 *   created now when `create` is set and no store exists).
 * - `absent`: no store exists, and `create` is not set.
 * - `stale`: the store is another generation, or `generation` was retired.
 *
 * Call it only while holding the store, so nothing creates or removes it
 * meanwhile; it is synchronous, so no other request runs in between.
 */
export function claimStore(
  storePath: string,
  generation: string | undefined,
  create: boolean,
): "ok" | "absent" | "stale" {
  const record = readRecord(storePath);
  const exists = existsSync(storePath);
  if (!exists && !create) return "absent";
  if (generation === undefined) {
    // A legacy request: only a store without a generation of its own.
    if (exists) return record.current === undefined ? "ok" : "stale";
    if (record.current !== undefined) writeRecord(storePath, { retired: record.retired });
    return "ok";
  }
  if (record.retired.includes(generation)) return "stale";
  if (exists && record.current !== undefined) return record.current === generation ? "ok" : "stale";
  // A new store, or a legacy store adopted by its first request that names a generation.
  if (record.current !== generation) writeRecord(storePath, { current: generation, retired: record.retired });
  return "ok";
}

/**
 * Remove the store at `storePath` if it is `generation`, with its WAL files,
 * its workspace marker, and its steer fences; the generation is retired first,
 * so a removal that dies halfway is finished by a retry and nothing reopens
 * the store meanwhile. Call it only while holding the store.
 *
 * - `removed`: the store was this generation and is gone.
 * - `absent`: no store exists.
 * - `stale`: the store is another generation: this one is already gone.
 *
 * Returns whether the workspace marker existed, for a removed store.
 */
export function removeStore(
  storePath: string,
  generation: string | undefined,
): { outcome: "removed" | "absent" | "stale"; hadWorkspace: boolean } {
  const record = readRecord(storePath);
  const exists = existsSync(storePath);
  const marker = workspaceMarker(storePath);
  const hadWorkspace = existsSync(marker);
  if (generation === undefined) {
    if (record.current !== undefined) return { outcome: "stale", hadWorkspace: false };
  } else {
    // Another generation's store: this one is already gone. A store without a
    // generation is a legacy store, or this generation's whose removal died
    // after retiring it; either is this request's to remove.
    if (record.current !== undefined && record.current !== generation) {
      return { outcome: "stale", hadWorkspace: false };
    }
    // Retired also when no store exists: a request of this generation still on
    // its way must not create one after the removal was confirmed.
    writeRecord(storePath, {
      retired: record.retired.includes(generation) ? record.retired : [...record.retired, generation],
    });
  }
  for (const suffix of ["", "-wal", "-shm"]) rmSync(`${storePath}${suffix}`, { force: true });
  rmSync(marker, { force: true });
  rmSync(steerFenceFile(storePath), { force: true });
  return { outcome: exists ? "removed" : "absent", hadWorkspace };
}

/** The line one fenced steer takes in the fence file. */
function fenceLine(conversation: string, steerKey: string): string {
  return JSON.stringify([conversation, steerKey]);
}

/**
 * Record, durably, that the steer `steerKey` of `conversation` is never to be
 * admitted: a status lookup is about to report it as never sent. Appended and
 * synced before the lookup answers, so it holds across a restart and for a
 * replay of the turn it was sent to. No harness writes it: the store's one
 * writer stays the turn's harness.
 */
export function fenceSteer(storePath: string, conversation: string, steerKey: string): void {
  const fd = openSync(steerFenceFile(storePath), "a");
  try {
    writeSync(fd, `${fenceLine(conversation, steerKey)}\n`);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
}

/** Whether a status lookup fenced the steer `steerKey` of `conversation` (see `fenceSteer`). */
export function steerFenced(storePath: string, conversation: string, steerKey: string): boolean {
  const file = steerFenceFile(storePath);
  if (!existsSync(file)) return false;
  const line = fenceLine(conversation, steerKey);
  return readFileSync(file, "utf8").split("\n").includes(line);
}
