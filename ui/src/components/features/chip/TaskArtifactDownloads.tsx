"use client";

import { Download, Eye } from "lucide-react";
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
    <div className="flex flex-wrap items-center gap-2">
      {jsonFigurePaths.map((path, index) => (
        <a
          key={`figure-${path}`}
          href={artifactUrl(path)}
          download={fileName(path)}
          className="btn btn-xs btn-outline gap-1"
        >
          <Download className="h-3 w-3" />
          Figure JSON{jsonFigurePaths.length > 1 ? ` ${index + 1}` : ""}
        </a>
      ))}
      {rawDataPaths.map((path, index) => (
        <div key={`raw-${path}`} className="join">
          <button
            type="button"
            className="btn btn-xs btn-outline join-item gap-1"
            onClick={() => setPreviewPath(path)}
          >
            <Eye className="h-3 w-3" /> Preview
          </button>
          <a
            href={artifactUrl(path)}
            download={fileName(path)}
            className="btn btn-xs btn-outline gap-1"
          >
            <Download className="h-3 w-3" />
            Raw data{rawDataPaths.length > 1 ? ` ${index + 1}` : ""} (.nc)
          </a>
        </div>
      ))}
      <RawDataPreviewDialog path={previewPath} onClose={() => setPreviewPath(null)} />
    </div>
  );
}
