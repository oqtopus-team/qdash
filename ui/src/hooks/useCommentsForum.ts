import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useListAllComments,
  getListAllCommentsQueryKey,
  useGetCommentReplies,
  getGetCommentRepliesQueryKey,
  useCreateTaskResultComment,
  useDeleteTaskResultComment,
  useCloseCommentThread,
  useReopenCommentThread,
} from "@/client/task-result/task-result";
import type { CommentResponse } from "@/schemas";

export type { CommentResponse as ForumComment };

export type StatusFilter = "open" | "closed" | "all";

const PAGE_SIZE = 50;

function buildIsClosedParam(status: StatusFilter): boolean | null | undefined {
  if (status === "open") return false;
  if (status === "closed") return true;
  return null; // "all"
}

export function useCommentsForum() {
  const queryClient = useQueryClient();
  const [skip, setSkip] = useState(0);
  const [taskIdFilter, setTaskIdFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("open");

  const params = {
    skip,
    limit: PAGE_SIZE,
    task_id: taskIdFilter || undefined,
    is_closed: buildIsClosedParam(statusFilter),
  };

  const { data, isLoading } = useListAllComments(params);

  const comments = data?.data?.comments ?? [];
  const total = data?.data?.total ?? 0;

  const goToPage = useCallback((page: number) => {
    setSkip(page * PAGE_SIZE);
  }, []);

  const filterByTaskId = useCallback((taskId: string) => {
    setTaskIdFilter(taskId);
    setSkip(0);
  }, []);

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

  const closeComment = useCallback(
    (commentId: string) => {
      closeMutation.mutate({ commentId });
    },
    [closeMutation],
  );

  const reopenComment = useCallback(
    (commentId: string) => {
      reopenMutation.mutate({ commentId });
    },
    [reopenMutation],
  );

  const refresh = useCallback(() => {
    invalidateList();
  }, [invalidateList]);

  return {
    comments,
    total,
    skip,
    pageSize: PAGE_SIZE,
    isLoading,
    taskIdFilter,
    filterByTaskId,
    statusFilter,
    setStatusFilter,
    closeComment,
    reopenComment,
    goToPage,
    refresh,
  };
}

export function useCommentReplies(commentId: string | null) {
  const queryClient = useQueryClient();
  const effectiveId = commentId ?? "";
  const { data, isLoading } = useGetCommentReplies(effectiveId, {
    query: { enabled: !!commentId },
  });

  const replies = data?.data ?? [];

  const createMutation = useCreateTaskResultComment();
  const deleteMutation = useDeleteTaskResultComment();

  const invalidateReplies = useCallback(() => {
    if (!commentId) return;
    queryClient.invalidateQueries({
      queryKey: getGetCommentRepliesQueryKey(commentId),
    });
    // Also invalidate the list to update reply_count
    queryClient.invalidateQueries({
      queryKey: getListAllCommentsQueryKey(),
    });
  }, [queryClient, commentId]);

  const addReply = useCallback(
    async (taskId: string, content: string) => {
      if (!commentId) return;
      const result = await createMutation.mutateAsync({
        taskId,
        data: { content, parent_id: commentId },
      });
      invalidateReplies();
      return result;
    },
    [commentId, createMutation, invalidateReplies],
  );

  const deleteReply = useCallback(
    async (taskId: string, replyId: string) => {
      await deleteMutation.mutateAsync({ taskId, commentId: replyId });
      invalidateReplies();
    },
    [deleteMutation, invalidateReplies],
  );

  return {
    replies,
    isLoading,
    isSubmitting: createMutation.isPending,
    addReply,
    deleteReply,
    fetchReplies: invalidateReplies,
  };
}
