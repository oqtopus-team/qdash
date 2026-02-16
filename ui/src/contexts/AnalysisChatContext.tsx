"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import type { AnalysisContext } from "@/hooks/useAnalysisChat";
import type { ChatMessage } from "@/hooks/useAnalysisChat";

// Module-level session store — survives re-renders and context changes
const sessionStore = new Map<string, ChatMessage[]>();

function makeSessionKey(ctx: AnalysisContext): string {
  return `${ctx.taskId}:${ctx.executionId}:${ctx.qid}`;
}

interface AnalysisChatContextValue {
  isOpen: boolean;
  context: AnalysisContext | null;
  openAnalysisChat: (context: AnalysisContext) => void;
  closeAnalysisChat: () => void;
  toggleAnalysisChat: () => void;
  clearCurrentSession: () => void;
  getSessionMessages: (ctx: AnalysisContext) => ChatMessage[];
  setSessionMessages: (ctx: AnalysisContext, messages: ChatMessage[]) => void;
}

const AnalysisChatCtx = createContext<AnalysisChatContextValue | null>(null);

export function AnalysisChatProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [context, setContext] = useState<AnalysisContext | null>(null);

  const openAnalysisChat = useCallback((ctx: AnalysisContext) => {
    setContext(ctx);
    setIsOpen(true);
  }, []);

  const closeAnalysisChat = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggleAnalysisChat = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const clearCurrentSession = useCallback(() => {
    if (context) {
      sessionStore.delete(makeSessionKey(context));
    }
  }, [context]);

  const getSessionMessages = useCallback((ctx: AnalysisContext) => {
    return sessionStore.get(makeSessionKey(ctx)) || [];
  }, []);

  const setSessionMessages = useCallback(
    (ctx: AnalysisContext, messages: ChatMessage[]) => {
      sessionStore.set(makeSessionKey(ctx), messages);
    },
    [],
  );

  return (
    <AnalysisChatCtx.Provider
      value={{
        isOpen,
        context,
        openAnalysisChat,
        closeAnalysisChat,
        toggleAnalysisChat,
        clearCurrentSession,
        getSessionMessages,
        setSessionMessages,
      }}
    >
      {children}
    </AnalysisChatCtx.Provider>
  );
}

export function useAnalysisChatContext() {
  const ctx = useContext(AnalysisChatCtx);
  if (!ctx) {
    throw new Error(
      "useAnalysisChatContext must be used within AnalysisChatProvider",
    );
  }
  return ctx;
}
