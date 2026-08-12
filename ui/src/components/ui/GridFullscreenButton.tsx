"use client";

import { Maximize, Minimize } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

interface GridFullscreenButtonProps {
  isFullscreen?: boolean;
  onToggle: () => void;
}

export const gridControlButtonClass =
  "btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200";

export function GridFullscreenButton({ isFullscreen, onToggle }: GridFullscreenButtonProps) {
  const label = isFullscreen ? "Exit fullscreen" : "Fullscreen";
  return (
    <div className="absolute top-2 right-2 z-30">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onToggle}
            className={gridControlButtonClass}
            aria-label={label}
            aria-pressed={isFullscreen ?? false}
          >
            {isFullscreen ? (
              <Minimize className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Maximize className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="left">
          {isFullscreen ? "Exit fullscreen (Esc)" : label}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
