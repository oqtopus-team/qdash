"use client";

import { useEffect, useRef } from "react";

import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { useControls } from "react-zoom-pan-pinch";

import { GridFullscreenButton, gridControlButtonClass } from "@/components/ui/GridFullscreenButton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

interface GridZoomControlsProps {
  isFullscreen?: boolean;
  /** Omit to hide the fullscreen toggle */
  onToggleFullscreen?: () => void;
}

export function GridZoomControls({ isFullscreen, onToggleFullscreen }: GridZoomControlsProps = {}) {
  const { zoomIn, zoomOut, resetTransform } = useControls();

  // Re-center once the panel has finished resizing around the fullscreen toggle.
  const previousFullscreenRef = useRef(isFullscreen);
  useEffect(() => {
    if (previousFullscreenRef.current === isFullscreen) return;
    previousFullscreenRef.current = isFullscreen;
    const timeoutId = window.setTimeout(() => resetTransform(0), 150);
    return () => window.clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFullscreen]);

  return (
    <div className="absolute top-2 right-2 z-30 flex flex-col gap-1">
      {onToggleFullscreen && (
        <>
          <GridFullscreenButton isFullscreen={isFullscreen} onToggle={onToggleFullscreen} inline />
          <div className="h-px bg-base-content/20 mx-1" />
        </>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => zoomIn()}
            className={gridControlButtonClass}
            aria-label="Zoom in"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="left">Zoom in</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => zoomOut()}
            className={gridControlButtonClass}
            aria-label="Zoom out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="left">Zoom out</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => resetTransform()}
            className={gridControlButtonClass}
            aria-label="Reset view"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="left">Reset view</TooltipContent>
      </Tooltip>
    </div>
  );
}
