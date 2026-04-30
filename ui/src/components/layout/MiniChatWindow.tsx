"use client";

import React, {
  useState,
  useRef,
  useEffect,
  useMemo,
  useCallback,
} from "react";
import { Send, X, Bot, Minus, Maximize2, GripHorizontal } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  useAnalysisChat,
  type ChatMessage,
  type BlocksResult,
} from "@/hooks/useAnalysisChat";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";
import { ChatPlotlyChart } from "@/components/features/chat/ChatPlotlyChart";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

// ---------------------------------------------------------------------------
// Drag hook
// ---------------------------------------------------------------------------

function useDrag(initialPosition: { x: number; y: number }) {
  const [position, setPosition] = useState(initialPosition);
  const dragState = useRef<{
    isDragging: boolean;
    startX: number;
    startY: number;
    startPosX: number;
    startPosY: number;
  } | null>(null);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      // Only drag on primary button
      if (e.button !== 0) return;
      // Don't start drag when clicking interactive elements (buttons, etc.)
      const target = e.target as HTMLElement;
      if (target.closest("button")) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      dragState.current = {
        isDragging: true,
        startX: e.clientX,
        startY: e.clientY,
        startPosX: position.x,
        startPosY: position.y,
      };
    },
    [position],
  );

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const state = dragState.current;
    if (!state?.isDragging) return;

    const dx = e.clientX - state.startX;
    const dy = e.clientY - state.startY;

    const newX = state.startPosX + dx;
    const newY = state.startPosY + dy;

    // Clamp to viewport
    const maxX = window.innerWidth - 100;
    const maxY = window.innerHeight - 40;
    setPosition({
      x: Math.max(0, Math.min(newX, maxX)),
      y: Math.max(0, Math.min(newY, maxY)),
    });
  }, []);

  const handlePointerUp = useCallback(() => {
    dragState.current = null;
  }, []);

  const resetPosition = useCallback(() => {
    setPosition(initialPosition);
  }, [initialPosition]);

  return {
    position,
    resetPosition,
    dragHandlers: {
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
    },
  };
}

// ---------------------------------------------------------------------------
// Shared rendering helpers (compact versions)
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

function MiniMessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-primary text-primary-content rounded-2xl rounded-br-sm px-3 py-1.5 max-w-[85%] text-xs">
          {message.content}
        </div>
      </div>
    );
  }

  const blocksResult = parseBlocksContent(message.content);

  return (
    <div className="flex gap-1.5">
      <div className="w-5 h-5 rounded-md bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-3 h-3 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        {blocksResult ? (
          <>
            {blocksResult.blocks.map((block, i) => {
              if (block.type === "text" && block.content) {
                return (
                  <div
                    key={i}
                    className="prose prose-sm max-w-none text-xs mt-0.5"
                  >
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
        ) : (
          <div className="prose prose-sm max-w-none text-xs mt-0.5">
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
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Suggested questions
// ---------------------------------------------------------------------------

const MINI_SUGGESTED_QUESTIONS = [
  "How should I interpret this result?",
  "Is this value within expected range?",
  "What should I try next?",
];

// ---------------------------------------------------------------------------
// Size constants
// ---------------------------------------------------------------------------

const WINDOW_WIDTH = 360;
const WINDOW_HEIGHT = 460;
const MARGIN = 16;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function MiniChatWindow() {
  const {
    miniChat,
    closeMiniChat,
    activeSessionId,
    activeSession,
    openAnalysisChat,
    getSessionMessages,
    setSessionMessages,
  } = useAnalysisChatContext();

  const [minimized, setMinimized] = useState(false);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Default position: bottom-right
  const defaultPos = useMemo(
    () => ({
      x:
        typeof window !== "undefined"
          ? window.innerWidth - WINDOW_WIDTH - MARGIN
          : 0,
      y:
        typeof window !== "undefined"
          ? window.innerHeight - WINDOW_HEIGHT - MARGIN
          : 0,
    }),
    [],
  );

  const { position, resetPosition, dragHandlers } = useDrag(defaultPos);

  // Reset position when window opens
  useEffect(() => {
    if (miniChat.isOpen) {
      resetPosition();
      setMinimized(false);
    }
  }, [miniChat.isOpen, resetPosition]);

  const effectiveContext = activeSession?.context ?? miniChat.context;

  const initialMessages = useMemo(
    () => (effectiveContext ? getSessionMessages(effectiveContext) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeSessionId],
  );

  const { messages, isLoading, statusMessage, sendMessage } = useAnalysisChat(
    effectiveContext ?? null,
    {
      initialMessages,
      onMessagesChange: (msgs) => {
        if (!activeSessionId || !effectiveContext) return;
        setSessionMessages(effectiveContext, msgs);
      },
    },
  );

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMessage]);

  // Focus input when opened
  useEffect(() => {
    if (miniChat.isOpen && !minimized) {
      inputRef.current?.focus();
    }
  }, [miniChat.isOpen, minimized]);

  if (!miniChat.isOpen) return null;

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

  const handleExpand = () => {
    if (effectiveContext) {
      openAnalysisChat(effectiveContext);
    }
    closeMiniChat();
  };

  return (
    <div
      className="fixed z-[1100] flex flex-col bg-base-100 border border-base-300 rounded-xl shadow-2xl"
      style={{
        left: position.x,
        top: position.y,
        width: minimized ? 220 : WINDOW_WIDTH,
        height: minimized ? "auto" : WINDOW_HEIGHT,
      }}
    >
      {/* Draggable header */}
      <div
        {...dragHandlers}
        className="flex items-center justify-between px-3 py-2 border-b border-base-300 bg-base-200/50 rounded-t-xl select-none touch-none"
        style={{ cursor: "grab" }}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <GripHorizontal className="w-3.5 h-3.5 text-base-content/30 flex-shrink-0" />
          <Bot className="w-4 h-4 text-primary flex-shrink-0" />
          <span className="text-xs font-bold truncate">
            {effectiveContext
              ? `${effectiveContext.taskName} / ${effectiveContext.qid}`
              : "AI Chat"}
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setMinimized((prev) => !prev)}
            className="btn btn-ghost btn-xs btn-square"
            title={minimized ? "Expand" : "Minimize"}
          >
            <Minus className="w-3 h-3" />
          </button>
          <button
            onClick={handleExpand}
            className="btn btn-ghost btn-xs btn-square"
            title="Open in sidebar"
          >
            <Maximize2 className="w-3 h-3" />
          </button>
          <button
            onClick={closeMiniChat}
            className="btn btn-ghost btn-xs btn-square"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Body (hidden when minimized) */}
      {!minimized && (
        <>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
            {messages.length === 0 ? (
              <div className="text-center py-4">
                <Bot className="w-6 h-6 mx-auto text-primary/30 mb-2" />
                <p className="text-xs text-base-content/60 mb-3">
                  Ask about this calibration result
                </p>
                <div className="flex flex-col gap-1.5">
                  {MINI_SUGGESTED_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      onClick={() => {
                        if (!isLoading) sendMessage(q);
                      }}
                      className="btn btn-outline btn-xs text-left justify-start text-[11px]"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <MiniMessageBubble key={idx} message={msg} />
              ))
            )}

            {isLoading && (
              <div className="flex gap-1.5">
                <div className="w-5 h-5 rounded-md bg-primary/10 flex items-center justify-center flex-shrink-0 animate-pulse">
                  <Bot className="w-3 h-3 text-primary" />
                </div>
                <div className="flex items-center gap-1 py-1">
                  {statusMessage ? (
                    <span className="text-[10px] text-base-content/60">
                      {statusMessage}
                    </span>
                  ) : (
                    <>
                      <span
                        className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce"
                        style={{ animationDelay: "0ms" }}
                      />
                      <span
                        className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce"
                        style={{ animationDelay: "150ms" }}
                      />
                      <span
                        className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce"
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
          <div className="flex items-end gap-1.5 p-2 border-t border-base-300">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about this result..."
              rows={1}
              className="textarea textarea-bordered flex-1 min-h-[32px] max-h-20 resize-none text-xs py-1.5 leading-tight"
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="btn btn-primary btn-xs h-8 w-8 rounded-lg"
            >
              <Send className="w-3 h-3" />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
