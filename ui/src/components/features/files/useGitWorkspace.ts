"use client";

import { useCallback, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/Toast";
import {
  type FileWorkspace,
  type GitPushResult,
  type GitWorkspaceStatus,
  workspaceQueryKeys,
} from "@/lib/fileWorkspace";
import { getApiErrorMessage } from "@/lib/utils/apiError";

export interface PullRequestCreated {
  pr_url: string;
  pr_number: number;
  branch: string;
}

/**
 * Git state and actions of one workspace: status polling, pull, and push as a
 * pull request, with the toasts both pages show.
 */
export function useGitWorkspace(workspace: FileWorkspace, options?: { onPulled?: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [prResult, setPrResult] = useState<PullRequestCreated | null>(null);
  const onPulled = options?.onPulled;

  const statusQuery = useQuery<GitWorkspaceStatus>({
    queryKey: workspaceQueryKeys.gitStatus(workspace),
    queryFn: workspace.getGitStatus,
    refetchInterval: 10_000,
  });

  const invalidateWorkspace = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: workspaceQueryKeys.tree(workspace) });
    queryClient.invalidateQueries({ queryKey: workspaceQueryKeys.content(workspace) });
    queryClient.invalidateQueries({ queryKey: workspaceQueryKeys.gitStatus(workspace) });
  }, [queryClient, workspace]);

  const pullMutation = useMutation({
    mutationFn: workspace.pull,
    onSuccess: (result) => {
      toast.success(`Pulled ${workspace.key}: now at ${result.commit ?? "unknown"}`);
      invalidateWorkspace();
      onPulled?.();
    },
    onError: (error: Error) => {
      toast.error(`Git pull failed: ${getApiErrorMessage(error, "Unknown error")}`);
    },
  });

  const pushMutation = useMutation({
    mutationFn: (message: string) => workspace.push(message),
    onSuccess: (result: GitPushResult) => {
      if (result.pr_url) {
        toast.success(`Pull request #${result.pr_number} created!`);
        setPrResult({
          pr_url: result.pr_url,
          pr_number: result.pr_number ?? 0,
          branch: result.branch ?? "",
        });
      } else if (result.commit) {
        toast.success(`Pushed commit: ${result.commit}`);
      } else {
        toast.info(result.message || "No changes to commit");
      }
      queryClient.invalidateQueries({ queryKey: workspaceQueryKeys.gitStatus(workspace) });
    },
    onError: (error: Error) => {
      toast.error(`Git push failed: ${getApiErrorMessage(error, "Unknown error")}`);
    },
  });

  return {
    status: statusQuery.data,
    refetchStatus: statusQuery.refetch,
    invalidateWorkspace,
    pull: () => pullMutation.mutate(),
    isPulling: pullMutation.isPending,
    push: (message?: string) =>
      pushMutation.mutate(message?.trim() || workspace.defaultCommitMessage),
    isPushing: pushMutation.isPending,
    prResult,
    dismissPr: () => setPrResult(null),
  };
}
