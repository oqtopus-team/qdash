"use client";

import { ChartNoAxesCombined, Download, Eye, FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { RawDataPreviewDialog } from "./RawDataPreviewDialog";
import { FigureJsonPreviewDialog } from "./FigureJsonPreviewDialog";

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

function archiveUrl(paths: string[]): string {
  const query = new URLSearchParams();
  paths.forEach((path) => query.append("paths", path));
  return `/api/executions/artifacts/archive?${query.toString()}`;
}

export function TaskArtifactDownloads({
  jsonFigurePaths = [],
  rawDataPaths = [],
}: TaskArtifactDownloadsProps) {
  const [rawPreviewPath, setRawPreviewPath] = useState<string | null>(null);
  const [figurePreviewPath, setFigurePreviewPath] = useState<string | null>(null);

  if (jsonFigurePaths.length === 0 && rawDataPaths.length === 0) return null;

  const artifacts = [
    ...jsonFigurePaths.map((path, index) => ({
      path,
      label: `Figure JSON${jsonFigurePaths.length > 1 ? ` ${index + 1}` : ""}`,
      type: "figure" as const,
    })),
    ...rawDataPaths.map((path, index) => ({
      path,
      label: `Raw data${rawDataPaths.length > 1 ? ` ${index + 1}` : ""}`,
      type: "raw" as const,
    })),
  ];

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {artifacts.map(({ path, label, type }) => (
          <div
            key={`${type}-${path}`}
            className="flex min-w-0 items-stretch rounded-lg border border-base-300 bg-base-100 transition-colors hover:border-primary/40 hover:bg-base-200"
          >
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-3 rounded-l-lg px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              onClick={() =>
                type === "figure" ? setFigurePreviewPath(path) : setRawPreviewPath(path)
              }
            >
              {type === "figure" ? (
                <ChartNoAxesCombined className="h-5 w-5 shrink-0 text-primary" />
              ) : (
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-primary" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-medium">{label}</span>
                <span className="block truncate text-xs text-base-content/60">
                  {fileName(path)}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
                <Eye className="h-3.5 w-3.5" /> Preview
              </span>
            </button>
            <a
              href={artifactUrl(path)}
              download={fileName(path)}
              aria-label={`Download ${fileName(path)}`}
              title={type === "figure" ? "Download figure JSON" : "Download NetCDF"}
              className="flex shrink-0 items-center border-l border-base-300 px-3 text-base-content/60 hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <Download className="h-4 w-4" />
            </a>
          </div>
        ))}
      </div>
      {artifacts.length > 1 && (
        <div className="flex justify-end">
          <a
            href={archiveUrl(artifacts.map(({ path }) => path))}
            download="artifacts.zip"
            className="btn btn-sm btn-outline gap-2"
          >
            <Download className="h-4 w-4" /> Download all (.zip)
          </a>
        </div>
      )}
      <FigureJsonPreviewDialog
        path={figurePreviewPath}
        onClose={() => setFigurePreviewPath(null)}
      />
      <RawDataPreviewDialog path={rawPreviewPath} onClose={() => setRawPreviewPath(null)} />
    </div>
  );
}
