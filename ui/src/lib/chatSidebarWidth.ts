/**
 * The docked chat sidebar's width on large screens, dragged by its left edge
 * and remembered per browser. Below the `lg` breakpoint the sidebar covers the
 * screen and the width does not apply.
 */

const STORAGE_KEY = "qdash_chat_sidebar_width";

export const DEFAULT_SIDEBAR_WIDTH = 448; // 28rem, the width before it was adjustable
export const MIN_SIDEBAR_WIDTH = 320;
/** Never wider than this, nor than 60% of the window, so the page stays usable. */
const MAX_SIDEBAR_WIDTH = 960;

export function maxSidebarWidth(windowWidth: number): number {
  return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, Math.floor(windowWidth * 0.6)));
}

export function clampSidebarWidth(width: number, windowWidth: number): number {
  if (!Number.isFinite(width)) return DEFAULT_SIDEBAR_WIDTH;
  return Math.min(maxSidebarWidth(windowWidth), Math.max(MIN_SIDEBAR_WIDTH, Math.round(width)));
}

export function getStoredSidebarWidth(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const value = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function setStoredSidebarWidth(width: number): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, String(Math.round(width)));
  } catch {
    // Remembering the width is a convenience; the drag still applies.
  }
}

export function clearStoredSidebarWidth(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear.
  }
}
