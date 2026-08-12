"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { TransformWrapper, TransformComponent, useControls } from "react-zoom-pan-pinch";
import { X, ZoomIn, ZoomOut, Maximize2, LineChart, Image } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

const PlotlyRenderer = dynamic(
  () => import("@/components/charts/PlotlyRenderer").then((mod) => mod.PlotlyRenderer),
  { ssr: false },
);

interface FigureLightboxProps {
  src: string;
  alt?: string;
  jsonFigurePath?: string;
  onClose: () => void;
}

function LightboxControls({
  onClose,
  jsonFigurePath,
  isInteractive,
  onToggleInteractive,
}: {
  onClose: () => void;
  jsonFigurePath?: string;
  isInteractive: boolean;
  onToggleInteractive: () => void;
}) {
  const { zoomIn, zoomOut, resetTransform } = useControls();
  return (
    <div className="absolute top-4 right-4 z-50 flex gap-2">
      {jsonFigurePath && (
        <button
          type="button"
          onClick={onToggleInteractive}
          className="btn btn-sm bg-base-100/90 shadow-lg hover:bg-base-200 gap-1"
          title={isInteractive ? "Static View" : "Interactive View"}
          aria-label={isInteractive ? "Switch to static view" : "Switch to interactive view"}
        >
          {isInteractive ? (
            <>
              <Image className="h-4 w-4" />
              <span className="text-xs">Static</span>
            </>
          ) : (
            <>
              <LineChart className="h-4 w-4" />
              <span className="text-xs">Interactive</span>
            </>
          )}
        </button>
      )}
      {!isInteractive && (
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => zoomIn()}
                className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
                aria-label="Zoom in"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Zoom in</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => zoomOut()}
                className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
                aria-label="Zoom out"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Zoom out</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => resetTransform()}
                className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
                aria-label="Reset zoom"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Reset zoom</TooltipContent>
          </Tooltip>
        </>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-sm btn-circle bg-base-100/90 shadow-lg hover:bg-base-200"
            aria-label="Close figure"
          >
            <X className="h-4 w-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">Close figure</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function FigureLightbox({ src, alt, jsonFigurePath, onClose }: FigureLightboxProps) {
  const [isInteractive, setIsInteractive] = useState(false);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="h-[calc(100dvh-2rem)] max-h-none max-w-none overflow-hidden rounded-2xl bg-neutral/95 p-0">
        <DialogTitle className="sr-only">Figure preview</DialogTitle>
        <DialogDescription className="sr-only">
          Expanded figure with pan, zoom, and optional interactive controls.
        </DialogDescription>
        <TransformWrapper
          initialScale={1}
          minScale={0.5}
          maxScale={5}
          wheel={{ step: 0.1 }}
          doubleClick={{ mode: "zoomIn", step: 0.7 }}
          disabled={isInteractive}
        >
          <LightboxControls
            onClose={onClose}
            jsonFigurePath={jsonFigurePath}
            isInteractive={isInteractive}
            onToggleInteractive={() => setIsInteractive((v) => !v)}
          />
          {isInteractive && jsonFigurePath ? (
            <div className="flex h-full w-full items-center justify-center">
              <div className="max-h-[90%] max-w-[90%] overflow-auto rounded-xl bg-base-100 p-4 shadow-lg">
                <PlotlyRenderer
                  fullPath={`/api/executions/figure?path=${encodeURIComponent(jsonFigurePath)}`}
                />
              </div>
            </div>
          ) : (
            <TransformComponent
              wrapperStyle={{ width: "100%", height: "100%" }}
              contentStyle={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- pan/zoom relies on native image sizing */}
              <img
                src={src}
                alt={alt || "Figure"}
                className="max-h-[90%] max-w-[90%] object-contain"
              />
            </TransformComponent>
          )}
        </TransformWrapper>
      </DialogContent>
    </Dialog>
  );
}
