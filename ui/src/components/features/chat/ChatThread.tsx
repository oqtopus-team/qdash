"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useGetCopilotPreferences, useListCopilotSkills } from "@/client/copilot/copilot";
import { ArrowDown, GitBranch, LayoutDashboard } from "lucide-react";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { useChatScrollIntent } from "@/hooks/useChatScrollIntent";
import { useChatSuggestions, type ChatSuggestion } from "@/hooks/useChatSuggestions";
import { replyAfter, useCopilotChat } from "@/hooks/useCopilotChat";
import { useChatAttachments } from "@/hooks/useChatAttachments";
import { useChatGreeting } from "@/hooks/useChatGreeting";
import { useAuth } from "@/contexts/AuthContext";
import { useChatPageSummary } from "@/contexts/ChatDockContext";
import { withViewTransition } from "@/lib/viewTransition";
import { ChatComposer, type ChatComposerHandle } from "@/components/features/chat/ChatComposer";
import { ChatContextBar } from "@/components/features/chat/ChatContextBar";
import { ChatLinkPreviewProvider } from "@/components/features/chat/ChatLinkPreview";
import { ChatNotice, ChatPendingSteers } from "@/components/features/chat/ChatPendingSteers";
import { DetachedTurnRow } from "@/components/features/chat/ChatTurnStatus";
import { ChatAgentSessionStatus } from "@/components/features/chat/ChatAgentSessionStatus";
import { linkedAgentSessions } from "@/lib/chatAgentSession";
import { QdashBotAvatar } from "@/components/ui/UserAvatar";
import {
  AssistantMessage,
  LiveAssistantMessage,
  UserMessage,
} from "@/components/features/chat/ChatMessages";
import type { TaskChatContext } from "@/types/copilotChat";

/**
 * - page: the /chat page, roomy, greeting centered with the composer
 * - panel: the docked sidebar
 * - compact: the floating window above modals
 */
type ChatThreadVariant = "page" | "panel" | "compact";

/**
 * Jump-to-latest control. It shows once the user scrolls away from the bottom,
 * which also stops the thread following new content; it, scrolling back down,
 * or sending a message resumes following.
 */
