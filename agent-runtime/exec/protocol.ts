/**
 * What the runtime's relay tells the agent-exec server before the pi-env
 * daemon's own wire protocol starts, and the naming both sides share.
 *
 * The runtime opens one TCP connection per conversation. Its first line is a
 * JSON "hello" with the owner the daemon runs for and the daemon arguments
 * pi-env's `Connection` chose; everything after the newline is the daemon's
 * stdin. The hello carries no secret: Unix socket permissions restrict access
 * to the runtime, excluding workspace users. This file has no dependencies because the
 * exec image ships it without the runtime's node_modules.
 */
import { createHash } from "node:crypto";

export const DEFAULT_EXEC_SOCKET = "/run/agent-exec/exec.sock";
/** Longest hello line accepted, including the newline. */
export const HELLO_MAX_BYTES = 4096;
/** The uid range the server runs daemons as: one per owner, by hash. */
export const UID_BASE = 20000;
export const UID_SPAN = 40000;

export interface ExecHello {
  /** The QDash user the daemon works for; its workspace and uid derive from it. */
  owner: string;
  /** The daemon's arguments as pi-env's `Connection` appends them: `serve --token <hex>`. */
  argv: readonly string[];
}

const DAEMON_TOKEN = /^[0-9a-f]{32}$/;

/** Parse a hello line; anything unexpected is `undefined`, never partially trusted. */
export function parseHello(line: string): ExecHello | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return undefined;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
  const { owner, argv } = parsed as Record<string, unknown>;
  if (typeof owner !== "string" || owner.length === 0 || owner.length > 256) return undefined;
  if (
    !Array.isArray(argv) ||
    argv.length !== 3 ||
    argv[0] !== "serve" ||
    argv[1] !== "--token" ||
    typeof argv[2] !== "string" ||
    !DAEMON_TOKEN.test(argv[2])
  ) {
    return undefined;
  }
  return { owner, argv: [argv[0], argv[1], argv[2]] };
}

/**
 * A stable, filename-safe directory name for an owner or session id: a readable
 * prefix for operators plus a hash suffix that keeps distinct ids distinct.
 */
export function workspaceName(id: string): string {
  const prefix = id.replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^\.+/, "_").slice(0, 32) || "id";
  const hash = createHash("sha256").update(id).digest("hex").slice(0, 12);
  return `${prefix}-${hash}`;
}

/** 32-bit FNV-1a of the UTF-8 text. */
export function fnv1a32(text: string): number {
  let hash = 0x811c9dc5;
  for (const byte of Buffer.from(text, "utf8")) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/** Pick an unused uid; persisted directory ownership preserves it across restarts. */
export function ownerUid(owner: string, used: ReadonlySet<number> = new Set()): number {
  const start = fnv1a32(owner) % UID_SPAN;
  for (let offset = 0; offset < UID_SPAN; offset++) {
    const uid = UID_BASE + ((start + offset) % UID_SPAN);
    if (!used.has(uid)) return uid;
  }
  throw new Error("Copilot workspace uid range exhausted");
}
