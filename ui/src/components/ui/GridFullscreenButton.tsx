"use client";

import { Maximize, Minimize } from "lucide-react";

interface GridFullscreenButtonProps {
  isFullscreen?: boolean;
  onToggle: () => void;
  /** Render without the floating wrapper, e.g. inside GridZoomControls */
  inline?: boolean;
}

export const gridControlButtonClass =
  "btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200";

export function GridFullscreenButton({
  isFullscreen,
  onToggle,
  inline = false,
}: GridFullscreenButtonProps) {
  const button = (
    <button
      onClick={onToggle}
      className={gridControlButtonClass}
      title={isFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
      aria-label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
      aria-pressed={isFullscreen ?? false}
    >
      {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
    </button>
  );

  if (inline) return button;

  return <div className="absolute top-2 right-2 z-30">{button}</div>;
}
