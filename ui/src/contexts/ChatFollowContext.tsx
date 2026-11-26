"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useStickToBottomContext } from "use-stick-to-bottom";

/**
 * Whether the chat thread follows new content at its bottom. True outside a
 * thread, where no scroll position is kept to protect.
 */
const ChatFollowContext = createContext(true);

/**
 * Shares the thread's follow state with the messages in it, so a change of
 * layout can wait while the user reads older content. Render it inside
 * `<StickToBottom>`.
 */
export function ChatFollowProvider({ children }: { children: ReactNode }) {
  const { isAtBottom } = useStickToBottomContext();
  return <ChatFollowContext.Provider value={isAtBottom}>{children}</ChatFollowContext.Provider>;
}

/** Whether the thread follows new content, rather than the user reading away from the bottom. */
export function useChatFollowing(): boolean {
  return useContext(ChatFollowContext);
}
