"use client";

/**
 * Collapsible "reasoning" block: a trigger row and content that animates its
 * height open and closed, and that opens by itself while something streams
 * into it and closes again when the stream ends.
 *
 * Adapted from prompt-kit's Reasoning (https://www.prompt-kit.com, MIT). The
 * markdown option was dropped; callers render their own content.
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { ChevronRight } from "lucide-react";
import { twMerge } from "tailwind-merge";

type ReasoningContextValue = { isOpen: boolean; setOpen: (open: boolean) => void };

const ReasoningContext = createContext<ReasoningContextValue | null>(null);

function useReasoning(): ReasoningContextValue {
  const ctx = useContext(ReasoningContext);
  if (!ctx) throw new Error("ReasoningTrigger and ReasoningContent must be inside Reasoning");
  return ctx;
}

export interface ReasoningProps {
  children: ReactNode;
  className?: string;
  /** Controlled open state; omit to let the block manage itself. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** While true the block is held open; when it turns false the block closes. */
  isStreaming?: boolean;
  /** Initial state when uncontrolled and not streaming. */
  defaultOpen?: boolean;
}

export function Reasoning({
  children,
  className,
  open,
  onOpenChange,
  isStreaming = false,
  defaultOpen = false,
}: ReasoningProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const [autoOpened, setAutoOpened] = useState(false);
  const controlled = open !== undefined;
  const isOpen = controlled ? open : internalOpen;

  const setOpen = (next: boolean) => {
    if (!controlled) setInternalOpen(next);
    onOpenChange?.(next);
  };

  useEffect(() => {
    if (isStreaming && !autoOpened) {
      if (!controlled) setInternalOpen(true);
      setAutoOpened(true);
    }
    if (!isStreaming && autoOpened) {
      if (!controlled) setInternalOpen(false);
      setAutoOpened(false);
    }
  }, [isStreaming, autoOpened, controlled]);

  return (
    <ReasoningContext.Provider value={{ isOpen, setOpen }}>
      <div className={className}>{children}</div>
    </ReasoningContext.Provider>
  );
}

export type ReasoningTriggerProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> & {
  children: ReactNode;
  className?: string;
  /** Hide the chevron, e.g. while the block is held open by streaming. */
  hideChevron?: boolean;
};

export function ReasoningTrigger({
  children,
  className,
  hideChevron = false,
  ...props
}: ReasoningTriggerProps) {
  const { isOpen, setOpen } = useReasoning();
  return (
    <button
      type="button"
      className={twMerge("flex cursor-pointer items-center gap-2 text-left", className)}
      onClick={() => setOpen(!isOpen)}
      aria-expanded={isOpen}
      {...props}
    >
      {children}
      {!hideChevron && (
        <ChevronRight
          className={twMerge(
            "w-3 h-3 shrink-0 text-base-content/30 transition-transform",
            isOpen ? "rotate-90" : "",
          )}
        />
      )}
    </button>
  );
}

export type ReasoningContentProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
};

export function ReasoningContent({
  children,
  className,
  contentClassName,
  ...props
}: ReasoningContentProps) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const { isOpen } = useReasoning();

  // Animate max-height to the content's real height, and follow it as the
  // content grows while streaming.
  useEffect(() => {
    const outer = outerRef.current;
    const inner = innerRef.current;
    if (!outer || !inner) return;
    const apply = () => {
      if (!isOpen) {
        outer.style.maxHeight = "0px";
        return;
      }
      // A content height of 0 means it could not be measured (hidden ancestor,
      // test DOM); never clamp open content to nothing.
      const height = inner.scrollHeight;
      outer.style.maxHeight = height > 0 ? `${height}px` : "none";
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(inner);
    return () => observer.disconnect();
  }, [isOpen]);

  return (
    <div
      ref={outerRef}
      className={twMerge(
        "overflow-hidden transition-[max-height] duration-200 ease-out",
        className,
      )}
      style={{ maxHeight: isOpen ? undefined : "0px" }}
      aria-hidden={!isOpen}
      {...props}
    >
      <div ref={innerRef} className={contentClassName}>
        {children}
      </div>
    </div>
  );
}
