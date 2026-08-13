"use client";

import { Download, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { previewArtifactByPath } from "@/client/execution/execution";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import type { ArtifactPreviewResponse } from "@/schemas/artifactPreviewResponse";

type PreviewValue = number | string | boolean | null;

interface RawDataPreviewDialogProps {
  path: string | null;
  onClose: () => void;
}

function artifactUrl(path: string): string {
  return `/api/executions/artifact?path=${encodeURIComponent(path)}`;
}

function fileName(path: string): string {
  return path.split("/").pop() || "raw-data.nc";
}

function formatValue(value: PreviewValue | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : value.toPrecision(7);
  return String(value);
}

export function RawDataPreviewDialog({ path, onClose }: RawDataPreviewDialogProps) {
  const [preview, setPreview] = useState<ArtifactPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setPreview(null);
    setError(null);

    previewArtifactByPath({ path }, undefined, controller.signal)
      .then((response) => setPreview(response.data))
      .catch(() => {
        if (!controller.signal.aborted) setError("Unable to load the raw data preview.");
      });

    return () => controller.abort();
  }, [path]);

  return (
    <Dialog open={path !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl p-0 overflow-hidden">
        <div className="border-b border-base-300 p-5 pr-12">
          <DialogTitle>Raw data preview</DialogTitle>
          <DialogDescription className="mt-1 text-sm text-base-content/70">
            {preview?.filename ?? "Loading NetCDF metadata…"}
          </DialogDescription>
        </div>
        <div className="max-h-[65vh] overflow-auto p-5">
          {!preview && !error && (
            <div className="flex min-h-40 items-center justify-center gap-2 text-base-content/70">
              <Loader2 className="h-5 w-5 animate-spin" /> Loading preview…
            </div>
          )}
          {error && <div className="alert alert-error text-sm">{error}</div>}
          {preview && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2 text-xs">
                {preview.target && (
                  <span className="badge badge-outline">Target: {preview.target}</span>
                )}
                <span className="badge badge-outline">
                  Shape: {preview.shape.join(" × ") || "scalar"}
                </span>
                <span className="badge badge-outline">Type: {preview.dtype}</span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-base-300">
                <table className="table table-sm table-pin-rows">
                  <thead>
                    <tr>
                      {preview.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {preview.columns.map((column) => (
                          <td key={column} className="font-mono tabular-nums">
                            {formatValue(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-base-content/60">
                Showing {preview.rows.length} of {preview.total_rows} values
                {preview.truncated ? " (preview limited to the first 50)" : ""}.
              </p>
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-base-300 p-4">
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
            Close
          </button>
          {path && (
            <a
              className="btn btn-sm btn-primary gap-1"
              href={artifactUrl(path)}
              download={fileName(path)}
            >
              <Download className="h-4 w-4" /> Download
            </a>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
