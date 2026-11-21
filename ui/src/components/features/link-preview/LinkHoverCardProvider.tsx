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
import { LinkPreviewCard } from "@/components/features/link-preview/LinkPreviewCard";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/Popover";
import { describeLink, type LinkDescription, type LinkScope } from "@/lib/linkPreview";

/** Hover before a card opens, so a pointer crossing the page does not flash cards. */
export const CARD_OPEN_DELAY_MS = 400;
/** Grace period for the pointer to travel from the link into its card. */
export const CARD_CLOSE_DELAY_MS = 150;

/**
 * Marks a subtree's links: `"chat"` for chat answers, which keep their record leniency
 * (see `lib/chatLinks.ts`), and `"off"` for links that must not show a card, such as the
 * card's own content.
 */
const LINK_PREVIEW_ATTRIBUTE = "data-link-preview";

const LINK_SELECTOR = "a[href]";
const OFF_SELECTOR = `[${LINK_PREVIEW_ATTRIBUTE}="off"]`;
const CHAT_SELECTOR = `[${LINK_PREVIEW_ATTRIBUTE}="chat"]`;

type Source = "pointer" | "focus";

interface CardState {
  anchor: Element;
  link: LinkDescription;
}

interface Timer {
  id: number;
  anchor: Element;
}

const LinkHoverCardContext = createContext(false);

/**
 * Which links get a card: `"all"` covers every explicit link, `"chat"` only links inside a
 * `data-link-preview="chat"` subtree (chat answers), so ordinary page navigation stays free
 * of hover popups.
 */
export type LinkHoverCardScope = "all" | "chat";

/** The link an event happened on, unless it is in an opted-out subtree such as a card. */
function eventLink(target: EventTarget | null, scope: LinkHoverCardScope): Element | null {
  if (!(target instanceof Element)) return null;
  const anchor = target.closest(LINK_SELECTOR);
  if (!anchor || anchor.closest(OFF_SELECTOR)) return null;
  if (scope === "chat" && !anchor.closest(CHAT_SELECTOR)) return null;
  if (anchor.getAttribute("aria-disabled") === "true") return null;
  return anchor;
}

