"use client";

import { useCallback, useEffect, useState } from "react";

interface UseFullscreenPanelResult {
  /** Whether the panel is currently expanded to a fullscreen overlay */
  isFullscreen: boolean;
  /** Toggle the fullscreen overlay */
  toggleFullscreen: () => void;
  /** Leave the fullscreen overlay */
  exitFullscreen: () => void;
}

const openPanels: Array<() => void> = [];
let previousOverflow = "";

function handleKeyDown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (document.querySelector('dialog[open], .modal-open, [role="dialog"][data-state="open"]'))
    return;
  openPanels[openPanels.length - 1]?.();
}

function openPanel(exit: () => void) {
  if (openPanels.length === 0) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown, { capture: true });
  }
  openPanels.push(exit);

  return () => {
    const index = openPanels.lastIndexOf(exit);
    if (index === -1) return;
    openPanels.splice(index, 1);
    if (openPanels.length === 0) {
      document.body.style.overflow = previousOverflow;
      previousOverflow = "";
      window.removeEventListener("keydown", handleKeyDown, { capture: true });
    }
  };
}

/**
 * Fullscreen overlay state for grid panels.
 *
 * Uses a CSS overlay rather than the native Fullscreen API so that modals
 * rendered outside the panel subtree stay visible.
 */
export function useFullscreenPanel(): UseFullscreenPanelResult {
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => setIsFullscreen((prev) => !prev), []);
  const exitFullscreen = useCallback(() => setIsFullscreen(false), []);

  useEffect(() => {
    if (!isFullscreen) return;
    return openPanel(exitFullscreen);
  }, [isFullscreen, exitFullscreen]);

  return { isFullscreen, toggleFullscreen, exitFullscreen };
}
