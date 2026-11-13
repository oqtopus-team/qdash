"use client";

import { memo, useMemo } from "react";
import type React from "react";
import {
  Streamdown,
  defaultComponents,
  defaultRehypePlugins,
  defaultUrlTransform,
  useIsCodeFenceIncomplete,
  type Components,
  type ControlsConfig,
  type ExtraProps,
  type MermaidErrorComponentProps,
  type PluginConfig,
} from "streamdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { CodeBlock } from "@/components/features/chat/CodeBlock";
import { useChatLinkPreview } from "@/components/features/chat/ChatLinkPreview";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { createLazyMermaidPlugin } from "@/lib/chatMermaid";

/** The href Streamdown gives a link whose URL has not finished streaming. */
const INCOMPLETE_LINK = "streamdown:incomplete-link";

/**
 * A link in an answer. QDash records (task results, executions, forum posts,
 * figures) open as a preview over the chat; everything else opens in a new
 * tab, so a click never navigates away from the conversation.
 */
export function ChatLink({
  href,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) {
  const preview = useChatLinkPreview();
  if (href === INCOMPLETE_LINK) {
    // The URL is still arriving: show the label, link it once it is complete.
    return <span data-incomplete="true">{children}</span>;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      {...props}
      onClick={(event) => {
        props.onClick?.(event);
        if (event.defaultPrevented || !href || !preview) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        if (preview.preview(href)) event.preventDefault();
      }}
    >
      {children}
    </a>
  );
}

type CodeProps = React.JSX.IntrinsicElements["code"] & ExtraProps;

function codeText(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(codeText).join("");
  return String(children ?? "");
}

/** Fenced code: highlighted with copy, or a Mermaid diagram once its fence closes. */
function ChatCodeBlock({ node, className, children, ...props }: CodeProps) {
  const incomplete = useIsCodeFenceIncomplete();
  const language = /language-([\w+-]+)/.exec(className ?? "")?.[1];
  if (language === "mermaid" && !incomplete) {
    const MermaidCode = defaultComponents.code;
    return (
      <MermaidCode node={node} className={className} {...props}>
        {children}
      </MermaidCode>
    );
  }
  return (
    <CodeBlock language={language} caret={incomplete}>
      {codeText(children).replace(/\n$/, "")}
    </CodeBlock>
  );
}

function ChatInlineCode({ node: _node, className, children, ...props }: CodeProps) {
  return (
    <code className={`chat-inline-code ${className ?? ""}`} {...props}>
      {children}
    </code>
  );
}

function ChatMarkdownLink({
  node: _node,
  href,
  children,
  ...props
}: React.JSX.IntrinsicElements["a"] & ExtraProps) {
  return (
    <ChatLink href={href} {...props}>
      {children}
    </ChatLink>
  );
}

function ChatTable({
  node: _node,
  children,
  ...props
}: React.JSX.IntrinsicElements["table"] & ExtraProps) {
  return (
    <div className="chat-table-wrap">
      <table {...props}>{children}</table>
    </div>
  );
}

function ChatMermaidError({ chart, error }: MermaidErrorComponentProps) {
  return (
    <div className="my-3" data-testid="chat-mermaid-error">
      <p className="mb-1 text-xs text-base-content/50">
        This diagram could not be displayed: {error}
      </p>
      <CodeBlock language="mermaid">{chart}</CodeBlock>
    </div>
  );
}

/**
 * Typography comes from `prose` and `.chat-prose`, so prose elements render as
 * plain tags instead of Streamdown's own Tailwind styling. Paragraphs, `pre`
 * and footnote sections keep Streamdown's renderers, which unwrap code blocks.
 */
const components: Components = {
  a: ChatMarkdownLink,
  code: ChatCodeBlock,
  inlineCode: ChatInlineCode,
  table: ChatTable,
  thead: "thead",
  tbody: "tbody",
  tr: "tr",
  th: "th",
  td: "td",
  h1: "h1",
  h2: "h2",
  h3: "h3",
  h4: "h4",
  h5: "h5",
  h6: "h6",
  ol: "ol",
  ul: "ul",
  li: "li",
  hr: "hr",
  strong: "strong",
  blockquote: "blockquote",
  sup: "sup",
  sub: "sub",
  img: "img",
};

/**
 * Sanitize and harden without `rehype-raw`: raw HTML in an answer shows as
 * text, as it did before, instead of becoming elements.
 */
const rehypePlugins = [defaultRehypePlugins.sanitize, defaultRehypePlugins.harden];

/**
 * remark-math and rehype-katex are the app's existing math pipeline. Streamdown
 * runs the math plugin after sanitizing, so KaTeX markup is kept.
 */
const plugins: PluginConfig = {
  math: {
    name: "katex",
    type: "math",
    remarkPlugin: remarkMath,
    rehypePlugin: [rehypeKatex, { throwOnError: false, strict: false }],
  },
  mermaid: createLazyMermaidPlugin(),
};

// Code copy, tables and links use QDash's own components; only diagrams use Streamdown's controls.
const controls: ControlsConfig = {
  code: false,
  table: false,
  image: false,
  mermaid: { copy: true, download: false, fullscreen: true, panZoom: true },
};

const linkSafety = { enabled: false };

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
  /**
   * The text is still arriving. Unclosed Markdown (emphasis, links, fences,
   * tables) is completed for display and a caret follows the text. Saved
   * answers render statically, exactly as written.
   */
  streaming?: boolean;
}

/** Markdown for chat answers: GFM, math, highlighted code and Mermaid diagrams. */
export const ChatMarkdown = memo(function ChatMarkdown({
  children,
  className,
  streaming = false,
}: ChatMarkdownProps) {
  const isDark = useIsDarkTheme();
  const mermaid = useMemo(
    () => ({
      config: { theme: isDark ? "dark" : "neutral" },
      errorComponent: ChatMermaidError,
    }),
    [isDark],
  );
  return (
    <Streamdown
      // space-y-0 replaces Streamdown's block spacing; prose sets the margins.
      className={`space-y-0 chat-prose prose prose-sm max-w-none ${className ?? ""}`}
      mode={streaming ? "streaming" : "static"}
      isAnimating={streaming}
      parseIncompleteMarkdown={streaming}
      caret={streaming ? "block" : undefined}
      components={components}
      rehypePlugins={rehypePlugins}
      urlTransform={defaultUrlTransform}
      plugins={plugins}
      controls={controls}
      linkSafety={linkSafety}
      mermaid={mermaid}
      lineNumbers={false}
    >
      {normalizeMathDelimiters(children)}
    </Streamdown>
  );
});
