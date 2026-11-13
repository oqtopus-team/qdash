"use client";

import { Bot } from "lucide-react";
import { useState } from "react";

import { useChatDock } from "@/contexts/ChatDockContext";
import { useProject } from "@/contexts/ProjectContext";
import type { TaskChatContext } from "@/types/copilotChat";

import { EvaluationRequestModal } from "./EvaluationRequestModal";

interface AskAiButtonProps {
  taskId: string;
  chipId: string | null | undefined;
  taskName: string;
  qid: string;
  /** The result as a chat context; without it the button only offers evaluations. */
  chatContext?: TaskChatContext | null;
  /** How this surface opens the chat (inline split view, mini window); default: the dock. */
  onChat?: () => void;
  size?: "xs" | "sm";
  variant?: "primary" | "outline";
  className?: string;
  /** Called once an evaluation has been requested, so the host can show it is on its way. */
  onRequested?: () => void;
}

/**
 * The one "Ask AI" entry for a single task result, everywhere a result is
 * shown: the same request modal as the chip page's Evaluate, with the choice
 * of a recorded evaluation (model only or via Copilot) or a chat about the
 * result. A viewer who cannot request evaluations goes straight to the chat.
 */
export function AskAiButton({
  taskId,
  chipId,
  taskName,
  qid,
  chatContext,
  onChat,
  size = "sm",
  variant = "primary",
  className = "",
  onRequested,
}: AskAiButtonProps) {
  const { canEdit } = useProject();
  const { openTaskChat } = useChatDock();
  const [isOpen, setIsOpen] = useState(false);
  const chat = onChat ?? (chatContext ? () => openTaskChat(chatContext) : undefined);
  const missing = [!chipId && "chip", !taskName && "task", !qid && "qid"].filter(Boolean);
  // Spelled out so the modal below sees chipId as a string.
  const ready = !!chipId && !!taskName && !!qid;
  const buttonClass = `btn btn-${size} ${variant === "primary" ? "btn-primary" : "btn-outline"} gap-1 ${className}`;
  const iconClass = size === "xs" ? "h-3 w-3" : "h-4 w-4";

  if (!canEdit) {
    if (!chat) return null;
    return (
      <button type="button" className={buttonClass} onClick={chat} title="Chat about this result">
        <Bot className={iconClass} />
        Ask AI
      </button>
    );
  }

  return (
    <>
      <button
        type="button"
        className={buttonClass}
        onClick={() => setIsOpen(true)}
        disabled={!ready}
        title={
          ready
            ? "Evaluate this result with the calibration evaluation model, or chat about it"
            : `Missing ${missing.join(" / ")}`
        }
      >
        <Bot className={iconClass} />
        Ask AI
      </button>
      {ready && (
        <EvaluationRequestModal
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
          scope={{
            chipId,
            taskName,
            entityType: qid.includes("-") ? "coupling" : "qubit",
            taskIds: [taskId],
            trigger: "single",
          }}
          scopeLabel={`${taskName} · ${qid}`}
          onChat={chat}
          onRequested={onRequested}
        />
      )}
    </>
  );
}
