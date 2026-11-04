"use client";

import { Bot } from "lucide-react";

import { useOptionalChatDock, type InvestigationSurface } from "@/contexts/ChatDockContext";
import type { InvestigationTarget } from "@/types/copilotChat";

interface InvestigateWithAiButtonProps {
  /** The failure; without an execution there is nothing to investigate and nothing renders. */
  target: InvestigationTarget | null;
  /** The floating window above a modal, or the docked sidebar on a page. */
  surface?: InvestigationSurface;
  size?: "xs" | "sm";
  className?: string;
}

/**
 * One click from a failure's log to an AI investigation of it: the chat opens
 * with the recorded logs, identifiers and the source the assistant can read,
 * and asks for an evidence-backed cause. Clicking again resumes that chat.
 */
export function InvestigateWithAiButton({
  target,
  surface = "sidebar",
  size = "xs",
  className = "",
}: InvestigateWithAiButtonProps) {
  const dock = useOptionalChatDock();
  if (!dock || !target?.executionId) return null;

  return (
    <button
      type="button"
      className={`btn btn-${size} shrink-0 gap-1 whitespace-nowrap ${className}`}
      onClick={(event) => {
        // Inside a clickable card, the click must not also select the card.
        event.stopPropagation();
        dock.investigate(target, surface);
      }}
      title="Investigate this failure with the logs and the QDash source"
    >
      <Bot className={size === "xs" ? "h-3 w-3" : "h-4 w-4"} aria-hidden="true" />
      Investigate with AI
    </button>
  );
}
