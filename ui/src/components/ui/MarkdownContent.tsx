import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

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
  img({ src, alt, ...props }: React.ComponentPropsWithoutRef<"img">) {
    return (
      <img
        src={src}
        alt={alt ?? ""}
        className="max-w-full h-auto rounded border border-base-300 my-2"
        loading="lazy"
        {...props}
      />
    );
  },
};

export function MarkdownContent({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={`prose prose-sm max-w-none ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
