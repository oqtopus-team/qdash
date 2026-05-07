"use client";

import Link from "next/link";
import {
  AtSign,
  Bell,
  CheckCheck,
  MessageSquare,
  StickyNote,
} from "lucide-react";

import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  useNotificationActions,
  useNotifications,
} from "@/hooks/useNotifications";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { NotificationResponse } from "@/schemas";

function kindIcon(kind: string) {
  if (kind === "issue_reply") return <MessageSquare className="h-4 w-4" />;
  if (kind === "note_mention") return <StickyNote className="h-4 w-4" />;
  return <AtSign className="h-4 w-4" />;
}

function kindLabel(kind: string) {
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
            unread
              ? "bg-primary text-primary-content"
              : "bg-base-200 text-base-content/60"
          }`}
        >
          {kindIcon(notification.kind)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-sm">{notification.title}</span>
            <span className="badge badge-xs badge-ghost">
              {kindLabel(notification.kind)}
            </span>
            {unread && (
              <span className="badge badge-xs badge-primary">Unread</span>
            )}
          </div>
          {notification.excerpt && (
            <p className="mt-1 line-clamp-2 text-sm text-base-content/65">
              {notification.excerpt}
            </p>
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

export function NotificationsInboxPageContent() {
  const { data, isLoading, error } = useNotifications(false);
  const { markRead, markAllRead } = useNotificationActions();
  const notifications = data?.data.notifications ?? [];
  const unreadCount = data?.data.unread_count ?? 0;

  const handleOpen = (notification: NotificationResponse) => {
    if (notification.read_at == null) {
      markRead.mutate({ notificationId: notification.id });
    }
  };

  return (
    <PageContainer>
      <PageHeader
        title="Inbox"
        description="Mentions, replies, and notifications that need your attention"
      />

      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-base-content/60">
          <Bell className="h-4 w-4" />
          <span>
            {unreadCount > 0
              ? `${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}`
              : "No unread notifications"}
          </span>
        </div>
        <button
          className="btn btn-sm btn-ghost gap-2"
          onClick={() => markAllRead.mutate()}
          disabled={unreadCount === 0 || markAllRead.isPending}
        >
          <CheckCheck className="h-4 w-4" />
          Mark all read
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-base-300 bg-base-100">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <span className="loading loading-spinner loading-lg" />
          </div>
        ) : error ? (
          <div className="p-6 text-sm text-error">
            Failed to load notifications.
          </div>
        ) : notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
            <Bell className="h-8 w-8 text-base-content/30" />
            <p className="font-medium">Inbox is empty</p>
            <p className="max-w-md text-sm text-base-content/55">
              Mentions in issues and notes, issue replies, and future app
              notifications will appear here.
            </p>
          </div>
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
    </PageContainer>
  );
}
