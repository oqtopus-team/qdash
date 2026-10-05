"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  LineChart,
  ListChecks,
  PanelLeftOpen,
  Sparkles,
  SquarePen,
  GitCompare,
  History,
} from "lucide-react";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { useCopilotChat } from "@/hooks/useCopilotChat";
import { ChatComposer, type ChatComposerHandle } from "@/components/features/chat/ChatComposer";
import {
  AssistantMessage,
  LiveAssistantMessage,
  UserMessage,
} from "@/components/features/chat/ChatMessages";
import { ChatSidebar } from "@/components/features/chat/ChatSidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import {
  buildChatModelOptions,
  getStoredChatModelKey,
  resolveChatModelOption,
  setStoredChatModelKey,
} from "@/lib/copilotModels";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SUGGESTED_QUESTIONS = [
  { text: "Show T1 trend for Q00", Icon: LineChart },
  { text: "What are Q00's current parameters?", Icon: ListChecks },
  { text: "Compare T1 and T2 for Q01", Icon: GitCompare },
  { text: "Show gate fidelity history for Q00", Icon: History },
];

const MOBILE_BREAKPOINT_PX = 768;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScrollToBottomButton() {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();
  if (isAtBottom) return null;
  return (
    <button
      type="button"
      onClick={() => scrollToBottom()}
      className="absolute bottom-3 left-1/2 -translate-x-1/2 btn btn-circle btn-sm bg-base-100 border border-base-300 shadow-md hover:bg-base-200 animate-fade-in-up"
      aria-label="Scroll to bottom"
    >
      <ArrowDown className="w-4 h-4" />
    </button>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="w-full max-w-2xl mx-auto px-4 text-center">
      <div className="chat-avatar-bot w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-5">
        <Sparkles className="w-6 h-6 text-primary" />
      </div>
      <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight mb-2">
        How can I help with your qubits?
      </h1>
      <p className="text-sm text-base-content/50 mb-8">
        Ask about calibration data — I can fetch parameters, analyze trends, run Python and plot
        charts.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
        {SUGGESTED_QUESTIONS.map(({ text, Icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className="chat-suggestion-card group"
          >
            <Icon className="w-4 h-4 text-base-content/40 group-hover:text-primary transition-colors shrink-0" />
            <span className="text-sm leading-snug flex-1">{text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CopilotChatPage() {
  const [selectedModelKey, setSelectedModelKey] = useState(getStoredChatModelKey);
  const { data: copilotConfigResponse } = useGetCopilotConfig();
  const modelOptions = useMemo(
    () => buildChatModelOptions(copilotConfigResponse?.data ?? null),
    [copilotConfigResponse?.data],
  );
  const selectedModel = resolveChatModelOption(modelOptions, selectedModelKey);
  const modelOverride = selectedModel?.model ?? null;

  const handleModelChange = (key: string) => {
    setSelectedModelKey(key);
    setStoredChatModelKey(key);
  };

  const {
    sessions,
    activeSession,
    activeSessionId,
    isLoadingSessions,
    isLoading,
    statusMessage,
    liveTurn,
    createSession,
    switchSession,
    deleteSession,
    sendMessage,
    stop,
    retryLast,
  } = useCopilotChat({ modelOverride });

  const [input, setInput] = useState("");
  const [showSidebar, setShowSidebar] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const composerRef = useRef<ChatComposerHandle>(null);

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

  const messages = useMemo(() => activeSession?.messages ?? [], [activeSession?.messages]);
  const isEmpty = messages.length === 0 && !liveTurn;
  const isLoadingMessages = activeSession !== null && !activeSession.messagesLoaded;

  // Focus input on session switch
  useEffect(() => {
    composerRef.current?.focus();
  }, [activeSessionId]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;
      setInput("");
      sendMessage(trimmed);
    },
    [isLoading, sendMessage],
  );

  const handleNewChat = useCallback(() => {
    if (activeSession && activeSession.messages.length === 0) {
      composerRef.current?.focus();
      return;
    }
    createSession();
    if (isMobile) setShowSidebar(false);
  }, [activeSession, createSession, isMobile]);

  const handleSelect = useCallback(
    (id: string) => {
      switchSession(id);
      if (isMobile) setShowSidebar(false);
    },
    [isMobile, switchSession],
  );

  // Keyboard shortcuts: Esc stops streaming, Ctrl/Cmd+Shift+O starts a new chat.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isLoading) {
        e.preventDefault();
        stop();
      } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleNewChat, isLoading, stop]);

  const lastIndex = messages.length - 1;

  const composer = (
    <ChatComposer
      ref={composerRef}
      value={input}
      onChange={setInput}
      onSubmit={() => send(input)}
      onStop={stop}
      isStreaming={isLoading}
      modelOptions={modelOptions}
      selectedModelKey={selectedModel.key}
      onModelChange={handleModelChange}
    />
  );

  return (
    <div className="relative flex h-[calc(100vh-64px)] bg-base-100 overflow-hidden">
      {/* Sidebar */}
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

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center gap-1 px-3 h-12 shrink-0">
          {!showSidebar && (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => setShowSidebar(true)}
                    className="btn btn-ghost btn-sm btn-square"
                    aria-label="Open sidebar"
                  >
                    <PanelLeftOpen className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>Open sidebar</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={handleNewChat}
                    className="btn btn-ghost btn-sm btn-square"
                    aria-label="New chat"
                  >
                    <SquarePen className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>New chat</TooltipContent>
              </Tooltip>
            </>
          )}
          <h2 className="ml-1 text-sm font-medium truncate text-base-content/80">
            {activeSession && !isEmpty ? activeSession.title : "AI Chat"}
          </h2>
        </header>

        {isEmpty && !isLoadingMessages ? (
          /* Empty state: greeting and composer centered, ChatGPT-style */
          <div className="flex-1 flex flex-col items-center justify-center pb-[10vh] overflow-y-auto">
            <EmptyState onPick={send} />
            <div className="w-full max-w-3xl px-4 mt-8">{composer}</div>
          </div>
        ) : (
          <>
            <StickToBottom className="relative flex-1 min-h-0" resize="smooth" initial="instant">
              <StickToBottom.Content className="max-w-3xl mx-auto px-4 pt-4 pb-10 space-y-8">
                {isLoadingMessages && (
                  <div className="space-y-6 pt-4" aria-label="Loading messages">
                    <div className="ml-auto h-10 w-1/2 rounded-3xl bg-base-content/5 animate-pulse" />
                    <div className="h-24 w-5/6 rounded-xl bg-base-content/5 animate-pulse" />
                  </div>
                )}
                {messages.map((msg, idx) =>
                  msg.role === "user" ? (
                    <UserMessage key={idx} message={msg} />
                  ) : (
                    <AssistantMessage
                      key={idx}
                      message={msg}
                      isLast={idx === lastIndex && !liveTurn}
                      canRetry={!isLoading}
                      onRetry={retryLast}
                    />
                  ),
                )}
                {liveTurn && <LiveAssistantMessage turn={liveTurn} statusMessage={statusMessage} />}
              </StickToBottom.Content>
              <ScrollToBottomButton />
            </StickToBottom>

            <div className="shrink-0 px-4 pb-3">
              <div className="max-w-3xl mx-auto">
                {composer}
                <p className="text-[11px] text-base-content/35 text-center mt-2">
                  AI can make mistakes. Verify important calibration values.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
