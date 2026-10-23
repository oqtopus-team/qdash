"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Bot } from "lucide-react";
import { useChatDock } from "@/contexts/ChatDockContext";
import { DockedChatPanel } from "@/components/features/chat/DockedChatPanel";
import {
  clampSidebarWidth,
  clearStoredSidebarWidth,
  DEFAULT_SIDEBAR_WIDTH,
  getStoredSidebarWidth,
  setStoredSidebarWidth,
} from "@/lib/chatSidebarWidth";

/** The sidebar's width on large screens: remembered, dragged by its left edge, reset by a double click. */
function useSidebarWidth() {
  const [width, setWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(width);
  widthRef.current = width;

  useEffect(() => {
    const stored = getStoredSidebarWidth();
    if (stored !== null) setWidth(clampSidebarWidth(stored, window.innerWidth));
  }, []);

  const startDrag = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = widthRef.current;
    setDragging(true);
    const move = (e: PointerEvent) => {
      // The handle is on the left edge: moving left makes the sidebar wider.
      setWidth(clampSidebarWidth(startWidth + (startX - e.clientX), window.innerWidth));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      setDragging(false);
      setStoredSidebarWidth(widthRef.current);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  }, []);

  const reset = useCallback(() => {
    setWidth(DEFAULT_SIDEBAR_WIDTH);
    clearStoredSidebarWidth();
  }, []);

  return { width, dragging, startDrag, reset };
}

export function ChatSidebar() {
  const { isOpen, openGeneralChat, closeSidebar } = useChatDock();
  const pathname = usePathname();
  const { width, dragging, startDrag, reset } = useSidebarWidth();

  // The /chat page is the same chat at full size; a second copy beside it is noise.
  if (pathname === "/chat") return null;

  return (
    <>
      {/* Right-edge floating tab — always visible when sidebar is closed */}
      {!isOpen && (
        <button
          onClick={openGeneralChat}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-50 flex flex-col items-center gap-1.5 bg-primary text-primary-content px-1.5 py-3 rounded-l-xl shadow-lg hover:px-2 transition-all duration-200"
          title="Ask AI"
        >
          <Bot className="w-5 h-5" />
          <span
            className="text-[10px] font-semibold select-none"
            style={{ writingMode: "vertical-rl" }}
          >
            Ask AI
          </span>
        </button>
      )}

      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={closeSidebar}
          aria-hidden="true"
        />
      )}

      {/* Full-screen overlay below lg; inline flex panel of adjustable width at lg+ */}
      <div
        className={`relative bg-base-100 overflow-hidden max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-50 lg:h-screen lg:flex-shrink-0 lg:border-l lg:border-base-300 ${
          dragging ? "" : "transition-[width] duration-300 ease-in-out"
        } ${isOpen ? "max-lg:w-full lg:w-[var(--chat-sidebar-width)]" : "w-0"}`}
        style={{ ["--chat-sidebar-width" as string]: `${isOpen ? width : 0}px` }}
        data-testid="chat-sidebar"
      >
        {isOpen && (
          <>
            {/* Drag handle on the left edge (large screens); double-click restores the default width. */}
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize chat sidebar"
              title="Drag to resize · double-click to reset"
              onPointerDown={startDrag}
              onDoubleClick={reset}
              className={`absolute inset-y-0 left-0 z-10 hidden w-1.5 cursor-col-resize lg:block transition-colors hover:bg-primary/40 ${
                dragging ? "bg-primary/60" : "bg-transparent"
              }`}
            />
            <div className="h-full w-screen max-w-full lg:w-[var(--chat-sidebar-width)]">
              <DockedChatPanel onClose={closeSidebar} />
            </div>
          </>
        )}
      </div>
    </>
  );
}
