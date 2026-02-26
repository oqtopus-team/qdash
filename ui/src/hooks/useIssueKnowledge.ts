"use client";

import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useListIssueKnowledge,
  getListIssueKnowledgeQueryKey,
  useGetIssueKnowledge,
  getGetIssueKnowledgeQueryKey,
  useUpdateIssueKnowledge,
  useApproveIssueKnowledge,
  useRejectIssueKnowledge,
  useDeleteIssueKnowledge,
  useExtractIssueKnowledge,
} from "@/client/issue-knowledge/issue-knowledge";

type StatusFilter = "draft" | "approved" | "rejected" | "all";

const PAGE_SIZE = 50;

export function useIssueKnowledgeList() {
  const queryClient = useQueryClient();
  const [skip, setSkip] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("draft");
  const [taskNameFilter, setTaskNameFilter] = useState<string>("");

  const params = {
    skip,
    limit: PAGE_SIZE,
    status: statusFilter === "all" ? undefined : statusFilter,
    task_name: taskNameFilter || undefined,
  };

  const { data, isLoading } = useListIssueKnowledge(params);

  const items = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;

  const goToPage = useCallback((page: number) => {
    setSkip(page * PAGE_SIZE);
  }, []);

  const invalidateList = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: getListIssueKnowledgeQueryKey(),
    });
  }, [queryClient]);

  const filterByTaskName = useCallback((name: string) => {
    setTaskNameFilter(name);
    setSkip(0);
  }, []);

  const approveMutation = useApproveIssueKnowledge({
    mutation: { onSuccess: invalidateList },
  });

  const rejectMutation = useRejectIssueKnowledge({
    mutation: { onSuccess: invalidateList },
  });

  const deleteMutation = useDeleteIssueKnowledge({
    mutation: { onSuccess: invalidateList },
  });

  const approve = useCallback(
    (knowledgeId: string) => {
      approveMutation.mutate({ knowledgeId });
    },
    [approveMutation],
  );

  const reject = useCallback(
    (knowledgeId: string) => {
      rejectMutation.mutate({ knowledgeId });
    },
    [rejectMutation],
  );

  const deleteKnowledge = useCallback(
    (knowledgeId: string) => {
      deleteMutation.mutate({ knowledgeId });
    },
    [deleteMutation],
  );

  return {
    items,
    total,
    skip,
    pageSize: PAGE_SIZE,
    isLoading,
    statusFilter,
    setStatusFilter,
    taskNameFilter,
    filterByTaskName,
    approve,
    reject,
    deleteKnowledge,
    goToPage,
    refresh: invalidateList,
  };
}

export function useIssueKnowledgeDetail(knowledgeId: string) {
  const queryClient = useQueryClient();

  const { data, isLoading } = useGetIssueKnowledge(knowledgeId, {
    query: { enabled: !!knowledgeId },
  });

  const knowledge = data?.data ?? null;

  const updateMutation = useUpdateIssueKnowledge();
  const approveMutation = useApproveIssueKnowledge();
  const rejectMutation = useRejectIssueKnowledge();

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: getGetIssueKnowledgeQueryKey(knowledgeId),
    });
    queryClient.invalidateQueries({
      queryKey: getListIssueKnowledgeQueryKey(),
    });
  }, [queryClient, knowledgeId]);

  const update = useCallback(
    async (updates: {
      title?: string;
      severity?: string;
      symptom?: string;
      root_cause?: string;
      resolution?: string;
      lesson_learned?: string[];
    }) => {
      await updateMutation.mutateAsync({
        knowledgeId,
        data: updates,
      });
      invalidate();
    },
    [knowledgeId, updateMutation, invalidate],
  );

  const approve = useCallback(async () => {
    await approveMutation.mutateAsync({ knowledgeId });
    invalidate();
  }, [knowledgeId, approveMutation, invalidate]);

  const reject = useCallback(async () => {
    await rejectMutation.mutateAsync({ knowledgeId });
    invalidate();
  }, [knowledgeId, rejectMutation, invalidate]);

  return {
    knowledge,
    isLoading,
    isUpdating: updateMutation.isPending,
    update,
    approve,
    reject,
    refresh: invalidate,
  };
}

export function useExtractKnowledge() {
  const queryClient = useQueryClient();
  const extractMutation = useExtractIssueKnowledge();

  const extract = useCallback(
    async (issueId: string) => {
      const result = await extractMutation.mutateAsync({ issueId });
      queryClient.invalidateQueries({
        queryKey: getListIssueKnowledgeQueryKey(),
      });
      return result;
    },
    [extractMutation, queryClient],
  );

  return {
    extract,
    isExtracting: extractMutation.isPending,
    error: extractMutation.error,
  };
}
