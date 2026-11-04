/**
 * Recovery guidance for source-code requests sent to the config file actions.
 *
 * qdash_query's `files_tree` and `file_content` serve the configured
 * calibration-config directory only. A model investigating a traceback often
 * sends a source path there instead, gets "File not found" back, and keeps
 * retrying config reads. These helpers recognize such requests and name the
 * source tool call that answers them; they never read source themselves.
 */

/** Source roots the server serves by name; a path starting with one is located without a root. */
const SOURCE_ROOT_NAMES = new Set(["qdash", "qubex", "qubecalib"]);
const SOURCE_SUFFIXES = /\.(py|pyi)$/;

function normalize(path: string): string {
  return path.trim().replace(/\\/g, "/").replace(/^(?:\.\/)+/, "");
}

/** Whether a path names QDash or dependency source rather than a config file. */
export function looksLikeSourcePath(path: string | undefined): boolean {
  if (!path) return false;
  const value = normalize(path);
  if (!value) return false;
  const segments = value.split("/").filter(Boolean);
  return value.startsWith("/")
    || SOURCE_SUFFIXES.test(value)
    || segments.includes("site-packages")
    || segments.includes("dist-packages")
    || SOURCE_ROOT_NAMES.has(segments[0] ?? "");
}

/** The qdash_read_source arguments for a source path. */
export function readSourceArguments(path: string): { path: string; root?: string } {
  const value = normalize(path);
  const first = value.split("/").filter(Boolean)[0] ?? "";
  // Absolute, installed-package and root-qualified paths are located by the server.
  if (value.startsWith("/") || SOURCE_ROOT_NAMES.has(first) || /(site|dist)-packages\//.test(value)) {
    return { path: value };
  }
  return { root: "qdash", path: value.replace(/^\.?\//, "") };
}

/** The qdash_search_source arguments that list files under a source directory. */
export function searchSourceArguments(path: string): { root?: string; pathPrefix?: string; mode: "path"; query: string } {
  const value = normalize(path);
  const segments = value.split("/").filter(Boolean);
  const filename = segments.at(-1) ?? "";
  const query = !value.endsWith("/") && /\.[a-z0-9]+$/i.test(filename) ? filename : ".py";
  const rootIndex = segments.findIndex((segment) => SOURCE_ROOT_NAMES.has(segment));
  if (rootIndex < 0) return { mode: "path", query };
  const pathPrefix = segments.slice(rootIndex + 1).join("/");
  return { root: segments[rootIndex], ...(pathPrefix ? { pathPrefix } : {}), mode: "path", query };
}

const CONFIG_SCOPE = "qdash_query files_tree and file_content serve only the calibration config directory (the qubex config files), not QDash or qubex source code.";

export function fileContentSourceGuidance(path: string, reason: string): string {
  return [
    `\`${path}\` is not a config file (${reason}).`,
    CONFIG_SCOPE,
    "Do not retry file_content for source. Read it with:",
    "",
    `qdash_read_source ${JSON.stringify(readSourceArguments(path))}`,
    "",
    "If that file is not found, locate it with qdash_search_source (mode \"path\") or list the readable roots with qdash_list_source_roots.",
  ].join("\n");
}

export function filesTreeSourceGuidance(path: string): string {
  const intro = looksLikeSourcePath(path)
    ? `files_tree does not take a path and cannot list \`${path}\`.`
    : `files_tree does not take a path; \`${path}\` was not used.`;
  return [
    intro,
    CONFIG_SCOPE,
    "Call files_tree without path to list the config directory. For source code:",
    "",
    "- qdash_list_source_roots {} lists the readable source roots.",
    `- qdash_search_source ${JSON.stringify(searchSourceArguments(path))} lists file paths (narrow query to a file name).`,
    "- qdash_read_source reads one file, for example {\"path\":\"qdash/workflow/engine/task/executor.py\"}.",
  ].join("\n");
}

/** HTTP status of a QDash client error, when it has one. */
export function errorStatus(error: unknown): number | undefined {
  if (!error || typeof error !== "object") return undefined;
  const value = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown } };
  const status = Number(value.statusCode ?? value.status ?? value.response?.status);
  return Number.isFinite(status) ? status : undefined;
}
