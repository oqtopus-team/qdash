"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

/** Where the execution details panel lives on a desktop viewport. */
export type DetailPanelMode = "docked" | "floating" | "minimized";

export interface WindowRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ViewportSize {
  width: number;
  height: number;
}

/** Viewports at least this wide can float the panel; narrower ones keep the full-width drawer. */
export const FLOATING_PANEL_MEDIA_QUERY = "(min-width: 1024px)";
const FLOATING_MIN_WIDTH = 360;
const FLOATING_MIN_HEIGHT = 280;
const FLOATING_MARGIN = 16;
const DEFAULT_WIDTH = 520;
const DEFAULT_HEIGHT = 720;
// Keeps the default window below the app header.
const DEFAULT_TOP = 72;
const KEYBOARD_STEP = 16;
const KEYBOARD_STEP_LARGE = 64;

const MOTION_DURATION_MS = 180;
const MOTION_EASING = "cubic-bezier(0.2, 0, 0, 1)";

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

/** Fits a window inside the viewport, keeping the minimum size where the viewport allows it. */
export function clampWindowRect(rect: WindowRect, viewport: ViewportSize): WindowRect {
  const maxWidth = Math.max(1, viewport.width - 2 * FLOATING_MARGIN);
  const maxHeight = Math.max(1, viewport.height - 2 * FLOATING_MARGIN);
  const width = Math.min(Math.max(rect.width, FLOATING_MIN_WIDTH), maxWidth);
  const height = Math.min(Math.max(rect.height, FLOATING_MIN_HEIGHT), maxHeight);
  return {
    width,
    height,
    x: clamp(rect.x, FLOATING_MARGIN, viewport.width - width - FLOATING_MARGIN),
    y: clamp(rect.y, FLOATING_MARGIN, viewport.height - height - FLOATING_MARGIN),
  };
}

/** The first floating position: the right side of the viewport, below the app header. */
export function defaultWindowRect(viewport: ViewportSize): WindowRect {
  const width = Math.min(DEFAULT_WIDTH, viewport.width - 2 * FLOATING_MARGIN);
  const height = Math.min(DEFAULT_HEIGHT, viewport.height - DEFAULT_TOP - FLOATING_MARGIN);
  return clampWindowRect(
    { x: viewport.width - width - 2 * FLOATING_MARGIN, y: DEFAULT_TOP, width, height },
    viewport,
  );
}

