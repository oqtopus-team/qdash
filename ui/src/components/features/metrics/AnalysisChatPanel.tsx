"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  Send,
  X,
  Bot,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Trash2,
  Plus,
  ChevronDown,
  MessageSquare,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  useAnalysisChat,
  type AnalysisContext,
  type ChatMessage,
  type BlocksResult,
} from "@/hooks/useAnalysisChat";
import {
  useAnalysisChatContext,
  type ChatSession,
} from "@/contexts/AnalysisChatContext";
import { ChatPlotlyChart } from "@/components/features/chat/ChatPlotlyChart";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

interface AnalysisChatPanelProps {
  context: AnalysisContext | null;
}

// ---------------------------------------------------------------------------
// Markdown components with code block rendering
// ---------------------------------------------------------------------------

const markdownComponents = {
  code({
    className,
    children,
    ...props
  }: React.ComponentPropsWithoutRef<"code"> & { className?: string }) {
    const match = /language-(\w+)/.exec(className || "");
    const codeString = String(children).replace(/\n$/, "");
    if (match) {
      return <CodeBlock language={match[1]}>{codeString}</CodeBlock>;
    }
    return (
      <code className="bg-base-200 px-1 py-0.5 rounded text-sm" {...props}>
        {children}
      </code>
    );
  },
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AssessmentBadgeFromValue({
  assessment,
}: {
  assessment: string | null;
}) {
  if (assessment === "good") {
    return (
      <span className="badge badge-success badge-sm gap-1">
        <CheckCircle2 className="w-3 h-3" />
        Good
      </span>
    );
  }
  if (assessment === "warning") {
    return (
      <span className="badge badge-warning badge-sm gap-1">
        <AlertTriangle className="w-3 h-3" />
        Warning
      </span>
    );
  }
  if (assessment === "bad") {
    return (
      <span className="badge badge-error badge-sm gap-1">
        <XCircle className="w-3 h-3" />
        Bad
      </span>
    );
  }
  return null;
}

function AssessmentBadge({ content }: { content: string }) {
  if (content.includes("[Good]")) {
    return <AssessmentBadgeFromValue assessment="good" />;
  }
  if (content.includes("[Warning]")) {
    return <AssessmentBadgeFromValue assessment="warning" />;
  }
  if (content.includes("[Bad]")) {
    return <AssessmentBadgeFromValue assessment="bad" />;
  }
  return null;
}

/**
 * Try to parse content as a blocks-format JSON string.
 * Returns the parsed BlocksResult or null if not blocks format.
 */
function parseBlocksContent(content: string): BlocksResult | null {
  if (!content.startsWith("{")) return null;
  try {
    const data = JSON.parse(content);
    if (data.blocks && Array.isArray(data.blocks)) {
      return data as BlocksResult;
    }
  } catch {
    // Not JSON — legacy format
  }
  return null;
}

function BlocksContent({ blocks }: { blocks: BlocksResult }) {
  return (
    <>
      {blocks.assessment && (
        <AssessmentBadgeFromValue assessment={blocks.assessment} />
      )}
      {blocks.blocks.map((block, i) => {
        if (block.type === "text" && block.content) {
          return (
            <div key={i} className="prose prose-sm max-w-none text-sm mt-1">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {block.content}
              </ReactMarkdown>
            </div>
          );
        }
        if (block.type === "chart" && block.chart) {
          return (
            <ChatPlotlyChart
              key={i}
              data={block.chart.data as Record<string, unknown>[]}
              layout={block.chart.layout as Record<string, unknown>}
            />
          );
        }
        return null;
      })}
    </>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-primary text-primary-content rounded-2xl rounded-br-sm px-4 py-2 max-w-[85%] text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const blocksResult = parseBlocksContent(message.content);

  return (
    <div className="flex gap-2">
      <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
        <Bot className="w-4 h-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        {blocksResult ? (
          <BlocksContent blocks={blocksResult} />
        ) : (
          <>
            <AssessmentBadge content={message.content} />
            <div className="prose prose-sm max-w-none text-sm mt-1">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {message.content
                  .replace(/\*\*\[Good\]\*\*\s*/, "")
                  .replace(/\*\*\[Warning\]\*\*\s*/, "")
                  .replace(/\*\*\[Bad\]\*\*\s*/, "")}
              </ReactMarkdown>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function formatTimeAgo(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2 rounded-lg transition-colors text-xs group ${
        isActive
          ? "bg-primary/10 border border-primary/30"
          : "hover:bg-base-200 border border-transparent"
      }`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">
            {session.context
              ? session.context.taskName || "Untitled"
              : "General Chat"}
          </div>
          <div className="text-base-content/50 truncate">
            {session.context ? session.context.qid : "No specific task"}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-base-content/40">
            <span>{session.messages.length} msgs</span>
            <span>{formatTimeAgo(session.updatedAt)}</span>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="btn btn-ghost btn-xs btn-square opacity-0 group-hover:opacity-100 shrink-0"
          title="Delete session"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SUGGESTED_QUESTIONS = [
  "How should I interpret this result?",
  "Is this value within expected range?",
  "What could cause this issue?",
  "What should I try next?",
];

const GENERAL_SUGGESTED_QUESTIONS = [
  "What calibration tasks are available?",
  "How do I interpret T1 relaxation results?",
  "What are common qubit calibration issues?",
  "Explain the calibration workflow",
];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AnalysisChatPanel({ context }: AnalysisChatPanelProps) {
  const {
    closeAnalysisChat,
    sessions,
    activeSessionId,
    activeSession,
    switchSession,
    createNewSession,
    deleteSession,
    clearActiveSession,
    getSessionMessages,
    setSessionMessages,
  } = useAnalysisChatContext();

  const [showSessions, setShowSessions] = useState(false);

  // The context to use for the chat: prefer active session's context
  const effectiveContext = activeSession?.context ?? context;
  const isGeneralMode = !effectiveContext;

  // Restore messages from active session
  const initialMessages = useMemo(
    () =>
      effectiveContext
        ? getSessionMessages(effectiveContext)
        : (activeSession?.messages ?? []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeSessionId],
  );

  const { messages, isLoading, statusMessage, sendMessage } = useAnalysisChat(
    effectiveContext ?? null,
    {
      initialMessages,
      onMessagesChange: (msgs) => {
        if (!activeSessionId) return;
        if (effectiveContext) {
          setSessionMessages(effectiveContext, msgs);
        } else {
          // General mode: sync messages via dummy context key
          setSessionMessages(
            {
              taskId: "__general__",
              executionId: "",
              qid: "",
              taskName: "",
              chipId: "",
            } as AnalysisContext,
            msgs,
          );
        }
      },
    },
  );

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMessage]);

  // Focus input when session changes
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSessionId]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    setInput("");
    sendMessage(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewSession = () => {
    createNewSession(effectiveContext ?? null);
    setShowSessions(false);
  };

  return (
    <div className="flex flex-col h-full border-l border-base-300 bg-base-100">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-base-300 bg-base-200/50">
        <div className="flex items-center gap-2 min-w-0">
          <Bot className="w-4 h-4 text-primary flex-shrink-0" />
          <div className="min-w-0">
            <h3 className="text-sm font-bold truncate">
              {isGeneralMode ? "AI Chat" : "Ask AI"}
            </h3>
            {effectiveContext && (
              <p className="text-xs text-base-content/50 truncate">
                {effectiveContext.taskName} / {effectiveContext.qid}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={handleNewSession}
            className="btn btn-ghost btn-xs btn-square"
            title="New session"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          {messages.length > 0 && (
            <button
              onClick={clearActiveSession}
              className="btn btn-ghost btn-xs btn-square"
              title="Clear messages"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={closeAnalysisChat}
            className="btn btn-ghost btn-xs btn-square"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Session switcher */}
      {sessions.length > 0 && (
        <div className="border-b border-base-300">
          <button
            onClick={() => setShowSessions((prev) => !prev)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-xs text-base-content/60 hover:bg-base-200/50 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <MessageSquare className="w-3 h-3" />
              <span>Sessions ({sessions.length})</span>
            </div>
            <ChevronDown
              className={`w-3 h-3 transition-transform ${showSessions ? "rotate-180" : ""}`}
            />
          </button>
          {showSessions && (
            <div className="max-h-48 overflow-y-auto px-2 pb-2 space-y-1">
              {sessions.map((session) => (
                <SessionItem
                  key={session.id}
                  session={session}
                  isActive={session.id === activeSessionId}
                  onSelect={() => {
                    switchSession(session.id);
                    setShowSessions(false);
                  }}
                  onDelete={() => deleteSession(session.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages & Input */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
        {messages.length === 0 ? (
          <div className="text-center py-8">
            <Bot className="w-8 h-8 mx-auto text-primary/30 mb-3" />
            <p className="text-sm text-base-content/60 mb-4">
              {isGeneralMode
                ? "Ask anything about calibration"
                : "Ask about this calibration result"}
            </p>
            <div className="flex flex-col gap-2">
              {(isGeneralMode
                ? GENERAL_SUGGESTED_QUESTIONS
                : SUGGESTED_QUESTIONS
              ).map((q) => (
                <button
                  key={q}
                  onClick={() => {
                    if (!isLoading) sendMessage(q);
                  }}
                  className="btn btn-outline btn-xs text-left justify-start"
                >
                  {q}
                </button>
              ))}
            </div>
            {/* Show past sessions when in general mode with no active session */}
            {isGeneralMode && sessions.length > 0 && !activeSessionId && (
              <div className="mt-6 w-full">
                <p className="text-xs text-base-content/40 mb-2">
                  Or resume a previous session:
                </p>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {sessions.slice(0, 5).map((session) => (
                    <SessionItem
                      key={session.id}
                      session={session}
                      isActive={false}
                      onSelect={() => switchSession(session.id)}
                      onDelete={() => deleteSession(session.id)}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          messages.map((msg, idx) => <MessageBubble key={idx} message={msg} />)
        )}

        {isLoading && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 animate-pulse">
              <Bot className="w-4 h-4 text-primary" />
            </div>
            <div className="flex items-center gap-1.5 py-2">
              {statusMessage ? (
                <span className="text-xs text-base-content/60">
                  {statusMessage}
                </span>
              ) : (
                <>
                  <span
                    className="w-2 h-2 bg-primary/60 rounded-full animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="w-2 h-2 bg-primary/60 rounded-full animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="w-2 h-2 bg-primary/60 rounded-full animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  />
                </>
              )}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex items-end gap-2 p-3 border-t border-base-300">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isGeneralMode
              ? "Ask about calibration..."
              : "Ask about this result..."
          }
          rows={1}
          className="textarea textarea-bordered flex-1 min-h-[40px] max-h-24 resize-none text-sm py-2"
          disabled={isLoading}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          className="btn btn-primary btn-sm h-10 w-10 rounded-xl"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
