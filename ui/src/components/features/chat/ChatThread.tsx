"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ArrowDown, FlaskConical } from "lucide-react";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { useAuth } from "@/contexts/AuthContext";
import { useChatSuggestions, type ChatSuggestion } from "@/hooks/useChatSuggestions";
import { useCopilotChat } from "@/hooks/useCopilotChat";
import { withViewTransition } from "@/lib/viewTransition";
import { ChatComposer, type ChatComposerHandle } from "@/components/features/chat/ChatComposer";
import { ChatLinkPreviewProvider } from "@/components/features/chat/ChatLinkPreview";
import { QdashBotAvatar } from "@/components/ui/UserAvatar";
import {
  AssistantMessage,
  LiveAssistantMessage,
  UserMessage,
} from "@/components/features/chat/ChatMessages";
import type { AnalysisContext } from "@/types/copilotChat";

/**
 * - page: the /chat page, roomy, greeting centered with the composer
 * - panel: the docked sidebar
 * - compact: the floating window above modals
 */
type ChatThreadVariant = "page" | "panel" | "compact";

/** "CheckT1 · Q00" badge for chats about one result. */
export function ContextChip({ context }: { context: AnalysisContext }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary px-2 py-0.5 text-[11px] font-medium max-w-full"
      title={`${context.taskName} · ${context.qid} · ${context.chipId}`}
    >
      <FlaskConical className="w-3 h-3 shrink-0" />
      <span className="truncate">
        {context.taskName} · {context.qid}
      </span>
    </span>
  );
}

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

