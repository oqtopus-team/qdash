import { act, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

/**
 * Just enough layout for react-grid-layout to run in jsdom, which has none: a content width
 * that a test can change through ResizeObserver, offset parents, and element rectangles that
 * follow the grid's CSS transforms. The library itself is real; only the browser's geometry
 * is supplied.
 */

/** One grid column plus its gap, in px, at a 1200 px content width (12 columns, 16 px gaps). */
export const COLUMN_PITCH = (1200 - 11 * 16) / 12 + 16;
/** One grid row (120 px) plus its gap. */
export const ROW_PITCH = 120 + 16;

const TRANSLATE = /translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)/;

export function installGridEnvironment(initialWidth = 1200) {
  let width = initialWidth;
  const observers = new Set<{ callback: ResizeObserverCallback; observer: ResizeObserver }>();

  class ControlledResizeObserver implements ResizeObserver {
    private readonly entry: { callback: ResizeObserverCallback; observer: ResizeObserver };
    constructor(callback: ResizeObserverCallback) {
      this.entry = { callback, observer: this };
    }
    observe() {
      observers.add(this.entry);
    }
    unobserve() {
      observers.delete(this.entry);
    }
    disconnect() {
      observers.delete(this.entry);
    }
  }

  const originalObserver = globalThis.ResizeObserver;
  globalThis.ResizeObserver = ControlledResizeObserver;

  const offsetParent = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetParent");
  Object.defineProperty(HTMLElement.prototype, "offsetParent", {
    configurable: true,
    get(this: HTMLElement) {
      return this.parentElement;
    },
  });

  const rect = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
    this: Element,
  ) {
    const match = this instanceof HTMLElement ? TRANSLATE.exec(this.style.transform) : null;
    const left = match ? Number(match[1]) : 0;
    const top = match ? Number(match[2]) : 0;
    return {
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top,
      width,
      height: 0,
      toJSON: () => ({}),
    } as DOMRect;
  });

  return {
    /** Change the content width, as when the Agent sidebar opens or the window narrows. */
    resizeTo(next: number) {
      width = next;
      act(() => {
        for (const { callback, observer } of observers) {
          callback(
            [{ contentRect: { width: next, height: 0 } } as unknown as ResizeObserverEntry],
            observer,
          );
        }
      });
    },
    restore() {
      globalThis.ResizeObserver = originalObserver;
      if (offsetParent) Object.defineProperty(HTMLElement.prototype, "offsetParent", offsetParent);
      rect.mockRestore();
    },
  };
}

/** Press on `element`, move the pointer by `dx`, `dy` px in steps, and release. */
export function pointerDrag(element: Element, dx: number, dy: number) {
  const start = { clientX: 10, clientY: 10 };
  act(() => {
    fireEvent.mouseDown(element, start);
  });
  const steps = 4;
  for (let step = 1; step <= steps; step += 1) {
    act(() => {
      fireEvent.mouseMove(document, {
        clientX: start.clientX + (dx * step) / steps,
        clientY: start.clientY + (dy * step) / steps,
      });
    });
  }
  act(() => {
    fireEvent.mouseUp(document, { clientX: start.clientX + dx, clientY: start.clientY + dy });
  });
}
