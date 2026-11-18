"use client";

import { memo, useCallback, useMemo, useReducer, useState } from "react";
import type React from "react";
import { Markdown, type ControlsConfig } from "@pierre/words/react";
import "katex/dist/katex.min.css";
import { useChatLinkPreview } from "@/components/features/chat/ChatLinkPreview";
import {
  ChatMermaidDialog,
  type ChatMermaidDiagram,
} from "@/components/features/chat/ChatMermaidDialog";
import { useToast } from "@/components/ui/Toast";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import {
  chatMarkdownComponents,
  createChatPlugins,
  prepareChatMarkdown,
  type MermaidAction,
  type ChatDiagramCache,
} from "@/lib/chatMarkdown";
import { resetDiagram, startDiagramPan, zoomDiagram, ZOOM_STEP } from "@/lib/chatMermaidView";
import { copyText } from "@/lib/utils/clipboard";

export { normalizeMathDelimiters } from "@/lib/chatMarkdown";

type PreviewHandle = ReturnType<typeof useChatLinkPreview>;

/** Whether a click on `href` should open a preview instead of the browser's default. */
function handlePreviewClick(
  event: React.MouseEvent<HTMLElement>,
  href: string | undefined,
  preview: PreviewHandle,
): void {
  if (event.defaultPrevented || !href || !preview) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
  if (preview.preview(href)) event.preventDefault();
}

/**
 * A link in an answer. QDash records (task results, executions, forum posts,
 * figures) open as a preview over the chat; everything else opens in a new
 * tab, so a click never navigates away from the conversation.
 */
export function ChatLink({
  href,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  children?: React.ReactNode;
}) {
  const preview = useChatLinkPreview();
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      {...props}
      onClick={(event) => {
        props.onClick?.(event);
        handlePreviewClick(event, href, preview);
      }}
    >
      {children}
    </a>
  );
}

// Copy only: the renderer's download button has no counterpart in chat.
const controls: ControlsConfig = { code: { copy: true, download: false } };

const COPIED_MS = 2000;

/** Show "Copied" on a text button, or a pressed state on an icon button, for a moment. */
function flashCopied(button: HTMLButtonElement): void {
  if (button.dataset.copied) return;
  button.dataset.copied = "true";
  const label = button.getAttribute("aria-label");
  const text = button.textContent;
  const hasText = !button.querySelector("svg");
  if (hasText) button.textContent = "Copied";
  button.setAttribute("aria-label", "Copied");
  window.setTimeout(() => {
    delete button.dataset.copied;
    if (hasText) button.textContent = text;
    if (label === null) button.removeAttribute("aria-label");
    else button.setAttribute("aria-label", label);
  }, COPIED_MS);
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

/**
 * Markdown for chat answers: GFM, math, highlighted code and Mermaid diagrams.
 *
 * @pierre/words owns the rendered DOM and patches only what changed as text
 * streams in, so the interactive parts (link previews, copy buttons, diagram
 * controls) are handled here by delegation instead of as React components.
 */
export const ChatMarkdown = memo(function ChatMarkdown({
  children,
  className,
  streaming = false,
}: ChatMarkdownProps) {
  const isDark = useIsDarkTheme();
  const theme = isDark ? "dark" : "neutral";
  const preview = useChatLinkPreview();
  const toast = useToast();
  const [fullscreen, setFullscreen] = useState<ChatMermaidDiagram | null>(null);
  // Bumped when a diagram finishes rendering, so the renderer formats it again.
  const [diagramRevision, diagramSettled] = useReducer((revision: number) => revision + 1, 0);

  // Retain results for this mounted answer even after the shared cache evicts them.
  const diagrams = useMemo<ChatDiagramCache>(
    () => ({ results: new Map(), pending: new Set() }),
    [theme],
  );
  const plugins = useMemo(
    () => createChatPlugins(theme, diagramSettled, diagrams),
    // A new plugin object is what makes the renderer pick up a settled diagram.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme, diagramRevision, diagrams],
  );
  const source = useMemo(() => prepareChatMarkdown(children, streaming), [children, streaming]);

  const copy = useCallback(
    (button: HTMLButtonElement, text: string, failure: string) => {
      copyText(text).then(
        () => flashCopied(button),
        () => toast.error(failure),
      );
    },
    [toast],
  );

  // Runs before the renderer's own copy handler, which only knows the async
  // Clipboard API; copyText also works on plain-HTTP deployments.
  const onClickCapture = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as Element;
      const button = target.closest<HTMLButtonElement>("button[data-code-action]");
      if (!button || !event.currentTarget.contains(button)) return;
      event.stopPropagation();
      if (button.disabled || button.dataset.codeAction !== "copy") return;
      const block = button.closest<HTMLElement>('[data-markdown="code-block"]');
      const code = block?.dataset.code ?? block?.querySelector("pre code")?.textContent ?? "";
      copy(button, code, "Failed to copy code");
    },
    [copy],
  );

  const onClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as Element;
      const action = target.closest<HTMLButtonElement>("button[data-mermaid-action]");
      if (action && event.currentTarget.contains(action)) {
        const frame = action.closest<HTMLElement>("[data-chat-mermaid]");
        const viewport = frame?.querySelector<HTMLElement>("[data-mermaid-viewport]");
        if (!frame || !viewport) return;
        switch (action.dataset.mermaidAction as MermaidAction) {
          case "zoom-in":
            zoomDiagram(viewport, ZOOM_STEP);
            break;
          case "zoom-out":
            zoomDiagram(viewport, 1 / ZOOM_STEP);
            break;
          case "reset":
            resetDiagram(viewport);
            break;
          case "copy":
            copy(action, frame.dataset.source ?? "", "Failed to copy diagram source");
            break;
          case "fullscreen": {
            const canvas = viewport.querySelector("[data-mermaid-canvas]");
            setFullscreen({
              svg: canvas?.innerHTML ?? "",
              source: frame.dataset.source ?? "",
            });
            break;
          }
        }
        return;
      }
      const anchor = target.closest<HTMLAnchorElement>("a[href]");
      if (anchor && event.currentTarget.contains(anchor)) {
        handlePreviewClick(event, anchor.getAttribute("href") ?? undefined, preview);
      }
    },
    [copy, preview],
  );

  const onPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const viewport = (event.target as Element).closest<HTMLElement>("[data-mermaid-viewport]");
    if (viewport && event.currentTarget.contains(viewport)) {
      startDiagramPan(viewport, event.nativeEvent);
    }
  }, []);

  return (
    <>
      <Markdown
        className={`chat-prose prose prose-sm max-w-none ${className ?? ""}`}
        mode={streaming ? "streaming" : "static"}
        isAnimating={streaming}
        caret={streaming ? "block" : undefined}
        cjk
        math
        components={chatMarkdownComponents}
        plugins={plugins}
        controls={controls}
        lineNumbers={false}
        onClickCapture={onClickCapture}
        onClick={onClick}
        onPointerDown={onPointerDown}
      >
        {source}
      </Markdown>
      {fullscreen && <ChatMermaidDialog diagram={fullscreen} onClose={() => setFullscreen(null)} />}
    </>
  );
});
