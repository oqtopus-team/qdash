"use client";

import { useCallback, useRef } from "react";
import { Copy, RotateCcw, X, ZoomIn, ZoomOut } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { resetDiagram, startDiagramPan, zoomDiagram, ZOOM_STEP } from "@/lib/chatMermaidView";
import { copyText } from "@/lib/utils/clipboard";

export interface ChatMermaidDiagram {
  /** Sanitized SVG from `renderMermaid`. */
  svg: string;
  source: string;
}

interface ChatMermaidDialogProps {
  diagram: ChatMermaidDiagram | null;
  onClose: () => void;
}

/** A diagram from an answer at full size, with wheel zoom and drag to pan. */
export function ChatMermaidDialog({ diagram, onClose }: ChatMermaidDialogProps) {
  const toast = useToast();
  const viewport = useRef<HTMLDivElement | null>(null);

  // The viewport mounts inside the dialog portal; a ref callback attaches the
  // non-passive wheel listener that zooming needs.
  const attachViewport = useCallback((node: HTMLDivElement | null) => {
    viewport.current = node;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = node.getBoundingClientRect();
      const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      zoomDiagram(node, factor, event.clientX - rect.left, event.clientY - rect.top);
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  const zoom = (factor: number) => {
    if (viewport.current) zoomDiagram(viewport.current, factor);
  };

  const copySource = () => {
    if (!diagram) return;
    copyText(diagram.source).then(
      () => toast.success("Diagram source copied"),
      () => toast.error("Failed to copy diagram source"),
    );
  };

  return (
    <Dialog open={diagram !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex h-[calc(100dvh-2rem)] max-w-[calc(100vw-2rem)] flex-col gap-3 overflow-hidden p-4">
        <div className="flex items-center justify-between gap-2">
          <DialogTitle>Diagram</DialogTitle>
          <DialogDescription className="sr-only">
            Mermaid diagram from the answer. Scroll to zoom and drag to pan.
          </DialogDescription>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Zoom out"
              onClick={() => zoom(1 / ZOOM_STEP)}
            >
              <ZoomOut className="size-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Zoom in"
              onClick={() => zoom(ZOOM_STEP)}
            >
              <ZoomIn className="size-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Reset view"
              onClick={() => viewport.current && resetDiagram(viewport.current)}
            >
              <RotateCcw className="size-4" aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={copySource}>
              <Copy data-icon="inline-start" aria-hidden="true" />
              Copy source
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Close"
              onClick={onClose}
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        </div>
        {diagram && (
          <div
            ref={attachViewport}
            className="chat-mermaid-viewport chat-mermaid-fullscreen min-h-0 flex-1 rounded-[var(--radius-box)] border border-base-content/10"
            data-mermaid-viewport
            data-testid="chat-mermaid-fullscreen"
            role="img"
            aria-label="Mermaid chart"
            onPointerDown={(event) =>
              startDiagramPan(event.currentTarget, event.nativeEvent, { always: true })
            }
          >
            <div
              className="chat-mermaid-canvas"
              data-mermaid-canvas
              // Sanitized by renderMermaid: strict mode, no scripts, handlers or link targets.
              dangerouslySetInnerHTML={{ __html: diagram.svg }}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
