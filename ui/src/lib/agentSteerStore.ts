/**
 * Steers the chat does not know the fate of yet, kept in the tab's session
 * storage so a reload does not lose them.
 *
 * A steer the runtime may hold, but the chat does not show, keeps Continue
 * locked (see `isUnresolvedSteer`). Held only in memory, a reload would forget
 * it and unlock Continue while the runtime may still place it. So the chat
 * writes each unresolved steer here before it sends the request, and restores
 * it after a reload, to ask the runtime where it stands. It never sends a
 * restored steer again.
 *
 * Isolation: one entry per signed-in user (`owner`), in session storage, so it
 * lives only in this tab. Restoring for one user removes every other user's
 * entry, and a steer is only restored into a session that user's session list
 * holds. Only what the chat needs to ask about the steer and place it is kept:
 * its request ID, text, project, the turn it was sent to, and where it stands.
 * No credential is stored.
 */

import type { PendingSteer, PendingSteerStatus, SteerAnchor } from "@/lib/agentSteer";
import { isUnresolvedSteer } from "@/lib/agentSteer";

const PREFIX = "qdash.agent.pendingSteers.v1:";

/** The fields kept of an unresolved steer. */
export interface StoredSteer {
  requestId: string;
  text: string;
  status: Extract<PendingSteerStatus, "sending" | "queued" | "unconfirmed" | "delivered">;
  projectId: string | null;
  anchor?: SteerAnchor;
  entryId?: string | null;
}

/** Unresolved steers by session ID. */
export type StoredSteers = Record<string, StoredSteer[]>;

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function keyFor(owner: string): string {
  return PREFIX + encodeURIComponent(owner);
}

const STORED_STATUSES = new Set(["sending", "queued", "unconfirmed", "delivered"]);

function parseAnchor(value: unknown): SteerAnchor | undefined {
  if (!value || typeof value !== "object") return undefined;
  const { start, userText } = value as { start?: unknown; userText?: unknown };
  if (typeof start !== "number" || !Number.isInteger(start) || start < 0) return undefined;
  if (userText !== null && typeof userText !== "string") return undefined;
  return { start, userText };
}

function parseSteer(value: unknown): StoredSteer | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (typeof v.requestId !== "string" || !v.requestId) return null;
  if (typeof v.text !== "string" || typeof v.status !== "string") return null;
  if (!STORED_STATUSES.has(v.status)) return null;
  if (v.projectId !== null && typeof v.projectId !== "string") return null;
  const anchor = parseAnchor(v.anchor);
  return {
    requestId: v.requestId,
    text: v.text,
    status: v.status as StoredSteer["status"],
    projectId: v.projectId,
    ...(anchor ? { anchor } : {}),
    ...(typeof v.entryId === "string" ? { entryId: v.entryId } : {}),
  };
}

/** The steers stored for `owner`; empty when there are none, the entry is unreadable, or storage is off. */
export function readStoredSteers(owner: string): StoredSteers {
  const store = storage();
  if (!store) return {};
  let raw: string | null;
  try {
    raw = store.getItem(keyFor(owner));
  } catch {
    return {};
  }
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("shape");
    const out: StoredSteers = {};
    for (const [sessionId, list] of Object.entries(parsed as Record<string, unknown>)) {
      if (!Array.isArray(list)) continue;
      const steers = list.map(parseSteer).filter((s): s is StoredSteer => s !== null);
      if (steers.length) out[sessionId] = steers;
    }
    return out;
  } catch {
    try {
      store.removeItem(keyFor(owner));
    } catch {
      // Nothing more to do: it is read as empty.
    }
    return {};
  }
}

function writeAll(owner: string, all: StoredSteers): boolean {
  const store = storage();
  if (!store) return false;
  try {
    if (Object.keys(all).length === 0) store.removeItem(keyFor(owner));
    else store.setItem(keyFor(owner), JSON.stringify(all));
    return true;
  } catch {
    return false;
  }
}

/** What is kept of a steer, or null when it is resolved and need not be. */
function toStoredSteer(steer: PendingSteer): StoredSteer | null {
  // A steer placed in the conversation but not saved with it yet is kept as
  // delivered: after a reload it is placed again unless the saved one has it.
  if (!isUnresolvedSteer(steer) && !(steer.status === "delivered" && steer.saving)) return null;
  return {
    requestId: steer.requestId,
    text: steer.text,
    status: steer.status as StoredSteer["status"],
    projectId: steer.projectId ?? null,
    ...(steer.anchor ? { anchor: steer.anchor } : {}),
    ...(steer.entryId !== undefined ? { entryId: steer.entryId } : {}),
  };
}

/**
 * Store the unresolved steers of one session, replacing what was stored for it.
 * `keep`: also keep stored steers of the session `steers` does not name, for a
 * write before the stored ones were restored. False when storage refused it.
 */
export function storeSessionSteers(
  owner: string,
  sessionId: string,
  steers: PendingSteer[],
  keep = false,
): boolean {
  const all = readStoredSteers(owner);
  const list = steers.map(toStoredSteer).filter((s): s is StoredSteer => s !== null);
  if (keep) {
    const named = new Set(steers.map((s) => s.requestId));
    list.unshift(...(all[sessionId] ?? []).filter((s) => !named.has(s.requestId)));
  }
  if (list.length) all[sessionId] = list;
  else delete all[sessionId];
  return writeAll(owner, all);
}

/** Forget the stored steers of the given sessions. */
export function forgetStoredSessions(owner: string, sessionIds: Iterable<string>): void {
  const all = readStoredSteers(owner);
  let changed = false;
  for (const id of sessionIds) {
    if (id in all) {
      delete all[id];
      changed = true;
    }
  }
  if (changed) writeAll(owner, all);
}

/** Forget every stored steer of `owner`. */
export function forgetStoredSteers(owner: string): void {
  writeAll(owner, {});
}

/** Remove the stored steers of every user but `owner`. */
export function forgetOtherOwners(owner: string): void {
  const store = storage();
  if (!store) return;
  try {
    const mine = keyFor(owner);
    const others: string[] = [];
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (key && key.startsWith(PREFIX) && key !== mine) others.push(key);
    }
    others.forEach((key) => store.removeItem(key));
  } catch {
    // Storage is off: there is nothing to remove.
  }
}

/**
 * A stored steer as the chat holds it after a reload. Its request may still
 * have been on its way, or queued, when the page went away: the runtime has
 * not said where it stands, so it is unconfirmed until a status lookup says.
 */
export function restoreSteer(stored: StoredSteer): PendingSteer {
  return {
    requestId: stored.requestId,
    text: stored.text,
    status: stored.status === "delivered" ? "delivered" : "unconfirmed",
    projectId: stored.projectId,
    ...(stored.anchor ? { anchor: stored.anchor } : {}),
    ...(stored.entryId !== undefined ? { entryId: stored.entryId } : {}),
  };
}
