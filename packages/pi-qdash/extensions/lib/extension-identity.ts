import { realpathSync } from "node:fs";
import { basename, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Whether a tool pi runs under a name is the definition pi-qdash registered,
 * from pi's own registry rather than from the tool's name or annotations.
 *
 * pi's registry (`pi.getAllTools()`) reports, for each name, the registration
 * that won it: its `parameters` object as registered and the `sourceInfo` of
 * the extension that registered it. A tool is pi-qdash's own when both hold:
 *
 * - its `parameters` is the very object pi-qdash passed to `registerTool`
 *   for that name, and
 * - its `sourceInfo.path` names the file pi-qdash's extension entry was
 *   loaded from (compared by real path, so symlinks such as workspace
 *   installs and `/var` versus `/private/var` agree; case-folded on Windows).
 *
 * Anything else fails closed: no registry, a name pi does not list, missing
 * or synthetic source metadata (`<inline>`, `builtin:`, `<sdk:…>`), or an
 * entry path that cannot be resolved.
 */

/** pi's source metadata for a registered tool, as far as identity needs it. */
export interface SourceInfoLike {
  path?: unknown;
  baseDir?: unknown;
}

/** A file path's comparison key: its real path, case-folded on Windows; undefined when it does not resolve. */
export function filePathKey(path: string): string | undefined {
  try {
    const real = realpathSync.native(path);
    return process.platform === "win32" ? real.toLowerCase() : real;
  } catch {
    return undefined;
  }
}

/** The key of an extension entry given as a `file:` URL (`import.meta.url`) or an absolute path. */
export function entryPathKey(entry: string | URL | undefined): string | undefined {
  if (entry === undefined) return undefined;
  try {
    const path = entry instanceof URL || /^file:/i.test(entry) ? fileURLToPath(entry) : entry;
    return isAbsolute(path) ? filePathKey(path) : undefined;
  } catch {
    return undefined;
  }
}

/** Whether pi's path names no file: `<inline>`, `<sdk:name>`, `builtin:name`. */
function isSyntheticPath(path: string): boolean {
  return path.startsWith("<") || path.startsWith("builtin:");
}

/**
 * The key of the file a tool's `sourceInfo` names. pi records the path an
 * extension was given as and, when it resolved a relative one, the directory
 * of the resolved file.
 */
export function sourceFileKey(info: SourceInfoLike | undefined): string | undefined {
  const path = info?.path;
  if (typeof path !== "string" || path.length === 0 || isSyntheticPath(path)) return undefined;
  if (/^file:/i.test(path)) return entryPathKey(path);
  if (isAbsolute(path)) return filePathKey(path);
  const baseDir = info?.baseDir;
  return typeof baseDir === "string" && isAbsolute(baseDir) ? filePathKey(join(baseDir, basename(path))) : undefined;
}

/** A registered tool as `pi.getAllTools()` reports it, as far as identity needs it. */
export interface RegisteredToolLike {
  name: string;
  parameters?: unknown;
  sourceInfo?: SourceInfoLike;
}

/**
 * Decide, from pi's registry, whether the tool pi runs under a name is the
 * definition this extension registered from `entry`.
 */
export function createOwnershipCheck(entry: string | URL | undefined) {
  const entryKey = entryPathKey(entry);
  // sourceInfo objects are shared per extension, so each is resolved once.
  const fromEntry = new WeakMap<object, boolean>();
  const isFromEntry = (info: SourceInfoLike | undefined): boolean => {
    if (entryKey === undefined || !info || typeof info !== "object") return false;
    let known = fromEntry.get(info);
    if (known === undefined) {
      known = sourceFileKey(info) === entryKey;
      fromEntry.set(info, known);
    }
    return known;
  };
  return {
    /** Whether the entry resolved; without it nothing is pi-qdash's own. */
    resolved: entryKey !== undefined,
    /**
     * Whether `tool`, pi's registration for its name, is the one this
     * extension made with `parameters`.
     */
    owns(tool: RegisteredToolLike | undefined, parameters: unknown): boolean {
      if (!tool || typeof parameters !== "object" || parameters === null) return false;
      return tool.parameters === parameters && isFromEntry(tool.sourceInfo);
    },
  };
}
