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

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // An open modal owns Escape first.
      if (document.querySelector("dialog[open], .modal-open")) return;
      setIsFullscreen(false);
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isFullscreen]);

  return { isFullscreen, toggleFullscreen, exitFullscreen };
}
