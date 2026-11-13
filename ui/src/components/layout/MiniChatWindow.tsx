"use client";

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { GripHorizontal, Minus, PanelRight, SquarePen, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useChatDock } from "@/contexts/ChatDockContext";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import { CHAT_PAGE_PATH, sessionToFollow } from "@/lib/followStreamingChat";
import { ChatThread } from "@/components/features/chat/ChatThread";
import {
  RecentChatsMenu,
  SurfaceButton,
  SurfaceTitle,
} from "@/components/features/chat/ChatSurfaceControls";

// ---------------------------------------------------------------------------
// Drag hook
// ---------------------------------------------------------------------------

function useDrag(initialPosition: { x: number; y: number }) {
  const [position, setPosition] = useState(initialPosition);
  const dragState = useRef<{
    isDragging: boolean;
    startX: number;
    startY: number;
    startPosX: number;
    startPosY: number;
  } | null>(null);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      // Only drag on primary button
      if (e.button !== 0) return;
      // Don't start drag when clicking interactive elements (buttons, etc.)
      const target = e.target as HTMLElement;
      if (target.closest("button")) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      dragState.current = {
        isDragging: true,
        startX: e.clientX,
        startY: e.clientY,
        startPosX: position.x,
        startPosY: position.y,
      };
    },
    [position],
  );

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const state = dragState.current;
    if (!state?.isDragging) return;

    const dx = e.clientX - state.startX;
    const dy = e.clientY - state.startY;

    const newX = state.startPosX + dx;
    const newY = state.startPosY + dy;

    // Clamp to viewport
    const maxX = window.innerWidth - 100;
    const maxY = window.innerHeight - 40;
    setPosition({
      x: Math.max(0, Math.min(newX, maxX)),
      y: Math.max(0, Math.min(newY, maxY)),
    });
  }, []);

  const handlePointerUp = useCallback(() => {
    dragState.current = null;
  }, []);

  const resetPosition = useCallback(() => {
    setPosition(initialPosition);
  }, [initialPosition]);

  return {
    position,
    resetPosition,
    dragHandlers: {
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
    },
  };
}

// ---------------------------------------------------------------------------
// Size constants
// ---------------------------------------------------------------------------

const WINDOW_WIDTH = 400;
const WINDOW_HEIGHT = 560;
const MARGIN = 16;
// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Floating chat above modals, opened by "Ask AI" in result modals where the
 * docked sidebar would sit behind the overlay. Shows the same active chat as
 * the sidebar, so expanding it keeps a streaming answer going.
 */
