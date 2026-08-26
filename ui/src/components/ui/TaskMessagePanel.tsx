"use client";

import type { LucideIcon } from "lucide-react";
import { AlertCircle, Info } from "lucide-react";

import { useToast } from "@/components/ui/Toast";

interface TaskMessagePanelProps {
  status: string | null | undefined;
  message: string | null | undefined;
  stackTrace?: string | null;
  /** Render "No error message recorded." instead of nothing when a failed task has no message. */
  showEmptyFallback?: boolean;
  className?: string;
}

interface MessageTone {
  title: string;
  Icon: LucideIcon;
  frameClass: string;
  headerClass: string;
  bodyClass: string;
  stackHeaderClass: string;
  stackBodyClass: string;
}

/** Map a task status to the frame, header, and body classes the panel renders with. */
function toneFor(status: string | null | undefined): MessageTone {
  if (status === "failed") {
    return {
      title: "Error Log",
      Icon: AlertCircle,
      frameClass: "border-error/40",
      headerClass: "bg-error/10 text-error",
      bodyClass: "bg-error/5 text-error/80",
      stackHeaderClass: "border-error/20 bg-error/5 text-error/60",
      stackBodyClass: "bg-error/5 text-error/60",
    };
  }
  if (status === "cancelled") {
    return {
      title: "Message",
      Icon: Info,
      frameClass: "border-warning/40",
      headerClass: "bg-warning/10 text-warning",
      bodyClass: "bg-warning/5 text-base-content/70",
      stackHeaderClass: "border-warning/20 bg-warning/5 text-base-content/50",
      stackBodyClass: "bg-warning/5 text-base-content/60",
    };
  }
  return {
    title: "Message",
    Icon: Info,
    frameClass: "border-base-300",
    headerClass: "bg-base-200 text-base-content/70",
    bodyClass: "bg-base-100 text-base-content/70",
    stackHeaderClass: "border-base-300 bg-base-100 text-base-content/50",
    stackBodyClass: "bg-base-100 text-base-content/60",
  };
}

/**
 * Renders a task's status message with status-driven styling.
 *
 * Keeping the status check inside this component is the point: every call site
 * gets the same failed / cancelled / neutral treatment, so a success message can
 * no longer end up inside an error-looking frame.
 */
export function TaskMessagePanel({
  status,
  message,
  stackTrace,
  showEmptyFallback = false,
  className = "",
}: TaskMessagePanelProps) {
  const toast = useToast();
  const trimmedMessage = message?.trim();
  const trimmedStackTrace = stackTrace?.trim();

  if (!trimmedMessage && !trimmedStackTrace) {
    if (showEmptyFallback && status === "failed") {
      return (
        <div
          className={`rounded-lg border border-base-300 p-3 text-sm text-base-content/60 ${className}`}
        >
          No error message recorded.
        </div>
      );
    }
    return null;
  }

  const tone = toneFor(status);
  const { Icon } = tone;

  const copyStackTrace = async () => {
    try {
      await navigator.clipboard.writeText(trimmedStackTrace ?? "");
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Failed to copy to clipboard");
    }
  };

  return (
    <div className={`overflow-hidden rounded-lg border ${tone.frameClass} ${className}`}>
      <div
        className={`flex items-center gap-2 px-3 py-2 text-sm font-semibold ${tone.headerClass}`}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" />
        {tone.title}
      </div>
      {trimmedMessage && (
        <pre
          className={`whitespace-pre-wrap break-all px-3 py-3 font-mono text-xs ${tone.bodyClass}`}
        >
          {trimmedMessage}
        </pre>
      )}
      {trimmedStackTrace && (
        <>
          <div
            className={`flex items-center justify-between border-t px-3 py-1 text-xs font-semibold ${tone.stackHeaderClass}`}
          >
            Stack Trace
            <button type="button" className="btn btn-ghost btn-xs" onClick={copyStackTrace}>
              Copy
            </button>
          </div>
          <pre
            className={`max-h-96 overflow-auto whitespace-pre-wrap break-all px-3 py-3 font-mono text-xs ${tone.stackBodyClass}`}
          >
            {trimmedStackTrace}
          </pre>
        </>
      )}
    </div>
  );
}
