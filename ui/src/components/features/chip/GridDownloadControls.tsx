"use client";

import { Download, X } from "lucide-react";

import { DownloadConfirmModal } from "@/components/features/chip/DownloadConfirmModal";
import type { GridArtifactDownload } from "@/components/features/chip/useGridArtifactDownload";

interface GridDownloadControlsProps {
  download: GridArtifactDownload;
  /** Called when selection starts, so the grid can leave conflicting modes. */
  onStart?: () => void;
}

/** Toolbar controls that start, adjust, and submit a grid's artifact download selection. */
export function GridDownloadControls({ download, onStart }: GridDownloadControlsProps) {
  if (!download.isSelecting) {
    return (
      <div className="flex items-center gap-2">
        <button
          className="btn btn-sm btn-outline"
          onClick={() => {
            onStart?.();
            download.start();
          }}
          title="Select figures to download"
          disabled={download.availableCount === 0}
        >
          <Download data-icon="inline-start" />
          Download
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-base-content/70">
        {download.selectedIds.size} / {download.availableCount} selected
      </span>
      <button className="btn btn-sm btn-ghost" onClick={download.selectAll} title="Select all">
        All
      </button>
      <button className="btn btn-sm btn-ghost" onClick={download.clear} title="Clear selection">
        Clear
      </button>
      <button
        className="btn btn-sm btn-primary"
        onClick={() => download.setIsConfirmOpen(true)}
        disabled={download.selectedIds.size === 0 || download.isDownloading}
      >
        {download.isDownloading ? (
          <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
        ) : (
          <Download data-icon="inline-start" />
        )}
        Download
      </button>
      <button className="btn btn-sm btn-ghost btn-circle" onClick={download.cancel} title="Cancel">
        <X size={16} />
      </button>
    </div>
  );
}

/** Confirmation dialog that picks artifact kinds and submits the grid's download. */
export function GridDownloadConfirmModal({ download }: { download: GridArtifactDownload }) {
  return (
    <DownloadConfirmModal
      isOpen={download.isConfirmOpen}
      selectedCount={download.selectedIds.size}
      options={download.options}
      counts={download.counts}
      isSubmitting={download.isDownloading}
      onOptionsChange={download.setOptions}
      onConfirm={download.download}
      onClose={() => download.setIsConfirmOpen(false)}
    />
  );
}
