"use client";

import { ChartNoAxesCombined, Download, Eye, FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { RawDataPreviewDialog } from "./RawDataPreviewDialog";
import { FigureJsonPreviewDialog } from "./FigureJsonPreviewDialog";

const ARCHIVE_PATH_LIMIT = 100;

interface TaskArtifactDownloadsProps {
  jsonFigurePaths?: string[];
  rawDataPaths?: string[];
  /** Figure image paths; shown elsewhere, so they are only added to the ZIP archive. */
  imagePaths?: string[];
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

function uniquePaths(paths: string[]): string[] {
  return Array.from(new Set(paths.filter(Boolean)));
}

/** Unique paths for "Download all", in image, figure JSON, raw data order. */
function taskArtifactArchivePaths({
  jsonFigurePaths = [],
  rawDataPaths = [],
  imagePaths = [],
}: TaskArtifactDownloadsProps): string[] {
  return uniquePaths([...imagePaths, ...jsonFigurePaths, ...rawDataPaths]);
}

/** Whether TaskArtifactDownloads renders anything for the given paths. */
export function hasTaskArtifactDownloads(props: TaskArtifactDownloadsProps): boolean {
  const { jsonFigurePaths = [], rawDataPaths = [] } = props;
  return (
    jsonFigurePaths.length > 0 ||
    rawDataPaths.length > 0 ||
    taskArtifactArchivePaths(props).length > 1
  );
}

export function TaskArtifactDownloads({
  jsonFigurePaths = [],
  rawDataPaths = [],
  imagePaths = [],
}: TaskArtifactDownloadsProps) {
  const [rawPreviewPath, setRawPreviewPath] = useState<string | null>(null);
  const [figurePreviewPath, setFigurePreviewPath] = useState<string | null>(null);

  if (!hasTaskArtifactDownloads({ jsonFigurePaths, rawDataPaths, imagePaths })) return null;

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

  const archivePaths = taskArtifactArchivePaths({
    jsonFigurePaths,
    rawDataPaths,
    imagePaths,
  });
  const archiveImageCount = uniquePaths(imagePaths).length;
  const archiveLimitExceeded = archivePaths.length > ARCHIVE_PATH_LIMIT;

  return (
    <div className="space-y-3">
      {artifacts.length > 0 && (
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
      )}
      {archivePaths.length > 1 && (
        <div className="flex flex-wrap items-center justify-end gap-2">
          {archiveImageCount > 0 && !archiveLimitExceeded && (
            <span className="text-xs text-base-content/60">
              Includes {archiveImageCount} figure image
              {archiveImageCount > 1 ? "s" : ""}
            </span>
          )}
          {archiveLimitExceeded && (
            <span className="text-xs text-warning">
              Download all supports up to {ARCHIVE_PATH_LIMIT} files. Download these artifacts
              individually.
            </span>
          )}
          {archiveLimitExceeded ? (
            <button type="button" className="btn btn-sm btn-outline gap-2" disabled>
              <Download className="h-4 w-4" /> Download all (.zip)
            </button>
          ) : (
            <a
              href={archiveUrl(archivePaths)}
              download="artifacts.zip"
              className="btn btn-sm btn-outline gap-2"
            >
              <Download className="h-4 w-4" /> Download all (.zip)
            </a>
          )}
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
