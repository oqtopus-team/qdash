"use client";

import React, { useEffect, useRef, useId } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import dynamic from "next/dynamic";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

const ChatPlotlyChart = dynamic(
  () =>
    import("@/components/features/chat/ChatPlotlyChart").then(
      (m) => m.ChatPlotlyChart,
    ),
  { ssr: false },
);

/**
 * Renders a mermaid diagram from a code string.
 * Uses mermaid.render() on the client side only.
 */
function MermaidDiagram({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uniqueId = useId().replace(/:/g, "_");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "loose",
        });
        const { svg } = await mermaid.render(`mermaid${uniqueId}`, code);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (e) {
        // Fallback: show as code block
        if (!cancelled && containerRef.current) {
          containerRef.current.textContent = code;
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, uniqueId]);

  return (
    <div
      ref={containerRef}
      className="my-3 flex justify-center overflow-x-auto"
    />
  );
}

const MENTION_RE = /@(qdash)\b/gi;

/**
 * Splits text into segments, wrapping @qdash mentions with a highlight span.
 */
function highlightMentions(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(MENTION_RE.source, MENTION_RE.flags);

  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    parts.push(
      <span
        key={match.index}
        className="inline-flex items-center bg-primary/15 text-primary font-semibold rounded px-1 py-0.5 text-[0.85em]"
      >
        @{match[1]}
      </span>,
    );
    lastIndex = re.lastIndex;
  }

  if (lastIndex === 0) return text;
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return <>{parts}</>;
}

/**
 * Attempt to parse a JSON code block as a Plotly chart spec.
 * Returns the parsed data/layout or null.
 */
function tryParsePlotlyJson(
  code: string,
): { data: Record<string, unknown>[]; layout: Record<string, unknown> } | null {
  try {
    const obj = JSON.parse(code);
    if (
      obj &&
      typeof obj === "object" &&
      Array.isArray(obj.data) &&
      obj.layout &&
      typeof obj.layout === "object"
    ) {
      return {
        data: obj.data as Record<string, unknown>[],
        layout: obj.layout as Record<string, unknown>,
      };
    }
  } catch {
    // not valid JSON
  }
  return null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const markdownComponents: Record<string, React.ComponentType<any>> = {
  code({
    className,
    children,
    ...props
  }: React.ComponentPropsWithoutRef<"code"> & { className?: string }) {
    const match = /language-(\w+)/.exec(className || "");
    const codeString = String(children).replace(/\n$/, "");

    // Render mermaid diagrams
    if (match && match[1] === "mermaid") {
      return <MermaidDiagram code={codeString} />;
    }

    // Render Plotly charts from JSON code blocks
    if (match && match[1] === "json") {
      const plotly = tryParsePlotlyJson(codeString);
      if (plotly) {
        return <ChatPlotlyChart data={plotly.data} layout={plotly.layout} />;
      }
    }

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
  // Intercept paragraph nodes to highlight @mentions in text
  p({ children, ...props }: React.ComponentPropsWithoutRef<"p">) {
    return (
      <p {...props}>
        {React.Children.map(children, (child) => {
          if (typeof child === "string" && MENTION_RE.test(child)) {
            return highlightMentions(child);
          }
          return child;
        })}
      </p>
    );
  },
  // Also handle mentions in list items
  li({ children, ...props }: React.ComponentPropsWithoutRef<"li">) {
    return (
      <li {...props}>
        {React.Children.map(children, (child) => {
          if (typeof child === "string" && MENTION_RE.test(child)) {
            return highlightMentions(child);
          }
          return child;
        })}
      </li>
    );
  },
};

/**
 * Custom URL transform that extends the default behaviour to allow
 * `data:` URIs.  react-markdown v10 strips any protocol not in its
 * safe-list (http, https, mailto …) which breaks inline base64 images
 * returned by the task-knowledge API.
 */
function urlTransform(url: string): string {
  if (url.startsWith("data:")) return url;
  // Fall back to the built-in sanitisation for everything else.
  const colon = url.indexOf(":");
  const questionMark = url.indexOf("?");
  const numberSign = url.indexOf("#");
  const slash = url.indexOf("/");
  if (
    colon === -1 ||
    (slash !== -1 && colon > slash) ||
    (questionMark !== -1 && colon > questionMark) ||
    (numberSign !== -1 && colon > numberSign) ||
    /^(https?|ircs?|mailto|xmpp)$/i.test(url.slice(0, colon))
  ) {
    return url;
  }
  return "";
}

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
        urlTransform={urlTransform}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
