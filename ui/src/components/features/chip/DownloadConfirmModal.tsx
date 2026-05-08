"use client";

import { Database, FileJson, FileText, Image, X } from "lucide-react";
import type { ReactNode } from "react";

export interface DownloadOptions {
  figureImages: boolean;
  jsonFigures: boolean;
  rawData: boolean;
  aiTriageNotes: boolean;
}

export interface DownloadItemCounts {
  figureImages: number;
  jsonFigures: number;
  rawData: number;
  aiTriageNotes: number;
}

interface DownloadConfirmModalProps {
  isOpen: boolean;
  selectedCount: number;
  options: DownloadOptions;
  counts: DownloadItemCounts;
  isSubmitting: boolean;
  onOptionsChange: (options: DownloadOptions) => void;
  onConfirm: () => void;
  onClose: () => void;
}

export function DownloadConfirmModal({
  isOpen,
  selectedCount,
  options,
  counts,
  isSubmitting,
  onOptionsChange,
  onConfirm,
  onClose,
}: DownloadConfirmModalProps) {
  if (!isOpen) return null;

  const selectedItemCount =
    (options.figureImages ? counts.figureImages : 0) +
    (options.jsonFigures ? counts.jsonFigures : 0) +
    (options.rawData ? counts.rawData : 0) +
    (options.aiTriageNotes ? counts.aiTriageNotes : 0);

  const toggle = (key: keyof DownloadOptions) => {
    onOptionsChange({ ...options, [key]: !options[key] });
  };

  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-lg">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold text-lg">Download task artifacts</h3>
            <p className="text-sm text-base-content/70 mt-1">
              {selectedCount} task result{selectedCount === 1 ? "" : "s"}{" "}
              selected
            </p>
          </div>
          <button
            className="btn btn-sm btn-ghost btn-circle"
            onClick={onClose}
            disabled={isSubmitting}
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-2">
          <DownloadOptionRow
            icon={<Image className="h-4 w-4" />}
            label="Figure images"
            count={counts.figureImages}
            checked={options.figureImages}
            onToggle={() => toggle("figureImages")}
          />
          <DownloadOptionRow
            icon={<FileJson className="h-4 w-4" />}
            label="JSON figures"
            count={counts.jsonFigures}
            checked={options.jsonFigures}
            onToggle={() => toggle("jsonFigures")}
          />
          <DownloadOptionRow
            icon={<Database className="h-4 w-4" />}
            label="Raw data"
            count={counts.rawData}
            checked={options.rawData}
            onToggle={() => toggle("rawData")}
          />
          <DownloadOptionRow
            icon={<FileText className="h-4 w-4" />}
            label="AI triage notes"
            count={counts.aiTriageNotes}
            checked={options.aiTriageNotes}
            onToggle={() => toggle("aiTriageNotes")}
          />
        </div>

        <div className="modal-action">
          <button
            className="btn btn-ghost"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={onConfirm}
            disabled={isSubmitting || selectedItemCount === 0}
          >
            {isSubmitting ? (
              <span className="loading loading-spinner loading-xs" />
            ) : null}
            Download
          </button>
        </div>
      </div>
      <button
        className="modal-backdrop"
        onClick={isSubmitting ? undefined : onClose}
      >
        close
      </button>
    </div>
  );
}

function DownloadOptionRow({
  icon,
  label,
  count,
  checked,
  onToggle,
}: {
  icon: ReactNode;
  label: string;
  count: number;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={`flex items-center justify-between gap-3 rounded-lg border border-base-300 px-3 py-2 ${
        count === 0 ? "opacity-50" : "cursor-pointer hover:bg-base-200"
      }`}
    >
      <span className="flex items-center gap-2 text-sm">
        {icon}
        {label}
      </span>
      <span className="flex items-center gap-3">
        <span className="text-xs text-base-content/60">{count}</span>
        <input
          type="checkbox"
          className="checkbox checkbox-sm"
          checked={checked}
          onChange={onToggle}
          disabled={count === 0}
        />
      </span>
    </label>
  );
}
