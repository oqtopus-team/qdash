/**
 * Pointers to the chat turns this tab started and has not seen saved yet, kept
 * in the tab's session storage so a reload, or the chat provider mounting
 * again, can reattach to a turn that still runs instead of forgetting it.
 *
 * A pointer names a turn; it never holds what the turn said. The transcript
 * comes from the server (the chat saves the user's message before the turn's
 * request goes out), and the turn's events come from the runtime when the chat
 * reattaches with the turn's request ID, which submits nothing. Kept per turn:
 * the session, the request ID, the project the turn was sent from, where the
 * turn starts in the transcript, whether it is a continue, when it started,
 * and the last activity the chat showed (a short label such as "Waiting for
 * the expert's answer") with its time, so a restored chat can say what it last
 * knew while it reconnects. No message text, tool argument, tool result, or
 * credential is stored.
 *
 * Isolation: one entry per signed-in user (`owner`), in session storage, so it
 * lives only in this tab. Restoring for one user removes every other user's
 * entry; signing out removes all of them. A pointer is only resumed in the
 * project it was sent from, and only into a session the user's list holds.
 */

import type { ChatEventKind, TurnActivitySnapshot } from "@/types/agentChat";

const PREFIX = "qdash.agent.activeTurns.v1:";
/** The steer store's prefix (agentSteerStore.ts), cleared together on sign-out. */
const STEER_PREFIX = "qdash.agent.pendingSteers.v1:";
/** At most this many pointers are kept per user; the oldest go first. */
export const MAX_STORED_TURNS = 20;
const EVENT_KINDS = new Set<string>(["answer", "approval", "question", "edit", "expert", "failed"]);

function parseNotified(value: unknown): ChatEventKind[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const kinds = [...new Set(value.filter((k): k is ChatEventKind => EVENT_KINDS.has(k)))];
  return kinds.length ? kinds : undefined;
}

/** The longest activity label or tool name kept. */
const MAX_ACTIVITY_LENGTH = 120;

function parseActivity(value: unknown): TurnActivitySnapshot | undefined {
  if (!value || typeof value !== "object") return undefined;
  const { tool, label } = value as { tool?: unknown; label?: unknown };
  if (typeof label !== "string" || !label) return undefined;
  if (tool !== null && typeof tool !== "string") return undefined;
  return {
    tool: tool === null ? null : tool.slice(0, MAX_ACTIVITY_LENGTH),
    label: label.slice(0, MAX_ACTIVITY_LENGTH),
  };
}

/** What is kept of one turn. */
export interface StoredTurn {
  sessionId: string;
  requestId: string;
  /** The project the turn was sent from; every request of the turn names it. */
  projectId: string | null;
  /** How many messages precede the turn in the transcript. */
  start: number;
  /** A continue: the turn added no user message. */
  continuing: boolean;
  startedAt: number;
  /** The last activity the chat showed for the turn, and when the turn last sent something. */
  activity?: TurnActivitySnapshot | null;
  lastUpdateAt?: number;
  /**
   * The turn's stream ended; the pointer stays until the transcript holding its
   * end is saved, so a reload before that replays the turn rather than losing it.
   */
  ended?: boolean;
  /** The chat notifications already raised for the turn, so a replay raises none again. */
  notified?: ChatEventKind[];
}

/** Stored turns by session ID: one turn per session runs at a time. */
export type StoredTurns = Record<string, StoredTurn>;

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

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function parseTurn(value: unknown): StoredTurn | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (typeof v.sessionId !== "string" || !v.sessionId) return null;
  if (typeof v.requestId !== "string" || !v.requestId) return null;
  if (v.projectId !== null && typeof v.projectId !== "string") return null;
  if (!isCount(v.start) || typeof v.continuing !== "boolean") return null;
  if (typeof v.startedAt !== "number" || !Number.isFinite(v.startedAt)) return null;
  return {
    sessionId: v.sessionId,
    requestId: v.requestId,
    projectId: v.projectId,
    start: v.start,
    continuing: v.continuing,
    startedAt: v.startedAt,
    ...(parseActivity(v.activity) ? { activity: parseActivity(v.activity) } : {}),
    ...(typeof v.lastUpdateAt === "number" && Number.isFinite(v.lastUpdateAt)
      ? { lastUpdateAt: v.lastUpdateAt }
      : {}),
    ...(v.ended === true ? { ended: true } : {}),
    ...(parseNotified(v.notified) ? { notified: parseNotified(v.notified) } : {}),
  };
}

