"use client";

import { X } from "lucide-react";

import { useGetProvenanceLineage } from "@/client/provenance/provenance";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

import { ProvenanceGraph } from "./ProvenanceGraph";

/** Deep enough to reach the seed values of a full calibration chain. */
const FULL_DEPTH = 20;

interface LineageGraphDialogProps {
  open: boolean;
  onClose: () => void;
  entityId: string;
  /** Parameter and target named in the header. */
  title: string;
}

/** The whole ancestry of one value as a graph; fetched only when opened, since it is the slow view. */
export function LineageGraphDialog({ open, onClose, entityId, title }: LineageGraphDialogProps) {
  const { data, isLoading, isError } = useGetProvenanceLineage(
    entityId,
    { max_depth: FULL_DEPTH },
    { query: { enabled: open && !!entityId } },
  );
  const graph = data?.data;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex h-[92dvh] w-[96vw] max-w-[1800px] flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <DialogTitle>Lineage graph</DialogTitle>
            <DialogDescription className="text-xs text-base-content/60">
              {title}: every value this one derives from
              {graph ? `, ${graph.nodes.length} nodes` : ""}.
            </DialogDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-circle"
            aria-label="Close lineage graph"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <span className="loading loading-spinner loading-lg" />
            </div>
          ) : isError || !graph ? (
            <p role="alert" className="py-12 text-center text-sm text-base-content/60">
              The lineage graph could not be loaded.
            </p>
          ) : (
            <ProvenanceGraph nodes={graph.nodes} edges={graph.edges} originId={entityId} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
