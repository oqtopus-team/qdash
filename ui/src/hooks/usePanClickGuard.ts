"use client";

import { useMemo, useRef } from "react";

import type { HTMLAttributes, MouseEvent } from "react";

/** Pointer travel in CSS pixels beyond which a press counts as a drag, not a click. */
const DRAG_THRESHOLD_PX = 5;

type PanClickGuardHandlers = Pick<
  HTMLAttributes<HTMLDivElement>,
  "onPointerDownCapture" | "onPointerMoveCapture" | "onClickCapture"
>;

interface PointerPress {
  x: number;
  y: number;
  dragged: boolean;
}

/** Marks the press as a drag once the pointer has travelled past the threshold. */
function trackPointerTravel(press: PointerPress | null, event: MouseEvent): void {
  if (!press) return;
  if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > DRAG_THRESHOLD_PX) {
    press.dragged = true;
  }
}

/**
 * Capture-phase handlers that stop the click ending a pan from reaching the content beneath it.
 *
 * Pan/zoom content tracks the pointer, so mouseup lands on the mousedown element and the browser
 * fires click. Pointer events give mouse, pen and touch one code path; travel is tracked during
 * the press so a drag that returns to its start is still a drag.
 */
export function usePanClickGuard(): PanClickGuardHandlers {
  const pressRef = useRef<PointerPress | null>(null);

  return useMemo(
    () => ({
      onPointerDownCapture: (event) => {
        pressRef.current = { x: event.clientX, y: event.clientY, dragged: false };
      },
      onPointerMoveCapture: (event) => {
        trackPointerTravel(pressRef.current, event);
      },
      onClickCapture: (event) => {
        // Keyboard activation reports detail 0 and has no press of its own to compare against.
        if (event.detail === 0) return;

        trackPointerTravel(pressRef.current, event);
        const dragged = pressRef.current?.dragged ?? false;
        pressRef.current = null;

        if (dragged) {
          event.stopPropagation();
          event.preventDefault();
        }
      },
    }),
    [],
  );
}
