import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useListAllComments,
  getListAllCommentsQueryKey,
  useCloseCommentThread,
  useReopenCommentThread,
} from "@/client/task-result/task-result";
import type { CommentResponse } from "@/schemas";

export type { CommentResponse as TaskResultIssue };

export type StatusFilter = "open" | "closed" | "all";

function buildIsClosedParam(status: StatusFilter): boolean | null | undefined {
  if (status === "open") return false;
  if (status === "closed") return true;
  return null; // "all"
}

export function useTaskResultIssues(taskId: string) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("open");

  const params = {
    skip: 0,
    limit: 200,
    task_id: taskId,
    is_closed: buildIsClosedParam(statusFilter),
  };

  const { data, isLoading } = useListAllComments(params);

  const issues = data?.data?.comments ?? [];
  const total = data?.data?.total ?? 0;

  const invalidateList = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: getListAllCommentsQueryKey(),
    });
  }, [queryClient]);

  const closeMutation = useCloseCommentThread({
    mutation: { onSuccess: invalidateList },
  });

  const reopenMutation = useReopenCommentThread({
    mutation: { onSuccess: invalidateList },
  });

  const closeIssue = useCallback(
    (commentId: string) => {
      closeMutation.mutate({ commentId });
    },
    [closeMutation],
  );

  const reopenIssue = useCallback(
    (commentId: string) => {
      reopenMutation.mutate({ commentId });
    },
    [reopenMutation],
  );

  return {
    issues,
    total,
    isLoading,
    statusFilter,
    setStatusFilter,
    closeIssue,
    reopenIssue,
    invalidateList,
  };
}
