import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useListIssues,
  getListIssuesQueryKey,
  useCloseIssue,
  useReopenIssue,
} from "@/client/issue/issue";
import type { IssueResponse } from "@/schemas";

export type { IssueResponse as TaskResultIssue };

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

  const { data, isLoading } = useListIssues(params);

  const issues = data?.data?.issues ?? [];
  const total = data?.data?.total ?? 0;

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
