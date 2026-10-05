"use client";

import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import type { AnalysisContext } from "@/types/copilotChat";

/**
 * Where the in-app chat is shown outside the /chat page: the docked sidebar or
 * the floating window that sits above modals. Both render the active session
 * of CopilotChatSessionProvider, so a chat moves between them mid-stream.
 */
interface AnalysisChatContextValue {
  /** Resume the chat about this result, or start one, without opening a surface. */
  focusAnalysisChat: (context: AnalysisContext) => void;
  isOpen: boolean;
  openAnalysisChat: (context: AnalysisContext) => void;
  openGeneralChat: () => void;
  /** Show the active session in the sidebar. */
  openSidebar: () => void;
  closeAnalysisChat: () => void;

  miniChat: { isOpen: boolean };
  openMiniChat: (context: AnalysisContext) => void;
  closeMiniChat: () => void;
}

const AnalysisChatCtx = createContext<AnalysisChatContextValue | null>(null);

export function AnalysisChatProvider({ children }: { children: React.ReactNode }) {
  const { activeSession, findSessionByContext, switchSession, createNewSession } =
    useCopilotChatSessionContext();
  const [isOpen, setIsOpen] = useState(false);
  const [miniOpen, setMiniOpen] = useState(false);

  /** Resume the chat about this result, or start one. */
  const focusContext = useCallback(
    (context: AnalysisContext) => {
      const existing = findSessionByContext(context);
      if (existing) switchSession(existing.id);
      else createNewSession(context);
    },
    [createNewSession, findSessionByContext, switchSession],
  );

  const openAnalysisChat = useCallback(
    (context: AnalysisContext) => {
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

  const closeAnalysisChat = useCallback(() => setIsOpen(false), []);

  const openMiniChat = useCallback(
    (context: AnalysisContext) => {
      focusContext(context);
      setMiniOpen(true);
    },
    [focusContext],
  );

  const closeMiniChat = useCallback(() => setMiniOpen(false), []);

  const value = useMemo(
    () => ({
      focusAnalysisChat: focusContext,
      isOpen,
      openAnalysisChat,
      openGeneralChat,
      openSidebar,
      closeAnalysisChat,
      miniChat: { isOpen: miniOpen },
      openMiniChat,
      closeMiniChat,
    }),
    [
      focusContext,
      isOpen,
      openAnalysisChat,
      openGeneralChat,
      openSidebar,
      closeAnalysisChat,
      miniOpen,
      openMiniChat,
      closeMiniChat,
    ],
  );

  return <AnalysisChatCtx.Provider value={value}>{children}</AnalysisChatCtx.Provider>;
}

export function useAnalysisChatContext() {
  const ctx = useContext(AnalysisChatCtx);
  if (!ctx) {
    throw new Error("useAnalysisChatContext must be used within AnalysisChatProvider");
  }
  return ctx;
}
