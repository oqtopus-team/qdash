"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";

import { downloadMetricsPdf } from "@/client/metrics/metrics";

interface MetricsPdfDownloadButtonProps {
  chipId: string;
  withinHours?: number;
  selectionMode: "latest" | "best" | "average";
  disabled?: boolean;
}

export function MetricsPdfDownloadButton({
  chipId,
  withinHours,
  selectionMode,
  disabled = false,
}: MetricsPdfDownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    if (!chipId || isDownloading) return;

    setIsDownloading(true);
    setError(null);

    try {
      const response = await downloadMetricsPdf(
        chipId,
        {
          within_hours: withinHours,
          selection_mode: selectionMode,
        },
        { responseType: "blob" },
      );

      const blob = new Blob([response.data as BlobPart], {
        type: "application/pdf",
      });

      // Generate filename with timestamp
      const now = new Date();
      const timestamp = now
        .toISOString()
        .slice(0, 19)
        .replace(/[-:T]/g, "")
        .replace(/(\d{8})(\d{6})/, "$1_$2");
      const filename = `metrics_report_${chipId}_${timestamp}.pdf`;

      // Download the PDF
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch (err) {
      console.error("PDF download failed:", err);
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleDownload}
        disabled={disabled || isDownloading || !chipId}
        className="btn btn-primary btn-sm gap-2"
        title="Download metrics report as PDF"
      >
        {isDownloading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="hidden sm:inline">Generating...</span>
          </>
        ) : (
          <>
            <Download className="h-4 w-4" />
            <span className="hidden sm:inline">PDF</span>
          </>
        )}
      </button>
      {error && (
        <div className="text-xs text-error max-w-48 text-right">{error}</div>
      )}
    </div>
  );
}
