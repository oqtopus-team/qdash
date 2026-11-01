"use client";

import { useState, type ReactNode } from "react";

import { X } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import type { ProvenanceTarget } from "@/lib/provenanceTarget";

import { ParameterLineagePanel } from "./ParameterLineagePanel";

interface ParameterLineageDialogProps {
  /** Parameter to show; null keeps the dialog closed. */
  target: ProvenanceTarget | null;
  onClose: () => void;
}

/** The lineage panel in a dialog, for pages and modals that show a value but have no room beside it. */
export function ParameterLineageDialog({ target, onClose }: ParameterLineageDialogProps) {
  return (
    <Dialog open={!!target} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl p-0">
        <div className="flex items-start justify-between gap-3 border-b border-base-300 px-5 py-3">
          <div>
            <DialogTitle>Lineage</DialogTitle>
            <DialogDescription className="text-xs text-base-content/60">
              Where this value came from and what depends on it.
            </DialogDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-circle"
            aria-label="Close lineage"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-4">
          {target && (
            <ParameterLineagePanel
              key={`${target.parameterName}:${target.qid}`}
              parameterName={target.parameterName}
              qid={target.qid}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface LineageButtonProps {
  /** Parameter to open; null disables the button (the task published nothing). */
  target: ProvenanceTarget | null;
  className?: string;
  children: ReactNode;
}

/** Button that opens one parameter's lineage in a dialog. */
export function LineageButton({ target, className, children }: LineageButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={className} disabled={!target} onClick={() => setOpen(true)}>
        {children}
      </button>
      <ParameterLineageDialog target={open ? target : null} onClose={() => setOpen(false)} />
    </>
  );
}
