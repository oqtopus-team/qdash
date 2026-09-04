"use client";

import { GitBranch, X } from "lucide-react";
import Link from "next/link";

import { CouplingMetricHistoryModal } from "@/components/features/metrics/CouplingMetricHistoryModal";
import { QubitMetricHistoryModal } from "@/components/features/metrics/QubitMetricHistoryModal";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

import {
  MetricNotePanel,
  type NoteEntry,
  type NoteEntryWithMetric,
  type TargetNoteEntry,
} from "./MetricNotePanel";
import type { GetChipNotesSummaryParams } from "@/schemas";
import type { MentionCandidate } from "@/components/ui/MarkdownEditor";

interface DashboardMetricModalProps {
  chipId: string;
  /** "0" for a qubit, "0-1" for a coupling. */
  targetId: string;
  metricKey: string;
  metricTitle: string;
  metricUnit: string;
  startAt?: string | null;
  endAt?: string | null;
  /** Cooldown scope identifiers for metric notes. */
  cooldownId?: string | null;
  cooldownLabel?: string | null;
  noteScopeParams?: GetChipNotesSummaryParams;
  /** Target-level note for this qubit/coupling, if any. */
  targetNote?: TargetNoteEntry;
  /** Legacy metric note for this exact (target, metric) pair, if any. */
  legacyMetricNote?: NoteEntry;
  /** Legacy metric notes for the same target. */
  legacyMetricNotes?: NoteEntryWithMetric[];
  mentionCandidates?: MentionCandidate[];
  onClose: () => void;
}

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} → Q${b}`;
  }
  return `Q${targetId}`;
}

/**
 * Full-screen modal that opens from a dashboard cell click. The body is split
 * between the metric-history view and an inline target-note panel so that
 * users can inspect history and edit shared qubit/coupling context.
 */
export function DashboardMetricModal({
  chipId,
  targetId,
  metricKey,
  metricTitle,
  metricUnit,
  startAt,
  endAt,
  cooldownId,
  cooldownLabel,
  noteScopeParams,
  targetNote,
  legacyMetricNote,
  legacyMetricNotes,
  mentionCandidates,
  onClose,
}: DashboardMetricModalProps) {
  const isCoupling = targetId.includes("-");

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-sm:top-auto max-sm:bottom-0 max-sm:translate-y-0 max-sm:rounded-b-none w-full p-0 h-[90vh] sm:h-[95vh] !overflow-hidden flex flex-col"
        style={{ maxWidth: "1800px" }}
      >
        {/* Header */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <DialogTitle className="text-lg sm:text-2xl font-bold truncate">
              {formatTarget(targetId)} · {metricTitle}
            </DialogTitle>
            <DialogDescription className="text-sm text-base-content/70 mt-0.5">
              Metric history, per-task notes, and shared target context.
            </DialogDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-circle flex-shrink-0 ml-2"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body — history (main) + metric note (side/top panel) */}
        <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden">
          <div className="w-full flex-none min-w-0 lg:flex-1 lg:min-h-0 lg:overflow-auto p-3 sm:p-6 order-2 lg:order-1">
            {isCoupling ? (
              <CouplingMetricHistoryModal
                chipId={chipId}
                couplingId={targetId}
                metricName={metricKey}
                metricUnit={metricUnit}
                startAt={startAt}
                endAt={endAt}
              />
            ) : (
              <QubitMetricHistoryModal
                chipId={chipId}
                qid={targetId}
                metricName={metricKey}
                metricUnit={metricUnit}
                startAt={startAt}
                endAt={endAt}
              />
            )}
          </div>

          <div className="order-1 lg:order-2 w-full lg:w-[360px] lg:min-w-[320px] lg:max-w-[400px] border-b lg:border-b-0 border-base-300 flex-shrink-0">
            <MetricNotePanel
              chipId={chipId}
              targetId={targetId}
              metricKey={metricKey}
              metricTitle={metricTitle}
              cooldownId={cooldownId}
              cooldownLabel={cooldownLabel}
              noteScopeParams={noteScopeParams}
              existing={targetNote}
              legacyMetricNote={legacyMetricNote}
              legacyMetricNotes={legacyMetricNotes}
              mentionCandidates={mentionCandidates}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-base-300 flex justify-between items-center">
          {!isCoupling && (
            <Link
              href={`/provenance?parameter=${encodeURIComponent(metricKey)}&qid=${encodeURIComponent(targetId)}&tab=lineage`}
              className="btn btn-ghost btn-sm sm:btn-md gap-1"
            >
              <GitBranch className="h-4 w-4" />
              <span className="hidden sm:inline">Lineage</span>
            </Link>
          )}
          <div className="flex gap-2 ml-auto">
            <button type="button" onClick={onClose} className="btn btn-ghost btn-sm sm:btn-md">
              Close
            </button>
            {!isCoupling && (
              <a
                href={`/chip/${chipId}/qubit/${targetId}`}
                className="btn btn-primary btn-sm sm:btn-md"
              >
                Details
              </a>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
