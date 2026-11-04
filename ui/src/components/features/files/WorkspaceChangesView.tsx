"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import type { GitStatusEntry } from "@pierre/trees";
import { useQueries } from "@tanstack/react-query";
import { Columns2, FileDiff, Rows3 } from "lucide-react";

import {
  type FileWorkspace,
  type GitWorkspaceStatus,
  workspaceQueryKeys,
} from "@/lib/fileWorkspace";

const PierreDiffViewer = dynamic(
  () => import("@/components/ui/PierreDiffViewer").then((module) => module.PierreDiffViewer),
  {
    loading: () => (
      <div className="flex min-h-24 items-center justify-center">
        <span className="loading loading-spinner loading-md" />
      </div>
    ),
    ssr: false,
  },
);

export type DiffLayout = "unified" | "split";

/** Tree decorations from the workspace's git status: modified and untracked files. */
export function gitStatusEntries(status: GitWorkspaceStatus | undefined): GitStatusEntry[] {
  if (!status?.is_git_repo) return [];
  return [
    ...(status.changed_files ?? []).map((path) => ({ path, status: "modified" as const })),
    ...(status.untracked_files ?? []).map((path) => ({ path, status: "untracked" as const })),
  ];
}

/** DOM id of a file's section in the changes view, for the sidebar list to scroll to. */
export function changeSectionId(path: string): string {
  return `change-${encodeURIComponent(path)}`;
}

/** Changed and untracked files of a workspace, from its git status. */
export function changedPaths(status: GitWorkspaceStatus | undefined): string[] {
  if (!status?.is_git_repo) return [];
  return Array.from(new Set([...(status.changed_files ?? []), ...(status.untracked_files ?? [])]));
}

/**
 * Every saved change of the workspace as a stacked diff against the last
 * commit: what a Create PR would send. Clicking a file name opens it.
 */
export function WorkspaceChangesView({
  workspace,
  status,
  onOpenFile,
}: {
  workspace: FileWorkspace;
  status: GitWorkspaceStatus | undefined;
  onOpenFile: (path: string) => void;
}) {
  const [layout, setLayout] = useState<DiffLayout>("unified");
  const paths = useMemo(() => changedPaths(status), [status]);
  const contents = useQueries({
    queries: paths.map((path) => ({
      queryKey: workspaceQueryKeys.content(workspace, path),
      queryFn: () => workspace.getContent(path),
      retry: false,
    })),
  });

  if (paths.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-base-content/50">
        <div className="text-center">
          <FileDiff className="mx-auto mb-2 h-8 w-8 opacity-60" />
          <p className="text-sm mb-1">No changes</p>
          <p className="text-sm">Saved edits appear here, ready for a pull request.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-base-300 bg-base-200 px-4 py-2 text-sm">
        <span>
          <strong>{paths.length}</strong> changed {paths.length === 1 ? "file" : "files"} since{" "}
          <span className="font-mono text-info">{status?.commit}</span>
        </span>
        <div className="join">
          <button
            type="button"
            className={`btn btn-xs join-item ${layout === "unified" ? "btn-active" : "btn-ghost"}`}
            onClick={() => setLayout("unified")}
            title="Unified"
          >
            <Rows3 size={14} />
          </button>
          <button
            type="button"
            className={`btn btn-xs join-item ${layout === "split" ? "btn-active" : "btn-ghost"}`}
            onClick={() => setLayout("split")}
            title="Side by side"
          >
            <Columns2 size={14} />
          </button>
        </div>
      </div>
      <div className="flex-1 space-y-4 overflow-auto p-4">
        {paths.map((path, index) => {
          const query = contents[index];
          return (
            <section
              key={path}
              id={changeSectionId(path)}
              className="scroll-mt-4 rounded-lg border border-base-300 bg-base-100"
            >
              <div className="flex items-center justify-between border-b border-base-300 px-3 py-2">
                <button
                  type="button"
                  className="link link-hover truncate font-mono text-sm"
                  onClick={() => onOpenFile(path)}
                  title="Open in the editor"
                >
                  {path}
                </button>
                {query.isError && (
                  <span
                    className="badge badge-error badge-sm"
                    title="The file is gone from the working tree"
                  >
                    deleted
                  </span>
                )}
              </div>
              {query.data ? (
                <PierreDiffViewer
                  filename={path}
                  newContent={query.data.content}
                  oldContent={query.data.base_content}
                  layout={layout}
                />
              ) : query.isError ? (
                <p className="px-3 py-2 text-sm text-base-content/60">
                  This file was deleted; the pull request will remove it.
                </p>
              ) : (
                <div className="flex min-h-16 items-center justify-center">
                  <span className="loading loading-spinner loading-sm" />
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
