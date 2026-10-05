"use client";

import { useMemo, useState } from "react";
import {
  FlaskConical,
  MessageSquare,
  PanelLeftClose,
  Search,
  SquarePen,
  Trash2,
} from "lucide-react";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import type { CopilotSession } from "@/hooks/useCopilotChat";

const DAY_MS = 86_400_000;

function groupLabel(ts: number, now: Date): string {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (ts >= startOfToday) return "Today";
  if (ts >= startOfToday - DAY_MS) return "Yesterday";
  if (ts >= startOfToday - 7 * DAY_MS) return "Previous 7 days";
  if (ts >= startOfToday - 30 * DAY_MS) return "Previous 30 days";
  return "Older";
}

function groupSessions(sessions: CopilotSession[]): [string, CopilotSession[]][] {
  const now = new Date();
  const groups = new Map<string, CopilotSession[]>();
  for (const session of [...sessions].sort((a, b) => b.updatedAt - a.updatedAt)) {
    const label = groupLabel(session.updatedAt, now);
    const list = groups.get(label);
    if (list) list.push(session);
    else groups.set(label, [session]);
  }
  return [...groups.entries()];
}

interface ChatSidebarProps {
  sessions: CopilotSession[];
  activeSessionId: string | null;
  isLoading: boolean;
  onNewChat: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  isLoading,
  onNewChat,
  onSelect,
  onDelete,
  onClose,
}: ChatSidebarProps) {
  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<CopilotSession | null>(null);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q ? sessions.filter((s) => s.title.toLowerCase().includes(q)) : sessions;
    return groupSessions(filtered);
  }, [sessions, query]);

  return (
    <aside className="chat-sidebar">
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onClose}
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Close sidebar"
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent>Close sidebar</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onNewChat}
              className="btn btn-ghost btn-sm btn-square"
              aria-label="New chat"
            >
              <SquarePen className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent>New chat (Ctrl+Shift+O)</TooltipContent>
        </Tooltip>
      </div>

      <div className="px-3 pb-2">
        <label className="chat-sidebar-search">
          <Search className="w-3.5 h-3.5 text-base-content/40" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats"
            className="flex-1 bg-transparent outline-none text-sm min-w-0"
          />
        </label>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-3" aria-label="Chat history">
        {isLoading && sessions.length === 0 && (
          <div className="space-y-2 px-2 pt-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-8 rounded-lg bg-base-content/5 animate-pulse" />
            ))}
          </div>
        )}
        {groups.map(([label, items]) => (
          <section key={label} className="mt-3 first:mt-1">
            <h3 className="px-2.5 pb-1 text-[11px] font-semibold text-base-content/45">{label}</h3>
            <ul className="space-y-px">
              {items.map((session) => {
                const active = session.id === activeSessionId;
                return (
                  <li key={session.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(session.id)}
                      className={`chat-sidebar-item ${active ? "chat-sidebar-item-active" : ""}`}
                      aria-current={active ? "page" : undefined}
                      title={session.title}
                    >
                      {session.context && (
                        <FlaskConical
                          className="w-3.5 h-3.5 mr-1.5 shrink-0 text-primary/70"
                          aria-label="About a calibration result"
                        />
                      )}
                      <span className="truncate">{session.title}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPendingDelete(session)}
                      className={`absolute right-1 top-1/2 -translate-y-1/2 btn btn-ghost btn-xs btn-square text-base-content/40 hover:text-error ${
                        active
                          ? "opacity-100"
                          : "opacity-0 group-hover:opacity-100 focus:opacity-100"
                      }`}
                      aria-label={`Delete ${session.title}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
        {!isLoading && groups.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-xs text-base-content/40">
            <MessageSquare className="w-5 h-5" />
            {query ? "No matching chats" : "No chats yet"}
          </div>
        )}
      </nav>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete chat?"
        description={
          <>
            This will delete <strong>{pendingDelete?.title}</strong>. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          if (pendingDelete) onDelete(pendingDelete.id);
          setPendingDelete(null);
        }}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      />
    </aside>
  );
}
