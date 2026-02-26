"use client";

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
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
  Check,
  Loader2,
  Sparkles,
  ArrowRight,
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
      <code className="bg-base-200 px-1.5 py-0.5 rounded-md text-sm font-mono" {...props}>
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
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20">
        <CheckCircle2 className="w-3.5 h-3.5" />
        Good
      </span>
    );
  }
  if (assessment === "warning") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-warning/10 text-warning border border-warning/20">
        <AlertTriangle className="w-3.5 h-3.5" />
        Warning
      </span>
    );
  }
  if (assessment === "bad") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-error/10 text-error border border-error/20">
        <XCircle className="w-3.5 h-3.5" />
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
    <div className="mb-2">
      <div className="flex items-center gap-1.5 text-xs text-base-content/50 mb-2">
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
                className="flex-shrink-0 rounded-lg border border-base-300 overflow-hidden hover:border-primary/50 hover:shadow-md transition-all cursor-pointer"
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
              className="flex-shrink-0 rounded-lg border border-base-300 overflow-hidden hover:border-primary/50 hover:shadow-md transition-all cursor-pointer"
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
      {blocks.assessment && (
        <div className="mb-2">
          <AssessmentBadge assessment={blocks.assessment} />
        </div>
      )}
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

function MessageBubble({
  message,
  isLatest,
}: {
  message: CopilotMessage;
  isLatest: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className={`flex justify-end ${isLatest ? "animate-fade-in-up" : ""}`}>
        <div className="chat-bubble-user rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[75%] text-sm whitespace-pre-wrap shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const blocksResult = parseBlocksContent(message.content);

  return (
    <div className={`flex gap-3 ${isLatest ? "animate-fade-in-up" : ""}`}>
      <div className="w-8 h-8 rounded-xl chat-avatar-bot flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm">
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
      className={`w-full text-left px-3 py-2.5 rounded-xl group ${
        isActive
          ? "chat-session-active shadow-sm"
          : "hover:bg-base-200/80 border border-transparent"
      }`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium truncate">{session.title}</div>
          <div className="flex items-center gap-2 mt-1 text-xs text-base-content/50">
            {session.context?.qid && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-base-300/50 text-[10px] font-medium">
                {session.context.qid}
              </span>
            )}
            <span>{session.messages.length} msgs</span>
            <span className="text-base-content/30">{formatTime(session.updatedAt)}</span>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="btn btn-ghost btn-xs btn-square opacity-0 group-hover:opacity-100 shrink-0 text-base-content/40 hover:text-error"
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
  {
    text: "Show T1 trend for Q00",
    icon: "chart",
  },
  {
    text: "What are Q00's current parameters?",
    icon: "params",
  },
  {
    text: "Compare T1 and T2 for Q01",
    icon: "compare",
  },
  {
    text: "Show gate fidelity history for Q00",
    icon: "history",
  },
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
    completedTools,
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

  const messages = useMemo(
    () => activeSession?.messages ?? [],
    [activeSession?.messages],
  );

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
        <div className="w-64 flex-shrink-0 bg-base-200/30 border-r border-base-300/50 flex flex-col">
          {/* Sidebar Header */}
          <div className="flex items-center justify-between px-3 py-3 border-b border-base-300/50">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-base-content/60" />
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
          <div className="px-3 py-3">
            <button
              onClick={createSession}
              className="btn btn-primary btn-sm w-full gap-1.5"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          </div>

          {/* Session List */}
          <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
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
              <div className="text-center py-8 text-xs text-base-content/30">
                No sessions yet
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat Header */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-base-300/50 bg-base-100">
          {!showSessionSidebar && (
            <button
              onClick={() => setShowSessionSidebar(true)}
              className="btn btn-ghost btn-sm btn-square"
              title="Show sessions"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          )}
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="w-6 h-6 rounded-lg chat-avatar-bot flex items-center justify-center">
              <Bot className="w-3.5 h-3.5 text-primary" />
            </div>
            <h2 className="text-sm font-bold truncate">
              {activeSession?.title || "AI Chat"}
            </h2>
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearActiveSession}
              className="btn btn-ghost btn-xs gap-1 text-base-content/50 hover:text-error"
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
              <div className="max-w-lg text-center">
                <div className="w-16 h-16 rounded-2xl chat-avatar-bot flex items-center justify-center mx-auto mb-6 shadow-md">
                  <Sparkles className="w-7 h-7 text-primary" />
                </div>
                <h3 className="text-xl font-bold mb-2">AI Chat</h3>
                <p className="text-sm text-base-content/50 mb-8 leading-relaxed">
                  Ask questions about qubit calibration data. I can fetch
                  parameters, show trends, and create visualizations.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {SUGGESTED_QUESTIONS.map((q) => (
                    <button
                      key={q.text}
                      onClick={() => {
                        if (!isLoading) {
                          setInput("");
                          sendMessage(q.text);
                        }
                      }}
                      className="chat-suggestion-card group"
                    >
                      <span className="text-xs text-left leading-relaxed flex-1">
                        {q.text}
                      </span>
                      <ArrowRight className="w-3.5 h-3.5 text-base-content/20 group-hover:text-primary group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Message List */
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {messages.map((msg, idx) => (
                <MessageBubble
                  key={idx}
                  message={msg}
                  isLatest={idx === messages.length - 1}
                />
              ))}

              {isLoading && (
                <div className="flex gap-3 animate-fade-in-up">
                  <div className="w-8 h-8 rounded-xl chat-avatar-bot flex items-center justify-center flex-shrink-0">
                    <Bot className="w-4 h-4 text-primary animate-pulse" />
                  </div>
                  <div className="flex flex-col gap-1.5 py-1.5 min-w-0">
                    {completedTools.length > 0 && (
                      <div className="flex flex-col gap-1 mb-1">
                        {completedTools.map((tool, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 text-xs text-base-content/40"
                          >
                            <div className="w-4 h-4 rounded-full bg-success/10 flex items-center justify-center flex-shrink-0">
                              <Check className="w-2.5 h-2.5 text-success" />
                            </div>
                            <span>{tool}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <Loader2 className="w-2.5 h-2.5 text-primary animate-spin" />
                      </div>
                      <span className="text-sm text-base-content/50">
                        {statusMessage || "Thinking..."}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 text-sm text-error bg-error/5 rounded-xl px-4 py-3 border border-error/20">
                  <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="bg-base-100 px-4 py-3">
          <div className="max-w-3xl mx-auto">
            <div className="chat-input-card flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about calibration data..."
                rows={1}
                className="flex-1 min-h-[44px] max-h-32 resize-none text-sm py-3 px-1 bg-transparent border-none outline-none focus:ring-0 placeholder:text-base-content/30"
                disabled={isLoading}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="btn btn-primary btn-sm h-10 w-10 rounded-xl flex-shrink-0 mb-0.5"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <p className="text-[10px] text-base-content/25 text-center mt-2">
              Press Enter to send, Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
