"use client";

import { Download, Eye, FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { RawDataPreviewDialog } from "./RawDataPreviewDialog";

interface TaskArtifactDownloadsProps {
  jsonFigurePaths?: string[];
  rawDataPaths?: string[];
}

function artifactUrl(path: string): string {
  return `/api/executions/artifact?path=${encodeURIComponent(path)}`;
}

function fileName(path: string): string {
  return path.split("/").pop() || "artifact";
}

export function TaskArtifactDownloads({
  jsonFigurePaths = [],
  rawDataPaths = [],
}: TaskArtifactDownloadsProps) {
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  if (jsonFigurePaths.length === 0 && rawDataPaths.length === 0) return null;

  return (
    <div className="space-y-3">
      {rawDataPaths.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {rawDataPaths.map((path, index) => (
            <button
              key={`raw-${path}`}
              type="button"
              className="flex min-w-0 items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-base-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              onClick={() => setPreviewPath(path)}
            >
              <FileSpreadsheet className="h-5 w-5 shrink-0 text-primary" />
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-medium">
                  Raw data{rawDataPaths.length > 1 ? ` ${index + 1}` : ""}
                </span>
                <span className="block truncate text-xs text-base-content/60">
                  {fileName(path)}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
                <Eye className="h-3.5 w-3.5" /> Preview
              </span>
            </button>
          ))}
        </div>
      )}
      {jsonFigurePaths.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {jsonFigurePaths.map((path, index) => (
            <a
              key={`figure-${path}`}
              href={artifactUrl(path)}
              download={fileName(path)}
              className="btn btn-xs btn-ghost gap-1"
            >
              <Download className="h-3 w-3" />
              Figure JSON{jsonFigurePaths.length > 1 ? ` ${index + 1}` : ""}
            </a>
          ))}
        </div>
      )}
      <RawDataPreviewDialog path={previewPath} onClose={() => setPreviewPath(null)} />
    </div>
  );
}