function greetingFor(hour: number): string {
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function EmptyState({
  variant,
  context,
  suggestions,
  onPick,
}: {
  variant: ChatThreadVariant;
  context: AnalysisContext | null;
  suggestions: ChatSuggestion[];
  onPick: (text: string) => void;
}) {
  const { user, username } = useAuth();
  const large = variant === "page";
  const name = user?.display_name || username;
  const title = context
    ? "Ask about this result"
    : large
      ? `${greetingFor(new Date().getHours())}${name ? `, ${name}` : ""}`
      : "Ask anything about calibration";

  if (large) {
    return (
      <div className="w-full text-center px-4">
        <QdashBotAvatar size={48} className="mx-auto mb-5 chat-avatar-hero" />
        {context && (
          <div className="mb-3">
            <ContextChip context={context} />
          </div>
        )}
        <h2 className="text-2xl sm:text-[28px] font-medium tracking-tight">{title}</h2>
      </div>
    );
  }

  return (
    <div className="w-full mx-auto px-1">
      {context && (
        <div className="mb-2">
          <ContextChip context={context} />
        </div>
      )}
      <h2 className="text-sm font-semibold mb-1">{title}</h2>
      <p className="text-xs text-base-content/50 mb-4">
        {context
          ? "The result figures are attached to your first question."
          : "I can fetch parameters, analyze trends, run Python and plot charts."}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {(variant === "compact" ? suggestions.slice(0, 3) : suggestions).map(({ text, Icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className="chat-suggestion-pill group"
          >
            <Icon className="w-3.5 h-3.5 text-base-content/40 group-hover:text-primary transition-colors shrink-0" />
            <span className="text-xs leading-snug">{text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Suggestion pills under the composer on the page. */
function SuggestionPills({
  suggestions,
  onPick,
}: {
  suggestions: ChatSuggestion[];
  onPick: (text: string) => void;
}) {
  return (
    <div className="flex flex-wrap justify-center gap-2 mt-4 animate-fade-in-up">
      {suggestions.map(({ text, Icon }) => (
        <button
          key={text}
          type="button"
          onClick={() => onPick(text)}
          className="chat-suggestion-pill group"
        >
          <Icon className="w-3.5 h-3.5 text-base-content/40 group-hover:text-primary transition-colors shrink-0" />
          <span className="text-[13px] leading-snug">{text}</span>
        </button>
      ))}
    </div>
  );
}

export interface ChatThreadHandle {
  focus: () => void;
}

interface ChatThreadProps {
  variant: ChatThreadVariant;
  /** Defaults to the active session. */
  sessionId?: string | null;
}

/** Messages, live answer and composer of one chat, shared by every chat surface. */
export const ChatThread = forwardRef<ChatThreadHandle, ChatThreadProps>(function ChatThread(
  { variant, sessionId },
  ref,
) {
  const {
    session,
    messages,
    isLoadingMessages,
    isStreaming,
    liveTurn,
    statusMessage,
    model,
    send,
    decide,
    stop,
    retryLast,
    editMessage,
    rateAnswer,
  } = useCopilotChat(sessionId);
  const [input, setInput] = useState("");
  const composerRef = useRef<ChatComposerHandle>(null);
  useImperativeHandle(ref, () => ({ focus: () => composerRef.current?.focus() }), []);

  const context = session?.context ?? null;
  const suggestions = useChatSuggestions(Boolean(context));
  const isEmpty = messages.length === 0 && !liveTurn;
  const lastIndex = messages.length - 1;

  // Focus the composer on session switch
  useEffect(() => {
    composerRef.current?.focus();
  }, [session?.id]);

  // Esc stops the answer that is streaming here.
  useEffect(() => {
    if (!isStreaming) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) {
        e.preventDefault();
        stop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isStreaming, stop]);

  const submit = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming || isLoadingMessages) return;
      setInput("");
      // The first send turns the greeting into a thread; morph the mark and
      // the composer into their new places instead of swapping layouts.
      withViewTransition(() => send(trimmed));
    },
    [isLoadingMessages, isStreaming, send],
  );

  const focusComposer = useCallback(() => composerRef.current?.focus(), []);

  const composer = (
    <ChatComposer
      ref={composerRef}
      value={input}
      onChange={setInput}
      onSubmit={() => submit(input)}
      onStop={stop}
      isStreaming={isStreaming}
      disabled={isLoadingMessages}
      placeholder={context ? "Ask about this result..." : "Ask about calibration data..."}
      modelOptions={model.options}
      selectedModelKey={model.selected.key}
      onModelChange={model.select}
      compact={variant !== "page"}
    />
  );

  const pad = variant === "page" ? "px-4" : "px-3";
  const density =
    variant === "page" ? "" : variant === "panel" ? "chat-compact" : "chat-compact chat-compact-xs";

  if (isEmpty && !isLoadingMessages) {
    return (
      <div
        className={`flex-1 min-h-0 flex flex-col overflow-y-auto ${
          variant === "page" ? "chat-page-thread items-center justify-center pb-[10vh]" : ""
        } ${density}`}
      >
        {variant === "page" ? (
          <div className="w-full max-w-3xl px-4">
            <EmptyState
              variant={variant}
              context={context}
              suggestions={suggestions}
              onPick={submit}
            />
            <div className="mt-8">{composer}</div>
            <SuggestionPills suggestions={suggestions} onPick={submit} />
          </div>
        ) : (
          <>
            <div className={`flex-1 flex items-center ${pad} py-4`}>
              <EmptyState
                variant={variant}
                context={context}
                suggestions={suggestions}
                onPick={submit}
              />
            </div>
            <div className={`${pad} pb-3`}>{composer}</div>
          </>
        )}
      </div>
    );
  }

  return (
    <ChatLinkPreviewProvider>
      <div
        className={`flex-1 min-h-0 flex flex-col ${variant === "page" ? "chat-page-thread" : ""} ${density}`}
      >
        <StickToBottom className="relative flex-1 min-h-0" resize="smooth" initial="instant">
          <StickToBottom.Content
            className={`${variant === "page" ? "max-w-3xl mx-auto px-4 pt-6 pb-10 space-y-7" : `${pad} pt-3 pb-6 space-y-5`}`}
          >
            {isLoadingMessages && (
              <div className="space-y-6 pt-4" aria-label="Loading messages">
                <div className="ml-auto h-10 w-1/2 rounded-3xl bg-base-content/5 animate-pulse" />
                <div className="h-24 w-5/6 rounded-xl bg-base-content/5 animate-pulse" />
              </div>
            )}
            {messages.map((msg, idx) =>
              msg.role === "user" ? (
                <UserMessage
                  key={idx}
                  message={msg}
                  canEdit={!isStreaming && !isLoadingMessages}
                  onEdit={(text) => editMessage(idx, text)}
                />
              ) : (
                <AssistantMessage
                  key={idx}
                  message={msg}
                  isLast={idx === lastIndex && !liveTurn}
                  canRetry={!isStreaming}
                  onRetry={retryLast}
                  answer={
                    messages[idx + 1]?.role === "user" ? messages[idx + 1].content : undefined
                  }
                  onAnswer={submit}
                  onDecide={decide}
                  onOther={focusComposer}
                  onRate={(feedback) => rateAnswer(idx, feedback)}
                />
              ),
            )}
            {liveTurn && <LiveAssistantMessage turn={liveTurn} statusMessage={statusMessage} />}
          </StickToBottom.Content>
          <ScrollToBottomButton />
        </StickToBottom>

        <div className={`shrink-0 ${pad} pb-3`}>
          <div className={variant === "page" ? "max-w-3xl mx-auto" : ""}>
            {composer}
            {variant === "page" && (
              <p className="text-[11px] text-base-content/35 text-center mt-2">
                AI can make mistakes. Verify important calibration values.
              </p>
            )}
          </div>
        </div>
      </div>
    </ChatLinkPreviewProvider>
  );
});
