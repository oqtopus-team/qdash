"use client";

import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

const components: Components = {
  // Fenced blocks render through CodeBlock; `pre` is a pass-through so the
  // block is not wrapped in a second, unstyled <pre>.
  pre({ children }) {
    return <>{children}</>;
  },
  code({ className, children, ...props }) {
    const match = /language-([\w+-]+)/.exec(className || "");
    const codeString = String(children).replace(/\n$/, "");
    if (match || codeString.includes("\n")) {
      return <CodeBlock language={match?.[1]}>{codeString}</CodeBlock>;
    }
    return (
      <code className="chat-inline-code" {...props}>
        {children}
      </code>
    );
  },
  a({ href, children, ...props }) {
    const external = href ? /^https?:\/\//.test(href) : false;
    return (
      <a
        href={href}
        {...props}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      >
        {children}
      </a>
    );
  },
  table({ children, ...props }) {
    return (
      <div className="chat-table-wrap">
        <table {...props}>{children}</table>
      </div>
    );
  },
};

/**
 * Models write LaTeX as \( \) and \[ \] as often as $ and $$, but remark-math
 * only understands dollars. Rewrite the bracket forms outside code spans.
 */
export function normalizeMathDelimiters(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
    .map((part, i) => {
      if (i % 2 === 1) return part;
      return part
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr: string) => `\n$$\n${expr.trim()}\n$$\n`)
        .replace(/\\\(([\s\S]+?)\\\)/g, (_, expr: string) => `$${expr}$`);
    })
    .join("");
}

interface ChatMarkdownProps {
  children: string;
  className?: string;
}

/** Markdown for chat answers: GFM, math, highlighted code. */
export const ChatMarkdown = memo(function ChatMarkdown({ children, className }: ChatMarkdownProps) {
  return (
    <div className={`chat-prose prose prose-sm max-w-none ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
        components={components}
      >
        {normalizeMathDelimiters(children)}
      </ReactMarkdown>
    </div>
  );
});