function readViewport(): ViewportSize {
  return { width: window.innerWidth, height: window.innerHeight };
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

/** Subscribes to a media query; the server snapshot is `false` so SSR renders the narrow layout. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia?.(query);
      list?.addEventListener?.("change", onChange);
      return () => list?.removeEventListener?.("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia?.(query).matches === true,
    () => false,
  );
}

/** Stops any running window animation so the element shows its committed layout at once. */
function cancelWindowAnimations(element: Element | null) {
  element?.getAnimations?.().forEach((animation) => animation.cancel());
}

/**
 * Animates an element into its current layout. With `from`, the element morphs from that
 * rectangle (FLIP); without it, it fades and settles in. A new call cancels the running one, so
 * rapid mode changes stay interruptible, and reduced motion or a missing Web Animations API
 * applies the layout without motion.
 */
export function animateWindowEntry(
  element: HTMLElement | null,
  from: DOMRect | null,
  origin = "top left",
) {
  if (!element || typeof element.animate !== "function" || prefersReducedMotion()) return;
  cancelWindowAnimations(element);
  const to = element.getBoundingClientRect();
  let first: Keyframe;
  if (from && to.width > 0 && to.height > 0) {
    const dx = from.left - to.left;
    const dy = from.top - to.top;
    const sx = from.width / to.width;
    const sy = from.height / to.height;
    first = {
      transformOrigin: "top left",
      transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`,
      opacity: 0.6,
    };
  } else {
    first = { transformOrigin: origin, transform: "translateY(6px) scale(0.98)", opacity: 0 };
  }
  element.animate(
    [first, { transformOrigin: first.transformOrigin, transform: "none", opacity: 1 }],
    {
      duration: MOTION_DURATION_MS,
      easing: MOTION_EASING,
    },
  );
}

type PointerSession = {
  kind: "move" | "resize";
  pointerId: number;
  // The element holding pointer capture, released when the session ends for any reason.
  target: HTMLElement;
  startX: number;
  startY: number;
  origin: WindowRect;
  current: WindowRect;
};

function releaseCapture({ target, pointerId }: PointerSession) {
  try {
    if (target.hasPointerCapture?.(pointerId)) target.releasePointerCapture(pointerId);
  } catch {
    // The pointer is already gone, so there is no capture left to release.
  }
}

/**
 * Geometry of the single floating execution details window: position and size, pointer drag
 * and resize, keyboard nudges, and viewport clamping.
 *
 * Pointer moves write the element's style directly and commit to state on release, so the
 * window tracks the pointer without re-rendering the page on every move. A drag or resize also
 * ends, releasing its capture, when the pointer capture is lost, the viewport resizes, the
 * window stops floating, or the component unmounts, so no stale session can move the window.
 */
export function useFloatingWindowGeometry(
  windowRef: React.RefObject<HTMLElement | null>,
  enabled: boolean,
) {
  const [storedRect, setRect] = useState<WindowRect | null>(null);
  const [interaction, setInteraction] = useState<"move" | "resize" | null>(null);
  const session = useRef<PointerSession | null>(null);
  // The first floating render already has a position, so an opening animation can measure it.
  // Later floats reuse the last position. `enabled` is only true in the browser.
  const rect = storedRect ?? (enabled ? defaultWindowRect(readViewport()) : null);

  // Ends the active drag or resize, keeping where the window got to.
  const finishSession = useCallback(() => {
    const active = session.current;
    if (!active) return;
    // Cleared first, so the `lostpointercapture` that releasing fires finds nothing to end.
    session.current = null;
    releaseCapture(active);
    setRect(clampWindowRect(active.current, readViewport()));
    setInteraction(null);
  }, []);

  // A session must not outlive the floating window: ending it here covers a breakpoint change
  // that docks the window mid-drag, which also removes the handlers that would see the release.
  useEffect(() => {
    if (!enabled) return;
    return finishSession;
  }, [enabled, finishSession]);

  // Commit the position when the window floats, fitted to a viewport that may have changed.
  useEffect(() => {
    if (!enabled) return;
    setRect((current) =>
      current ? clampWindowRect(current, readViewport()) : defaultWindowRect(readViewport()),
    );
  }, [enabled]);

  // Keep the window reachable when the viewport shrinks.
  useEffect(() => {
    if (!enabled) return;
    const handleResize = () => {
      // The drag started against the old viewport, so it ends rather than jumping.
      finishSession();
      setRect((current) => (current ? clampWindowRect(current, readViewport()) : current));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [enabled, finishSession]);

  const applyStyle = useCallback(
    (next: WindowRect) => {
      const element = windowRef.current;
      if (!element) return;
      element.style.left = `${next.x}px`;
      element.style.top = `${next.y}px`;
      element.style.width = `${next.width}px`;
      element.style.height = `${next.height}px`;
    },
    [windowRef],
  );

  const startPointer = useCallback(
    (kind: "move" | "resize", event: React.PointerEvent<HTMLElement>) => {
      if (!rect || event.button !== 0 || session.current) return;
      event.preventDefault();
      // Direct manipulation wins over any running open or dock animation.
      cancelWindowAnimations(windowRef.current);
      event.currentTarget.setPointerCapture?.(event.pointerId);
      session.current = {
        kind,
        pointerId: event.pointerId,
        target: event.currentTarget,
        startX: event.clientX,
        startY: event.clientY,
        origin: rect,
        current: rect,
      };
      setInteraction(kind);
    },
    [rect, windowRef],
  );

  const movePointer = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      const active = session.current;
      if (!active || active.pointerId !== event.pointerId) return;
      const dx = event.clientX - active.startX;
      const dy = event.clientY - active.startY;
      const { origin } = active;
      const viewport = readViewport();
      const next =
        active.kind === "move"
          ? clampWindowRect({ ...origin, x: origin.x + dx, y: origin.y + dy }, viewport)
          : clampWindowRect(
              {
                ...origin,
                width: Math.min(origin.width + dx, viewport.width - origin.x - FLOATING_MARGIN),
                height: Math.min(origin.height + dy, viewport.height - origin.y - FLOATING_MARGIN),
              },
              viewport,
            );
      active.current = next;
      applyStyle(next);
    },
    [applyStyle],
  );

  // Release, cancel, and a lost capture all end the session for that pointer.
  const endPointer = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (session.current?.pointerId !== event.pointerId) return;
      finishSession();
    },
    [finishSession],
  );

  const moveBy = useCallback((dx: number, dy: number) => {
    setRect((stored) => {
      const current = stored ?? defaultWindowRect(readViewport());
      return clampWindowRect({ ...current, x: current.x + dx, y: current.y + dy }, readViewport());
    });
  }, []);

  const resizeBy = useCallback((dw: number, dh: number) => {
    setRect((stored) => {
      const viewport = readViewport();
      const current = stored ?? defaultWindowRect(viewport);
      return clampWindowRect(
        {
          ...current,
          width: Math.min(current.width + dw, viewport.width - current.x - FLOATING_MARGIN),
          height: Math.min(current.height + dh, viewport.height - current.y - FLOATING_MARGIN),
        },
        viewport,
      );
    });
  }, []);

  const reset = useCallback(() => setRect(defaultWindowRect(readViewport())), []);

  const pointerHandlers = (kind: "move" | "resize") => ({
    onPointerDown: (event: React.PointerEvent<HTMLElement>) => startPointer(kind, event),
    onPointerMove: movePointer,
    onPointerUp: endPointer,
    onPointerCancel: endPointer,
    onLostPointerCapture: endPointer,
  });

  return { rect, interaction, pointerHandlers, moveBy, resizeBy, reset };
}

/** Maps an arrow key to a step, larger with Shift; `null` for any other key. */
export function arrowKeyDelta(event: React.KeyboardEvent): { dx: number; dy: number } | null {
  const step = event.shiftKey ? KEYBOARD_STEP_LARGE : KEYBOARD_STEP;
  switch (event.key) {
    case "ArrowLeft":
      return { dx: -step, dy: 0 };
    case "ArrowRight":
      return { dx: step, dy: 0 };
    case "ArrowUp":
      return { dx: 0, dy: -step };
    case "ArrowDown":
      return { dx: 0, dy: step };
    default:
      return null;
  }
}
