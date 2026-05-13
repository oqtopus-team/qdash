"use client";

import { GitBranch, X } from "lucide-react";
import Link from "next/link";

import { CouplingMetricHistoryModal } from "@/components/features/metrics/CouplingMetricHistoryModal";
import { QubitMetricHistoryModal } from "@/components/features/metrics/QubitMetricHistoryModal";

import {
  MetricNotePanel,
  type NoteEntry,
  type NoteEntryWithMetric,
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
  /** The metric note for this exact (target, metric) pair, if any. */
  chipNote?: NoteEntry;
  /** Notes for the same target on OTHER metrics (read-only context). */
  otherNotes?: NoteEntryWithMetric[];
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
 * between the metric-history view and an inline metric-note panel so that
 * users can inspect history and edit the note in the same context.
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
  chipNote,
  otherNotes,
  mentionCandidates,
  onClose,
}: DashboardMetricModalProps) {
  const isCoupling = targetId.includes("-");

  return (
    <div
      className="modal modal-bottom sm:modal-middle modal-open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal-box w-full bg-base-100 p-0 h-[90vh] sm:h-[95vh] overflow-hidden flex flex-col"
        style={{ maxWidth: "1800px" }}
      >
        {/* Header */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg sm:text-2xl font-bold truncate">
              {formatTarget(targetId)} · {metricTitle}
            </h2>
            <p className="text-sm text-base-content/70 mt-0.5">
              Metric history, per-task notes, and a per-cooldown metric note.
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-circle flex-shrink-0 ml-2"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body — history (main) + metric note (side/top panel) */}
        <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-hidden">
          <div className="flex-1 min-w-0 overflow-auto p-3 sm:p-6 order-2 lg:order-1">
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
              existing={chipNote}
              otherNotes={otherNotes}
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
            <button
              onClick={onClose}
              className="btn btn-ghost btn-sm sm:btn-md"
            >
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
      </div>
    </div>
  );
}
