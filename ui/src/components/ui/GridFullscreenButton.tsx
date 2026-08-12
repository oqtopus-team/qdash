"use client";

import { Maximize, Minimize } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

interface GridFullscreenButtonProps {
  /** Current fullscreen state, from useFullscreenPanel */
  isFullscreen?: boolean;
  /** Enter or leave fullscreen */
  onToggle: () => void;
  /** Render without the floating wrapper, e.g. inside GridZoomControls */
  inline?: boolean;
}

export const gridControlButtonClass =
  "btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200";

/**
 * Fullscreen toggle for grid panels, shared by the region and pan/zoom views
 */
export function GridFullscreenButton({
  isFullscreen,
  onToggle,
  inline = false,
}: GridFullscreenButtonProps) {
  const label = isFullscreen ? "Exit fullscreen" : "Fullscreen";
  const button = (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onToggle}
          className={gridControlButtonClass}
          aria-label={label}
          aria-pressed={isFullscreen ?? false}
        >
          {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
        </button>
      </TooltipTrigger>
      <TooltipContent side="left">{isFullscreen ? "Exit fullscreen (Esc)" : label}</TooltipContent>
    </Tooltip>
  );

  if (inline) return button;

  return <div className="absolute top-2 right-2 z-30">{button}</div>;
}
