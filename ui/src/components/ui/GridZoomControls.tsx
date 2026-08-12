"use client";

import { useEffect, useRef } from "react";

import { Maximize, Maximize2, Minimize, ZoomIn, ZoomOut } from "lucide-react";
import { useControls } from "react-zoom-pan-pinch";

interface GridZoomControlsProps {
  isFullscreen?: boolean;
  /** Omit to hide the fullscreen toggle */
  onToggleFullscreen?: () => void;
}

export function GridZoomControls({ isFullscreen, onToggleFullscreen }: GridZoomControlsProps = {}) {
  const { zoomIn, zoomOut, resetTransform } = useControls();
  const buttonClass = "btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200";

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
          <button
            onClick={onToggleFullscreen}
            className={buttonClass}
            title={isFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
            aria-pressed={isFullscreen}
          >
            {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
          </button>
          <div className="h-px bg-base-content/20 mx-1" />
        </>
      )}
      <button onClick={() => zoomIn()} className={buttonClass} title="Zoom in">
        <ZoomIn className="h-4 w-4" />
      </button>
      <button onClick={() => zoomOut()} className={buttonClass} title="Zoom out">
        <ZoomOut className="h-4 w-4" />
      </button>
      <button onClick={() => resetTransform()} className={buttonClass} title="Reset view">
        <Maximize2 className="h-4 w-4" />
      </button>
    </div>
  );
}
