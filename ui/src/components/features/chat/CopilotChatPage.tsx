"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Send,
  Bot,
  Trash2,
  Plus,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ImageIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  useCopilotChat,
  type CopilotMessage,
  type CopilotSession,
} from "@/hooks/useCopilotChat";
import { ChatPlotlyChart } from "@/components/features/chat/ChatPlotlyChart";
import { CodeBlock } from "@/components/features/chat/CodeBlock";
import type { BlocksResult } from "@/hooks/useAnalysisChat";

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

function parseBlocksContent(content: string): BlocksResult | null {
  if (!content.startsWith("{")) return null;
  try {
    const data = JSON.parse(content);
    if (data.blocks && Array.isArray(data.blocks)) {
      return data as BlocksResult;
    }
  } catch {
    // Not JSON
  }
  return null;
}

function AssessmentBadge({ assessment }: { assessment: string | null }) {
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

function ImageSentBadge({
  imagesSent,
}: {
  imagesSent: BlocksResult["images_sent"];
}) {
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const modalRef = useRef<HTMLDialogElement>(null);

  const openPreview = useCallback((src: string) => {
    setPreviewSrc(src);
    modalRef.current?.showModal();
  }, []);

  if (!imagesSent) return null;
  const {
    experiment_figure,
    experiment_figure_paths,
    expected_images,
    task_name,
  } = imagesSent;
  if (!experiment_figure && expected_images.length === 0) return null;

  const parts: string[] = [];
  if (experiment_figure) parts.push("実験結果画像");
  if (expected_images.length > 0)
    parts.push(`参照画像${expected_images.length}枚`);

  const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";

  return (
    <div className="mb-1">
      <div className="flex items-center gap-1.5 text-xs text-base-content/50 mb-1.5">
        <ImageIcon className="w-3.5 h-3.5" />
        <span>{parts.join(" + ")}を送信</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {experiment_figure &&
          experiment_figure_paths.map((fp) => {
            const src = `${baseURL}/executions/figure?path=${encodeURIComponent(fp)}`;
            return (
              <button
                key={fp}
                onClick={() => openPreview(src)}
                className="flex-shrink-0 rounded border border-base-300 overflow-hidden hover:border-primary transition-colors cursor-pointer"
              >
                <img
                  src={src}
                  alt="実験結果"
                  className="h-16 w-auto object-contain bg-base-200"
                  loading="lazy"
                />
              </button>
            );
          })}
        {expected_images.map((img) => {
          const src = `${baseURL}/copilot/expected-image?task_name=${encodeURIComponent(task_name)}&index=${img.index}`;
          return (
            <button
              key={`expected-${img.index}`}
              onClick={() => openPreview(src)}
              className="flex-shrink-0 rounded border border-base-300 overflow-hidden hover:border-primary transition-colors cursor-pointer"
            >
              <img
                src={src}
                alt={img.alt_text}
                className="h-16 w-auto object-contain bg-base-200"
                loading="lazy"
              />
            </button>
          );
        })}
      </div>
      <dialog ref={modalRef} className="modal">
        <div className="modal-box max-w-3xl p-4">
          {previewSrc && (
            <img src={previewSrc} alt="Preview" className="w-full h-auto" />
          )}
        </div>
        <form method="dialog" className="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </div>
  );
}

function BlocksContent({ blocks }: { blocks: BlocksResult }) {
  return (
    <>
      <ImageSentBadge imagesSent={blocks.images_sent} />
      {blocks.assessment && <AssessmentBadge assessment={blocks.assessment} />}
      {blocks.blocks.map((block, i) => {
        if (block.type === "text" && block.content) {
          return (
            <div key={i} className="prose prose-sm max-w-none mt-1">
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

function MessageBubble({ message }: { message: CopilotMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-primary text-primary-content rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[75%] text-sm whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  const blocksResult = parseBlocksContent(message.content);

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-4 h-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0 max-w-[85%]">
        {blocksResult ? (
          <BlocksContent blocks={blocksResult} />
        ) : (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffDays === 0) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function SessionListItem({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: CopilotSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors group ${
        isActive
          ? "bg-primary/10 border border-primary/20"
          : "hover:bg-base-200 border border-transparent"
      }`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium truncate">{session.title}</div>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-base-content/50">
            {session.context?.qid && (
              <span className="badge badge-ghost badge-xs">
                {session.context.qid}
              </span>
            )}
            <span>{session.messages.length} msgs</span>
            <span>{formatTime(session.updatedAt)}</span>
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
  "Show T1 trend for Q00",
  "What are Q00's current parameters?",
  "Compare T1 and T2 for Q01",
  "Show gate fidelity history for Q00",
];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CopilotChatPage() {
  const {
    sessions,
    activeSession,
    activeSessionId,
    isLoading,
    statusMessage,
    error,
    createSession,
    switchSession,
    deleteSession,
    sendMessage,
    clearActiveSession,
  } = useCopilotChat();

  const [input, setInput] = useState("");
  const [showSessionSidebar, setShowSessionSidebar] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const messages = activeSession?.messages ?? [];

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMessage]);

  // Focus input on session switch
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

  return (
    <div className="flex h-[calc(100vh-64px)] bg-base-100">
      {/* Session Sidebar */}
      {showSessionSidebar && (
        <div className="w-64 flex-shrink-0 bg-base-200/50 border-r border-base-300 flex flex-col">
          {/* Sidebar Header */}
          <div className="flex items-center justify-between px-3 py-3 border-b border-base-300">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4" />
              <span className="text-sm font-semibold">Sessions</span>
            </div>
            <button
              onClick={() => setShowSessionSidebar(false)}
              className="btn btn-ghost btn-xs btn-square"
              title="Hide sessions"
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          </div>

          {/* New Session Button */}
          <div className="px-3 py-2">
            <button
              onClick={createSession}
              className="btn btn-primary btn-sm w-full gap-1.5"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          </div>

          {/* Session List */}
          <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
            {sessions.map((session) => (
              <SessionListItem
                key={session.id}
                session={session}
                isActive={session.id === activeSessionId}
                onSelect={() => switchSession(session.id)}
                onDelete={() => deleteSession(session.id)}
              />
            ))}
            {sessions.length === 0 && (
              <div className="text-center py-8 text-xs text-base-content/40">
                No sessions yet
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat Header */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-base-300 bg-base-100">
          {!showSessionSidebar && (
            <button
              onClick={() => setShowSessionSidebar(true)}
              className="btn btn-ghost btn-sm btn-square"
              title="Show sessions"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          )}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Bot className="w-4 h-4 text-primary flex-shrink-0" />
            <h2 className="text-sm font-bold truncate">
              {activeSession?.title || "AI Chat"}
            </h2>
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearActiveSession}
              className="btn btn-ghost btn-xs gap-1"
              title="Clear messages"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          )}
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {!activeSession || messages.length === 0 ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center h-full px-4">
              <div className="max-w-md text-center">
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6">
                  <Bot className="w-8 h-8 text-primary" />
                </div>
                <h3 className="text-xl font-bold mb-2">AI Chat</h3>
                <p className="text-sm text-base-content/60 mb-8">
                  Ask questions about qubit calibration data. I can fetch
                  parameters, show trends, and create visualizations.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {SUGGESTED_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      onClick={() => {
                        if (!isLoading) {
                          setInput("");
                          sendMessage(q);
                        }
                      }}
                      className="btn btn-outline btn-sm text-left justify-start h-auto py-2.5 px-3 text-xs"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Message List */
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {messages.map((msg, idx) => (
                <MessageBubble key={idx} message={msg} />
              ))}

              {isLoading && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 animate-pulse">
                    <Bot className="w-4 h-4 text-primary" />
                  </div>
                  <div className="flex items-center gap-2 py-2">
                    {statusMessage ? (
                      <span className="text-sm text-base-content/60">
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

              {error && (
                <div className="text-sm text-error bg-error/5 rounded-lg px-3 py-2 border border-error/20">
                  {error}
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-base-300 bg-base-100 px-4 py-3">
          <div className="max-w-3xl mx-auto flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about calibration data..."
              rows={1}
              className="textarea textarea-bordered flex-1 min-h-[44px] max-h-32 resize-none text-sm py-2.5"
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="btn btn-primary btn-sm h-11 w-11 rounded-xl"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
