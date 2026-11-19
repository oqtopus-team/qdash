/**
 * Which of pi's `codemode` and `tool_search` a pi session should have
 * active, so that pi-qdash offers them to a new user without overriding a
 * selection the user made.
 *
 * pi itself records a session's tool loadout in its transcript (system
 * messages with `toolsAdded`/`toolsRemoved`) and restores it before
 * `session_start` on resume, fork, and tree navigation; a reload keeps the
 * active tools; a new session starts from the `defaultTools` setting. pi-qdash
 * follows that and adds what pi does not keep:
 *
 * 1. `reload` keeps the active tools as they are.
 * 2. The session's own branch decides when it records the tool: pi's loadout
 *    records, or a `pi-qdash-tool-selection` entry pi-qdash appends when the
 *    selection changed since the branch last recorded it (when each run starts
 *    and at shutdown).
 * 3. A session that replaced another through `newSession` or `fork` and whose
 *    branch records nothing takes the selection the replaced session had at
 *    `session_shutdown`. The two are paired by pi's session file, or for an
 *    in-memory fork by its session manager. Without either identity, a new
 *    in-memory session uses its own settings and defaults.
 * 4. A `defaultTools` setting entry for the tool (`codemode`, `+codemode`,
 *    `-codemode`) decides next.
 * 5. Otherwise pi-qdash activates the tool: the first activation for a new
 *    user.
 */

/** Tools whose activation pi-qdash manages. */
export type ManagedTool = "codemode" | "tool_search";

/** Active or not, per managed tool; a missing tool is not decided. */
export type ToolSelection = Partial<Record<ManagedTool, boolean>>;

/** Custom entry type of pi-qdash's selection records in a pi session. */
export const SELECTION_ENTRY = "pi-qdash-tool-selection";

type EntryLike = {
  type?: string;
  customType?: string;
  data?: unknown;
  message?: { role?: string; toolsAdded?: { name?: string }[]; toolsRemoved?: { name?: string }[] };
};

/**
 * The selection a branch records, oldest to newest, the latest record per
 * tool winning: pi's loadout changes and pi-qdash's selection entries.
 * `fromPi` lists the tools whose latest record is pi's, which pi has
 * already restored.
 */
export function branchSelection(
  entries: readonly EntryLike[],
  managed: readonly ManagedTool[],
): { selection: ToolSelection; fromPi: Set<ManagedTool> } {
  const selection: ToolSelection = {};
  const fromPi = new Set<ManagedTool>();
  const isManaged = (name: unknown): name is ManagedTool => managed.includes(name as ManagedTool);
  for (const entry of entries) {
    if (entry?.type === "message" && entry.message?.role === "system") {
      for (const [list, active] of [[entry.message.toolsAdded, true], [entry.message.toolsRemoved, false]] as const) {
        for (const tool of list ?? []) {
          if (!isManaged(tool?.name)) continue;
          selection[tool.name] = active;
          fromPi.add(tool.name);
        }
      }
    } else if (entry?.type === "custom" && entry.customType === SELECTION_ENTRY && entry.data && typeof entry.data === "object") {
      for (const [name, active] of Object.entries(entry.data as Record<string, unknown>)) {
        if (!isManaged(name) || typeof active !== "boolean") continue;
        selection[name] = active;
        fromPi.delete(name);
      }
    }
  }
  return { selection, fromPi };
}

/** What a `defaultTools` setting says about each managed tool; the last entry naming it wins. */
export function settingsSelection(defaultTools: unknown, managed: readonly ManagedTool[]): ToolSelection {
  const selection: ToolSelection = {};
  if (!Array.isArray(defaultTools)) return selection;
  for (const entry of defaultTools) {
    if (typeof entry !== "string") continue;
    const sign = entry[0] === "-" ? false : true;
    const name = entry[0] === "-" || entry[0] === "+" ? entry.slice(1) : entry;
    if (managed.includes(name as ManagedTool)) selection[name as ManagedTool] = sign;
  }
  return selection;
}

/** The selection a replaced session leaves for the session that replaces it. */
interface Handoff {
  selection: ToolSelection;
  reason: "new" | "fork";
  /** pi's session file of the replacing session, when sessions are persisted. */
  targetSessionFile: string | undefined;
  /** The replaced session's manager; an in-memory fork keeps it. */
  sessionManager: object;
}

/** Most handoffs kept waiting for a replacing session; older ones are dropped. */
const MAX_PENDING = 8;

// One list per process: a replacing session loads pi-qdash afresh, and pi
// gives the two extension instances no shared object.
const HANDOFFS_KEY = Symbol.for("@oqtopus-team/pi-qdash/tool-selection-handoffs");
function pendingHandoffs(): Handoff[] {
  const store = globalThis as unknown as Record<symbol, Handoff[] | undefined>;
  return (store[HANDOFFS_KEY] ??= []);
}

/** Leave `selection` for the session replacing this one through `newSession` or `fork`. */
export function leaveHandoff(handoff: Handoff): void {
  const pending = pendingHandoffs();
  // A session replaced twice keeps only its latest handoff.
  const index = pending.findIndex((other) => other.sessionManager === handoff.sessionManager);
  if (index !== -1) pending.splice(index, 1);
  pending.push(handoff);
  if (pending.length > MAX_PENDING) pending.shift();
}

/**
 * Take the handoff a starting session pairs with: the one whose target is its
 * session file or the one from its own session manager (an in-memory fork).
 * An unrelated manager never consumes a pending handoff, even if only one
 * exists. Every handoff the session matched is removed.
 */
export function takeHandoff(start: {
  reason: string;
  sessionFile: string | undefined;
  sessionManager: object;
}): ToolSelection | undefined {
  if (start.reason !== "new" && start.reason !== "fork") return undefined;
  const pending = pendingHandoffs();
  const take = (index: number) => pending.splice(index, 1)[0]?.selection;
  const index = pending.findIndex(
    (handoff) =>
      handoff.reason === start.reason &&
      ((start.sessionFile !== undefined && handoff.targetSessionFile === start.sessionFile) ||
        handoff.sessionManager === start.sessionManager),
  );
  if (index !== -1) return take(index);
  return undefined;
}

/** Forget every pending handoff (tests). */
export function clearHandoffs(): void {
  pendingHandoffs().length = 0;
}
