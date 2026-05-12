import { useQueryClient } from "@tanstack/react-query";

import {
  getGetUnreadNotificationCountQueryKey,
  getListNotificationsQueryKey,
  useGetUnreadNotificationCount,
  useListNotifications,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
} from "@/client/notification/notification";

export function useNotifications(unreadOnly = false) {
  return useListNotifications(
    { unread_only: unreadOnly, limit: 100 },
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

export function useNotificationActions() {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getListNotificationsQueryKey() });
    queryClient.invalidateQueries({
      queryKey: getGetUnreadNotificationCountQueryKey(),
    });
  };

  const markRead = useMarkNotificationRead({
    mutation: { onSuccess: invalidate },
  });
  const markAllRead = useMarkAllNotificationsRead({
    mutation: { onSuccess: invalidate },
  });

  return { markRead, markAllRead };
}
