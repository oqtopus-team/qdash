/**
 * Which chat to carry into the floating window when the user leaves /chat.
 *
 * Leaving the chat page while an answer streams would otherwise hide the
 * answer until the user reopens a chat surface. The active session wins when
 * it is streaming; otherwise any streaming session is followed.
 */
export const CHAT_PAGE_PATH = "/chat";

export function sessionToFollow(
  previousPath: string | null,
  nextPath: string,
  activeSessionId: string | null,
  runningSessionIds: readonly string[],
): string | null {
  if (previousPath !== CHAT_PAGE_PATH || nextPath === CHAT_PAGE_PATH) return null;
  if (activeSessionId && runningSessionIds.includes(activeSessionId)) return activeSessionId;
  return runningSessionIds[0] ?? null;
}
