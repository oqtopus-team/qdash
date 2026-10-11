/**
 * A git-backed file workspace the UI can browse, edit, pull, and push as a PR.
 *
 * Two exist: the Qubex configuration tree and the task knowledge repository.
 * They share the same API shape under different paths, so the editor and the
 * git toolbar take a workspace instead of importing one client.
 */

import type { AxiosResponse } from "axios";

import {
  getFileContent,
  getFileTree,
  getGitStatus,
  gitPullConfig,
  gitPushConfig,
  saveFileContent,
} from "@/client/file/file";
import {
  getKnowledgeFileContent,
  getKnowledgeFileTree,
  getKnowledgeGitStatus,
  gitPullKnowledge,
  gitPushKnowledge,
  saveKnowledgeFileContent,
} from "@/client/knowledge/knowledge";
import type { FileTreeNode } from "@/schemas";

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
}

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
  key: "config" | "knowledge";
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
  saveContent: (path: string, content: string) => Promise<{ message: string; path: string }>;
  getGitStatus: () => Promise<GitWorkspaceStatus>;
  pull: () => Promise<GitPullResult>;
  push: (commitMessage: string) => Promise<GitPushResult>;
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
  saveContent: (path, content) =>
    saveFileContent({ path, content }).then((r) => r.data as { message: string; path: string }),
  getGitStatus: () => getGitStatus().then((r) => r.data as GitWorkspaceStatus),
  pull: () => gitPullConfig().then((r) => r.data as GitPullResult),
  push: (commit_message) => gitPushConfig({ commit_message }).then((r) => r.data as GitPushResult),
};

export const KNOWLEDGE_WORKSPACE: FileWorkspace = {
  key: "knowledge",
  title: "Knowledge Files",
  editorPath: "/knowledge/files",
  defaultCommitMessage: "Update task knowledge from UI",
  seedImport: false,
  bulkDownload: false,
  getTree: () => getKnowledgeFileTree().then(data),
  getContent: (path) =>
    getKnowledgeFileContent({ path }).then((r) => r.data as unknown as WorkspaceFileContent),
  saveContent: (path, content) =>
    saveKnowledgeFileContent({ path, content }).then(
      (r) => r.data as { message: string; path: string },
    ),
  getGitStatus: () => getKnowledgeGitStatus().then((r) => r.data as GitWorkspaceStatus),
  pull: () => gitPullKnowledge().then((r) => r.data as GitPullResult),
  push: (commit_message) =>
    gitPushKnowledge({ commit_message }).then((r) => r.data as GitPushResult),
};

/** Query keys the workspace's data lives under, so saves and pulls can invalidate them. */
export const workspaceQueryKeys = {
  tree: (workspace: FileWorkspace) => ["fileWorkspace", workspace.key, "tree"] as const,
  content: (workspace: FileWorkspace, path?: string | null) =>
    path == null
      ? (["fileWorkspace", workspace.key, "content"] as const)
      : (["fileWorkspace", workspace.key, "content", path] as const),
  gitStatus: (workspace: FileWorkspace) => ["fileWorkspace", workspace.key, "gitStatus"] as const,
};

/** The markdown file of one task's knowledge inside the knowledge repository. */
export function knowledgeIndexPath(category: string, taskName: string): string {
  return `${category}/${taskName}/index.md`;
}
