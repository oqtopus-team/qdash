"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { toast } from "sonner";

import { useChatDock } from "@/contexts/ChatDockContext";
import { useAgentChatSessionContext } from "@/contexts/AgentChatSessionContext";
import type { ChatEventKind, ChatTurnEvent } from "@/types/agentChat";

const CHAT_PAGE = "/chat";

type ToastKind = "success" | "error" | "warning" | "info";

/**
 * What each notable moment says, how it looks, and how long it stays in milliseconds
 * (`Infinity`: until dismissed; Sonner falls back to its default for 0).
 */
const NOTICES: Record<ChatEventKind, { title: string; type: ToastKind; duration: number }> = {
  answer: { title: "Answer ready", type: "success", duration: 8000 },
  approval: { title: "Approval needed", type: "warning", duration: Infinity },
  question: { title: "The assistant asked you a question", type: "warning", duration: Infinity },
  edit: { title: "The assistant proposed a change", type: "info", duration: 8000 },
  expert: { title: "Waiting for the expert's answer", type: "info", duration: 8000 },
  failed: { title: "The answer failed", type: "error", duration: Infinity },
};

/** The toast of one moment of one turn: the same ID updates it instead of adding another. */
export function chatToastId(event: Pick<ChatTurnEvent, "requestId" | "kind">): string {
  return `chat:${event.requestId}:${event.kind}`;
}

/**
 * Tells the user, with a toast, when a chat turn reaches a moment that matters: an answer is
 * ready, it waits for their approval or answer, it proposed a change, it waits for an expert,
 * or it failed. Raised by the turn's own stream once per turn (see `subscribeChatEvents`),
 * never by tool steps or text as they stream, and never for history loaded from the server.
 *
 * A toast is shown only for the signed-in user and the open project the turn belongs to, and
 * not while that chat is on screen in a visible tab. Its **Open chat** action shows that chat;
 * nothing is switched or sent on its own. The chat's own status line stays the lasting record.
 * Toasts go through the app's Sonner toaster (`ToastContainer`) like every other notice.
 */
export function ChatNotifier({
  owner,
  project,
}: {
  owner: string | null | undefined;
  project: string | null | undefined;
}) {
  const { subscribeChatEvents, activeSessionId, switchSession, hasSession } =
    useAgentChatSessionContext();
  const { isOpen, miniChat, openSidebar } = useChatDock();
  const pathname = usePathname();

  // Read by the listener, which is subscribed once.
  const latest = useRef({
    owner,
    project,
    activeSessionId,
    isOpen,
    miniOpen: miniChat.isOpen,
    pathname,
    switchSession,
    hasSession,
    openSidebar,
  });
  latest.current = {
    owner,
    project,
    activeSessionId,
    isOpen,
    miniOpen: miniChat.isOpen,
    pathname,
    switchSession,
    hasSession,
    openSidebar,
  };

  // The toasts still up, by session: opening that chat takes them away.
  const shown = useRef<Map<string, Set<string>>>(new Map());

  useEffect(() => {
    const onScreen = (sessionId: string) => {
      const now = latest.current;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return false;
      if (now.activeSessionId !== sessionId) return false;
      return now.pathname === CHAT_PAGE || now.isOpen || now.miniOpen;
    };
    const openChat = (event: ChatTurnEvent) => {
      const now = latest.current;
      // Another user signed in, or the chat is gone: the toast opens nothing.
      if (
        now.owner !== event.owner ||
        (now.project !== undefined && now.project !== event.projectId) ||
        !now.hasSession(event.sessionId)
      )
        return;
      now.switchSession(event.sessionId);
      if (now.pathname !== CHAT_PAGE && !now.miniOpen) now.openSidebar();
    };
    return subscribeChatEvents((event) => {
      const now = latest.current;
      if (event.owner !== now.owner) return;
      // A turn of another project is not this project's news.
      if (now.project !== undefined && event.projectId !== now.project) return;
      if (onScreen(event.sessionId)) return;
      const notice = NOTICES[event.kind];
      const id = chatToastId(event);
      const ids = shown.current.get(event.sessionId) ?? new Set<string>();
      ids.add(id);
      shown.current.set(event.sessionId, ids);
      toast[notice.type](notice.title, {
        id,
        description: event.detail ? `${event.chatTitle}: ${event.detail}` : event.chatTitle,
        duration: notice.duration,
        // Sonner dismisses the toast after the action runs.
        action: { label: "Open chat", onClick: () => openChat(event) },
      });
    });
  }, [subscribeChatEvents]);

  // The chat came on screen: its toasts said what it now shows itself.
  const visibleSession =
    activeSessionId && (pathname === CHAT_PAGE || isOpen || miniChat.isOpen)
      ? activeSessionId
      : null;
  useEffect(() => {
    if (!visibleSession) return;
    const ids = shown.current.get(visibleSession);
    if (!ids) return;
    shown.current.delete(visibleSession);
    for (const id of ids) toast.dismiss(id);
  }, [visibleSession]);

  return null;
}
