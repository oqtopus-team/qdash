/**
 * Extensions trusted as a whole, next to the allowlisted pi-qdash package.
 *
 * Two sources qualify. Local checkouts: package directories (the layout pi
 * installs: a package.json with a `pi` manifest) placed under
 * `agent-runtime/extensions/`, which compose mounts into the runtime container,
 * so an extension can be iterated on without publishing it and rebuilding the
 * image. Installed packages: `TRUSTED_EXTENSION_PACKAGES` names pi packages the
 * image installs at a pinned version, so the same extension runs in production.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve, sep } from "node:path";

/** A local checkout found under the extensions mount. */
export interface ExtensionCheckout {
  /** Absolute package directory, passed to pi as an extension path. */
  path: string;
  /** The package name from its manifest, or null when it has none. */
  name: string | null;
}

/**
 * Package directories under `dir` that carry a pi manifest, sorted by path.
 *
 * An empty or missing directory (production, or a clone without checkouts)
 * yields nothing; a directory without a `pi` manifest is ignored rather than
 * failing startup, since the mount may hold unrelated files.
 */
export function discoverExtensionCheckouts(dir: string): ExtensionCheckout[] {
  if (!existsSync(dir)) return [];
  const checkouts: ExtensionCheckout[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory() && !entry.isSymbolicLink()) continue;
    const root = join(dir, entry.name);
    const manifest = join(root, "package.json");
    if (!existsSync(manifest)) continue;
    try {
      const parsed: unknown = JSON.parse(readFileSync(manifest, "utf8"));
      if (typeof parsed !== "object" || parsed === null || !("pi" in parsed)) continue;
      const name = (parsed as { name?: unknown }).name;
      checkouts.push({ path: resolve(root), name: typeof name === "string" ? name : null });
    } catch {
      // Not a package manifest; skip the directory.
    }
  }
  return checkouts.sort((a, b) => a.path.localeCompare(b.path));
}

/**
 * Checkouts trusted as a whole: every checkout except those of packages that
 * keep a per-name allowlist (pi-qdash). Such a checkout still loads and
 * replaces the pinned copy, so it can be developed in place, but its tools
 * pass the same review gate as in production.
 */
export function trustedCheckoutRoots(
  checkouts: ReadonlyArray<ExtensionCheckout>,
  allowlistedPackages: readonly string[],
): string[] {
  return checkouts
    .filter((checkout) => checkout.name === null || !allowlistedPackages.includes(checkout.name))
    .map((checkout) => checkout.path);
}

/**
 * How to report one pi extension load error.
 *
 * pi loads the checkouts before the installed packages and rejects an installed
 * extension whose tool name a checkout already defines. That conflict is the
 * intended replacement, not a fault, so it is reported as such.
 */
export function describeExtensionError(
  path: string,
  error: string,
  checkoutPaths: readonly string[],
): { level: "info" | "error"; message: string } {
  const replacement = /conflicts with (\S+)/.exec(error);
  const by = replacement?.[1];
  if (by && isLocalExtension(by, checkoutPaths) && !isLocalExtension(path, checkoutPaths)) {
    return { level: "info", message: `[agent-runtime] local checkout ${by} replaces installed ${path}` };
  }
  return { level: "error", message: `[agent-runtime] extension ${path}: ${error}` };
}

/** Whether an extension file lives inside one of the local checkout roots. */
export function isLocalExtension(extensionPath: string, roots: readonly string[]): boolean {
  const resolved = resolve(extensionPath);
  return roots.some((root) => resolved === root || resolved.startsWith(root + sep));
}

/**
 * Whether an extension file belongs to one of the named installed packages.
 *
 * pi installs npm packages under its agent directory's `node_modules`, so the
 * package name (scope included) appears as path segments right after a
 * `node_modules` segment, e.g. `/app/.pi-agent/npm/node_modules/@scope/name/extensions/x.ts`.
 */
export function isInstalledPackage(extensionPath: string, packages: readonly string[]): boolean {
  if (packages.length === 0) return false;
  const normalized = resolve(extensionPath).split(sep).join("/");
  return packages.some((name) => normalized.includes(`/node_modules/${name}/`));
}

/** Whether an extension is trusted as a whole: a local checkout or a listed package. */
export function isTrustedExtension(
  extensionPath: string,
  roots: readonly string[],
  packages: readonly string[] = [],
): boolean {
  return isLocalExtension(extensionPath, roots) || isInstalledPackage(extensionPath, packages);
}

/**
 * System-prompt lines for the tools of trusted extensions.
 *
 * pi-qdash's routing guide comes from its `qdash` skill (tool-guide.ts), which
 * knows nothing about other extensions. Their tools describe themselves with
 * pi's `promptSnippet`/`promptGuidelines`, so those are inlined instead.
 */
export function buildLocalToolGuide(
  extensions: ReadonlyArray<{
    path: string;
    tools?: ReadonlyMap<
      string,
      { definition: { description: string; promptSnippet?: string; promptGuidelines?: string[] } }
    >;
  }>,
  roots: readonly string[],
  enabledTools: ReadonlySet<string>,
  packages: readonly string[] = [],
): string | null {
  const lines: string[] = [];
  for (const extension of extensions) {
    if (!isTrustedExtension(extension.path, roots, packages)) continue;
    for (const [name, { definition }] of extension.tools ?? []) {
      if (!enabledTools.has(name)) continue;
      lines.push(`- \`${name}\`: ${definition.promptSnippet ?? definition.description}`);
      for (const guideline of definition.promptGuidelines ?? []) lines.push(`  - ${guideline}`);
    }
  }
  return lines.length ? lines.join("\n") : null;
}

/** Tool names provided by trusted extensions, for logging and the tool list. */
export function localToolNames(
  extensions: ReadonlyArray<{ path: string; tools?: ReadonlyMap<string, unknown> }>,
  roots: readonly string[],
  packages: readonly string[] = [],
): string[] {
  if (roots.length === 0 && packages.length === 0) return [];
  return [
    ...new Set(
      extensions
        .filter((extension) => isTrustedExtension(extension.path, roots, packages))
        .flatMap((extension) => [...(extension.tools?.keys() ?? [])]),
    ),
  ];
}
