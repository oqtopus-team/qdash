"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { useGetExecution } from "@/client/execution/execution";
import { useGetForumPost } from "@/client/forum/forum";
import { useGetTaskResult } from "@/client/task/task";
import { ChatLinkCard, formatValue } from "@/components/features/chat/ChatLinkCard";
import { FigureStrip, figureUrl } from "@/components/features/chat/ChatFigures";
import { ExecutionProgress } from "@/components/features/chat/ExecutionProgress";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { ImagePreviewDialog } from "@/components/ui/ImagePreviewDialog";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/Popover";
import { chatLinkPagePath, classifyChatLink, type ChatLink } from "@/lib/chatLinks";

type PreviewLink = Extract<
  ChatLink,
  { kind: "task-result" | "execution" | "forum-post" | "figure" }
>;

/** How a link was reached: a hovering pointer waits for the open delay, keyboard focus does not. */
export type ChatLinkHoverSource = "pointer" | "focus";

interface ChatLinkPreviewValue {
  /** Open a preview for the link; false when the link is not previewable. */
  preview: (href: string) => boolean;
  /** The pointer or keyboard focus reached a link: show its hover card. */
  enterLink: (anchor: HTMLAnchorElement, source: ChatLinkHoverSource) => void;
  /** The pointer or focus left a link: hide its card unless the pointer moves into it. */
  leaveLink: (anchor: HTMLAnchorElement, source?: ChatLinkHoverSource) => void;
  /** A press began on a link: close its card, and do not reopen it for the focus that follows. */
  pressLink: (anchor: HTMLAnchorElement) => void;
  /** Close the hover card now. */
  dismissCard: () => void;
}

const ChatLinkPreviewContext = createContext<ChatLinkPreviewValue | null>(null);

/** The preview hook, or null outside a provider (links then behave normally). */
export function useChatLinkPreview(): ChatLinkPreviewValue | null {
  return useContext(ChatLinkPreviewContext);
}

/** Hover before a card opens, so a pointer crossing the answer does not flash cards. */
export const CARD_OPEN_DELAY_MS = 400;
/** Grace period for the pointer to travel from the link into its card. */
export const CARD_CLOSE_DELAY_MS = 150;

interface HoverCardState {
  anchor: HTMLAnchorElement;
  link: ChatLink;
}

/** Whether `anchor` is a link the chat should describe in a hover card. */
function isHoverCardLink(anchor: HTMLAnchorElement): boolean {
  const href = anchor.getAttribute("href");
  return Boolean(href);
}

/**
 * Previewable links open in a dialog over the chat; the rest are left to the browser.
 * Every link also shows a compact hover card on pointer hover or keyboard focus.
 */
