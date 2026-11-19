"use client";

import { Copy } from "lucide-react";

import type { CollisionCellResponse } from "@/schemas";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { QubitTile } from "@/components/ui/QubitTile";
import { useToast } from "@/components/ui/Toast";
import { copyText } from "@/lib/utils/clipboard";

import { formatNumber } from "../panelConfig";

function formatCheckValue(value: number | null): string {
  return value === null ? "Not finite" : formatNumber(value);
}

function cellName(cell: CollisionCellResponse): string {
  return cell.source && cell.target
    ? `Q${cell.source} → Q${cell.target}`
    : `Q${cell.qid ?? cell.key.replace(/^Q/, "")}`;
}

/** Plain-text report of a cell, for pasting into notes or chat. */
function collisionCellReport(cell: CollisionCellResponse, checkTitle: string): string {
  const lines = [`${checkTitle}: ${cellName(cell)}`, cell.label];
  if (cell.hops) lines.push(`Hops: ${cell.hops}`);
  if (cell.checks.length > 0) {
    lines.push("", "Checks:");
    for (const item of cell.checks) lines.push(`- ${item.label}: ${formatCheckValue(item.value)}`);
  }
  if (cell.estimates.length > 0) {
    lines.push("", "Defaults and estimates:");
    for (const note of cell.estimates) lines.push(`- ${note}`);
  }
  return lines.join("\n");
}

interface CollisionCellDialogProps {
  cell: CollisionCellResponse | null;
  checkTitle: string;
  onOpenChange: (open: boolean) => void;
}

/** Selectable details of one evaluated qubit or directed pair. */
export function CollisionCellDialog({ cell, checkTitle, onOpenChange }: CollisionCellDialogProps) {
  const toast = useToast();

  const handleCopy = async () => {
    if (!cell) return;
    try {
      await copyText(collisionCellReport(cell, checkTitle));
      toast.success("Copied check details");
    } catch {
      toast.error("Failed to copy check details");
    }
  };

  return (
    <Dialog open={cell !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl select-text">
        {cell && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <DialogTitle className="flex flex-wrap items-center gap-2">
                {cell.source && cell.target ? (
                  <>
                    <QubitTile qid={cell.source} />
                    <span className="text-base-content/60">to</span>
                    <QubitTile qid={cell.target} />
                  </>
                ) : (
                  <QubitTile qid={cell.qid ?? cell.key.replace(/^Q/, "")} />
                )}
                <span>{checkTitle}</span>
                {cell.hops ? (
                  <span className="badge badge-ghost badge-sm">
                    {cell.hops} {cell.hops === 1 ? "hop" : "hops"}
                  </span>
                ) : null}
              </DialogTitle>
              <DialogDescription className="flex items-center gap-2 text-sm">
                <span
                  className="inline-block h-3 w-3 shrink-0 rounded-sm"
                  style={{ backgroundColor: cell.color }}
                  aria-hidden="true"
                />
                {cell.label}
              </DialogDescription>
            </div>

            {cell.checks.length > 0 && (
              <section aria-labelledby="collision-cell-checks">
                <h3
                  id="collision-cell-checks"
                  className="mb-1 text-xs font-medium text-base-content/60"
                >
                  Checks
                </h3>
                <div className="overflow-x-auto rounded-[var(--radius-box)] border border-base-content/10">
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th className="text-right">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cell.checks.map((item, index) => (
                        <tr key={`${item.label}-${index}`}>
                          <td>{item.label}</td>
                          <td className="text-right font-mono tabular-nums">
                            {formatCheckValue(item.value)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {cell.estimates.length > 0 && (
              <section aria-labelledby="collision-cell-estimates">
                <h3
                  id="collision-cell-estimates"
                  className="mb-1 text-xs font-medium text-base-content/60"
                >
                  Defaults and estimates
                </h3>
                <ul className="list-disc space-y-1 pl-5 text-sm text-base-content/80">
                  {cell.estimates.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </section>
            )}

            <div className="modal-action mt-0">
              <button type="button" className="btn btn-ghost" onClick={() => onOpenChange(false)}>
                Close
              </button>
              <button type="button" className="btn" onClick={handleCopy}>
                <Copy data-icon="inline-start" aria-hidden="true" />
                Copy all
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
