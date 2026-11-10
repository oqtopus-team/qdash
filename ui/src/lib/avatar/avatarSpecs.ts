import { useEffect, useSyncExternalStore } from "react";

import { listUserAvatars } from "@/client/user-avatar/user-avatar";

/**
 * Custom avatar specs of users, fetched in batches and shared by every `UserAvatar`.
 *
 * Avatars render from the username alone; a custom spec only replaces the automatic avatar once
 * it arrives. Usernames requested in the same tick are looked up with one request, so a page
 * of forum posts costs one request rather than one per author. A failed lookup leaves the
 * automatic avatar in place and is retried by a later mount after a short delay.
 *
 * The cache belongs to one authenticated session. `AuthProvider` starts a new session whenever
 * the access token changes (login, logout, or an expired token), which drops every cached spec
 * and queued lookup and makes responses to requests of the previous session be ignored. The
 * session holds no credential; it is identified only by object identity.
 */
type Entry =
  | { status: "loaded"; spec: string | null; at: number }
  | { status: "failed"; at: number };

interface Session {
  /** False before login and after logout; no lookup is made then. */
  authenticated: boolean;
  entries: Map<string, Entry>;
  // Usernames queued for the next batch or in a request that has not finished.
  inFlight: Set<string>;
  queued: Set<string>;
  flushScheduled: boolean;
}

/** An opaque handle of the session a write was started in. */
export type AvatarSpecSession = object;

const MAX_BATCH = 100;
const FRESH_MS = 5 * 60 * 1000;
const RETRY_AFTER_MS = 30 * 1000;

function newSession(authenticated: boolean): Session {
  return {
    authenticated,
    entries: new Map(),
    inFlight: new Set(),
    queued: new Set(),
    flushScheduled: false,
  };
}

let session = newSession(false);
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function needsLookup(current: Session, username: string, now: number): boolean {
  if (!current.authenticated || current.inFlight.has(username)) return false;
  const entry = current.entries.get(username);
  if (!entry) return true;
  if (entry.status === "failed") return now - entry.at >= RETRY_AFTER_MS;
  return now - entry.at >= FRESH_MS;
}

async function lookup(owner: Session, usernames: string[]): Promise<void> {
  const startedAt = Date.now();
  let specs: Map<string, string> | null = null;
  try {
    const response = await listUserAvatars(
      { username: usernames },
      // Repeat the key (`username=a&username=b`) as FastAPI expects for a list parameter.
      { paramsSerializer: { indexes: null } },
    );
    specs = new Map(response.data.avatars.map((avatar) => [avatar.username, avatar.spec]));
  } catch {
    // Leave `specs` null: the lookup failed.
  }
  // The response belongs to a session that has ended; its state is already discarded.
  if (owner !== session) return;
  const at = Date.now();
  for (const username of usernames) {
    owner.inFlight.delete(username);
    const previous = owner.entries.get(username);
    if (specs) {
      // A spec saved in this tab while the request ran is newer than the response.
      if (previous?.status === "loaded" && previous.at >= startedAt) continue;
      owner.entries.set(username, { status: "loaded", spec: specs.get(username) ?? null, at });
    } else if (previous?.status !== "loaded") {
      // Keep a spec loaded earlier; the next mount after the delay retries.
      owner.entries.set(username, { status: "failed", at });
    }
  }
  notify();
}

function flush(owner: Session): void {
  owner.flushScheduled = false;
  if (owner !== session) return;
  const usernames = [...owner.queued];
  owner.queued = new Set();
  for (let start = 0; start < usernames.length; start += MAX_BATCH) {
    void lookup(owner, usernames.slice(start, start + MAX_BATCH));
  }
}

/** Queues a lookup of `username`'s custom spec unless a fresh result or request exists. */
export function requestAvatarSpec(username: string): void {
  const current = session;
  if (!username || !needsLookup(current, username, Date.now())) return;
  // A stale loaded spec stays visible while it is refreshed.
  current.inFlight.add(username);
  current.queued.add(username);
  if (!current.flushScheduled) {
    current.flushScheduled = true;
    setTimeout(() => flush(current), 0);
  }
}

/**
 * Starts a new cache session, dropping every cached spec and pending lookup.
 *
 * Called by `AuthProvider` when the access token changes. Mounted avatars fall back to the
 * automatic avatar at once and, when `authenticated`, look their users up again.
 */
export function startAvatarSpecSession(authenticated: boolean): void {
  session = newSession(authenticated);
  notify();
}

/** The current session, to pass to `setAvatarSpec` after an asynchronous save. */
export function currentAvatarSpecSession(): AvatarSpecSession {
  return session;
}

/**
 * Records a spec saved in this tab so every avatar of the user updates at once.
 *
 * When `startedIn` is given and another session has started since, the write is dropped.
 */
export function setAvatarSpec(
  username: string,
  spec: string | null,
  startedIn: AvatarSpecSession = session,
): void {
  if (startedIn !== session || !session.authenticated) return;
  session.entries.set(username, { status: "loaded", spec, at: Date.now() });
  notify();
}

function getSession(): Session {
  return session;
}

/** The custom spec of `username`, or null while unknown or when the user has none. */
export function useCustomAvatarSpec(username: string): string | null {
  const current = useSyncExternalStore(subscribe, getSession, getSession);
  // A new session re-requests every mounted user.
  useEffect(() => requestAvatarSpec(username), [username, current]);
  return useSyncExternalStore(
    subscribe,
    () => {
      const entry = session.entries.get(username);
      return entry?.status === "loaded" ? entry.spec : null;
    },
    () => null,
  );
}
