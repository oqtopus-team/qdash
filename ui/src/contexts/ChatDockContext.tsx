"use client";

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import type { EditProposal, PageContext, TaskChatContext } from "@/types/copilotChat";
import { matchesEditTarget } from "@/lib/copilotEditTarget";

/**
 * What a page tells the chat about itself. A page registers one while it is
 * mounted; without one the dock still names the route and title, so the
 * assistant always knows where the user is.
 */
export interface PageContextProvider {
  /** Read at the moment a turn is sent, so an editor's buffer is current. */
  current(): PageContext | null;
  /** Replace the page's editable code, for an edit the assistant proposed. */
  applyCode?(code: string): void;
}

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

  /** Tell the chat what this page shows; returns the unregister function for unmount. */
  registerPage: (provider: PageContextProvider) => () => void;
  /** The page a turn sent now would describe; null on the chat page itself. */
  currentPage: () => PageContext | null;
  /** Hand proposed code to the open editor; false when no page takes code. */
  applyCode: (edit: EditProposal) => boolean;
  canApplyCode: boolean;
}

const ChatDockCtx = createContext<ChatDockValue | null>(null);

export function ChatDockProvider({ children }: { children: React.ReactNode }) {
  const { activeSession, findSessionByContext, switchSession, createNewSession } =
    useCopilotChatSessionContext();
  const [isOpen, setIsOpen] = useState(false);
  const [miniOpen, setMiniOpen] = useState(false);
  const pathname = usePathname();
  const pageProvider = useRef<PageContextProvider | null>(null);
  const [canApplyCode, setCanApplyCode] = useState(false);

  const registerPage = useCallback((provider: PageContextProvider) => {
    pageProvider.current = provider;
    setCanApplyCode(Boolean(provider.applyCode));
    return () => {
      if (pageProvider.current !== provider) return;
      pageProvider.current = null;
      setCanApplyCode(false);
    };
  }, []);

  const currentPage = useCallback((): PageContext | null => {
    // The chat page is the chat; there is nothing else on it to describe.
    if (!pathname || pathname.startsWith("/chat")) return null;
    const page = pageProvider.current?.current();
    if (page) return page;
    return { path: pathname, title: typeof document === "undefined" ? "" : document.title };
  }, [pathname]);

  const applyCode = useCallback((edit: EditProposal): boolean => {
    const provider = pageProvider.current;
    if (!provider?.applyCode || !matchesEditTarget(edit, provider.current())) return false;
    provider.applyCode(edit.code);
    return true;
  }, []);

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
      registerPage,
      currentPage,
      applyCode,
      canApplyCode,
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
      registerPage,
      currentPage,
      applyCode,
      canApplyCode,
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

/** The dock when there is one; null where the chat renders without it (tests, isolated pages). */
export function useOptionalChatDock(): ChatDockValue | null {
  return useContext(ChatDockCtx);
}
