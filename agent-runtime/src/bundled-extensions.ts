/**
 * The pi packages the Agent Runtime loads: the pi-qdash and pi-qcaleval
 * sources built into its image, and nothing else.
 *
 * pi-qdash keeps a per-tool allowlist; pi-qcaleval is trusted by its bundled
 * root. The runtime's resource loader reads no pi settings, installed packages,
 * or auto-discovered extension and skill directories, so the tools and skills
 * of a chat are always the ones of the image. A standalone pi installation
 * keeps its own settings and is not affected.
 */

import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";

import { DefaultResourceLoader, SettingsManager } from "@earendil-works/pi-coding-agent";

/** A pi package bundled into the runtime image. */
export interface BundledExtension {
  /** Absolute package directory, passed to pi as an extension path. */
  path: string;
  /** The package name from its manifest. */
  name: string;
}

/** Bundled packages are explicit; arbitrary directories in packages/ never become tools. */
export function bundledExtensions(packagesDir: string): BundledExtension[] {
  const expected = new Map([
    ["pi-qdash", "@oqtopus-team/pi-qdash"],
    ["pi-qcaleval", "@oqtopus-team/pi-qcaleval"],
  ]);
  return [...expected].map(([directory, name]) => {
    const path = resolve(packagesDir, directory);
    const manifest = JSON.parse(readFileSync(join(path, "package.json"), "utf8"));
    if (manifest.name !== name || !manifest.pi?.extensions?.length) {
      throw new Error(`Invalid bundled extension: ${path}`);
    }
    return { path, name };
  });
}

/**
 * A resource loader that loads only the bundled packages and their skills.
 *
 * In-memory settings keep pi from reading or installing the packages of a
 * `settings.json`, and `noExtensions`/`noSkills` drop the extensions and skills
 * pi would otherwise discover under the agent and working directories. The
 * packages passed as extension paths still contribute the skills their
 * manifests declare.
 */
export function createBundledResourceLoader(options: {
  cwd: string;
  agentDir: string;
  bundled: readonly BundledExtension[];
}): DefaultResourceLoader {
  return new DefaultResourceLoader({
    cwd: options.cwd,
    agentDir: options.agentDir,
    settingsManager: SettingsManager.inMemory(),
    additionalExtensionPaths: options.bundled.map(({ path }) => path),
    noExtensions: true,
    noSkills: true,
  });
}

/** Identify the source and locked dependencies even in images without git metadata. */
export function bundledSourceVersion(root: string, version: string): string {
  const hash = createHash("sha256");
  const add = (relative: string) => {
    const path = join(root, relative);
    if (!existsSync(path)) return;
    if (statSync(path).isDirectory()) {
      for (const name of readdirSync(path).sort()) add(`${relative}/${name}`);
    } else {
      hash.update(relative).update("\0").update(readFileSync(path)).update("\0");
    }
  };
  for (const path of ["package.json", "extensions", "skills", "../../bun.lock"]) add(path);
  return `${version}+source.${hash.digest("hex").slice(0, 16)}`;
}

/**
 * Bundled roots trusted as a whole: every bundled package except those that
 * keep a per-name allowlist (pi-qdash), whose tools pass the reviewed list.
 */
export function trustedBundleRoots(
  bundled: ReadonlyArray<BundledExtension>,
  allowlistedPackages: readonly string[],
): string[] {
  return bundled
    .filter((extension) => !allowlistedPackages.includes(extension.name))
    .map((extension) => extension.path);
}

/** Whether an extension file lives inside one of the trusted roots. */
export function isTrustedExtension(extensionPath: string, roots: readonly string[]): boolean {
  const resolved = resolve(extensionPath);
  return roots.some((root) => resolved === root || resolved.startsWith(root + sep));
}

/** The package an extension file belongs to, as recorded with an evaluation. */
export interface ExtensionPackage {
  name: string;
  /** The manifest version, with the bundled source hash for a bundled package. */
  version: string;
  source: "package";
}

/** The nearest package manifest above an extension file. */
export function extensionPackage(
  extensionPath: string,
  bundledRoots: readonly string[] = [],
): ExtensionPackage | undefined {
  let dir = dirname(resolve(extensionPath));
  for (;;) {
    const manifest = join(dir, "package.json");
    if (existsSync(manifest)) {
      try {
        const parsed = JSON.parse(readFileSync(manifest, "utf8")) as {
          name?: unknown;
          version?: unknown;
        };
        if (typeof parsed.name === "string") {
          const version = typeof parsed.version === "string" ? parsed.version : "unknown";
          return {
            name: parsed.name,
            version: isTrustedExtension(extensionPath, bundledRoots)
              ? bundledSourceVersion(dir, version)
              : version,
            source: "package",
          };
        }
      } catch {
        // Not a readable manifest; keep looking upwards.
      }
    }
    const parent = dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
}

/**
 * One startup line per bundled package: name, source version, path, trust,
 * and the tools and skills it contributed, so a running runtime shows which
 * build of each package it serves.
 */
export function describeBundledExtensions(
  bundled: ReadonlyArray<BundledExtension>,
  trustedRoots: readonly string[],
  extensions: ReadonlyArray<{ path: string; tools?: ReadonlyMap<string, unknown> }>,
  skills: ReadonlyArray<{ name: string; filePath: string }>,
): string[] {
  return bundled.map(({ path, name }) => {
    const within = (file: string) => isTrustedExtension(file, [path]);
    const tools = extensions.filter((extension) => within(extension.path))
      .flatMap((extension) => [...(extension.tools?.keys() ?? [])]);
    const skillNames = skills.filter((skill) => within(skill.filePath)).map((skill) => skill.name);
    const version = extensionPackage(join(path, "package.json"), [path])?.version ?? "unknown";
    const trust = trustedRoots.includes(path) ? "trusted" : "allowlisted";
    return `[agent-runtime] bundled extension ${name}@${version} (${path}, ${trust}): ${tools.length} tools, skills: ${skillNames.join(", ") || "none"}`;
  });
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
): string | null {
  const lines: string[] = [];
  for (const extension of extensions) {
    if (!isTrustedExtension(extension.path, roots)) continue;
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
): string[] {
  if (roots.length === 0) return [];
  return [
    ...new Set(
      extensions
        .filter((extension) => isTrustedExtension(extension.path, roots))
        .flatMap((extension) => [...(extension.tools?.keys() ?? [])]),
    ),
  ];
}
