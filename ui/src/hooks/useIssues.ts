import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useListIssues,
  getListIssuesQueryKey,
  useGetIssueReplies,
  getGetIssueRepliesQueryKey,
  useCreateIssue,
  useDeleteIssue,
  useUpdateIssue,
  useCloseIssue,
  useReopenIssue,
  getGetIssueQueryKey,
} from "@/client/issue/issue";
type StatusFilter = "open" | "closed" | "all";

const PAGE_SIZE = 50;

function buildIsClosedParam(status: StatusFilter): boolean | null | undefined {
  if (status === "open") return false;
  if (status === "closed") return true;
  return null; // "all"
}

export function useIssues() {
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

  const { data, isLoading } = useListIssues(params);

  const issues = data?.data?.issues ?? [];
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
      queryKey: getListIssuesQueryKey(),
    });
  }, [queryClient]);

  const closeMutation = useCloseIssue({
    mutation: { onSuccess: invalidateList },
  });

  const reopenMutation = useReopenIssue({
    mutation: { onSuccess: invalidateList },
  });

  const closeIssue = useCallback(
    (issueId: string) => {
      closeMutation.mutate({ issueId });
    },
    [closeMutation],
  );

  const reopenIssue = useCallback(
    (issueId: string) => {
      reopenMutation.mutate({ issueId });
    },
    [reopenMutation],
  );

  const refresh = useCallback(() => {
    invalidateList();
  }, [invalidateList]);

  return {
    issues,
    total,
    skip,
    pageSize: PAGE_SIZE,
    isLoading,
    taskIdFilter,
    filterByTaskId,
    statusFilter,
    setStatusFilter,
    closeIssue,
    reopenIssue,
    goToPage,
    refresh,
  };
}

export function useIssueReplies(issueId: string | null) {
  const queryClient = useQueryClient();
  const effectiveId = issueId ?? "";
  const { data, isLoading } = useGetIssueReplies(effectiveId, {
    query: { enabled: !!issueId },
  });

  const replies = data?.data ?? [];

  const createMutation = useCreateIssue();
  const deleteMutation = useDeleteIssue();
  const updateMutation = useUpdateIssue();

  const invalidateReplies = useCallback(() => {
    if (!issueId) return;
    queryClient.invalidateQueries({
      queryKey: getGetIssueRepliesQueryKey(issueId),
    });
    queryClient.invalidateQueries({
      queryKey: getGetIssueQueryKey(issueId),
    });
    // Also invalidate the list to update reply_count
    queryClient.invalidateQueries({
      queryKey: getListIssuesQueryKey(),
    });
  }, [queryClient, issueId]);

  const addReply = useCallback(
    async (taskId: string, content: string) => {
      if (!issueId) return;
      const result = await createMutation.mutateAsync({
        taskId,
        data: { content, parent_id: issueId },
      });
      invalidateReplies();
      return result;
    },
    [issueId, createMutation, invalidateReplies],
  );

  const deleteReply = useCallback(
    async (_taskId: string, replyId: string) => {
      await deleteMutation.mutateAsync({ issueId: replyId });
      invalidateReplies();
    },
    [deleteMutation, invalidateReplies],
  );

  const editReply = useCallback(
    async (replyId: string, content: string, title?: string | null) => {
      await updateMutation.mutateAsync({
        issueId: replyId,
        data: { content, title: title ?? undefined },
      });
      invalidateReplies();
    },
    [updateMutation, invalidateReplies],
  );

  return {
    replies,
    isLoading,
    isSubmitting: createMutation.isPending,
    addReply,
    deleteReply,
    editReply,
    fetchReplies: invalidateReplies,
  };
}
