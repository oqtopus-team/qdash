"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { ChevronLeft, ChevronRight } from "lucide-react";

interface FigureStripProps {
  children: ReactNode;
  /** Classes of the scrolling row itself (height, padding, background). */
  className?: string;
}

interface StripState {
  canScroll: boolean;
  atStart: boolean;
  atEnd: boolean;
  index: number;
  count: number;
}

const INITIAL: StripState = { canScroll: false, atStart: true, atEnd: true, index: 0, count: 0 };

/**
 * A horizontal row of figures that says so: when the row overflows it shows previous and next
 * buttons, a position such as "2 / 3", and a fade on the hidden side, so nobody has to guess that
 * more figures sit to the right. With one figure, or room for all, it is a plain row.
 */
export function FigureStrip({ children, className = "" }: FigureStripProps) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<StripState>(INITIAL);

  const measure = useCallback(() => {
    const row = rowRef.current;
    if (!row) return;
    const items = Array.from(row.children) as HTMLElement[];
    const canScroll = row.scrollWidth > row.clientWidth + 1;
    const atStart = row.scrollLeft <= 1;
    const atEnd = row.scrollLeft + row.clientWidth >= row.scrollWidth - 1;
    // The current figure is the first one whose middle is past the scrolled-away part.
    let index = 0;
    for (let i = 0; i < items.length; i += 1) {
      if (items[i].offsetLeft + items[i].offsetWidth / 2 > row.scrollLeft) {
        index = i;
        break;
      }
    }
    setState({ canScroll, atStart, atEnd, index, count: items.length });
  }, []);

  useEffect(() => {
    const row = rowRef.current;
    if (!row) return;
    measure();
    row.addEventListener("scroll", measure, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(row);
    for (const item of Array.from(row.children)) observer?.observe(item);
    return () => {
      row.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [measure, children]);

  const step = (direction: -1 | 1) => {
    const row = rowRef.current;
    if (!row) return;
    const items = Array.from(row.children) as HTMLElement[];
    const target = items[Math.min(items.length - 1, Math.max(0, state.index + direction))];
    if (target) row.scrollTo({ left: target.offsetLeft, behavior: "smooth" });
  };

  return (
    <div className="relative">
      <div ref={rowRef} className={`flex items-center overflow-x-auto ${className}`}>
        {children}
      </div>
      {state.canScroll && (
        <>
          {!state.atEnd && (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-base-100 to-transparent"
            />
          )}
          {!state.atStart && (
            <button
              type="button"
              aria-label="Previous figure"
              onClick={() => step(-1)}
              className="btn btn-circle btn-sm absolute left-2 top-1/2 -translate-y-1/2 border-base-300 bg-base-100 shadow-none"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}
          {!state.atEnd && (
            <button
              type="button"
              aria-label="Next figure"
              onClick={() => step(1)}
              className="btn btn-circle btn-sm absolute right-2 top-1/2 -translate-y-1/2 border-base-300 bg-base-100 shadow-none"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          )}
          <span
            aria-live="polite"
            className="absolute bottom-2 right-2 rounded border border-base-300 bg-base-100 px-1.5 py-0.5 font-mono text-xs text-base-content/70"
          >
            {state.index + 1} / {state.count}
          </span>
        </>
      )}
    </div>
  );
}
