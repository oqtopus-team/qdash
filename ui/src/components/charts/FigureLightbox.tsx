"use client";

import React, { useCallback, useEffect } from "react";
import {
  TransformWrapper,
  TransformComponent,
  useControls,
} from "react-zoom-pan-pinch";
import { X, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";

interface FigureLightboxProps {
  src: string;
  alt?: string;
  onClose: () => void;
}

function LightboxControls({ onClose }: { onClose: () => void }) {
  const { zoomIn, zoomOut, resetTransform } = useControls();
  return (
    <div className="absolute top-4 right-4 z-50 flex gap-2">
      <button
        onClick={() => zoomIn()}
        className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
        title="Zoom in"
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        onClick={() => zoomOut()}
        className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
        title="Zoom out"
      >
        <ZoomOut className="h-4 w-4" />
      </button>
      <button
        onClick={() => resetTransform()}
        className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
        title="Reset zoom"
      >
        <Maximize2 className="h-4 w-4" />
      </button>
      <button
        onClick={onClose}
        className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
        title="Close"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function FigureLightbox({ src, alt, onClose }: FigureLightboxProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <TransformWrapper
        initialScale={1}
        minScale={0.5}
        maxScale={5}
        wheel={{ step: 0.1 }}
        doubleClick={{ mode: "zoomIn", step: 0.7 }}
      >
        <LightboxControls onClose={onClose} />
        <TransformComponent
          wrapperStyle={{
            width: "100vw",
            height: "100vh",
          }}
          contentStyle={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <img
            src={src}
            alt={alt || "Figure"}
            className="max-w-[90vw] max-h-[90vh] object-contain"
          />
        </TransformComponent>
      </TransformWrapper>
    </div>
  );
}
