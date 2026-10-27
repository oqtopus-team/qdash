"use client";

import type { ReactNode } from "react";

import {
  ArrowDown,
  ChevronDown,
  ExternalLink,
  GitBranch,
  GitPullRequestArrow,
  RefreshCw,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { type GitWorkspaceStatus, unpublishedCount } from "@/lib/fileWorkspace";

import type { PullRequestCreated } from "./useGitWorkspace";

interface GitWorkspaceToolbarProps {
  status: GitWorkspaceStatus | undefined;
  onPull: () => void;
  onPush: () => void;
  isPulling: boolean;
  isPushing: boolean;
  /** Publish unpublished calibration files, then pull. Absent for a workspace without a repository. */
  onSync?: () => void;
  isSyncing?: boolean;
  /** Hidden on small screens when the page has its own mobile controls. */
  hideOnMobile?: boolean;
  pushTitle?: string;
  /** Extra entries for the repository menu (e.g. a download). */
  menuItems?: ReactNode;
}

/**
 * The workspace's repository as one menu (branch @ commit, pull, extras) plus
 * the primary Create PR action.
 */
export function GitWorkspaceToolbar({
  status,
  onPull,
  onPush,
  isPulling,
  isPushing,
  onSync,
  isSyncing = false,
  hideOnMobile = false,
  pushTitle = "Create a pull request with the saved changes",
  menuItems,
}: GitWorkspaceToolbarProps) {
  const responsive = hideOnMobile ? "hidden sm:inline-flex" : "inline-flex";
  const attention = status?.has_remote_updates || status?.is_dirty;
  const unpublished = unpublishedCount(status);
  return (
    <>
      <RepositoryBadges status={status} hideOnMobile={hideOnMobile} />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={`btn btn-sm btn-ghost ${responsive} gap-1 font-normal`}
            title={status?.commit_message ?? "Repository"}
            aria-label="Repository menu"
          >
            <GitBranch size={16} className="shrink-0 opacity-70" />
            {status?.is_git_repo ? (
              <span className="hidden md:inline">
                <span className="text-base-content/70">{status.branch || "main"}</span>
                <span className="text-base-content/40"> @ </span>
                <span className="font-mono text-info">{status.commit || "unknown"}</span>
              </span>
            ) : (
              <span className="hidden md:inline text-base-content/60">No repository</span>
            )}
            {status?.has_remote_updates && (
              <span
                className="inline-flex h-2 w-2 rounded-full bg-warning"
                title="Remote has new changes"
              />
            )}
            {!status?.has_remote_updates && status?.is_dirty && (
              <span
                className="text-warning"
                title="Saved changes not yet in a pull request"
                aria-label="Saved changes not yet in a pull request"
              >
                ●
              </span>
            )}
            <ChevronDown size={14} className={`shrink-0 opacity-60 ${attention ? "" : ""}`} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel className="truncate text-xs text-base-content/60">
            {status?.is_git_repo
              ? `${status.branch || "main"} @ ${status.commit || "unknown"}`
              : "Not cloned yet"}
          </DropdownMenuLabel>
          <DropdownMenuItem onSelect={onPull} disabled={isPulling}>
            {isPulling ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <ArrowDown size={16} />
            )}
            <span className="flex-1">Pull latest</span>
            {status?.has_remote_updates && (
              <span className="badge badge-warning badge-xs">new</span>
            )}
          </DropdownMenuItem>
          {onSync && status?.mode !== "plain" && (
            <DropdownMenuItem onSelect={onSync} disabled={isSyncing}>
              {isSyncing ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                <RefreshCw size={16} />
              )}
              <span className="flex-1">Sync</span>
              {unpublished > 0 && (
                <span
                  className="badge badge-warning badge-xs"
                  title={`${unpublished} unpublished ${unpublished === 1 ? "change" : "changes"}`}
                >
                  {unpublished}
                </span>
              )}
            </DropdownMenuItem>
          )}
          {menuItems && (
            <>
              <DropdownMenuSeparator />
              {menuItems}
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
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

const MODE_LABEL: Record<string, string> = {
  github: "GitHub",
  "local-git": "Local git",
  plain: "No repository",
};

/**
 * How the workspace is synchronized (GitHub, local git, none), its Qubex
 * layout, and the count of unpublished changes.
 */
function RepositoryBadges({
  status,
  hideOnMobile = false,
}: {
  status: GitWorkspaceStatus | undefined;
  hideOnMobile?: boolean;
}) {
  if (!status?.mode) return null;
  const unpublished = unpublishedCount(status);
  const responsive = hideOnMobile ? "hidden sm:flex" : "flex";
  return (
    <div className={`${responsive} items-center gap-1`} data-testid="repository-badges">
      <span
        className={`badge badge-sm ${status.mode === "github" ? "badge-info" : "badge-ghost"}`}
        title={`Repository mode: ${status.mode}`}
      >
        {MODE_LABEL[status.mode] ?? status.mode}
      </span>
      {status.layout && (
        <span
          className="badge badge-sm badge-outline"
          title={
            status.layout_version
              ? `Qubex layout ${status.layout_version} (${status.layout})${
                  status.manifest_present
                    ? ", declared by qubex-config.json"
                    : ", inferred from the tree"
                }`
              : `Qubex layout: ${status.layout}`
          }
        >
          {status.layout_version ? `${status.layout} ${status.layout_version}` : status.layout}
        </span>
      )}
      {status.layout_version && status.manifest_present === false && (
        <span
          className="badge badge-sm badge-warning"
          title={`The configuration repository has no qubex-config.json; the layout version ${status.layout_version} is inferred from the tree`}
        >
          no manifest
        </span>
      )}
      {status.schemas_status === "differs" && (
        <span
          className="badge badge-sm badge-warning"
          title="schemas/ in the configuration tree differs from the schemas QDash validates with"
        >
          schemas
        </span>
      )}
      {status.review_required && (
        <span
          className="badge badge-sm badge-outline"
          title="Workflow publishes open a pull request"
        >
          review
        </span>
      )}
      {unpublished > 0 && (
        <span
          className="badge badge-sm badge-warning"
          title={`${unpublished} unpublished ${unpublished === 1 ? "change" : "changes"}`}
          aria-label={`${unpublished} unpublished ${unpublished === 1 ? "change" : "changes"}`}
        >
          {unpublished} unpublished
        </span>
      )}
    </div>
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
