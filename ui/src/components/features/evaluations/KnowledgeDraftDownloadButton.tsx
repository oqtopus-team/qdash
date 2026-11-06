"use client";

import { Download } from "lucide-react";
import { useState } from "react";

import { downloadKnowledgeDraftArchive } from "@/client/evaluation/evaluation";
import { useToast } from "@/components/ui/Toast";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { saveBlob } from "@/lib/utils/download";

/** Save the zip a run's knowledge draft was uploaded as, to inspect or reuse it. */
export function KnowledgeDraftDownloadButton({
  draftId,
  filename,
}: {
  draftId: string;
  filename: string;
}) {
  const toast = useToast();
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    setDownloading(true);
    try {
      const response = await downloadKnowledgeDraftArchive(draftId);
      saveBlob(response.data, filename);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not download the knowledge draft"));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-xs btn-outline gap-1"
      onClick={download}
      disabled={downloading}
      title="The zip this run was evaluated against, as uploaded"
    >
      {downloading ? (
        <span className="loading loading-spinner loading-xs" />
      ) : (
        <Download className="h-3 w-3" />
      )}
      Download zip
    </button>
  );
}
