"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { buildForumThreadZip } from "@/lib/forum/exportThreadZip";
import type { ForumPostResponse } from "@/schemas";
import { saveBlob } from "@/lib/utils/download";

interface ForumThreadDownloadButtonProps {
  post: ForumPostResponse;
  replies: ForumPostResponse[];
  disabled?: boolean;
}

export function ForumThreadDownloadButton({
  post,
  replies,
  disabled = false,
}: ForumThreadDownloadButtonProps) {
  const [isExporting, setIsExporting] = useState(false);

  const handleDownload = async () => {
    setIsExporting(true);
    try {
      const { filename, blob } = await buildForumThreadZip(post, replies);

      saveBlob(blob, filename);
    } catch {
      toast.error("Failed to export thread");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-square shrink-0 text-base-content/40 hover:text-primary"
          onClick={handleDownload}
          disabled={disabled || isExporting}
          aria-label="Download thread"
        >
          {isExporting ? (
            <span className="loading loading-spinner loading-xs" />
          ) : (
            <Download className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent>Download as Markdown + assets (.zip)</TooltipContent>
    </Tooltip>
  );
}
