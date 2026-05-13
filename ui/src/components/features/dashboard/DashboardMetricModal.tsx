"use client";

import { useState } from "react";

import { GitBranch, Pencil, StickyNote, X } from "lucide-react";
import Link from "next/link";

import { CouplingMetricHistoryModal } from "@/components/features/metrics/CouplingMetricHistoryModal";
import { QubitMetricHistoryModal } from "@/components/features/metrics/QubitMetricHistoryModal";
import { formatDateTime } from "@/lib/utils/datetime";

import {
  ChipNoteEditor,
  type NoteEntry,
  type NoteEntryWithMetric,
} from "./ChipNoteEditor";

interface DashboardMetricModalProps {
  chipId: string;
  /** "0" for a qubit, "0-1" for a coupling. */
  targetId: string;
  metricKey: string;
  metricTitle: string;
  metricUnit: string;
  startAt?: string | null;
  endAt?: string | null;
  /** The chip note for this exact (target, metric) pair, if any. */
  chipNote?: NoteEntry;
  /** Notes for the same target on OTHER metrics (read-only context). */
  otherNotes?: NoteEntryWithMetric[];
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
 * Full-screen modal that opens from a dashboard cell click. Contains:
 *   - the existing metric-history modal body (history / tasks / figures / per-task note / issues)
 *   - a top banner showing/editing the per-(target, metric) "chip note"
 */
export function DashboardMetricModal({
  chipId,
  targetId,
  metricKey,
  metricTitle,
  metricUnit,
  startAt,
  endAt,
  chipNote,
  otherNotes,
  onClose,
}: DashboardMetricModalProps) {
  const [editingChipNote, setEditingChipNote] = useState(false);
  const isCoupling = targetId.includes("-");

  return (
    <>
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
                Metric history, per-task notes and issues for this target.
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

          {/* Per-(target, metric) chip-note banner */}
          <div className="px-4 sm:px-6 py-2 border-b border-base-300 bg-base-200/40">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-base-content/70 flex items-center gap-1.5">
                  <StickyNote className="h-3.5 w-3.5" />
                  Note for {formatTarget(targetId)} · {metricTitle}
                  {chipNote?.username && (
                    <span className="font-normal text-base-content/50">
                      · {chipNote.username} ·{" "}
                      {formatDateTime(chipNote.updatedAt)}
                    </span>
                  )}
                </div>
                <p className="text-sm whitespace-pre-wrap break-words mt-0.5">
                  {chipNote?.content ?? (
                    <span className="text-base-content/40 italic">
                      No note for this metric yet.
                    </span>
                  )}
                </p>
              </div>
              <button
                className="btn btn-xs btn-ghost gap-1 flex-shrink-0"
                onClick={() => setEditingChipNote(true)}
              >
                <Pencil className="h-3 w-3" />
                {chipNote ? "Edit" : "Add"}
              </button>
            </div>
          </div>

          {/* Modal body — full metric history */}
          <div className="flex-1 overflow-auto p-3 sm:p-6">
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

      {/* Nested chip-note editor overlay */}
      {editingChipNote && (
        <ChipNoteEditor
          chipId={chipId}
          targetId={targetId}
          metricKey={metricKey}
          metricTitle={metricTitle}
          existing={chipNote}
          otherNotes={otherNotes}
          onClose={() => setEditingChipNote(false)}
        />
      )}
    </>
  );
}