function ScrollToBottomButton({ followKey }: { followKey: number }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();
  useChatScrollIntent();
  const lastFollowKey = useRef(followKey);
  useEffect(() => {
    if (followKey === lastFollowKey.current) return;
    lastFollowKey.current = followKey;
    // What the user just sent is what they want to read the answer to.
    void scrollToBottom();
  }, [followKey, scrollToBottom]);
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

function EmptyState({
  variant,
  context,
  suggestions,
  onPick,
}: {
  variant: ChatThreadVariant;
  context: TaskChatContext | null;
  suggestions: ChatSuggestion[];
  onPick: (text: string) => void;
}) {
  const large = variant === "page";
  const { user, username } = useAuth();
  const greeting = useChatGreeting(user?.display_name?.trim() || username);
  const title = context ? "Ask about this result" : greeting;

  if (large) {
    return (
      <div className="w-full text-center px-4">
        <QdashBotAvatar size={64} unframed className="mx-auto mb-5 chat-avatar-hero" />
        <h2 className="text-xl font-medium break-words">{title}</h2>
      </div>
    );
  }

  return (
    <div className={`w-full mx-auto px-1 ${variant === "panel" ? "text-center" : ""}`}>
      {variant === "panel" && <QdashBotAvatar size={80} unframed className="mb-4" />}
      <h2 className="text-sm font-medium mb-1 break-words">{title}</h2>
      <p className="text-xs text-base-content/50 mb-4 mx-auto max-w-64">
        {context
          ? "The result figures are attached to your first question."
          : "I can fetch parameters, analyze trends, run Python and plot charts."}
      </p>
      <div
        className={
          variant === "panel" ? "flex flex-col items-center gap-2 mt-5" : "flex flex-wrap gap-1.5"
        }
      >
        {(variant === "compact" ? suggestions.slice(0, 3) : suggestions).map(({ text, Icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className={
              variant === "panel"
                ? "btn btn-ghost btn-sm h-auto min-h-8 max-w-full bg-base-200/60 px-3 py-1.5 text-base-content/60 font-normal"
                : "chat-suggestion-pill group"
            }
          >
            {variant !== "panel" && (
              <Icon className="w-3.5 h-3.5 text-base-content/40 group-hover:text-primary transition-colors shrink-0" />
            )}
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
          <span className="text-xs leading-snug">{text}</span>
        </button>
      ))}
    </div>
  );
}

/** Above a branched chat: where it came from, and what it shares with that chat. */
function BranchOrigin() {
  return (
    <p className="flex items-start gap-1.5 text-xs text-base-content/55">
      <GitBranch className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
      <span>
        Branched from another chat at one of its answers. It shares that chat&apos;s workspace files
        as they are now, and only one of them answers at a time.
      </span>
    </p>
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
    connection,
    detachedTurn,
    model,
    thinking,
    send,
    decide,
    stop,
    retryLast,
    canRetryLast,
    canEditMessage,
    editMessage,
    rateAnswer,
    steers,
    steer,
    resendSteer,
    checkSteer,
    dismissSteer,
    notice: chatNotice,
    dismissNotice,
    continueLast,
    canContinue,
    branchFrom,
    canBranchAt,
    branchingIndex,
  } = useCopilotChat(sessionId);
  const { data: preferences } = useGetCopilotPreferences({ query: { staleTime: 60_000 } });
  // Offered after `/` in the composer; without the runtime the menu simply stays closed.
  const { data: skillList } = useListCopilotSkills({
    query: { staleTime: 5 * 60_000, retry: false },
  });
  const [input, setInput] = useState("");
  const { attachments, attach, remove, clear, isStaging, notice, isPending } = useChatAttachments(
    session?.id,
  );
  const composerRef = useRef<ChatComposerHandle>(null);
  useImperativeHandle(ref, () => ({ focus: () => composerRef.current?.focus() }), []);

  const context = session?.context ?? null;
  // Subscribed, so the shown page follows navigation and the editor registering, loading, or
  // switching panes; a send still reads the dock's current page at that moment.
  const page = useChatPageSummary();
  const generalSuggestions = useChatSuggestions(Boolean(context));
  // A page with its own starter requests (a dashboard draft) offers those in a general chat;
  // picking one sends it, like any suggestion.
  const pageSuggestions = page?.suggestions;
  const suggestions = useMemo<ChatSuggestion[]>(
    () =>
      !context && pageSuggestions?.length
        ? pageSuggestions.map((text) => ({ text, Icon: LayoutDashboard }))
        : generalSuggestions,
    [context, generalSuggestions, pageSuggestions],
  );
  const isEmpty = messages.length === 0 && !liveTurn && !detachedTurn && steers.length === 0;
  // The calibration session this chat's own tool calls last acted on, if any.
  const liveSteps = liveTurn?.steps;
  const agentSessionId = useMemo(
    () => linkedAgentSessions(messages, liveSteps).slice(-1)[0] ?? null,
    [messages, liveSteps],
  );
  const chatTurn = isStreaming ? "live" : detachedTurn ? "detached" : "none";
  const lastIndex = messages.length - 1;
  const sentCount = messages.filter((m) => m.role === "user").length + steers.length;

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
      if (!trimmed || isLoadingMessages || isPending()) return;
      if (isStreaming) {
        // The answer in progress reads it after its current step; figures wait for a new message.
        if (attachments.length === 0 && steer(trimmed)) setInput("");
        return;
      }
      const images = attachments.map(({ data, mimeType }) => ({ data, mimeType }));
      // The first send turns the greeting into a thread; morph the mark and
      // the composer into their new places instead of swapping layouts.
      withViewTransition(() => {
        if (isPending() || !send(trimmed, images)) return;
        setInput("");
        clear();
      });
    },
    [attachments, clear, isLoadingMessages, isPending, isStreaming, send, steer],
  );

  const focusComposer = useCallback(() => composerRef.current?.focus(), []);

  const composer = (
    <>
      <ChatContextBar context={context} investigation={session?.investigation} page={page} />
      <ChatComposer
        ref={composerRef}
        value={input}
        onChange={setInput}
        onSubmit={() => submit(input)}
        onStop={stop}
        isStreaming={isStreaming}
        disabled={isLoadingMessages}
        placeholder={context ? "Ask about this result" : "Ask a question"}
        attachments={attachments}
        onAttach={attach}
        onRemoveAttachment={remove}
        isStaging={isStaging}
        attachmentNotice={notice}
        modelOptions={model.options}
        selectedModelKey={model.selected.key}
        onModelChange={model.select}
        modelStatus={model.status}
        thinkingChoice={thinking.choice}
        thinkingModelDefault={thinking.modelDefault}
        onThinkingChange={thinking.select}
        instructionsActive={Boolean(preferences?.data.instructions)}
        compact={variant !== "page"}
        steerable
        skills={skillList?.data.skills}
      />
    </>
  );

  const pad = variant === "page" ? "px-3 sm:px-4" : "px-3";
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
          <div className="w-full max-w-3xl px-3 sm:px-4">
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
            {session?.branch && <BranchOrigin />}
            {isLoadingMessages && (
              <div className="space-y-6 pt-4" aria-label="Loading messages">
                <div className="ml-auto h-10 w-1/2 rounded-3xl bg-base-content/5 animate-pulse" />
                <div className="h-24 w-5/6 rounded-[var(--radius-box)] bg-base-content/5 animate-pulse" />
              </div>
            )}
            {messages.map((msg, idx) =>
              msg.role === "user" ? (
                <UserMessage
                  key={idx}
                  message={msg}
                  canEdit={!isLoadingMessages && canEditMessage(idx)}
                  onEdit={(text) => editMessage(idx, text)}
                />
              ) : (
                <AssistantMessage
                  key={idx}
                  message={msg}
                  isLast={idx === lastIndex && !liveTurn}
                  canRetry={canRetryLast}
                  onRetry={retryLast}
                  answer={replyAfter(messages, idx)}
                  onAnswer={submit}
                  onDecide={decide}
                  onOther={focusComposer}
                  onRate={(feedback) => rateAnswer(idx, feedback)}
                  canContinue={canContinue}
                  onContinue={continueLast}
                  canBranch={canBranchAt(idx)}
                  branching={idx === branchingIndex}
                  onBranch={() => branchFrom(idx)}
                />
              ),
            )}
            {liveTurn && (
              <LiveAssistantMessage
                turn={liveTurn}
                statusMessage={statusMessage}
                connection={connection}
              />
            )}
            {!liveTurn && detachedTurn && <DetachedTurnRow turn={detachedTurn} />}
            <ChatPendingSteers
              steers={steers}
              isStreaming={isStreaming}
              onResend={resendSteer}
              onCheck={checkSteer}
              onDismiss={dismissSteer}
            />
            {chatNotice && <ChatNotice text={chatNotice} onDismiss={dismissNotice} />}
          </StickToBottom.Content>
          <ScrollToBottomButton followKey={sentCount} />
        </StickToBottom>

        <div className={`shrink-0 ${pad} pb-3`}>
          <div className={variant === "page" ? "max-w-3xl mx-auto" : ""}>
            {agentSessionId && (
              <div className="mb-2">
                <ChatAgentSessionStatus
                  agentSessionId={agentSessionId}
                  chatTurn={chatTurn}
                  // An explicit, ordinary message: the user's model and approvals apply.
                  onContinue={
                    isLoadingMessages
                      ? undefined
                      : () => submit(`Continue calibration session ${agentSessionId}.`)
                  }
                />
              </div>
            )}
            {composer}
            {variant === "page" && (
              <p className="text-xs text-base-content/35 text-center mt-2">
                AI can make mistakes. Verify important calibration values.
              </p>
            )}
          </div>
        </div>
      </div>
    </ChatLinkPreviewProvider>
  );
});
