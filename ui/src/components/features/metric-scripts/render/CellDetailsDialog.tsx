"use client";

import type { ReactNode } from "react";

import { Copy } from "lucide-react";

import type { CellCheck, MetricCell, MetricInfo } from "@/schemas";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { QubitTile } from "@/components/ui/QubitTile";
import { useToast } from "@/components/ui/Toast";
import { copyText } from "@/lib/utils/clipboard";
import { formatDateTime } from "@/lib/utils/datetime";

import { cellName, displayUnit, formatNumber, STATUS_LABELS } from "../format";

function formatCheckValue(value: CellCheck["value"]): string {
  if (value === null || value === undefined) return "–";
  return typeof value === "number" ? formatNumber(value) : value;
}

function valueText(cell: MetricCell, unit: string): string {
  if (typeof cell.value !== "number") return STATUS_LABELS[cell.status];
  return `${formatNumber(cell.value)}${unit ? ` ${unit}` : ""}`;
}

function diagnosticText(cell: MetricCell): string | null {
  const diagnostic = cell.diagnostic;
  if (!diagnostic) return null;
  const where = [
    diagnostic.function ? `in ${diagnostic.function}()` : null,
    diagnostic.line ? `line ${diagnostic.line}` : null,
  ]
    .filter(Boolean)
    .join(", ");
  return where ? `${diagnostic.message} (${where})` : diagnostic.message;
}

/** Plain-text report of a cell, for pasting into notes or chat. */
function cellReport(cell: MetricCell, metric: Pick<MetricInfo, "title" | "unit">): string {
  const unit = displayUnit(metric.unit);
  const lines = [`${metric.title}: ${cellName(cell)}`, `Value: ${valueText(cell, unit)}`];
  lines.push(`Status: ${STATUS_LABELS[cell.status]}`);
  if (cell.label) lines.push(`Label: ${cell.label}`);
  if (cell.hops) lines.push(`Hops: ${cell.hops}`);
  const count = cell.assessment?.count;
  if (typeof count === "number") lines.push(`Count: ${count}`);
  if (cell.message) lines.push(`Message: ${cell.message}`);
  const diagnostic = diagnosticText(cell);
  if (diagnostic) lines.push(`Diagnostic: ${diagnostic}`);
  const checks = cell.assessment?.checks ?? [];
  if (checks.length > 0) {
    lines.push("", "Checks:");
    for (const item of checks) lines.push(`- ${item.label}: ${formatCheckValue(item.value)}`);
  }
  const estimates = cell.assessment?.estimates ?? [];
  if (estimates.length > 0) {
    lines.push("", "Defaults and estimates:");
    for (const note of estimates) lines.push(`- ${note}`);
  }
  const references = cell.references ?? [];
  if (references.length > 0) {
    lines.push("", "Inputs:");
    for (const ref of references) {
      const value =
        typeof ref.value === "number"
          ? `${formatNumber(ref.value)}${ref.unit ? ` ${displayUnit(ref.unit)}` : ""}`
          : "–";
      const parts = [`${ref.metric}[${ref.target}] = ${value}`];
      if (ref.timestamp) parts.push(`at ${ref.timestamp}`);
      if (ref.task_id) parts.push(`task ${ref.task_id}`);
      lines.push(`- ${parts.join(", ")}`);
    }
  }
  return lines.join("\n");
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1 text-xs font-medium text-base-content/60">{title}</h3>
      {children}
    </section>
  );
}

interface CellDetailsDialogProps {
  cell: MetricCell | null;
  metric: Pick<MetricInfo, "title" | "unit">;
  /** Colour the cell is drawn in, shown next to its label. */
  color?: string;
  onOpenChange: (open: boolean) => void;
}

/** Selectable details of one evaluated qubit or directed pair. */
export function CellDetailsDialog({ cell, metric, color, onOpenChange }: CellDetailsDialogProps) {
  const toast = useToast();
  const unit = displayUnit(metric.unit);

  const handleCopy = async () => {
    if (!cell) return;
    try {
      await copyText(cellReport(cell, metric));
      toast.success("Copied cell details");
    } catch {
      toast.error("Failed to copy cell details");
    }
  };

  const checks = cell?.assessment?.checks ?? [];
  const estimates = cell?.assessment?.estimates ?? [];
  const references = cell?.references ?? [];
  const count = cell?.assessment?.count;
  const diagnostic = cell ? diagnosticText(cell) : null;

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
                  <QubitTile qid={cell.qid ?? cell.key} />
                )}
                <span>{metric.title}</span>
                {cell.hops ? (
                  <span className="badge badge-ghost badge-sm">
                    {cell.hops} {cell.hops === 1 ? "hop" : "hops"}
                  </span>
                ) : null}
              </DialogTitle>
              <DialogDescription className="flex flex-wrap items-center gap-2 text-sm">
                {color && (
                  <span
                    className="inline-block h-3 w-3 shrink-0 rounded-sm"
                    style={{ backgroundColor: color }}
                    aria-hidden="true"
                  />
                )}
                <span className="font-mono tabular-nums">{valueText(cell, unit)}</span>
                {cell.label && <span className="text-base-content/70">{cell.label}</span>}
                {typeof count === "number" && (
                  <span className="badge badge-ghost badge-sm">n = {count}</span>
                )}
              </DialogDescription>
            </div>

            {(cell.message || diagnostic) && (
              <div
                role={cell.status === "error" ? "alert" : undefined}
                className={`alert alert-soft text-sm ${cell.status === "error" ? "alert-error" : "alert-warning"}`}
              >
                <div className="flex min-w-0 flex-col gap-1">
                  {cell.message && <span className="whitespace-pre-wrap">{cell.message}</span>}
                  {diagnostic && diagnostic !== cell.message && (
                    <span className="font-mono text-xs">{diagnostic}</span>
                  )}
                </div>
              </div>
            )}

            {checks.length > 0 && (
              <Section title="Checks">
                <div className="overflow-x-auto rounded-[var(--radius-box)] border border-base-content/10">
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th className="text-right">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {checks.map((item, index) => (
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
              </Section>
            )}

            {estimates.length > 0 && (
              <Section title="Defaults and estimates">
                <ul className="list-disc space-y-1 pl-5 text-sm text-base-content/80">
                  {estimates.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </Section>
            )}

            {references.length > 0 && (
              <Section title="Inputs">
                <div className="overflow-x-auto rounded-[var(--radius-box)] border border-base-content/10">
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Target</th>
                        <th className="text-right">Value</th>
                        <th>Measured</th>
                        <th>Task</th>
                      </tr>
                    </thead>
                    <tbody>
                      {references.map((ref, index) => (
                        <tr key={`${ref.metric}-${ref.target}-${ref.task_id ?? index}`}>
                          <td className="font-mono">{ref.metric}</td>
                          <td className="font-mono">{ref.target}</td>
                          <td className="text-right font-mono tabular-nums whitespace-nowrap">
                            {typeof ref.value === "number" ? formatNumber(ref.value) : "–"}
                            {ref.unit ? ` ${displayUnit(ref.unit)}` : ""}
                          </td>
                          <td className="whitespace-nowrap">
                            {ref.timestamp ? formatDateTime(ref.timestamp) : "–"}
                          </td>
                          <td className="max-w-40 truncate font-mono" title={ref.task_id ?? ""}>
                            {ref.task_id ?? "–"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
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
