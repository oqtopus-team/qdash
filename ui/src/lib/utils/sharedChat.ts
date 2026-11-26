/**
 * Links to a chat snapshot shared with a project.
 *
 * A share is readable only in its own project, so its link always names that project:
 * a recipient whose active project is another one still opens the share where it lives.
 */

/** The page a project member opens to read a shared snapshot, in the project it belongs to. */
export function sharedChatPath(shareId: string, projectId: string): string {
  return `/chat/shared/${encodeURIComponent(shareId)}?project=${encodeURIComponent(projectId)}`;
}

/** The absolute link to copy for a shared snapshot; the path alone outside a browser. */
export function sharedChatUrl(shareId: string, projectId: string): string {
  const path = sharedChatPath(shareId, projectId);
  return typeof window === "undefined" ? path : `${window.location.origin}${path}`;
}