/** The turns stored for `owner`; empty when there are none, the entry is unreadable, or storage is off. */
export function readStoredTurns(owner: string): StoredTurns {
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
    const out: StoredTurns = {};
    for (const [sessionId, value] of Object.entries(parsed as Record<string, unknown>)) {
      const turn = parseTurn(value);
      if (turn && turn.sessionId === sessionId) out[sessionId] = turn;
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

function writeAll(owner: string, all: StoredTurns): boolean {
  const store = storage();
  if (!store) return false;
  try {
    const kept = Object.values(all)
      .sort((a, b) => b.startedAt - a.startedAt)
      .slice(0, MAX_STORED_TURNS);
    if (kept.length === 0) store.removeItem(keyFor(owner));
    else
      store.setItem(
        keyFor(owner),
        JSON.stringify(Object.fromEntries(kept.map((t) => [t.sessionId, t]))),
      );
    return true;
  } catch {
    return false;
  }
}

/** Store a turn, replacing whatever was stored for its session. False when storage refused it. */
export function storeTurn(owner: string, turn: StoredTurn): boolean {
  const all = readStoredTurns(owner);
  const { activity, ...rest } = turn;
  const bounded = parseActivity(activity);
  all[turn.sessionId] = { ...rest, ...(bounded ? { activity: bounded } : {}) };
  return writeAll(owner, all);
}

/**
 * Update the stored turn of a session, only while it is still the turn `requestId`
 * names: a late update of an older turn never touches the pointer of a newer one.
 */
export function patchStoredTurn(
  owner: string,
  sessionId: string,
  requestId: string,
  patch: Partial<Pick<StoredTurn, "activity" | "lastUpdateAt" | "ended" | "notified">>,
): void {
  const all = readStoredTurns(owner);
  const current = all[sessionId];
  if (!current || current.requestId !== requestId) return;
  const { activity, ...rest } = { ...current, ...patch };
  const bounded = parseActivity(activity);
  all[sessionId] = { ...rest, ...(bounded ? { activity: bounded } : {}) };
  writeAll(owner, all);
}

/** Forget the stored turn of a session, only while it is the turn `requestId` names (any when omitted). */
export function forgetStoredTurn(owner: string, sessionId: string, requestId?: string): void {
  const all = readStoredTurns(owner);
  const current = all[sessionId];
  if (!current || (requestId !== undefined && current.requestId !== requestId)) return;
  delete all[sessionId];
  writeAll(owner, all);
}

/** Forget every stored turn of `owner`. */
export function forgetStoredTurns(owner: string): void {
  writeAll(owner, {});
}

function removeKeys(match: (key: string) => boolean): void {
  const store = storage();
  if (!store) return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (key && match(key)) keys.push(key);
    }
    keys.forEach((key) => store.removeItem(key));
  } catch {
    // Storage is off: there is nothing to remove.
  }
}

/** Remove the stored turns of every user but `owner`. */
export function forgetOtherTurnOwners(owner: string): void {
  const mine = keyFor(owner);
  removeKeys((key) => key.startsWith(PREFIX) && key !== mine);
}

/**
 * Remove everything the chat keeps in this tab for any user: turn pointers and
 * unresolved steers. Called on sign-out, before the page leaves.
 */
export function forgetChatTabState(): void {
  removeKeys((key) => key.startsWith(PREFIX) || key.startsWith(STEER_PREFIX));
}
