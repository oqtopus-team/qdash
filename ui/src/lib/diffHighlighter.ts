import { useSyncExternalStore } from "react";
import { canUseWASM, DEFAULT_THEMES, disposeHighlighter, preloadHighlighter } from "@pierre/diffs";

export type DiffHighlighter = "highlights" | "shiki-js";
let choice: DiffHighlighter | null = null;
let loading: Promise<void> | null = null;
const listeners = new Set<() => void>();

/** No viewer mounts until initialization settles, so a failed shared instance
 * can be disposed safely before any viewer requests the fallback engine. */
async function initialize(): Promise<void> {
  if (canUseWASM()) {
    try {
      await preloadHighlighter({
        themes: Object.values(DEFAULT_THEMES),
        langs: [],
        preferredHighlighter: "highlights",
      });
      choice = "highlights";
    } catch (error) {
      console.warn("Highlights is unavailable for diffs; using Shiki.", error);
      // Theme loading can reject after the shared Highlights instance is cached.
      await disposeHighlighter();
      choice = "shiki-js";
    }
  } else {
    choice = "shiki-js";
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  loading ??= initialize();
  return () => listeners.delete(listener);
}

/** Share one backend choice across viewers; SSR and hydration show a placeholder. */
export function useDiffHighlighter(): DiffHighlighter | null {
  return useSyncExternalStore(
    subscribe,
    () => choice,
    () => null,
  );
}
