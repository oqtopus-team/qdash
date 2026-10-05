"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { PanelLeftOpen, SquarePen } from "lucide-react";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import { ChatSidebar } from "@/components/features/chat/ChatSidebar";
import {
  ChatThread,
  ContextChip,
  type ChatThreadHandle,
} from "@/components/features/chat/ChatThread";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

const MOBILE_BREAKPOINT_PX = 768;

function HeaderButton({
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
          className="btn btn-ghost btn-sm btn-square"
          aria-label={label}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function CopilotChatPage() {
  const {
    sessions,
    activeSession,
    activeSessionId,
    isLoadingSessions,
    switchSession,
    deleteSession,
  } = useCopilotChatSessionContext();

  const [showSidebar, setShowSidebar] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const threadRef = useRef<ChatThreadHandle>(null);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT_PX - 1}px)`);
    const apply = () => {
      setIsMobile(mq.matches);
      if (mq.matches) setShowSidebar(false);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const handleNewChat = useCallback(() => {
    if (activeSession && activeSession.messages.length === 0 && !activeSession.context) {
      threadRef.current?.focus();
      return;
    }
    // The page starts from the greeting; the session is created on first send.
    switchSession(null);
    if (isMobile) setShowSidebar(false);
  }, [activeSession, isMobile, switchSession]);

  const handleSelect = useCallback(
    (id: string) => {
      switchSession(id);
      if (isMobile) setShowSidebar(false);
    },
    [isMobile, switchSession],
  );

  // Ctrl/Cmd+Shift+O starts a new chat.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleNewChat]);

  const hasMessages = Boolean(activeSession && activeSession.messages.length > 0);

  return (
    <div className="relative flex h-[calc(100vh-64px)] bg-base-100 overflow-hidden">
      {showSidebar && (
        <>
          {isMobile && (
            <button
              type="button"
              aria-label="Close sidebar"
              className="absolute inset-0 z-20 bg-black/30 animate-fade-in-up"
              onClick={() => setShowSidebar(false)}
            />
          )}
          <div className={isMobile ? "absolute inset-y-0 left-0 z-30 shadow-xl" : "contents"}>
            <ChatSidebar
              sessions={sessions}
              activeSessionId={activeSessionId}
              isLoading={isLoadingSessions}
              onNewChat={handleNewChat}
              onSelect={handleSelect}
              onDelete={deleteSession}
              onClose={() => setShowSidebar(false)}
            />
          </div>
        </>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center gap-1 px-3 h-12 shrink-0 min-w-0">
          {!showSidebar && (
            <>
              <HeaderButton label="Open sidebar" onClick={() => setShowSidebar(true)}>
                <PanelLeftOpen className="w-4 h-4" />
              </HeaderButton>
              <HeaderButton label="New chat" onClick={handleNewChat}>
                <SquarePen className="w-4 h-4" />
              </HeaderButton>
            </>
          )}
          <h2 className="ml-1 text-sm font-medium truncate text-base-content/80">
            {activeSession && hasMessages ? activeSession.title : "AI Chat"}
          </h2>
          {activeSession?.context && hasMessages && (
            <span className="ml-1 min-w-0 shrink">
              <ContextChip context={activeSession.context} />
            </span>
          )}
        </header>

        <ChatThread ref={threadRef} variant="page" />
      </div>
    </div>
  );
}