function fragmentLabel(id: string): string | null {
  const element = document.getElementById(id);
  const text = element?.textContent?.replace(/\s+/g, " ").trim();
  if (!text) return null;
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

function describeAnchor(anchor: Element): LinkDescription | null {
  const scope: LinkScope = anchor.closest(CHAT_SELECTOR) ? "chat" : "app";
  return describeLink({
    href: anchor.getAttribute("href") ?? "",
    download: anchor.getAttribute("download"),
    target: anchor.getAttribute("target"),
    scope,
    resolveFragment: fragmentLabel,
  });
}

/**
 * Shows a compact hover card for the explicit links in `scope`: `<a href>` and Next.js
 * `<Link>` alike, including links inside dialogs, menus and other portals. Links are found
 * by delegation on the document, so pages need no wrappers and clicks are left alone.
 *
 * A pointer opens the card after `CARD_OPEN_DELAY_MS`; keyboard focus opens it at once.
 * Touch never hovers, and focus that follows a press does not open a card. The app root
 * mounts one chat-scoped provider; a nested one (as the chat adds for isolated renders)
 * is a no-op.
 */
export function LinkHoverCardProvider({
  scope = "all",
  children,
}: {
  scope?: LinkHoverCardScope;
  children: ReactNode;
}) {
  const nested = useContext(LinkHoverCardContext);
  if (nested) return <>{children}</>;
  return (
    <LinkHoverCardContext.Provider value={true}>
      {children}
      <LinkHoverCardRoot scope={scope} />
    </LinkHoverCardContext.Provider>
  );
}

function LinkHoverCardRoot({ scope }: { scope: LinkHoverCardScope }) {
  const [card, setCard] = useState<CardState | null>(null);
  const cardRef = useRef<CardState | null>(null);
  const openTimerRef = useRef<Timer | null>(null);
  const closeTimerRef = useRef<Timer | null>(null);
  const insideCardRef = useRef(false);
  const focusedRef = useRef<Element | null>(null);
  const hoveredRef = useRef<Element | null>(null);
  // The last input: focus after a pointer press is not keyboard focus.
  const modalityRef = useRef<"keyboard" | "pointer">("keyboard");
  const cardId = useId();

  const clearOpen = useCallback(() => {
    if (openTimerRef.current) window.clearTimeout(openTimerRef.current.id);
    openTimerRef.current = null;
  }, []);

  const clearClose = useCallback(() => {
    if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current.id);
    closeTimerRef.current = null;
  }, []);

  const showCard = useCallback((next: CardState | null) => {
    cardRef.current = next;
    setCard(next);
  }, []);

  const dismiss = useCallback(() => {
    clearOpen();
    clearClose();
    insideCardRef.current = false;
    showCard(null);
  }, [clearOpen, clearClose, showCard]);

  const enterLink = useCallback(
    (anchor: Element, source: Source) => {
      if (source === "focus") {
        // Focus that a press or a hovering pointer caused is the pointer's.
        if (modalityRef.current === "pointer" || hoveredRef.current === anchor) return;
        focusedRef.current = anchor;
      } else {
        hoveredRef.current = anchor;
      }
      if (cardRef.current?.anchor === anchor) {
        clearClose();
        return;
      }
      const link = describeAnchor(anchor);
      if (!link) return;
      clearOpen();
      const open = () => {
        openTimerRef.current = null;
        if (!anchor.isConnected) return;
        clearClose();
        insideCardRef.current = false;
        showCard({ anchor, link });
      };
      // Focus opens at once; moving between links while a card is open switches at once too.
      if (source === "focus" || cardRef.current) open();
      else openTimerRef.current = { id: window.setTimeout(open, CARD_OPEN_DELAY_MS), anchor };
    },
    [clearOpen, clearClose, showCard],
  );

  const leaveLink = useCallback(
    (anchor: Element, source?: Source) => {
      if (source === "focus" && focusedRef.current === anchor) focusedRef.current = null;
      if (source === "pointer" && hoveredRef.current === anchor) hoveredRef.current = null;
      if (focusedRef.current === anchor || hoveredRef.current === anchor) return;
      if (openTimerRef.current?.anchor === anchor) clearOpen();
      if (cardRef.current?.anchor !== anchor || insideCardRef.current) return;
      clearClose();
      closeTimerRef.current = {
        id: window.setTimeout(() => {
          closeTimerRef.current = null;
          showCard(null);
        }, CARD_CLOSE_DELAY_MS),
        anchor,
      };
    },
    [clearOpen, clearClose, showCard],
  );

  // Delegate on the document, so links in portals (dialogs, menus) are reached too.
  useEffect(() => {
    const onPointerOver = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const anchor = eventLink(event.target, scope);
      if (anchor) enterLink(anchor, "pointer");
    };
    const onPointerOut = (event: PointerEvent) => {
      const anchor = eventLink(event.target, scope);
      // Moving between a link's own children is not leaving it.
      if (!anchor || (event.relatedTarget instanceof Node && anchor.contains(event.relatedTarget)))
        return;
      leaveLink(anchor, "pointer");
    };
    const onPointerDown = (event: PointerEvent) => {
      modalityRef.current = "pointer";
      const anchor = eventLink(event.target, scope);
      if (anchor) dismiss();
    };
    const onKeyDown = () => {
      modalityRef.current = "keyboard";
    };
    const onFocusIn = (event: FocusEvent) => {
      const anchor = eventLink(event.target, scope);
      if (anchor) enterLink(anchor, "focus");
    };
    const onFocusOut = (event: FocusEvent) => {
      const anchor = eventLink(event.target, scope);
      if (anchor) leaveLink(anchor, "focus");
    };
    // Activating a link, by press or by Enter, closes its card; the click itself goes on.
    const onClick = (event: MouseEvent) => {
      if (eventLink(event.target, scope)) dismiss();
    };

    document.addEventListener("pointerover", onPointerOver);
    document.addEventListener("pointerout", onPointerOut);
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("pointerover", onPointerOver);
      document.removeEventListener("pointerout", onPointerOut);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      document.removeEventListener("click", onClick, true);
    };
  }, [enterLink, leaveLink, dismiss, scope]);

  // Pending timers die with the provider.
  useEffect(
    () => () => {
      clearOpen();
      clearClose();
    },
    [clearOpen, clearClose],
  );

  // Close when the link leaves the page: a route change or a re-rendered answer.
  useEffect(() => {
    const anchor = card?.anchor;
    if (!anchor) return;
    const observer = new MutationObserver(() => {
      if (anchor.isConnected) return;
      if (focusedRef.current === anchor) focusedRef.current = null;
      if (hoveredRef.current === anchor) hoveredRef.current = null;
      dismiss();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [card, dismiss]);

  // Describe the link by its card while the card is open.
  useEffect(() => {
    const anchor = card?.anchor;
    if (!anchor) return;
    const previous = anchor.getAttribute("aria-describedby");
    anchor.setAttribute("aria-describedby", previous ? `${previous} ${cardId}` : cardId);
    return () => {
      if (previous === null) anchor.removeAttribute("aria-describedby");
      else anchor.setAttribute("aria-describedby", previous);
    };
  }, [card, cardId]);

  const anchorRef = useMemo(() => ({ current: card?.anchor ?? null }), [card]);

  return (
    <Popover open={card !== null} onOpenChange={(open) => !open && dismiss()}>
      <PopoverAnchor virtualRef={anchorRef} />
      {card && (
        <PopoverContent
          id={cardId}
          role="tooltip"
          side="top"
          align="start"
          hideWhenDetached
          data-testid="link-hover-card"
          data-link-preview="off"
          className="z-[1350] w-[min(20rem,calc(100vw-1.5rem))] p-3"
          // The card is supplementary: focus stays on the link, and leaving the link by
          // keyboard is handled by the link's blur.
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onFocusOutside={(event) => event.preventDefault()}
          // The card is not part of an open dialog or menu: keep a press inside it from
          // reaching their outside-press dismissal.
          onPointerDown={(event) => event.stopPropagation()}
          onPointerEnter={() => {
            insideCardRef.current = true;
            clearClose();
          }}
          onPointerLeave={() => {
            insideCardRef.current = false;
            leaveLink(card.anchor);
          }}
        >
          <LinkPreviewCard link={card.link} />
        </PopoverContent>
      )}
    </Popover>
  );
}
