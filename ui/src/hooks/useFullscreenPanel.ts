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

// Layers that want the next Escape, innermost last. A fullscreen panel and a slide-over
// preview opened on top of it each take one Escape in turn instead of both closing at once.
const escapeLayers: Array<() => void> = [];
let scrollLocks = 0;
let previousOverflow = "";

function handleKeyDown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (document.querySelector('dialog[open], .modal-open, [role="dialog"][data-state="open"]'))
    return;
  escapeLayers[escapeLayers.length - 1]?.();
}

function pushEscapeLayer(onEscape: () => void) {
  if (escapeLayers.length === 0) {
    window.addEventListener("keydown", handleKeyDown, { capture: true });
  }
  escapeLayers.push(onEscape);

  return () => {
    const index = escapeLayers.lastIndexOf(onEscape);
    if (index === -1) return;
    escapeLayers.splice(index, 1);
    if (escapeLayers.length === 0) {
      window.removeEventListener("keydown", handleKeyDown, { capture: true });
    }
  };
}

function lockScroll() {
  if (scrollLocks === 0) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  scrollLocks += 1;

  return () => {
    scrollLocks -= 1;
    if (scrollLocks === 0) {
      document.body.style.overflow = previousOverflow;
      previousOverflow = "";
    }
  };
}

/**
 * Let an open layer (a slide-over, a preview) take the next Escape ahead of any layer opened
 * before it, including a fullscreen panel.
 */
export function useEscapeLayer(active: boolean, onEscape: () => void): void {
  useEffect(() => {
    if (!active) return;
    return pushEscapeLayer(onEscape);
  }, [active, onEscape]);
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
    const unlockScroll = lockScroll();
    const popEscapeLayer = pushEscapeLayer(exitFullscreen);
    return () => {
      popEscapeLayer();
      unlockScroll();
    };
  }, [isFullscreen, exitFullscreen]);

  return { isFullscreen, toggleFullscreen, exitFullscreen };
}