export function MiniChatWindow() {
  const { miniChat, closeMiniChat, openSidebar, openMiniChatForSession, endInvestigation } =
    useChatDock();
  const { createNewSession, activeSession, activeSessionId, runs } = useCopilotChatSessionContext();
  const router = useRouter();
  const pathname = usePathname();
  const [minimized, setMinimized] = useState(false);

  // Leaving /chat mid-answer: follow the streaming chat in this window.
  // Arriving on /chat: the page shows it, so the window gets out of the way.
  const previousPath = useRef<string | null>(null);
  useEffect(() => {
    const from = previousPath.current;
    previousPath.current = pathname;
    if (from === pathname) return;
    if (pathname === CHAT_PAGE_PATH) {
      if (miniChat.isOpen) closeMiniChat();
      return;
    }
    const follow = sessionToFollow(from, pathname, activeSessionId, Object.keys(runs));
    if (follow) openMiniChatForSession(follow);
    // Only path changes should trigger this; the other values are read as they are then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const [viewport, setViewport] = useState({
    width: WINDOW_WIDTH + 2 * MARGIN,
    top: 0,
    left: 0,
    bottom: WINDOW_HEIGHT + 2 * MARGIN,
  });
  useEffect(() => {
    const dock = document.getElementById("mobile-tab-bar");
    const updateViewport = () => {
      const dockRect = dock?.getBoundingClientRect();
      const visibleBottom = window.visualViewport
        ? window.visualViewport.offsetTop + window.visualViewport.height
        : window.innerHeight;
      setViewport({
        width: window.visualViewport?.width ?? window.innerWidth,
        top: window.visualViewport?.offsetTop ?? 0,
        left: window.visualViewport?.offsetLeft ?? 0,
        bottom:
          dockRect && dockRect.height > 0 ? Math.min(dockRect.top, visibleBottom) : visibleBottom,
      });
    };
    updateViewport();
    const observer = new ResizeObserver(updateViewport);
    if (dock) observer.observe(dock);
    window.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("scroll", updateViewport);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("scroll", updateViewport);
    };
  }, []);

  // Measure the tab bar's outer top edge so its inset gap and safe-area padding count.
  const size = useMemo(
    () => ({
      width: Math.max(1, Math.min(WINDOW_WIDTH, viewport.width - 2 * MARGIN)),
      height: Math.max(1, Math.min(WINDOW_HEIGHT, viewport.bottom - viewport.top - 2 * MARGIN)),
    }),
    [viewport],
  );
  const defaultPos = useMemo(
    () => ({
      x: viewport.left + Math.max(0, viewport.width - size.width - MARGIN),
      y: Math.max(viewport.top, viewport.bottom - size.height - MARGIN),
    }),
    [viewport, size],
  );

  const { position, resetPosition, dragHandlers } = useDrag(defaultPos);

  // Reset position when window opens
  useEffect(() => {
    if (miniChat.isOpen) {
      resetPosition();
    }
  }, [miniChat.isOpen, resetPosition]);

  // Only opening the window resets the user's minimized choice.
  useEffect(() => {
    if (miniChat.isOpen) setMinimized(false);
  }, [miniChat.isOpen]);

  if (!miniChat.isOpen) return null;

  const handleExpand = () => {
    closeMiniChat();
    if (pathname === "/chat") return;
    openSidebar();
  };

  const openFullPage = () => {
    closeMiniChat();
    router.push("/chat");
  };

  return (
    <div
      className="fixed z-[1100] flex flex-col bg-base-100 border border-base-300 rounded-2xl shadow-2xl overflow-hidden"
      style={{
        left: position.x,
        top: position.y,
        width: minimized ? Math.min(260, size.width) : size.width,
        height: minimized ? "auto" : size.height,
      }}
      role="dialog"
      aria-label="AI chat"
    >
      {/* Draggable header */}
      <div
        {...dragHandlers}
        className="flex items-start gap-1.5 px-2.5 py-2 border-b border-base-300/70 bg-base-200/40 select-none touch-none"
        style={{ cursor: "grab" }}
      >
        <GripHorizontal className="w-3.5 h-3.5 mt-1 text-base-content/30 flex-shrink-0" />
        {minimized ? (
          <span className="flex-1 min-w-0 truncate text-sm font-medium">
            {activeSession?.title ?? "Ask AI"}
          </span>
        ) : (
          <SurfaceTitle />
        )}
        <div className="flex items-center gap-0.5 shrink-0">
          {!minimized && (
            <>
              <SurfaceButton
                label="New chat"
                onClick={() => {
                  endInvestigation(activeSession?.id);
                  createNewSession(activeSession?.context ?? null);
                }}
              >
                <SquarePen className="w-3.5 h-3.5" />
              </SurfaceButton>
              <RecentChatsMenu onOpenAll={openFullPage} />
            </>
          )}
          <SurfaceButton
            label={minimized ? "Expand chat" : "Minimize chat"}
            onClick={() => setMinimized((prev) => !prev)}
          >
            <Minus className="w-3.5 h-3.5" />
          </SurfaceButton>
          <SurfaceButton label="Open in sidebar" onClick={handleExpand}>
            <PanelRight className="w-3.5 h-3.5" />
          </SurfaceButton>
          <SurfaceButton label="Close chat" onClick={closeMiniChat}>
            <X className="w-3.5 h-3.5" />
          </SurfaceButton>
        </div>
      </div>

      {!minimized && <ChatThread variant="compact" />}
    </div>
  );
}
