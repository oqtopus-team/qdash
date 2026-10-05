"use client";

import { Download } from "lucide-react";
import { useState } from "react";

import { downloadZipFile } from "@/client/file/file";
import { getApiErrorMessage } from "@/lib/utils/apiError";

interface FilesBulkDownloadButtonProps {
  disabled?: boolean;
  onError: (message: string) => void;
}

function getArchiveFilename(contentDisposition: unknown): string {
  if (typeof contentDisposition !== "string") return "config-files.zip";

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      // Fall back to the plain filename or default below.
    }
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1] ?? "config-files.zip";
}

async function parseDownloadError(error: unknown): Promise<unknown> {
  const response = (error as { response?: { data?: unknown } } | null)?.response;
  if (response?.data instanceof Blob) {
    try {
      response.data = JSON.parse(await response.data.text());
    } catch {
      // Preserve the original response when it is not JSON.
    }
  }
  return error;
}

export function FilesBulkDownloadButton({
  disabled = false,
  onError,
}: FilesBulkDownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    if (isDownloading) return;

    setIsDownloading(true);
    try {
      const response = await downloadZipFile({ path: "." }, { responseType: "blob" });
      const blob = new Blob([response.data as unknown as BlobPart], {
        type: "application/zip",
      });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = downloadUrl;
      link.download = getArchiveFilename(response.headers["content-disposition"]);
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(link);
    } catch (error) {
      onError(
        getApiErrorMessage(await parseDownloadError(error), "Failed to download config files"),
      );
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-sm btn-outline hidden sm:flex"
      onClick={handleDownload}
      disabled={disabled || isDownloading}
      title="Download all config files as a ZIP archive"
    >
      {isDownloading ? (
        <span className="loading loading-spinner loading-xs" aria-hidden="true" />
      ) : (
        <Download size={16} aria-hidden="true" />
      )}
      <span className="ml-1">{isDownloading ? "Downloading..." : "Download"}</span>
    </button>
  );
}
