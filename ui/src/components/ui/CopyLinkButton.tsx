"use client";

import { Link as LinkIcon } from "lucide-react";

import { useToast } from "@/components/ui/Toast";
import { copyText } from "@/lib/utils/clipboard";

/** Copies a link to the clipboard and reports the outcome in a toast. */
export function CopyLinkButton({
  url,
  label = "Copy link",
  className = "btn btn-ghost btn-sm",
  disabled = false,
}: {
  /** The link to copy; the current page when omitted. */
  url?: string;
  label?: string;
  className?: string;
  disabled?: boolean;
}) {
  const toast = useToast();
  const handleCopy = async () => {
    try {
      await copyText(url ?? window.location.href);
      toast.success("Link copied");
    } catch {
      toast.error("Failed to copy the link");
    }
  };
  return (
    <button type="button" className={className} onClick={handleCopy} disabled={disabled}>
      <LinkIcon data-icon="inline-start" aria-hidden="true" />
      {label}
    </button>
  );
}
