import type { ReactNode } from "react";

interface LockedGridScrollerProps {
  children: ReactNode;
}

/**
 * Scroll container for a grid shown in the locked view. The locked grid keeps its default cell
 * size, so a grid wider or taller than the panel scrolls instead of clipping cells. The content
 * stays centered while it fits and starts at the top-left edge once it overflows. Render the
 * fullscreen button outside this container so it does not scroll with the grid.
 */
export function LockedGridScroller({ children }: LockedGridScrollerProps) {
  return (
    <div className="min-w-0 min-h-0 flex-1 self-stretch overflow-auto flex justify-center-safe items-start">
      {children}
    </div>
  );
}
