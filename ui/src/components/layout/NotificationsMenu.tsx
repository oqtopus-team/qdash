"use client";

import Link from "next/link";
import { useState } from "react";

import { Bell, CheckCheck } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import {
  useNotificationActions,
  useNotifications,
  useUnreadNotificationCount,
} from "@/hooks/useNotifications";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { NotificationResponse } from "@/schemas";

const PREVIEW_LIMIT = 5;

function formatUnreadCount(count: number) {
  return count > 99 ? "99+" : String(count);
}

/**
 * Top-bar bell with the unread count and a preview of the newest notifications.
 * The unread count polls continuously; the list itself is fetched only while the
 * menu is open. "View all" opens the full Inbox page.
 */
export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const { data: unreadResponse } = useUnreadNotificationCount();
  const { data, isLoading, error } = useNotifications(false, { enabled: open });
  const { markRead, markAllRead } = useNotificationActions();

  const unreadCount = unreadResponse?.data.unread_count ?? 0;
  const notifications = (data?.data.notifications ?? []).slice(0, PREVIEW_LIMIT);

  const handleOpen = (notification: NotificationResponse) => {
    if (notification.read_at == null) {
      markRead.mutate({ notificationId: notification.id });
    }
  };

  const label = unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications";

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-square relative"
          aria-label={label}
        >
          <Bell size={16} aria-hidden="true" />
          {unreadCount > 0 && (
            <span
              className="badge badge-primary badge-xs absolute -right-1 -top-1 px-1 font-mono"
              aria-hidden="true"
            >
              {formatUnreadCount(unreadCount)}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <span className="text-sm font-medium">Notifications</span>
          <button
            type="button"
            className="btn btn-ghost btn-xs gap-1 text-base-content/60"
            onClick={() => markAllRead.mutate()}
            disabled={unreadCount === 0 || markAllRead.isPending}
          >
            <CheckCheck size={14} aria-hidden="true" />
            Mark all read
          </button>
        </div>
        <DropdownMenuSeparator className="mx-0 my-0" />
        {isLoading ? (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-sm" />
          </div>
        ) : error ? (
          <p className="px-3 py-6 text-center text-sm text-error">Failed to load notifications.</p>
        ) : notifications.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-base-content/60">
            You are all caught up
          </p>
        ) : (
          <ul className="max-h-96 overflow-y-auto py-1">
            {notifications.map((notification) => {
              const unread = notification.read_at == null;
              return (
                <li key={notification.id}>
                  <DropdownMenuItem asChild className="mx-1 items-start rounded-lg px-2.5 py-2">
                    <Link href={notification.target_url} onClick={() => handleOpen(notification)}>
                      <span
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                          unread ? "bg-primary" : "bg-transparent"
                        }`}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-1 block text-sm font-medium">
                          {notification.title}
                        </span>
                        {notification.excerpt && (
                          <span className="mt-0.5 line-clamp-1 block text-xs text-base-content/60">
                            {notification.excerpt}
                          </span>
                        )}
                        <span className="mt-1 block text-xs text-base-content/60">
                          {notification.actor_username} ·{" "}
                          {formatRelativeTime(notification.created_at)}
                        </span>
                      </span>
                    </Link>
                  </DropdownMenuItem>
                </li>
              );
            })}
          </ul>
        )}
        <DropdownMenuSeparator className="mx-0 my-0" />
        <DropdownMenuItem asChild className="m-1 justify-center text-base-content/60">
          <Link href="/inbox">View all</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
