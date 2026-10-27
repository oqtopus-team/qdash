/**
 * A git-backed file workspace the UI can browse, edit, pull, and push as a PR.
 *
 * The Qubex configuration tree is the one served; the editor and the git
 * toolbar take a workspace instead of importing its client directly.
 */

import type { AxiosResponse } from "axios";

import { syncConfigRepository } from "@/client/config-repository/config-repository";
import {
  getFileContent,
  getFileImage,
  getFileTree,
  getGitStatus,
  gitPullConfig,
  gitPushConfig,
  saveFileContent,
} from "@/client/file/file";
import type { ConfigRepositorySyncResult, FileTreeNode } from "@/schemas";

/** Git status as the API reports it (a plain dict on the wire). */
export interface GitWorkspaceStatus {
  is_git_repo?: boolean;
  branch?: string;
  commit?: string;
  commit_message?: string;
  is_dirty?: boolean;
  changed_files?: string[];
  untracked_files?: string[];
  has_remote_updates?: boolean;
  message?: string;
  /** github, local-git or plain: how the tree is synchronized. */
  mode?: string;
  /** shared or legacy Qubex layout. */
  layout?: string;
  /** qubex-config layout version: 1.0 (legacy) or 2.0 (shared). */
  layout_version?: string;
  /** Whether qubex-config.json at the root declares the version. */
  manifest_present?: boolean;
  /** match, differs or absent: the tree's schemas/ copy versus the schemas QDash ships. */
  schemas_status?: string;
  /** Local commits not yet on the remote branch. */
  unpushed_commits?: number;
  /** Workflow publishes go through a pull request. */
  review_required?: boolean;
}

interface WorkspaceFileContent {
  content: string;
  base_content: string;
  is_saved_change: boolean;
  path: string;
  name: string;
  size: number;
  modified: string;
}

interface GitPullResult {
  success?: boolean;
  commit?: string | null;
  commit_message?: string;
  message?: string;
  /** Owned files published before the pull. */
  published?: string[];
}

export type GitSyncResult = ConfigRepositorySyncResult;

export interface GitPushResult {
  success?: boolean;
  commit?: string | null;
  commit_message?: string;
  message?: string;
  pr_url?: string;
  pr_number?: number;
  branch?: string;
}

export interface FileWorkspace {
  key: "config";
  /** Shown in the editor header and the explorer. */
  title: string;
  /** Route of the tree editor for this workspace. */
  editorPath: string;
  defaultCommitMessage: string;
  /** Config params files can be imported into QDash from the editor. */
  seedImport: boolean;
  bulkDownload: boolean;
  getTree: () => Promise<FileTreeNode[]>;
  getContent: (path: string) => Promise<WorkspaceFileContent>;
  /** A raster image in the workspace, for Markdown previews (the request carries the token). */
  getImage: (path: string) => Promise<Blob>;
  saveContent: (path: string, content: string) => Promise<{ message: string; path: string }>;
  getGitStatus: () => Promise<GitWorkspaceStatus>;
  /** `force` discards unpublished edits to shared files the server refused to overwrite (409). */
  pull: (force?: boolean) => Promise<GitPullResult>;
  push: (commitMessage: string) => Promise<GitPushResult>;
  /** Publish unpublished owned files, then pull. Only a repository-backed workspace has it. */
  sync?: (force?: boolean) => Promise<GitSyncResult>;
}

const data = <T>(response: AxiosResponse<T>): T => response.data;

export const CONFIG_WORKSPACE: FileWorkspace = {
  key: "config",
  title: "Config Files",
  editorPath: "/config",
  defaultCommitMessage: "Update config files from UI",
  seedImport: true,
  bulkDownload: true,
  getTree: () => getFileTree().then(data),
  getContent: (path) =>
    getFileContent({ path }).then((r) => r.data as unknown as WorkspaceFileContent),
  getImage: (path) => getFileImage({ path }).then(data),
  saveContent: (path, content) =>
    saveFileContent({ path, content }).then((r) => r.data as { message: string; path: string }),
  getGitStatus: () => getGitStatus().then((r) => r.data as GitWorkspaceStatus),
  pull: (force) =>
    gitPullConfig(force ? { force: true } : undefined).then((r) => r.data as GitPullResult),
  push: (commit_message) => gitPushConfig({ commit_message }).then((r) => r.data as GitPushResult),
  sync: (force) => syncConfigRepository({ force: Boolean(force) }).then(data),
};

/** Files with unpublished edits: saved changes plus commits not yet pushed. */
export function unpublishedCount(status: GitWorkspaceStatus | undefined): number {
  if (!status?.is_git_repo) return 0;
  const files = new Set([...(status.changed_files ?? []), ...(status.untracked_files ?? [])]);
  return files.size + (status.unpushed_commits ?? 0);
}

/** Query keys the workspace's data lives under, so saves and pulls can invalidate them. */
export const workspaceQueryKeys = {
  tree: (workspace: FileWorkspace) => ["fileWorkspace", workspace.key, "tree"] as const,
  content: (workspace: FileWorkspace, path?: string | null) =>
    path == null
      ? (["fileWorkspace", workspace.key, "content"] as const)
      : (["fileWorkspace", workspace.key, "content", path] as const),
  gitStatus: (workspace: FileWorkspace) => ["fileWorkspace", workspace.key, "gitStatus"] as const,
};

/**
 * Workspace path of an image a Markdown file references, such as
 * `./check_rabi_expected_1.png` next to `task.md`. Null for URLs, absolute
 * paths, and paths that climb out of the workspace: those are left to the browser.
 */
export function resolveWorkspaceImagePath(markdownPath: string, src: string): string | null {
  if (!src || /^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(src)) return null;
  const parts = markdownPath.split("/").slice(0, -1);
  let relative: string;
  try {
    relative = decodeURIComponent(src.split(/[?#]/)[0]);
  } catch {
    return null;
  }
  for (const segment of relative.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") {
      if (parts.length === 0) return null;
      parts.pop();
    } else {
      parts.push(segment);
    }
  }
  return parts.length > 0 ? parts.join("/") : null;
}
