"use client";

import { type FC, useCallback } from "react";
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ActionBarPrimitive,
  useMessage,
  useThreadRuntime,
} from "@assistant-ui/react";
import {
  SendHorizontal,
  Square,
  ArrowDown,
  Copy,
  Check,
  RefreshCw,
  Sparkles,
  BarChart3,
  Cpu,
  Zap,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useState } from "react";
import Image from "next/image";

// AI Avatar component using OQTOPUS logo
const AIAvatar: FC<{ size?: "sm" | "md" | "lg"; animate?: boolean }> = ({
  size = "md",
  animate = false,
}) => {
  const sizeMap = { sm: 24, md: 28, lg: 48 };
  const containerSize = { sm: "w-7 h-7", md: "w-8 h-8", lg: "w-14 h-14" };

  return (
    <div
      className={`${containerSize[size]} rounded-xl flex items-center justify-center shadow-sm flex-shrink-0 ${animate ? "animate-pulse" : ""}`}
      style={{
        background:
          "linear-gradient(135deg, oklch(var(--p) / 0.15) 0%, oklch(var(--s) / 0.15) 100%)",
      }}
    >
      <Image
        src="/oqtopus_logo.svg"
        alt="OQTOPUS"
        width={sizeMap[size]}
        height={sizeMap[size]}
        className="object-contain"
      />
    </div>
  );
};

// Custom text component for markdown rendering
const MarkdownText: FC = () => {
  const content = useMessage((m) => m.content);

  const textContent = content
    .filter(
      (part): part is { type: "text"; text: string } => part.type === "text",
    )
    .map((part) => part.text)
    .join("\n");

  return (
    <div className="text-base-content text-sm leading-relaxed prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 rounded-lg border border-base-300">
              <table className="table table-xs table-zebra w-full">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-base-200">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="text-base-content font-semibold text-left px-3 py-2">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="text-base-content px-3 py-2">{children}</td>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-base-200/50 transition-colors">
              {children}
            </tr>
          ),
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <code className="block bg-base-300/80 p-3 rounded-lg text-xs overflow-x-auto font-mono">
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-base-300/80 px-1.5 py-0.5 rounded text-xs font-mono text-primary">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="bg-base-300/80 rounded-lg text-xs overflow-x-auto my-3 p-0">
              {children}
            </pre>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-inside my-2 space-y-1 pl-1">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside my-2 space-y-1 pl-1">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="my-0.5">{children}</li>,
          p: ({ children }) => <p className="my-2 first:mt-0">{children}</p>,
          h1: ({ children }) => (
            <h1 className="text-xl font-bold my-3 text-base-content">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-bold my-2 text-base-content">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-bold my-2 text-base-content">
              {children}
            </h3>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              className="text-primary hover:text-primary/80 hover:underline transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-primary/50 pl-4 my-3 italic text-base-content/80 bg-base-200/30 py-2 rounded-r-lg">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-base-300" />,
          strong: ({ children }) => (
            <strong className="font-semibold text-base-content">
              {children}
            </strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
        }}
      >
        {textContent}
      </ReactMarkdown>
    </div>
  );
};

// Simple text component for user messages
const SimpleText: FC = () => {
  const content = useMessage((m) => m.content);

  const textContent = content
    .filter(
      (part): part is { type: "text"; text: string } => part.type === "text",
    )
    .map((part) => part.text)
    .join("\n");

  return <span className="whitespace-pre-wrap">{textContent}</span>;
};

