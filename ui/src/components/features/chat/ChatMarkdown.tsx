"use client";

import { memo, useCallback, useMemo, useReducer, useState } from "react";
import type React from "react";
import { Markdown, type ControlsConfig } from "@pierre/words/react";
import "katex/dist/katex.min.css";
import {
  ChatLink,
  handlePreviewClick,
  useChatLinkPreview,
} from "@/components/features/chat/ChatPreviewLink";
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
import { useCodeHighlighter } from "@/lib/highlight";
import { resetDiagram, startDiagramPan, zoomDiagram, ZOOM_STEP } from "@/lib/chatMermaidView";
import { codeBlockTitle, codeFileName, downloadText } from "@/lib/chatDownloads";
import { copyText } from "@/lib/utils/clipboard";

export { normalizeMathDelimiters } from "@/lib/chatMarkdown";

export { ChatLink };

// Both buttons are handled here: copy through the shared clipboard helper, and
// download with a file name from the fence's title or language.
const controls: ControlsConfig = { code: { copy: true, download: true } };

const CODE_BLOCK = '[data-markdown="code-block"]';

function blockCode(block: Element | null): string {
  if (!(block instanceof HTMLElement)) return "";
  return block.dataset.code ?? block.querySelector("pre code")?.textContent ?? "";
}

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
 * Hover cards for its links come from the app-wide `LinkHoverCardProvider`.
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
  // Highlights replaces highlight.js once it has loaded.
  const codeHighlighter = useCodeHighlighter(/`{3}|~{3}|(?:^|\n)(?: {4}|\t)/.test(children));
  const plugins = useMemo(
    () => createChatPlugins(theme, diagramSettled, diagrams),
    // A new plugin object is what makes the renderer pick up a settled diagram
    // or the loaded highlighter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme, diagramRevision, diagrams, codeHighlighter],
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

  // Runs before the renderer's own button handler, which only knows the async
  // Clipboard API and names every download `code.<language>`; copyText also
  // works on plain-HTTP deployments.
  const onClickCapture = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as Element;
      const button = target.closest<HTMLButtonElement>("button[data-code-action]");
      if (!button || !event.currentTarget.contains(button)) return;
      event.stopPropagation();
      if (button.disabled) return;
      const block = button.closest<HTMLElement>(CODE_BLOCK);
      const code = blockCode(block);
      if (button.dataset.codeAction !== "download") {
        copy(button, code, "Failed to copy code");
        return;
      }
      // The renderer drops the fence's title, so match the block to its source
      // fence by code, counting earlier blocks with the same code.
      const earlier = [...event.currentTarget.querySelectorAll(CODE_BLOCK)];
      const occurrence = earlier
        .slice(0, block ? earlier.indexOf(block) : 0)
        .filter((other) => blockCode(other) === code).length;
      const title = codeBlockTitle(source, code, occurrence);
      downloadText(codeFileName(block?.dataset.language, title), code);
    },
    [copy, source],
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
              // Focus returns here on close, or to the answer if streaming replaced it.
              opener: action,
              focusFallback: event.currentTarget,
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
        data-link-preview="chat"
      >
        {source}
      </Markdown>
      {fullscreen && <ChatMermaidDialog diagram={fullscreen} onClose={() => setFullscreen(null)} />}
    </>
  );
});
