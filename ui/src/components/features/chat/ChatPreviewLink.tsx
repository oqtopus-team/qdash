"use client";

import { createContext, useContext, type AnchorHTMLAttributes, type MouseEvent } from "react";

export interface ChatLinkPreviewValue {
  /** Open a preview for the link; false when the link is not previewable. */
  preview: (href: string) => boolean;
}

/**
 * Provided by `ChatLinkPreviewProvider`. Kept apart from the provider so
 * components the preview dialog renders (such as the execution progress card)
 * can link to records without importing the dialog that renders them.
 */
export const ChatLinkPreviewContext = createContext<ChatLinkPreviewValue | null>(null);

/** The preview hook, or null outside a provider (links then behave normally). */
export function useChatLinkPreview(): ChatLinkPreviewValue | null {
  return useContext(ChatLinkPreviewContext);
}

/** Whether a click on `href` should open a preview instead of the browser's default. */
export function handlePreviewClick(
  event: MouseEvent<HTMLElement>,
  href: string | undefined,
  preview: ChatLinkPreviewValue | null,
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
export function ChatLink({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
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
