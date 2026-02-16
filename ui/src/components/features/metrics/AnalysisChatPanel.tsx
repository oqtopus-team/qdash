"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  Send,
  X,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  useAnalysisChat,
  type AnalysisContext,
  type ChatMessage,
} from "@/hooks/useAnalysisChat";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";

interface AnalysisChatPanelProps {
  context: AnalysisContext | null;
}

function AssessmentBadge({ content }: { content: string }) {
  if (content.includes("[Good]")) {
    return (
      <span className="badge badge-success badge-sm gap-1">
        <CheckCircle2 className="w-3 h-3" />
        Good
      </span>
    );
  }
  if (content.includes("[Warning]")) {
    return (
      <span className="badge badge-warning badge-sm gap-1">
        <AlertTriangle className="w-3 h-3" />
        Warning
      </span>
    );
  }
  if (content.includes("[Bad]")) {
    return (
      <span className="badge badge-error badge-sm gap-1">
        <XCircle className="w-3 h-3" />
        Bad
      </span>
    );
  }
  return null;
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

  return (
    <div className="flex gap-2">
      <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
        <Sparkles className="w-4 h-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <AssessmentBadge content={message.content} />
        <div className="prose prose-sm max-w-none text-sm mt-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content
              .replace(/\*\*\[Good\]\*\*\s*/, "")
              .replace(/\*\*\[Warning\]\*\*\s*/, "")
              .replace(/\*\*\[Bad\]\*\*\s*/, "")}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

const SUGGESTED_QUESTIONS = [
  "How should I interpret this result?",
  "Is this value within expected range?",
  "What could cause this issue?",
  "What should I try next?",
];

export function AnalysisChatPanel({ context }: AnalysisChatPanelProps) {
  const {
    closeAnalysisChat,
    clearCurrentSession,
    getSessionMessages,
    setSessionMessages,
  } = useAnalysisChatContext();

  // clearKey forces re-computation of initialMessages after clearing
  const [clearKey, setClearKey] = useState(0);

  // Restore messages from session store
  const initialMessages = useMemo(
    () => (context ? getSessionMessages(context) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [context?.taskId, context?.executionId, context?.qid, clearKey],
  );

  const { messages, isLoading, statusMessage, sendMessage } = useAnalysisChat(
    context,
    {
      initialMessages,
      onMessagesChange: (msgs) => {
        if (context) setSessionMessages(context, msgs);
      },
    },
  );

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages or status changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMessage]);

  // Focus input on open
  useEffect(() => {
    inputRef.current?.focus();
  }, [context]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || !context) return;
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

  const handleClear = () => {
    clearCurrentSession();
    setClearKey((k) => k + 1);
  };

  return (
    <div className="flex flex-col h-full border-l border-base-300 bg-base-100">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-base-300 bg-base-200/50">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles className="w-4 h-4 text-primary flex-shrink-0" />
          <div className="min-w-0">
            <h3 className="text-sm font-bold truncate">Ask AI</h3>
            {context && (
              <p className="text-xs text-base-content/50 truncate">
                {context.taskName} / {context.qid}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              className="btn btn-ghost btn-xs btn-square"
              title="Clear session"
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

      {/* No context — guide the user */}
      {!context && (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <Sparkles className="w-10 h-10 text-primary/20 mb-4" />
          <p className="text-sm font-semibold text-base-content/70 mb-2">
            No analysis context selected
          </p>
          <p className="text-xs text-base-content/50 leading-relaxed">
            Open a metric detail modal and click{" "}
            <span className="badge badge-primary badge-xs gap-1 align-middle">
              <Sparkles className="w-2.5 h-2.5" />
              Ask AI
            </span>{" "}
            to start analyzing calibration results.
          </p>
        </div>
      )}

      {/* Messages & Input — only when context is set */}
      {context && (
        <>
          <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
            {messages.length === 0 ? (
              <div className="text-center py-8">
                <Sparkles className="w-8 h-8 mx-auto text-primary/30 mb-3" />
                <p className="text-sm text-base-content/60 mb-4">
                  Ask about this calibration result
                </p>
                <div className="flex flex-col gap-2">
                  {SUGGESTED_QUESTIONS.map((q) => (
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
              </div>
            ) : (
              messages.map((msg, idx) => (
                <MessageBubble key={idx} message={msg} />
              ))
            )}

            {isLoading && (
              <div className="flex gap-2">
                <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 animate-pulse">
                  <Sparkles className="w-4 h-4 text-primary" />
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
              placeholder="Ask about this result..."
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
        </>
      )}
    </div>
  );
}
