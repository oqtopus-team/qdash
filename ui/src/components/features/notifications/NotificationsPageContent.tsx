"use client";

import Link from "next/link";
import { AtSign, CheckCheck, Inbox, MessageSquare, RefreshCw, StickyNote } from "lucide-react";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { RefreshErrorAlert } from "@/components/ui/RefreshErrorAlert";
import { useNotificationActions, useNotifications } from "@/hooks/useNotifications";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { NotificationResponse } from "@/schemas";

const INBOX_FILTERS = ["all", "unread"] as const;
type InboxFilter = (typeof INBOX_FILTERS)[number];
const INBOX_FILTER_LABELS: Record<InboxFilter, string> = { all: "All", unread: "Unread only" };
/** `?filter=unread` shows unread items; a missing or unknown value shows everything. */
const inboxFilterParser = parseAsStringLiteral(INBOX_FILTERS).withDefault("all");

function kindIcon(kind: string) {
  if (kind === "forum_reply" || kind === "forum_mention") {
    return <MessageSquare className="h-4 w-4" />;
  }
  if (kind === "issue_reply") return <MessageSquare className="h-4 w-4" />;
  if (kind === "note_mention") return <StickyNote className="h-4 w-4" />;
  return <AtSign className="h-4 w-4" />;
}

function kindLabel(kind: string) {
  if (kind === "forum_reply") return "Forum reply";
  if (kind === "forum_mention") return "Forum mention";
  if (kind === "issue_reply") return "Reply";
  if (kind === "note_mention") return "Note mention";
  if (kind === "mention") return "Mention";
  return kind;
}

function NotificationRow({
  notification,
  onOpen,
}: {
  notification: NotificationResponse;
  onOpen: (notification: NotificationResponse) => void;
}) {
  const unread = notification.read_at == null;

  return (
    <Link
      href={notification.target_url}
      onClick={() => onOpen(notification)}
      className={`block border-b border-base-300 px-4 py-3 transition-colors hover:bg-base-200/70 ${
        unread ? "bg-primary/5" : "bg-base-100"
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
            unread ? "bg-primary text-primary-content" : "bg-base-200 text-base-content/60"
          }`}
        >
          {kindIcon(notification.kind)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-sm">{notification.title}</span>
            <span className="badge badge-xs badge-ghost">{kindLabel(notification.kind)}</span>
            {unread && <span className="badge badge-xs badge-primary">Unread</span>}
          </div>
          {notification.excerpt && (
            <p className="mt-1 line-clamp-2 text-sm text-base-content/65">{notification.excerpt}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-base-content/45">
            <span className="font-mono">{notification.actor_username}</span>
            <span>{formatRelativeTime(notification.created_at)}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

export function NotificationsPageContent() {
  const [filter, setFilter] = useQueryState("filter", inboxFilterParser);
  const unreadOnly = filter === "unread";
  const { data, isLoading, isError, isFetching, errorUpdateCount, refetch } =
    useNotifications(unreadOnly);
  const { markRead, markAllRead } = useNotificationActions();
  const notifications = data?.data.notifications ?? [];
  const unreadCount = data?.data.unread_count ?? 0;
  const retry = () => void refetch();
  // Retrying a failed first load puts the query back to pending; keep the error in place.
  const retryingFirstLoad = isLoading && errorUpdateCount > 0;

  const handleOpen = (notification: NotificationResponse) => {
    if (notification.read_at == null) {
      markRead.mutate({ notificationId: notification.id });
    }
  };

  return (
    <PageContainer>
      <PageHeader title="Inbox" description="Mentions, replies and system messages" />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="join" role="group" aria-label="Show notifications">
            {INBOX_FILTERS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={filter === value}
                className={`join-item btn btn-sm ${filter === value ? "btn-primary" : ""}`}
                onClick={() => void setFilter(value === "all" ? null : value)}
              >
                {INBOX_FILTER_LABELS[value]}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-sm text-base-content/60" aria-live="polite">
            <Inbox className="h-4 w-4" aria-hidden="true" />
            <span>
              {!data
                ? "Unread count unavailable"
                : unreadCount > 0
                  ? `${unreadCount} unread item${unreadCount === 1 ? "" : "s"}`
                  : "No unread items"}
            </span>
            {isFetching && !isLoading && (
              <span className="inline-flex items-center gap-1 text-xs">
                <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Refreshing
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-sm btn-ghost self-start sm:self-auto"
          onClick={() => markAllRead.mutate()}
          disabled={unreadCount === 0 || markAllRead.isPending}
        >
          <CheckCheck data-icon="inline-start" />
          Mark all read
        </button>
      </div>

      {isError && data && (
        <RefreshErrorAlert
          className="mb-3"
          message="Could not refresh the inbox. These items may be out of date."
          onRetry={retry}
          retrying={isFetching}
        />
      )}

      {isLoading && !retryingFirstLoad ? (
        <div className="card bg-base-200 shadow-sm">
          <div className="flex justify-center py-16">
            <span className="loading loading-spinner loading-lg" />
          </div>
        </div>
      ) : !data ? (
        isError || retryingFirstLoad ? (
          <ErrorCard
            title="Could not load the inbox"
            message="The request failed. Check the connection and try again."
            onRetry={retry}
            retrying={isFetching}
          />
        ) : null
      ) : (
        <div className="card bg-base-200 shadow-sm overflow-hidden">
          {notifications.length === 0 ? (
            unreadOnly ? (
              <EmptyState
                title="No unread items"
                description="You have read everything in your inbox."
                emoji="empty"
                size="md"
                action={
                  <button type="button" className="btn btn-sm" onClick={() => void setFilter(null)}>
                    Show all items
                  </button>
                }
              />
            ) : (
              <EmptyState
                title="Inbox is empty"
                description="Mentions in forum threads and notes, replies, and system messages will appear here."
                emoji="empty"
                size="md"
              />
            )
          ) : (
            notifications.map((notification) => (
              <NotificationRow
                key={notification.id}
                notification={notification}
                onOpen={handleOpen}
              />
            ))
          )}
        </div>
      )}
    </PageContainer>
  );
}
