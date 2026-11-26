"use client";

import { useMemo, useState } from "react";

import type { Task } from "@/schemas";

import { downloadFiguresAsZip } from "@/client/task-result/task-result";
import type {
  DownloadItemCounts,
  DownloadOptions,
} from "@/components/features/chip/DownloadConfirmModal";
import { useToast } from "@/components/ui/Toast";
import { getApiErrorMessage, parseBlobErrorBody } from "@/lib/utils/apiError";
import { saveBlob } from "@/lib/utils/download";

const DEFAULT_DOWNLOAD_OPTIONS: DownloadOptions = {
  figureImages: false,
  jsonFigures: false,
  rawData: true,
};

function toPathList(paths: string[] | string | null | undefined): string[] {
  if (!paths) return [];
  return Array.isArray(paths) ? paths : [paths];
}

function toNetcdfPathList(paths: string[] | string | null | undefined): string[] {
  return toPathList(paths).filter((path) => path.toLowerCase().endsWith(".nc"));
}

/** Whether a task result has any figure, JSON figure, or raw data file to download. */
export function hasDownloadableArtifacts(task: Task | null | undefined): boolean {
  return Boolean(
    toPathList(task?.figure_path).length ||
    toPathList(task?.json_figure_path).length ||
    toPathList(task?.raw_data_path).length,
  );
}

interface UseGridArtifactDownloadOptions {
  /** Task results of the grid, keyed by the IDs used for selection. */
  tasksById: Readonly<Record<string, Task | undefined>>;
  /** IDs that "Select all" selects: the displayed targets with downloadable artifacts. */
  downloadableIds: readonly string[];
  /** Name of the ZIP archive. */
  zipFilename: string;
}

/**
 * Selection and ZIP download of task artifacts from a chip grid.
 *
 * A failed download keeps the dialog, options, and selection so it can be retried.
 */
export function useGridArtifactDownload({
  tasksById,
  downloadableIds,
  zipFilename,
}: UseGridArtifactDownloadOptions) {
  const toast = useToast();
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDownloading, setIsDownloading] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [options, setOptions] = useState<DownloadOptions>(DEFAULT_DOWNLOAD_OPTIONS);

  const counts = useMemo(() => {
    const result: DownloadItemCounts = { figureImages: 0, jsonFigures: 0, rawData: 0 };
    selectedIds.forEach((id) => {
      const task = tasksById[id];
      result.figureImages += toPathList(task?.figure_path).length;
      result.jsonFigures += toPathList(task?.json_figure_path).length;
      result.rawData += toNetcdfPathList(task?.raw_data_path).length;
    });
    return result;
  }, [selectedIds, tasksById]);

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(downloadableIds));
  const clear = () => setSelectedIds(new Set());

  const start = () => {
    setIsSelecting(true);
    selectAll();
  };

  const cancel = () => {
    setIsSelecting(false);
    setSelectedIds(new Set());
  };

  const download = async () => {
    if (selectedIds.size === 0) return;

    const paths: string[] = [];
    selectedIds.forEach((id) => {
      const task = tasksById[id];
      if (!task) return;
      if (options.figureImages) paths.push(...toPathList(task.figure_path));
      if (options.jsonFigures) paths.push(...toPathList(task.json_figure_path));
      if (options.rawData) paths.push(...toNetcdfPathList(task.raw_data_path));
    });

    if (paths.length === 0) return;

    setIsDownloading(true);
    try {
      const response = await downloadFiguresAsZip(
        { paths, filename: zipFilename },
        { responseType: "blob" },
      );
      saveBlob(response.data as Blob, zipFilename);

      setIsConfirmOpen(false);
      cancel();
    } catch (error) {
      // Keep the dialog, options and selection so the download can be retried.
      toast.error(
        getApiErrorMessage(await parseBlobErrorBody(error), "Download failed. Please try again."),
      );
    } finally {
      setIsDownloading(false);
    }
  };

  return {
    isSelecting,
    selectedIds,
    availableCount: downloadableIds.length,
    isDownloading,
    isConfirmOpen,
    setIsConfirmOpen,
    options,
    setOptions,
    counts,
    toggle,
    selectAll,
    clear,
    start,
    cancel,
    download,
  };
}

export type GridArtifactDownload = ReturnType<typeof useGridArtifactDownload>;
