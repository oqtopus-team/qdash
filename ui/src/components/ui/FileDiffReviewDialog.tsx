"use client";

import dynamic from "next/dynamic";

import { GitCompareArrows, X } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./Dialog";

const PierreDiffViewer = dynamic(
  () => import("@/components/ui/PierreDiffViewer").then((module) => module.PierreDiffViewer),
  {
    loading: () => (
      <div className="flex min-h-64 items-center justify-center">
        <span className="loading loading-spinner loading-lg" />
      </div>
    ),
    ssr: false,
  },
);

interface FileDiffReviewDialogProps {
  filename: string;
  newContent: string;
  oldContent: string;
  onClose: () => void;
  open: boolean;
}

export function FileDiffReviewDialog({
  filename,
  newContent,
  oldContent,
  onClose,
  open,
}: FileDiffReviewDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent className="flex h-[min(85dvh,56rem)] max-w-6xl flex-col !overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-base-300 px-4 py-3">
          <div className="min-w-0">
            <DialogTitle className="flex items-center gap-2 font-semibold text-base">
              <GitCompareArrows size={18} className="text-primary" />
              Review saved changes
            </DialogTitle>
            <DialogDescription className="truncate font-mono text-xs text-base-content/60">
              {filename}
            </DialogDescription>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-circle btn-ghost"
            onClick={onClose}
            aria-label="Close diff review"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-base-100 p-3">
          <PierreDiffViewer filename={filename} newContent={newContent} oldContent={oldContent} />
        </div>

        <div className="flex justify-end border-t border-base-300 px-4 py-3">
          <button type="button" className="btn btn-sm" onClick={onClose}>
            Close
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
