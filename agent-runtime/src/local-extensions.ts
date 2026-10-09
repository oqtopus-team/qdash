/**
 * Local pi extension checkouts loaded next to the pinned pi-qdash package.
 *
 * `AGENT_RUNTIME_EXTENSION_PATHS` names package directories (the layout pi
 * installs: a package.json with a `pi` manifest) that are mounted into the
 * runtime container during development, so an extension can be iterated on
 * without publishing it and rebuilding the image.
 *
 * Pure functions only, so they can be tested without a running agent.
 */

import { resolve, sep } from "node:path";

/** Split the colon- or comma-separated environment value into absolute paths. */
export function parseExtensionPaths(value: string | undefined): string[] {
  if (!value) return [];
  return [
    ...new Set(
      value
        .split(/[:,]/)
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0)
        .map((entry) => resolve(entry)),
    ),
  ];
}

/** Whether an extension file lives inside one of the local checkout roots. */
export function isLocalExtension(extensionPath: string, roots: readonly string[]): boolean {
  const resolved = resolve(extensionPath);
  return roots.some((root) => resolved === root || resolved.startsWith(root + sep));
}

/**
 * Tool names provided by local extension checkouts.
 *
 * The pinned pi-qdash package is held to a reviewed allowlist. A checkout the
 * operator mounted deliberately is trusted as a whole instead, so every tool it
 * defines is offered to the model.
 */
export function localToolNames(
  extensions: ReadonlyArray<{ path: string; tools?: ReadonlyMap<string, unknown> }>,
  roots: readonly string[],
): string[] {
  if (roots.length === 0) return [];
  return [
    ...new Set(
      extensions
        .filter((extension) => isLocalExtension(extension.path, roots))
        .flatMap((extension) => [...(extension.tools?.keys() ?? [])]),
    ),
  ];
}
