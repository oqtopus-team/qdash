"use client";

import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { useControls } from "react-zoom-pan-pinch";

export function GridZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls();

  return (
    <div className="absolute top-2 right-2 z-30 flex flex-col gap-1">
      <button
        onClick={() => zoomIn()}
        className="btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200"
        title="Zoom in"
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        onClick={() => zoomOut()}
        className="btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200"
        title="Zoom out"
      >
        <ZoomOut className="h-4 w-4" />
      </button>
      <button
        onClick={() => resetTransform()}
        className="btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200"
        title="Reset view"
      >
        <Maximize2 className="h-4 w-4" />
      </button>
    </div>
  );
}
