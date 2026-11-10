import { useSyncExternalStore } from "react";

/**
 * Avatar ETags saved in this tab, keyed by username.
 *
 * Saving an avatar records its ETag here so every `UserAvatar` of that user requests the new
 * image at once instead of reusing the image the browser already decoded.
 */
const versions = new Map<string, string>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setAvatarVersion(username: string, etag: string): void {
  if (versions.get(username) === etag) return;
  versions.set(username, etag);
  for (const listener of listeners) listener();
}

export function useAvatarVersion(username: string): string | null {
  return useSyncExternalStore(
    subscribe,
    () => versions.get(username) ?? null,
    () => null,
  );
}
