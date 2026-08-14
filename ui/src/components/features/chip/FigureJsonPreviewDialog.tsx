"use client";

import { Download } from "lucide-react";

import { InteractiveFigureContent } from "@/components/charts/InteractiveFigureContent";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

interface FigureJsonPreviewDialogProps {
  path: string | null;
  onClose: () => void;
}

function artifactUrl(path: string): string {
  return `/api/executions/artifact?path=${encodeURIComponent(path)}`;
}

function fileName(path: string): string {
  return path.split("/").pop() || "figure.json";
}

export function FigureJsonPreviewDialog({ path, onClose }: FigureJsonPreviewDialogProps) {
  return (
    <Dialog open={path !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-auto">
        <div className="pr-8">
          <DialogTitle>Figure preview</DialogTitle>
          <DialogDescription className="mt-1 truncate">
            {path ? fileName(path) : "Interactive figure"}
          </DialogDescription>
        </div>
        {path && (
          <div className="flex justify-center overflow-auto py-2">
            <InteractiveFigureContent figureJsonPath={path} />
          </div>
        )}
        <div className="flex justify-end gap-2 border-t border-base-300 pt-4">
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
            Close
          </button>
          {path && (
            <a
              className="btn btn-sm btn-primary gap-1"
              href={artifactUrl(path)}
              download={fileName(path)}
            >
              <Download className="h-4 w-4" /> Download JSON
            </a>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
