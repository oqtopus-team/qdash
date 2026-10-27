"use client";

import { useCallback, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Axios from "axios";

import { useToast } from "@/components/ui/Toast";
import {
  type FileWorkspace,
  type GitPushResult,
  type GitSyncResult,
  type GitWorkspaceStatus,
  workspaceQueryKeys,
} from "@/lib/fileWorkspace";
import { getApiErrorMessage } from "@/lib/utils/apiError";

export interface PullRequestCreated {
  pr_url: string;
  pr_number: number;
  branch: string;
}

/** The server refused to overwrite unpublished edits to shared files. */
export interface PullConflict {
  message: string;
  /** Which action to retry with force. */
  action: "pull" | "sync";
}

function conflictOf(error: unknown, action: "pull" | "sync"): PullConflict | null {
  if (Axios.isAxiosError(error) && error.response?.status === 409) {
    return { message: getApiErrorMessage(error, "Shared files have unpublished changes"), action };
  }
  return null;
}

/**
 * Git state and actions of one workspace: status polling, pull, sync, and
 * push as a pull request, with the toasts both pages show. A 409 on pull or
 * sync is kept as `conflict` for the page to confirm a forced retry.
 */
export function useGitWorkspace(workspace: FileWorkspace, options?: { onPulled?: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [prResult, setPrResult] = useState<PullRequestCreated | null>(null);
  const [conflict, setConflict] = useState<PullConflict | null>(null);
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
    mutationFn: (force?: boolean) => workspace.pull(force),
    onSuccess: (result) => {
      const published = result.published?.length ?? 0;
      toast.success(
        `Pulled ${workspace.key}: now at ${result.commit ?? "unknown"}` +
          (published > 0 ? ` (published ${published} ${published === 1 ? "file" : "files"})` : ""),
      );
      setConflict(null);
      invalidateWorkspace();
      onPulled?.();
    },
    onError: (error: Error) => {
      const refused = conflictOf(error, "pull");
      if (refused) {
        setConflict(refused);
        return;
      }
      toast.error(`Git pull failed: ${getApiErrorMessage(error, "Unknown error")}`);
    },
  });

  const syncMutation = useMutation({
    mutationFn: (force?: boolean) => {
      if (!workspace.sync) throw new Error("This workspace has no repository to sync");
      return workspace.sync(force);
    },
    onSuccess: (result: GitSyncResult) => {
      const published = result.published?.length ?? 0;
      if (result.mode === "plain") {
        toast.info(result.message || "No repository configured; files are written in place");
      } else {
        toast.success(
          `Synced ${workspace.key}: ` +
            (published > 0
              ? `published ${published} ${published === 1 ? "file" : "files"}, `
              : "") +
            `now at ${result.commit ?? "unknown"}`,
        );
      }
      setConflict(null);
      invalidateWorkspace();
      onPulled?.();
    },
    onError: (error: Error) => {
      const refused = conflictOf(error, "sync");
      if (refused) {
        setConflict(refused);
        return;
      }
      toast.error(`Sync failed: ${getApiErrorMessage(error, "Unknown error")}`);
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
    pull: (force?: boolean) => pullMutation.mutate(force),
    isPulling: pullMutation.isPending,
    canSync: Boolean(workspace.sync),
    sync: (force?: boolean) => syncMutation.mutate(force),
    isSyncing: syncMutation.isPending,
    /** Set when a pull or sync was refused with 409; retry with `force` after confirming. */
    conflict,
    dismissConflict: () => setConflict(null),
    forceRetry: () => {
      if (!conflict) return;
      if (conflict.action === "sync") syncMutation.mutate(true);
      else pullMutation.mutate(true);
    },
    push: (message?: string) =>
      pushMutation.mutate(message?.trim() || workspace.defaultCommitMessage),
    isPushing: pushMutation.isPending,
    prResult,
    dismissPr: () => setPrResult(null),
  };
}