export function ChatLinkPreviewProvider({ children }: { children: ReactNode }) {
  const [link, setLink] = useState<PreviewLink | null>(null);
  const [card, setCard] = useState<HoverCardState | null>(null);
  const cardRef = useRef<HoverCardState | null>(null);
  const timerRef = useRef<number | null>(null);
  const pressedRef = useRef<HTMLAnchorElement | null>(null);
  const insideCardRef = useRef(false);
  const focusedLinkRef = useRef<HTMLAnchorElement | null>(null);
  const hoveredLinkRef = useRef<HTMLAnchorElement | null>(null);
  const cardId = useId();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const showCard = useCallback((next: HoverCardState | null) => {
    cardRef.current = next;
    setCard(next);
  }, []);

  const dismissCard = useCallback(() => {
    clearTimer();
    insideCardRef.current = false;
    showCard(null);
  }, [clearTimer, showCard]);

  const enterLink = useCallback(
    (anchor: HTMLAnchorElement, source: ChatLinkHoverSource) => {
      if (!isHoverCardLink(anchor)) return;
      if (source === "focus") focusedLinkRef.current = anchor;
      else hoveredLinkRef.current = anchor;
      if (source === "focus" && pressedRef.current === anchor) return;
      clearTimer();
      if (cardRef.current?.anchor === anchor) return;
      const open = () => {
        timerRef.current = null;
        if (!anchor.isConnected) return;
        showCard({ anchor, link: classifyChatLink(anchor.getAttribute("href")!) });
      };
      // Focus opens at once; moving between links while a card is open switches at once too.
      if (source === "focus" || cardRef.current) open();
      else timerRef.current = window.setTimeout(open, CARD_OPEN_DELAY_MS);
    },
    [clearTimer, showCard],
  );

  const leaveLink = useCallback(
    (anchor: HTMLAnchorElement, source?: ChatLinkHoverSource) => {
      if (source === "focus" && focusedLinkRef.current === anchor) focusedLinkRef.current = null;
      if (source === "pointer" && hoveredLinkRef.current === anchor) hoveredLinkRef.current = null;
      if (focusedLinkRef.current === anchor || hoveredLinkRef.current === anchor) return;
      if (pressedRef.current === anchor) pressedRef.current = null;
      if (cardRef.current?.anchor !== anchor) {
        clearTimer(); // a pending open for this link
        return;
      }
      if (insideCardRef.current) return;
      clearTimer();
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        showCard(null);
      }, CARD_CLOSE_DELAY_MS);
    },
    [clearTimer, showCard],
  );

  const pressLink = useCallback(
    (anchor: HTMLAnchorElement) => {
      pressedRef.current = anchor;
      dismissCard();
    },
    [dismissCard],
  );

  const preview = useCallback(
    (href: string) => {
      const classified = classifyChatLink(href);
      if (classified.kind === "internal" || classified.kind === "external") return false;
      dismissCard();
      setLink(classified);
      return true;
    },
    [dismissCard],
  );

  useEffect(() => clearTimer, [clearTimer]);

  // Describe the link by its card while the card is open.
  useEffect(() => {
    const anchor = card?.anchor;
    if (!anchor) return;
    const previous = anchor.getAttribute("aria-describedby");
    anchor.setAttribute("aria-describedby", cardId);
    return () => {
      if (previous === null) anchor.removeAttribute("aria-describedby");
      else anchor.setAttribute("aria-describedby", previous);
    };
  }, [card, cardId]);

  const value = useMemo(
    () => ({ preview, enterLink, leaveLink, pressLink, dismissCard }),
    [preview, enterLink, leaveLink, pressLink, dismissCard],
  );

  const anchorRef = useMemo(() => ({ current: card?.anchor ?? null }), [card]);

  return (
    <ChatLinkPreviewContext.Provider value={value}>
      {children}
      <Popover open={card !== null} onOpenChange={(open) => !open && dismissCard()}>
        <PopoverAnchor virtualRef={anchorRef} />
        {card && (
          <PopoverContent
            id={cardId}
            role="tooltip"
            side="top"
            align="start"
            hideWhenDetached
            data-testid="chat-link-card"
            className="w-[min(20rem,calc(100vw-1.5rem))] p-3"
            // The card is supplementary: focus stays on the link, and leaving the link by
            // keyboard is handled by the link's blur.
            onOpenAutoFocus={(event) => event.preventDefault()}
            onCloseAutoFocus={(event) => event.preventDefault()}
            onFocusOutside={(event) => event.preventDefault()}
            onPointerEnter={() => {
              insideCardRef.current = true;
              clearTimer();
            }}
            onPointerLeave={() => {
              insideCardRef.current = false;
              leaveLink(card.anchor);
            }}
          >
            <ChatLinkCard link={card.link} />
          </PopoverContent>
        )}
      </Popover>
      {link?.kind === "figure" ? (
        <ImagePreviewDialog src={figureUrl(link.path)} onClose={() => setLink(null)} />
      ) : (
        <ChatLinkPreviewDialog link={link} onClose={() => setLink(null)} />
      )}
    </ChatLinkPreviewContext.Provider>
  );
}

function OpenPageLink({ href }: { href: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-ghost">
      <ExternalLink data-icon="inline-start" />
      Open page
    </a>
  );
}

