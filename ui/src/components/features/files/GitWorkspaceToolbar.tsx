"use client";

import { ArrowDown, ExternalLink, GitPullRequestArrow } from "lucide-react";

import type { GitWorkspaceStatus } from "@/lib/fileWorkspace";

import type { PullRequestCreated } from "./useGitWorkspace";

interface GitWorkspaceToolbarProps {
  status: GitWorkspaceStatus | undefined;
  onPull: () => void;
  onPush: () => void;
  isPulling: boolean;
  isPushing: boolean;
  /** Hidden on small screens when the page has its own mobile controls. */
  hideOnMobile?: boolean;
  pushTitle?: string;
}

/** Branch and commit of a workspace with its Pull and Create PR actions. */
export function GitWorkspaceToolbar({
  status,
  onPull,
  onPush,
  isPulling,
  isPushing,
  hideOnMobile = false,
  pushTitle = "Create a pull request with the saved changes",
}: GitWorkspaceToolbarProps) {
  const responsive = hideOnMobile ? "hidden sm:flex" : "flex";
  return (
    <>
      {status?.is_git_repo && (
        <div
          className={`${hideOnMobile ? "hidden md:flex" : "flex"} items-center gap-2 px-2 sm:px-3 py-1 text-xs bg-base-100 border border-base-300 rounded`}
          title={status.commit_message}
        >
          <span className="text-base-content/70">{status.branch || "main"}</span>
          <span className="text-base-content/50">@</span>
          <span className="text-info">{status.commit || "unknown"}</span>
          {status.is_dirty && (
            <span className="text-warning" title="Saved changes not yet in a pull request">
              ●
            </span>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={onPull}
        className={`btn btn-sm ${responsive} ${status?.has_remote_updates ? "btn-warning" : "btn-info"}`}
        disabled={isPulling}
        title={
          status?.has_remote_updates
            ? "Remote has new changes - click to pull"
            : "Pull latest changes from the Git repository"
        }
      >
        {isPulling ? (
          <span className="loading loading-spinner loading-xs"></span>
        ) : (
          <ArrowDown size={16} />
        )}
        <span className="ml-1">Pull</span>
        {status?.has_remote_updates && (
          <span className="inline-flex h-2 w-2 rounded-full bg-warning-content animate-ping"></span>
        )}
      </button>
      <button
        type="button"
        onClick={onPush}
        className={`btn btn-sm btn-secondary ${responsive}`}
        disabled={isPushing}
        title={pushTitle}
      >
        {isPushing ? (
          <span className="loading loading-spinner loading-xs"></span>
        ) : (
          <GitPullRequestArrow size={16} />
        )}
        <span className="ml-1">Create PR</span>
      </button>
    </>
  );
}

/** Banner shown after a push opened a pull request. */
export function PullRequestBanner({
  pr,
  onDismiss,
}: {
  pr: PullRequestCreated | null;
  onDismiss: () => void;
}) {
  if (!pr) return null;
  return (
    <div className="px-4 py-2 bg-secondary/20 border-b border-secondary/30 flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm">
        <GitPullRequestArrow size={16} className="text-secondary" />
        <span>
          Pull request <strong>#{pr.pr_number}</strong> created on branch{" "}
          <strong>{pr.branch}</strong>
        </span>
      </div>
      <div className="flex items-center gap-2">
        <a
          href={pr.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-xs btn-ghost gap-1"
        >
          Open PR <ExternalLink size={12} />
        </a>
        <button type="button" onClick={onDismiss} className="btn btn-xs btn-ghost">
          ✕
        </button>
      </div>
    </div>
  );
}
