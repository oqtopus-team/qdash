import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetTaskResultComments,
  getGetTaskResultCommentsQueryKey,
  useCreateTaskResultComment,
  useDeleteTaskResultComment,
} from "@/client/task-result/task-result";
import type { CommentResponse } from "@/schemas";

export type { CommentResponse as TaskResultComment };

export function useTaskResultComments(taskId: string | undefined) {
  const queryClient = useQueryClient();
  const effectiveId = taskId ?? "";
  const { data, isLoading } = useGetTaskResultComments(effectiveId, {
    query: { enabled: !!taskId },
  });

  const comments = data?.data ?? [];

  const createMutation = useCreateTaskResultComment();
  const deleteMutation = useDeleteTaskResultComment();

  const invalidate = useCallback(() => {
    if (!taskId) return;
    queryClient.invalidateQueries({
      queryKey: getGetTaskResultCommentsQueryKey(taskId),
    });
  }, [queryClient, taskId]);

  const addComment = useCallback(
    async (content: string) => {
      if (!taskId) return;
      await createMutation.mutateAsync({
        taskId,
        data: { content, parent_id: null },
      });
      invalidate();
    },
    [taskId, createMutation, invalidate],
  );

  const deleteComment = useCallback(
    async (commentId: string) => {
      if (!taskId) return;
      await deleteMutation.mutateAsync({ taskId, commentId });
      invalidate();
    },
    [taskId, deleteMutation, invalidate],
  );

  return {
    comments,
    isLoading,
    isSubmitting: createMutation.isPending,
    addComment,
    deleteComment,
  };
}