// Copy button with feedback
const CopyButton: FC = () => {
  const [copied, setCopied] = useState(false);
  const content = useMessage((m) => m.content);

  const handleCopy = () => {
    const textContent = content
      .filter(
        (part): part is { type: "text"; text: string } => part.type === "text",
      )
      .map((part) => part.text)
      .join("\n");
    navigator.clipboard.writeText(textContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className={`btn btn-ghost btn-xs transition-all ${copied ? "text-success" : "opacity-0 group-hover:opacity-100"}`}
      title={copied ? "Copied!" : "Copy message"}
    >
      {copied ? (
        <Check className="w-3.5 h-3.5" />
      ) : (
        <Copy className="w-3.5 h-3.5" />
      )}
    </button>
  );
};

// User message component
const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root className="group flex justify-end py-3 px-4">
      <div className="flex items-end gap-2 max-w-[85%]">
        <ActionBarPrimitive.Root className="flex items-center">
          <CopyButton />
        </ActionBarPrimitive.Root>
        <div
          className="rounded-2xl rounded-br-sm px-4 py-2.5 shadow-sm text-sm"
          style={{
            background:
              "linear-gradient(135deg, oklch(var(--p)) 0%, oklch(var(--p) / 0.9) 100%)",
            color: "oklch(var(--pc))",
          }}
        >
          <SimpleText />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

// Assistant message component
const AssistantMessage: FC = () => {
  return (
    <MessagePrimitive.Root className="group py-4 px-4 hover:bg-base-200/20 transition-colors rounded-lg mx-2">
      <div className="flex gap-3 max-w-full">
        <AIAvatar size="sm" />
        <div className="flex-1 min-w-0">
          <MarkdownText />
          <ActionBarPrimitive.Root className="flex items-center gap-1 mt-2">
            <CopyButton />
            <ActionBarPrimitive.Reload asChild>
              <button
                className="btn btn-ghost btn-xs opacity-0 group-hover:opacity-100 transition-opacity"
                title="Regenerate"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </ActionBarPrimitive.Reload>
          </ActionBarPrimitive.Root>
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

// Loading indicator with animation
const LoadingIndicator: FC = () => {
  return (
    <div className="py-4 px-4 mx-2">
      <div className="flex gap-3">
        <AIAvatar size="sm" animate />
        <div className="flex items-center gap-1.5 py-2">
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
        </div>
      </div>
    </div>
  );
};

// Composer component
const Composer: FC = () => {
  return (
    <ComposerPrimitive.Root className="flex items-end gap-2 p-3 border-t border-base-300 bg-base-100/80 backdrop-blur-sm">
      <ComposerPrimitive.Input
        rows={1}
        autoFocus
        placeholder="Ask about metrics, qubits, or workflows..."
        className="textarea textarea-bordered flex-1 min-h-[44px] max-h-32 resize-none text-sm leading-relaxed py-2.5 focus:textarea-primary transition-colors"
      />
      <ThreadPrimitive.If running={false}>
        <ComposerPrimitive.Send asChild>
          <button
            className="btn btn-primary btn-sm h-11 w-11 rounded-xl shadow-sm hover:shadow-md transition-all"
            style={{
              background:
                "linear-gradient(135deg, oklch(var(--p)) 0%, oklch(var(--s)) 100%)",
            }}
          >
            <SendHorizontal className="w-4 h-4" />
          </button>
        </ComposerPrimitive.Send>
      </ThreadPrimitive.If>
      <ThreadPrimitive.If running>
        <ComposerPrimitive.Cancel asChild>
          <button className="btn btn-error btn-sm h-11 w-11 rounded-xl shadow-sm">
            <Square className="w-4 h-4" />
          </button>
        </ComposerPrimitive.Cancel>
      </ThreadPrimitive.If>
    </ComposerPrimitive.Root>
  );
};

// Scroll to bottom button
const ScrollToBottom: FC = () => {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <button className="absolute bottom-20 right-4 btn btn-circle btn-sm bg-base-100 shadow-lg hover:bg-base-200 z-10 border border-base-300">
        <ArrowDown className="w-4 h-4" />
      </button>
    </ThreadPrimitive.ScrollToBottom>
  );
};

interface Suggestion {
  label: string;
  prompt: string;
}

// Suggestion card component
const SuggestionCard: FC<{
  suggestion: Suggestion;
  icon: React.ReactNode;
  onClick: () => void;
}> = ({ suggestion, icon, onClick }) => {
  return (
    <button
      onClick={onClick}
      className="group flex items-start gap-3 p-3 rounded-xl border border-base-300 bg-base-100 hover:border-primary/50 hover:bg-base-200/50 transition-all text-left w-full"
    >
      <div className="p-2 rounded-lg bg-primary/10 text-primary group-hover:bg-primary/20 transition-colors">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-base-content truncate">
          {suggestion.label}
        </p>
        <p className="text-xs text-base-content/50 truncate mt-0.5">
          {suggestion.prompt.slice(0, 50)}...
        </p>
      </div>
    </button>
  );
};

// Suggestion buttons component that can send messages
const SuggestionButtons: FC<{ suggestions: Suggestion[] }> = ({
  suggestions,
}) => {
  const threadRuntime = useThreadRuntime();

  const handleClick = useCallback(
    (prompt: string) => {
      threadRuntime.append({
        role: "user",
        content: [{ type: "text", text: prompt }],
      });
    },
    [threadRuntime],
  );

  // Map suggestions to icons
  const icons = [
    <BarChart3 key="0" className="w-4 h-4" />,
    <Cpu key="1" className="w-4 h-4" />,
    <Zap key="2" className="w-4 h-4" />,
    <Sparkles key="3" className="w-4 h-4" />,
  ];

  return (
    <div className="grid grid-cols-1 gap-2 w-full max-w-sm">
      {suggestions.slice(0, 4).map((suggestion, index) => (
        <SuggestionCard
          key={index}
          suggestion={suggestion}
          icon={icons[index % icons.length]}
          onClick={() => handleClick(suggestion.prompt)}
        />
      ))}
    </div>
  );
};

// Welcome screen component
const WelcomeScreen: FC<{
  initialMessage?: string;
  suggestions?: Suggestion[];
}> = ({ initialMessage, suggestions }) => {
  return (
    <div className="flex flex-col items-center p-4 pt-6 text-center min-h-full">
      {/* Animated avatar */}
      <div className="relative mb-4">
        <AIAvatar size="lg" />
      </div>

      {/* Title */}
      <h3 className="text-lg font-bold text-base-content mb-1 flex items-center gap-2">
        <span>QDash Assistant</span>
        <Sparkles className="w-4 h-4 text-warning" />
      </h3>

      {/* Description */}
      <p className="text-sm text-base-content/60 mb-4 max-w-xs leading-relaxed">
        {initialMessage ||
          "I can help you analyze chip calibration metrics, explore qubit performance, and navigate workflows."}
      </p>

      {/* Suggestions */}
      {suggestions && suggestions.length > 0 && (
        <div className="w-full">
          <p className="text-xs text-base-content/40 mb-2 uppercase tracking-wider font-medium">
            Try asking
          </p>
          <SuggestionButtons suggestions={suggestions} />
        </div>
      )}
    </div>
  );
};

interface AssistantThreadProps {
  initialMessage?: string;
  suggestions?: Suggestion[];
}

export const AssistantThread: FC<AssistantThreadProps> = ({
  initialMessage,
  suggestions,
}) => {
  return (
    <ThreadPrimitive.Root className="relative flex flex-col h-full bg-base-100">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto scroll-smooth">
        <ThreadPrimitive.Empty>
          <WelcomeScreen
            initialMessage={initialMessage}
            suggestions={suggestions}
          />
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages
          components={{
            UserMessage: UserMessage,
            AssistantMessage: AssistantMessage,
          }}
        />

        <ThreadPrimitive.If running>
          <LoadingIndicator />
        </ThreadPrimitive.If>

        {/* Spacer at bottom */}
        <div className="h-4" />
      </ThreadPrimitive.Viewport>

      <ScrollToBottom />
      <Composer />
    </ThreadPrimitive.Root>
  );
};
