"use client";

import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import type { TaskChatContext } from "@/types/copilotChat";

/**
 * Where the in-app chat is shown outside the /chat page: the docked sidebar or
 * the floating window that sits above modals. Both render the active session
 * of CopilotChatSessionProvider, so a chat moves between them mid-stream.
 */
interface ChatDockValue {
  /** Resume the chat about this result, or start one, without opening a surface. */
  focusTaskChat: (context: TaskChatContext) => void;
  isOpen: boolean;
  openTaskChat: (context: TaskChatContext) => void;
  openGeneralChat: () => void;
  /** Show the active session in the sidebar. */
  openSidebar: () => void;
  closeSidebar: () => void;

  miniChat: { isOpen: boolean };
  openMiniChat: (context: TaskChatContext) => void;
  /** Show this session in the floating window, e.g. to follow a streaming answer. */
  openMiniChatForSession: (sessionId: string) => void;
  closeMiniChat: () => void;
}

const ChatDockCtx = createContext<ChatDockValue | null>(null);

export function ChatDockProvider({ children }: { children: React.ReactNode }) {
  const { activeSession, findSessionByContext, switchSession, createNewSession } =
    useCopilotChatSessionContext();
  const [isOpen, setIsOpen] = useState(false);
  const [miniOpen, setMiniOpen] = useState(false);

  /** Resume the chat about this result, or start one. */
  const focusContext = useCallback(
    (context: TaskChatContext) => {
      const existing = findSessionByContext(context);
      if (existing) switchSession(existing.id);
      else createNewSession(context);
    },
    [createNewSession, findSessionByContext, switchSession],
  );

  const openTaskChat = useCallback(
    (context: TaskChatContext) => {
      focusContext(context);
      setMiniOpen(false);
      setIsOpen(true);
    },
    [focusContext],
  );

  const openGeneralChat = useCallback(() => {
    // Keep the chat the user was in; start fresh only when there is none or it
    // is about a specific result.
    if (!activeSession || activeSession.context) createNewSession(null);
    setIsOpen(true);
  }, [activeSession, createNewSession]);

  const openSidebar = useCallback(() => {
    setMiniOpen(false);
    setIsOpen(true);
  }, []);

  const closeSidebar = useCallback(() => setIsOpen(false), []);

  const openMiniChat = useCallback(
    (context: TaskChatContext) => {
      focusContext(context);
      setMiniOpen(true);
    },
    [focusContext],
  );

  const openMiniChatForSession = useCallback(
    (sessionId: string) => {
      switchSession(sessionId);
      setIsOpen(false);
      setMiniOpen(true);
    },
    [switchSession],
  );

  const closeMiniChat = useCallback(() => setMiniOpen(false), []);

  const value = useMemo(
    () => ({
      focusTaskChat: focusContext,
      isOpen,
      openTaskChat,
      openGeneralChat,
      openSidebar,
      closeSidebar,
      miniChat: { isOpen: miniOpen },
      openMiniChat,
      openMiniChatForSession,
      closeMiniChat,
    }),
    [
      focusContext,
      isOpen,
      openTaskChat,
      openGeneralChat,
      openSidebar,
      closeSidebar,
      miniOpen,
      openMiniChat,
      openMiniChatForSession,
      closeMiniChat,
    ],
  );

  return <ChatDockCtx.Provider value={value}>{children}</ChatDockCtx.Provider>;
}

export function useChatDock() {
  const ctx = useContext(ChatDockCtx);
  if (!ctx) {
    throw new Error("useChatDock must be used within ChatDockProvider");
  }
  return ctx;
}