function Loading({ what }: { what: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-base-content/50">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading {what}…
    </div>
  );
}

const PARAMETER_LIMIT = 8;

function TaskResultPreview({ taskId }: { taskId: string }) {
  const query = useGetTaskResult(taskId, { query: { staleTime: 30_000 } });
  const result = query.data?.data;
  if (query.isError) return <p className="text-sm text-error">Could not load this task result.</p>;
  if (!result) return <Loading what="task result" />;

  const params = Object.entries(result.output_parameters ?? {}).slice(0, PARAMETER_LIMIT);
  return (
    <div className="space-y-3">
      <DialogTitle className="text-sm">
        {result.task_name}
        <span className="ml-2 font-normal text-base-content/50">· {result.qid}</span>
      </DialogTitle>
      <DialogDescription className="text-xs text-base-content/50">
        {result.status}
        {result.chip_id ? ` · ${result.chip_id}` : ""} · execution {result.execution_id}
        {result.message ? ` · ${result.message}` : ""}
      </DialogDescription>
      {result.figure_path.length > 0 && <FigureStrip paths={result.figure_path} />}
      {params.length > 0 && (
        <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
          {params.map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="font-mono text-base-content/55">{name}</dt>
              <dd className="m-0 font-mono">{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="flex justify-end">
        <OpenPageLink href={`/task-results/${encodeURIComponent(result.task_id)}`} />
      </div>
    </div>
  );
}

function ExecutionPreview({ executionId, chipId }: { executionId: string; chipId: string | null }) {
  const query = useGetExecution(executionId, { query: { staleTime: 5_000 } });
  const execution = query.data?.data;
  const resolvedChip = chipId ?? execution?.chip_id ?? null;
  return (
    <div className="space-y-3">
      <DialogTitle className="text-sm">{execution?.name ?? `Execution ${executionId}`}</DialogTitle>
      <DialogDescription className="sr-only">Execution status and tasks</DialogDescription>
      <ExecutionProgress executionId={executionId} />
      <div className="flex justify-end">
        <OpenPageLink
          href={chatLinkPagePath({
            kind: "execution",
            executionId,
            chipId: resolvedChip,
            href: "",
          })!}
        />
      </div>
    </div>
  );
}

const CONTENT_LIMIT = 600;

function ForumPostPreview({ postId }: { postId: string }) {
  const query = useGetForumPost(postId, { query: { staleTime: 30_000 } });
  const post = query.data?.data;
  if (query.isError) return <p className="text-sm text-error">Could not load this post.</p>;
  if (!post) return <Loading what="post" />;
  const content =
    post.content.length > CONTENT_LIMIT ? `${post.content.slice(0, CONTENT_LIMIT)}…` : post.content;
  return (
    <div className="space-y-3">
      <DialogTitle className="text-sm">{post.title || "Forum post"}</DialogTitle>
      <DialogDescription className="text-xs text-base-content/50">
        {post.username}
        {post.category ? ` · ${post.category}` : ""}
        {post.reply_count ? ` · ${post.reply_count} replies` : ""}
      </DialogDescription>
      <p className="whitespace-pre-wrap text-sm text-base-content/80">{content}</p>
      <div className="flex justify-end">
        <OpenPageLink href={`/forum/${encodeURIComponent(post.id)}`} />
      </div>
    </div>
  );
}

function ChatLinkPreviewDialog({
  link,
  onClose,
}: {
  link: Exclude<PreviewLink, { kind: "figure" }> | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={link !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl p-5" data-testid="chat-link-preview">
        {link?.kind === "task-result" && <TaskResultPreview taskId={link.taskId} />}
        {link?.kind === "execution" && (
          <ExecutionPreview executionId={link.executionId} chipId={link.chipId} />
        )}
        {link?.kind === "forum-post" && <ForumPostPreview postId={link.postId} />}
      </DialogContent>
    </Dialog>
  );
}
