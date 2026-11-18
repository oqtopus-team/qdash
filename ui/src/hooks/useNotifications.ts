import { useQueryClient } from "@tanstack/react-query";

import {
  getGetUnreadNotificationCountQueryKey,
  getListNotificationsQueryKey,
  useGetUnreadNotificationCount,
  useListNotifications,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
} from "@/client/notification/notification";
import { useToast } from "@/components/ui/Toast";
import { getApiErrorMessage } from "@/lib/utils/apiError";

interface UseNotificationsOptions {
  /** Set to false to skip fetching until the list is actually shown. */
  enabled?: boolean;
}

export function useNotifications(
  unreadOnly = false,
  { enabled = true }: UseNotificationsOptions = {},
) {
  return useListNotifications(
    { unread_only: unreadOnly, limit: 100 },
    {
      query: {
        enabled,
        staleTime: 15_000,
        refetchInterval: 60_000,
      },
    },
  );
}

/** Notifications shown on one page of the Inbox. */
export const INBOX_PAGE_SIZE = 50;

/**
 * One page of the Inbox list. Each filter and page is its own query, so a page never shows
 * items from another filter or page while it loads.
 */
export function useNotificationsPage(unreadOnly: boolean, page: number) {
  return useListNotifications(
    {
      unread_only: unreadOnly,
      skip: (page - 1) * INBOX_PAGE_SIZE,
      limit: INBOX_PAGE_SIZE,
    },
    {
      query: {
        staleTime: 15_000,
        refetchInterval: 60_000,
      },
    },
  );
}

export function useUnreadNotificationCount() {
  return useGetUnreadNotificationCount({
    query: {
      staleTime: 15_000,
      refetchInterval: 60_000,
    },
  });
}

interface UseNotificationActionsOptions {
  /**
   * Show an error toast when marking read fails. The toast is raised from the mutation itself,
   * so it still appears after opening a notification navigates away from the list.
   */
  reportErrors?: boolean;
}

export function useNotificationActions({
  reportErrors = false,
}: UseNotificationActionsOptions = {}) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getListNotificationsQueryKey() });
    queryClient.invalidateQueries({
      queryKey: getGetUnreadNotificationCountQueryKey(),
    });
  };

  // Read state changes only after the server confirms it; a failure leaves the list as it was.
  const markRead = useMarkNotificationRead({
    mutation: {
      onSuccess: invalidate,
      onError: reportErrors
        ? (error) =>
            toast.error(getApiErrorMessage(error, "Could not mark the notification as read"))
        : undefined,
    },
  });
  const markAllRead = useMarkAllNotificationsRead({
    mutation: {
      onSuccess: invalidate,
      onError: reportErrors
        ? (error) =>
            toast.error(getApiErrorMessage(error, "Could not mark all notifications as read"))
        : undefined,
    },
  });

  return { markRead, markAllRead };
}
