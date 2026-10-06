"use client";

import type { ReactNode } from "react";
import { FlaskConical, History, MessageSquare } from "lucide-react";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import { ContextChip } from "@/components/features/chat/ChatThread";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

const RECENT_LIMIT = 8;

/** Small square icon button with a tooltip, for chat surface headers. */
export function SurfaceButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          className="btn btn-ghost btn-xs btn-square text-base-content/60 hover:text-base-content"
          aria-label={label}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

/** Title of the active chat, with its result badge when it has one. */
export function SurfaceTitle() {
  const { activeSession } = useCopilotChatSessionContext();
  const hasMessages = Boolean(activeSession?.messages.length);
  return (
    <div className="min-w-0 flex-1">
      <div className="text-sm font-semibold truncate">
        {activeSession && hasMessages ? activeSession.title : "Ask AI"}
      </div>
      {activeSession?.context && hasMessages && (
        <div className="mt-0.5">
          <ContextChip context={activeSession.context} />
        </div>
      )}
    </div>
  );
}

/** Jump back to a recent chat without leaving the page. Full history lives on /chat. */
export function RecentChatsMenu({ onOpenAll }: { onOpenAll: () => void }) {
  const { sessions, activeSessionId, switchSession } = useCopilotChatSessionContext();
  const recent = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, RECENT_LIMIT);

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-square text-base-content/60 hover:text-base-content"
              aria-label="Recent chats"
            >
              <History className="w-3.5 h-3.5" />
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">Recent chats</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-72 max-h-96">
        <DropdownMenuLabel>Recent chats</DropdownMenuLabel>
        {recent.length === 0 && (
          <div className="px-2.5 py-2 text-xs text-base-content/45">No chats yet</div>
        )}
        {recent.map((session) => (
          <DropdownMenuItem
            key={session.id}
            onSelect={() => switchSession(session.id)}
            className={session.id === activeSessionId ? "bg-base-200" : ""}
          >
            {session.context ? (
              <FlaskConical className="w-3.5 h-3.5 shrink-0 text-primary" />
            ) : (
              <MessageSquare className="w-3.5 h-3.5 shrink-0 text-base-content/45" />
            )}
            <span className="truncate">{session.title}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onOpenAll}>
          <span className="text-xs text-base-content/70">View all in AI Chat</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
