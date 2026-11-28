"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { PanelLeftOpen, Share2, SquarePen } from "lucide-react";
import { useOptionalChatDock } from "@/contexts/ChatDockContext";
import { useAgentChatSessionContext } from "@/contexts/AgentChatSessionContext";
import { withViewTransition } from "@/lib/viewTransition";
import { ChatSidebar, RenameInput, SessionMenu } from "@/components/features/chat/ChatSidebar";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ChatShareDialog } from "@/components/features/chat/ChatShareDialog";
import { ChatThread, type ChatThreadHandle } from "@/components/features/chat/ChatThread";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { ChatStatusLine, useChatStatus } from "@/components/features/chat/ChatTurnStatus";

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

export function AgentChatPage() {
  const {
    sessions,
    activeSession,
    activeSessionId,
    isLoadingSessions,
    runs,
    detachedTurns,
    switchSession,
    deleteSession,
    renameSession,
  } = useAgentChatSessionContext();
  const endInvestigation = useOptionalChatDock()?.endInvestigation;
  // Chats with an answer going, streamed here or not (being restored, another project).
  const runningSessionIds = [...Object.keys(runs), ...Object.keys(detachedTurns ?? {})];
  const status = useChatStatus();

  const [showSidebar, setShowSidebar] = useState(true);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [sharing, setSharing] = useState(false);
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
    if (
      activeSession &&
      activeSession.messages.length === 0 &&
      !activeSession.context &&
      !activeSession.investigation
    ) {
      threadRef.current?.focus();
      return;
    }
    endInvestigation?.(activeSession?.id);
    // The page starts from the greeting; the session is created on first send.
    withViewTransition(() => switchSession(null));
    if (isMobile) setShowSidebar(false);
  }, [activeSession, endInvestigation, isMobile, switchSession]);

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
    // Fill the area AppLayout leaves under the navbar; on phones that excludes the tab bar,
    // which a fixed viewport height would push the composer under.
    <div className="relative flex h-full bg-base-100 overflow-hidden">
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
              runningSessionIds={runningSessionIds}
              isLoading={isLoadingSessions}
              onNewChat={handleNewChat}
              onSelect={handleSelect}
              onRename={renameSession}
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
          {activeSession && hasMessages ? (
            renaming ? (
              <RenameInput
                key={activeSession.id}
                initial={activeSession.title}
                onCommit={(title) => {
                  renameSession(activeSession.id, title);
                  setRenaming(false);
                }}
                onCancel={() => setRenaming(false)}
                className="chat-sidebar-rename ml-1 max-w-sm flex-1 text-sm font-medium"
              />
            ) : (
              <div className="ml-1 flex items-center gap-1 min-w-0">
                <h2 className="text-sm font-medium truncate text-base-content/80">
                  {activeSession.title}
                </h2>
                <SessionMenu
                  session={activeSession}
                  onRename={() => setRenaming(true)}
                  onDelete={() => setConfirmDelete(true)}
                  className="opacity-60 hover:opacity-100"
                />
                <ChatStatusLine status={status} className="ml-2" />
              </div>
            )
          ) : (
            <h2 className="ml-1 text-sm font-medium truncate text-base-content/80">Agent</h2>
          )}
          {activeSession && hasMessages && activeSession.messagesLoaded && (
            <button
              type="button"
              className="btn btn-ghost btn-sm ml-auto shrink-0"
              onClick={() => setSharing(true)}
            >
              <Share2 data-icon="inline-start" aria-hidden="true" />
              Share
            </button>
          )}
        </header>

        <ChatThread ref={threadRef} variant="page" />
      </div>

      {activeSession && (
        <ChatShareDialog
          open={sharing}
          onOpenChange={setSharing}
          sessionId={activeSession.id}
          title={activeSession.title}
          running={runningSessionIds.includes(activeSession.id)}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete chat?"
        description={
          <>
            This will delete <strong>{activeSession?.title}</strong>. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          if (activeSession) deleteSession(activeSession.id);
          setConfirmDelete(false);
        }}
        onOpenChange={(open) => !open && setConfirmDelete(false)}
      />
    </div>
  );
}
