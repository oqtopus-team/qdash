import { flushSync } from "react-dom";

type DocumentWithViewTransition = Document & {
  startViewTransition?: (update: () => void) => unknown;
};

/** True when the browser can animate between two DOM states and the user wants motion. */
export function canViewTransition(doc: Document = document, win: Window = window): boolean {
  if (typeof (doc as DocumentWithViewTransition).startViewTransition !== "function") return false;
  return !win.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Apply a state update as a view transition: elements that carry the same
 * `view-transition-name` before and after morph between their two places
 * (the QDash mark and the composer when the first message is sent), and the
 * rest cross-fades. Without browser support, or with reduced motion, the
 * update is applied directly.
 *
 * The update runs inside `flushSync` so the new DOM is in place when the
 * browser takes its "after" snapshot.
 */
export function withViewTransition(update: () => void): void {
  if (typeof document === "undefined" || !canViewTransition()) {
    update();
    return;
  }
  (document as DocumentWithViewTransition).startViewTransition!(() => {
    flushSync(update);
  });
}
