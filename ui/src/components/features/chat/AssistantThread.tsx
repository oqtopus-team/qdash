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
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useState } from "react";

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
    <div className="text-base-content text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children }) => (
            <div className="overflow-x-auto my-3">
              <table className="table table-xs table-zebra w-full border border-base-300 rounded-lg">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-base-300">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="text-base-content font-semibold text-left px-3 py-2 border-b border-base-300">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="text-base-content px-3 py-2 border-b border-base-200">
              {children}
            </td>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-base-200/50">{children}</tr>
          ),
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <code className="block bg-base-300 p-3 rounded-lg text-xs overflow-x-auto font-mono">
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-base-300 px-1.5 py-0.5 rounded text-xs font-mono">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="bg-base-300 rounded-lg text-xs overflow-x-auto my-3 p-0">
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
          p: ({ children }) => <p className="my-2">{children}</p>,
          h1: ({ children }) => (
            <h1 className="text-xl font-bold my-3">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-bold my-2">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-bold my-2">{children}</h3>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              className="text-primary hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-primary pl-4 my-3 italic opacity-80 bg-base-200/50 py-2 rounded-r">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-base-300" />,
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
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
      className="btn btn-ghost btn-xs opacity-0 group-hover:opacity-100 transition-opacity"
      title="Copy message"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
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
        <div className="bg-primary text-primary-content rounded-2xl rounded-br-md px-4 py-2.5 shadow-sm">
          <SimpleText />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

// Assistant message component - ChatGPT style without bubble
const AssistantMessage: FC = () => {
  return (
    <MessagePrimitive.Root className="group py-4 px-4 hover:bg-base-200/30 transition-colors">
      <div className="flex gap-3 max-w-full">
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-secondary to-accent flex items-center justify-center text-white text-[10px] font-bold mt-0.5">
          AI
        </div>
        <div className="flex-1 min-w-0">
          <MarkdownText />
          <ActionBarPrimitive.Root className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <CopyButton />
            <ActionBarPrimitive.Reload asChild>
              <button className="btn btn-ghost btn-xs" title="Regenerate">
                <RefreshCw className="w-3 h-3" />
              </button>
            </ActionBarPrimitive.Reload>
          </ActionBarPrimitive.Root>
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

// Loading indicator with animation - ChatGPT style
const LoadingIndicator: FC = () => {
  return (
    <div className="py-4 px-4">
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-secondary to-accent flex items-center justify-center text-white text-[10px] font-bold animate-pulse">
          AI
        </div>
        <div className="flex items-center gap-1">
          <span
            className="w-2 h-2 bg-base-content/40 rounded-full animate-bounce"
            style={{ animationDelay: "0ms" }}
          />
          <span
            className="w-2 h-2 bg-base-content/40 rounded-full animate-bounce"
            style={{ animationDelay: "150ms" }}
          />
          <span
            className="w-2 h-2 bg-base-content/40 rounded-full animate-bounce"
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
    <ComposerPrimitive.Root className="flex items-end gap-2 p-3 border-t border-base-300 bg-base-100">
      <ComposerPrimitive.Input
        rows={1}
        autoFocus
        placeholder="Type a message..."
        className="textarea textarea-bordered flex-1 min-h-[44px] max-h-32 resize-none text-sm leading-relaxed py-2.5"
      />
      <ThreadPrimitive.If running={false}>
        <ComposerPrimitive.Send asChild>
          <button className="btn btn-primary btn-sm h-11 w-11 rounded-xl shadow-sm">
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
      <button className="absolute bottom-20 right-4 btn btn-circle btn-sm btn-ghost bg-base-200 shadow-md hover:bg-base-300 z-10">
        <ArrowDown className="w-4 h-4" />
      </button>
    </ThreadPrimitive.ScrollToBottom>
  );
};

interface Suggestion {
  label: string;
  prompt: string;
}

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

  return (
    <div className="flex flex-wrap gap-2 justify-center max-w-sm">
      {suggestions.map((suggestion, index) => (
        <button
          key={index}
          onClick={() => handleClick(suggestion.prompt)}
          className="btn btn-sm btn-outline btn-primary hover:btn-primary transition-all"
        >
          {suggestion.label}
        </button>
      ))}
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
          <div className="flex flex-col items-center justify-center h-full p-6 text-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-secondary to-accent flex items-center justify-center text-white text-xl font-bold shadow-lg mb-4">
              AI
            </div>
            <h3 className="text-lg font-semibold text-base-content mb-2">
              QDash Assistant
            </h3>
            <p className="text-sm text-base-content/70 mb-4 max-w-sm">
              {initialMessage ||
                "I can help you analyze chip calibration metrics."}
            </p>
            {suggestions && suggestions.length > 0 && (
              <SuggestionButtons suggestions={suggestions} />
            )}
          </div>
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
