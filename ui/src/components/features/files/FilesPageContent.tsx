"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useEffect, useMemo } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  Check,
  Database,
  ExternalLink,
  File,
  FileJson,
  Folder,
  FolderOpen,
  GitPullRequestArrow,
  Pencil,
  Plus,
  Save,
} from "lucide-react";

import type {
  FileTreeNode,
  SaveFileRequest,
  GetFileContent200,
  GetGitStatus200,
  SaveFileContent200,
  GitPullConfig200,
  GitPushConfig200,
} from "@/schemas";
import type { AxiosResponse } from "axios";

import {
  getFileTree,
  getFileContent,
  saveFileContent,
  getGitStatus,
  gitPullConfig,
  gitPushConfig,
} from "@/client/file/file";
import { EditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useToast } from "@/components/ui/Toast";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

// Helper to check if file is a params YAML that can be imported
function parseParamsFilePath(
  path: string,
): { chipId: string; paramName: string } | null {
  // Match pattern: config/qubex/{chip_id}/params/{param_name}.yaml
  const match = path.match(/^config\/qubex\/([^/]+)\/params\/([^/]+)\.ya?ml$/);
  if (match) {
    return { chipId: match[1], paramName: match[2] };
  }
  return null;
}

// Extended git status type (API returns generic dict)
interface GitStatusExtended {
  is_git_repo?: boolean;
  branch?: string;
  commit?: string;
  is_dirty?: boolean;
  has_remote_updates?: boolean;
}

// Extended git push result type (API returns generic dict)
interface GitPushResult {
  pr_url?: string;
  pr_number?: number;
  branch?: string;
  commit?: string;
  message?: string;
}

// Seed import response type
interface SeedImportResponse {
  chip_id: string;
  source: string;
  imported_count: number;
  skipped_count: number;
  error_count: number;
  provenance_activity_id?: string | null;
}

export function FilesPageContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [isEditorLocked, setIsEditorLocked] = useState(true);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [importResult, setImportResult] = useState<SeedImportResponse | null>(
    null,
  );
  const [prResult, setPrResult] = useState<{
    pr_url: string;
    pr_number: number;
    branch: string;
  } | null>(null);

  // Check if selected file is a params YAML that can be imported
  const paramsFileInfo = useMemo(() => {
    if (!selectedFile) return null;
    return parseParamsFilePath(selectedFile);
  }, [selectedFile]);

  const {
    data: fileTreeData,
    isLoading: isTreeLoading,
    error: treeError,
  } = useQuery({
    queryKey: ["fileTree"],
    queryFn: () =>
      getFileTree().then((res: AxiosResponse<FileTreeNode[]>) => res.data),
  });

  const { data: fileContentData, isLoading: isContentLoading } = useQuery({
    queryKey: ["fileContent", selectedFile],
    queryFn: () =>
      getFileContent({ path: selectedFile || "" }).then(
        (res: AxiosResponse<GetFileContent200>) => res.data,
      ),
    enabled: !!selectedFile,
  });

  const { data: gitStatusData, refetch: refetchGitStatus } = useQuery({
    queryKey: ["gitStatus"],
    queryFn: () =>
      getGitStatus().then((res: AxiosResponse<GetGitStatus200>) => res.data),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const saveMutation = useMutation({
    mutationFn: (request: SaveFileRequest) =>
      saveFileContent(request).then(
        (res: AxiosResponse<SaveFileContent200>) => res.data,
      ),
    onSuccess: () => {
      setHasUnsavedChanges(false);
      toast.success("File saved successfully!");
      queryClient.invalidateQueries({
        queryKey: ["fileContent", selectedFile],
      });
      refetchGitStatus();
    },
    onError: (error: Error) => {
      toast.error(`Failed to save file: ${error.message}`);
    },
  });

  const pullMutation = useMutation({
    mutationFn: () =>
      gitPullConfig().then((res: AxiosResponse<GitPullConfig200>) => res.data),
    onSuccess: (data: GitPullConfig200) => {
      toast.success(
        `Git pull successful! Updated to commit: ${(data.commit as string) || "unknown"}`,
      );
      queryClient.invalidateQueries({ queryKey: ["fileTree"] });
      queryClient.invalidateQueries({ queryKey: ["fileContent"] });
      refetchGitStatus();
    },
    onError: (error: Error) => {
      toast.error(`Git pull failed: ${error.message}`);
    },
  });

  const pushMutation = useMutation({
    mutationFn: (message: string) =>
      gitPushConfig({ commit_message: message }).then(
        (res: AxiosResponse<GitPushConfig200>) => res.data,
      ),
    onSuccess: (data: GitPushConfig200) => {
      const result = data as GitPushResult;
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
        toast.info(String(result.message) || "No changes to commit");
      }
      setCommitMessage("");
      refetchGitStatus();
    },
    onError: (error: Error) => {
      toast.error(`Git push failed: ${error.message}`);
    },
  });

  // Seed import mutation
  const importMutation = useMutation({
    mutationFn: async ({
      chipId,
      paramName,
    }: {
      chipId: string;
      paramName: string;
    }) => {
      const response = await fetch("/api/calibrations/seed-import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chip_id: chipId,
          source: "qubex_params",
          parameters: [paramName],
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || `Import failed: ${response.status}`,
        );
      }
      return response.json() as Promise<SeedImportResponse>;
    },
    onSuccess: (data) => {
      setImportResult(data);
      toast.success(`Imported ${data.imported_count} parameters to QDash`);
    },
    onError: (error: Error) => {
      toast.error(`Import failed: ${error.message}`);
    },
  });

  useEffect(() => {
    if (
      fileContentData?.content !== undefined &&
      fileContentData?.content !== null
    ) {
      setFileContent(String(fileContentData.content));
      setHasUnsavedChanges(false);
    }
  }, [fileContentData]);

  const handleFileSelect = (path: string) => {
    if (hasUnsavedChanges) {
      if (
        !confirm(
          "You have unsaved changes. Do you want to discard them and open another file?",
        )
      ) {
        return;
      }
    }
    setSelectedFile(path);
    setHasUnsavedChanges(false);
    setIsEditorLocked(true); // Lock editor when opening new file
    setImportResult(null); // Clear import result when selecting new file
  };

  const handleImportToQDash = () => {
    if (!paramsFileInfo) return;
    importMutation.mutate({
      chipId: paramsFileInfo.chipId,
      paramName: paramsFileInfo.paramName,
    });
  };

  const toggleEditorLock = () => {
    setIsEditorLocked(!isEditorLocked);
  };

  const handleSave = () => {
    if (!selectedFile) {
      toast.error("No file selected");
      return;
    }

    saveMutation.mutate({
      path: selectedFile,
      content: fileContent,
    });
  };

  const handlePull = () => {
    if (hasUnsavedChanges) {
      if (
        !confirm(
          "You have unsaved changes. Git pull will overwrite them. Continue?",
        )
      ) {
        return;
      }
    }
    pullMutation.mutate();
  };

  const handlePush = () => {
    const message = commitMessage.trim() || "Update config files from UI";
    pushMutation.mutate(message);
  };

  const handleContentChange = (value: string | undefined) => {
    setFileContent(value || "");
    setHasUnsavedChanges(true);
  };

  const getLanguage = (filename: string): string => {
    if (filename.endsWith(".yaml") || filename.endsWith(".yml")) return "yaml";
    if (filename.endsWith(".json")) return "json";
    if (filename.endsWith(".toml")) return "toml";
    return "plaintext";
  };

  const getFileIcon = (node: FileTreeNode, isOpen = false) => {
    if (node.type === "directory") {
      return isOpen ? (
        <FolderOpen className="inline-block mr-1 text-yellow-600" size={14} />
      ) : (
        <Folder className="inline-block mr-1 text-yellow-600" size={14} />
      );
    }

    // File type specific icons
    if (node.name.endsWith(".json")) {
      return (
        <FileJson className="inline-block mr-1 text-yellow-500" size={14} />
      );
    }
    if (node.name.endsWith(".yaml") || node.name.endsWith(".yml")) {
      return <File className="inline-block mr-1 text-red-400" size={14} />;
    }
    if (node.name.endsWith(".toml")) {
      return <File className="inline-block mr-1 text-purple-400" size={14} />;
    }

    return <File className="inline-block mr-1 text-gray-400" size={14} />;
  };

  const renderFileTree = (nodes: FileTreeNode[], level = 0): JSX.Element[] => {
    return nodes.map((node) => (
      <div key={node.path}>
        {node.type === "directory" ? (
          <details className="group">
            <summary
              className="text-sm text-base-content/80 hover:bg-base-200 px-2 py-0.5 cursor-pointer select-none flex items-center list-none"
              style={{ paddingLeft: `${level * 12 + 8}px` }}
            >
              <span className="mr-1 transition-transform group-open:rotate-90">
                ▸
              </span>
              {getFileIcon(node, true)}
              <span className="truncate">{node.name}</span>
            </summary>
            {node.children && renderFileTree(node.children, level + 1)}
          </details>
        ) : (
          <div
            className={`text-sm px-2 py-0.5 cursor-pointer select-none flex items-center transition-colors ${
              selectedFile === node.path
                ? "bg-primary/20 text-base-content"
                : "text-base-content/80 hover:bg-base-200"
            }`}
            style={{ paddingLeft: `${level * 12 + 20}px` }}
            onClick={() => handleFileSelect(node.path)}
          >
            {getFileIcon(node)}
            <span className="truncate">{node.name}</span>
          </div>
        )}
      </div>
    ));
  };

  if (isTreeLoading) {
    return <EditorPageSkeleton />;
  }

  if (treeError) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <span>Failed to load file tree: {(treeError as Error)?.message}</span>
        </div>
        <button onClick={() => router.push("/")} className="btn btn-ghost mt-4">
          ← Back to Home
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="h-screen flex flex-col bg-base-300">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0">
            <div className="flex items-center gap-1 sm:gap-2 min-w-0 overflow-hidden">
              <span className="text-sm font-medium flex-shrink-0 hidden sm:inline">
                Config Files
              </span>
              {selectedFile && (
                <>
                  <span className="text-base-content/50 hidden sm:inline">
                    /
                  </span>
                  <span className="text-sm text-base-content/70 truncate">
                    {selectedFile}
                  </span>
                </>
              )}
            </div>
            {hasUnsavedChanges && (
              <span className="text-xs text-warning flex-shrink-0">●</span>
            )}
          </div>
          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 overflow-x-auto">
            <button
              onClick={toggleEditorLock}
              className={`btn btn-sm hidden sm:flex ${isEditorLocked ? "btn-outline" : "btn-warning"}`}
              title={isEditorLocked ? "Click to edit" : "Currently editing"}
            >
              <Pencil size={16} />
              <span className="ml-1">
                {isEditorLocked ? "Edit" : "Editing"}
              </span>
            </button>
            {(gitStatusData as GitStatusExtended | undefined)?.is_git_repo && (
              <div className="hidden md:flex items-center gap-2 px-2 sm:px-3 py-1 text-xs bg-base-100 border border-base-300 rounded">
                <span className="text-base-content/70">
                  {(gitStatusData as GitStatusExtended | undefined)?.branch ||
                    "main"}
                </span>
                <span className="text-base-content/50">@</span>
                <span className="text-info">
                  {(gitStatusData as GitStatusExtended | undefined)?.commit ||
                    "unknown"}
                </span>
                {(gitStatusData as GitStatusExtended | undefined)?.is_dirty && (
                  <span className="text-warning">●</span>
                )}
              </div>
            )}
            <button
              onClick={handlePull}
              className={`btn btn-sm hidden sm:flex ${(gitStatusData as GitStatusExtended | undefined)?.has_remote_updates ? "btn-warning" : "btn-info"}`}
              disabled={pullMutation.isPending}
              title={
                (gitStatusData as GitStatusExtended | undefined)
                  ?.has_remote_updates
                  ? "Remote has new changes - click to pull"
                  : "Pull latest changes from Git repository"
              }
            >
              {pullMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <ArrowDown size={16} />
              )}
              <span className="ml-1">Pull</span>
              {(gitStatusData as GitStatusExtended | undefined)
                ?.has_remote_updates && (
                <span className="inline-flex h-2 w-2 rounded-full bg-warning-content animate-ping"></span>
              )}
            </button>
            <button
              onClick={handlePush}
              className="btn btn-sm btn-secondary hidden sm:flex"
              disabled={pushMutation.isPending}
              title="Create a pull request with config changes"
            >
              {pushMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <GitPullRequestArrow size={16} />
              )}
              <span className="ml-1">Create PR</span>
            </button>
            <button
              onClick={handleSave}
              className={`btn btn-sm hidden sm:flex ${isEditorLocked ? "btn-outline" : "btn-success"}`}
              disabled={
                !selectedFile ||
                !hasUnsavedChanges ||
                saveMutation.isPending ||
                isEditorLocked
              }
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <>
                  <Save size={16} />
                  <span className="ml-1">Save</span>
                </>
              )}
            </button>
            {/* Import to QDash button - only show for params YAML files */}
            {paramsFileInfo && (
              <button
                onClick={handleImportToQDash}
                className="btn btn-sm btn-accent hidden sm:flex"
                disabled={importMutation.isPending}
                title={`Import ${paramsFileInfo.paramName} to QDash for provenance tracking`}
              >
                {importMutation.isPending ? (
                  <span className="loading loading-spinner loading-xs"></span>
                ) : (
                  <>
                    <Database size={16} />
                    <span className="ml-1">Import to QDash</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* PR created banner */}
        {prResult && (
          <div className="px-4 py-2 bg-secondary/20 border-b border-secondary/30 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <GitPullRequestArrow size={16} className="text-secondary" />
              <span>
                Pull request <strong>#{prResult.pr_number}</strong> created on
                branch <strong>{prResult.branch}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={prResult.pr_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-xs btn-ghost gap-1"
              >
                Open PR <ExternalLink size={12} />
              </a>
              <button
                onClick={() => setPrResult(null)}
                className="btn btn-xs btn-ghost"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Import success banner */}
        {importResult && (
          <div className="px-4 py-2 bg-success/20 border-b border-success/30 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <Check size={16} className="text-success" />
              <span>
                Imported {importResult.imported_count} values for{" "}
                <strong>{paramsFileInfo?.paramName}</strong> from{" "}
                <strong>{importResult.chip_id}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/provenance" className="btn btn-xs btn-ghost">
                View in Provenance →
              </Link>
              <button
                onClick={() => setImportResult(null)}
                className="btn btn-xs btn-ghost"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 flex overflow-hidden">
          <div
            className={`${isSidebarVisible ? "w-48 sm:w-64" : "w-0"} bg-base-100 border-r border-base-300 overflow-y-auto transition-all duration-200 overflow-hidden flex-shrink-0`}
          >
            <div className="py-2">
              <h2 className="text-xs font-bold text-base-content/60 mb-1 px-3 tracking-wider">
                EXPLORER
              </h2>
              <div className="text-xs text-base-content/50 px-3 mb-2 uppercase tracking-wide">
                Config Files
              </div>
              {fileTreeData && renderFileTree(fileTreeData)}
            </div>
          </div>

          <div className="flex-1 flex flex-col">
            {selectedFile ? (
              <>
                {isContentLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <span className="loading loading-spinner loading-lg"></span>
                  </div>
                ) : (
                  <Editor
                    height="100%"
                    language={getLanguage(selectedFile)}
                    theme="vs-dark"
                    value={fileContent}
                    onChange={handleContentChange}
                    onMount={(editor, monaco) => {
                      editor.onDidChangeCursorPosition((e) => {
                        setCursorPosition({
                          line: e.position.lineNumber,
                          column: e.position.column,
                        });
                      });

                      editor.addCommand(
                        monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
                        () => {
                          if (!isEditorLocked) {
                            handleSave();
                          }
                        },
                      );
                    }}
                    options={{
                      minimap: { enabled: true },
                      fontSize: 14,
                      lineNumbers: "on",
                      automaticLayout: true,
                      scrollBeyondLastLine: false,
                      padding: { top: 16, bottom: 16 },
                      wordWrap: "on",
                      folding: true,
                      renderLineHighlight: "all",
                      cursorStyle: "line",
                      cursorBlinking: "blink",
                      readOnly: isEditorLocked,
                      domReadOnly: isEditorLocked,
                    }}
                  />
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-base-content/50">
                <div className="text-center">
                  <p className="text-lg mb-2">No file selected</p>
                  <p className="text-sm">Select a file from the tree to edit</p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between px-4 py-1 bg-primary text-primary-content text-xs">
          <div className="flex items-center gap-4">
            {selectedFile && (
              <>
                <span>
                  Ln {cursorPosition.line}, Col {cursorPosition.column}
                </span>
                <span>{getLanguage(selectedFile).toUpperCase()}</span>
                <span>UTF-8</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-4">
            {selectedFile && (
              <span>{fileContent.split("\n").length} lines</span>
            )}
          </div>
        </div>

        {/* Mobile FAB */}
        <div className="fab fixed bottom-20 right-4 z-30 sm:hidden">
          <div
            tabIndex={0}
            role="button"
            className="btn btn-circle btn-primary shadow-lg"
          >
            <Plus size={20} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Sidebar
            </span>
            <button
              onClick={() => setIsSidebarVisible(!isSidebarVisible)}
              className="btn btn-circle btn-outline bg-base-100 shadow-lg"
            >
              <Folder size={20} />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              {isEditorLocked ? "Edit" : "Editing"}
            </span>
            <button
              onClick={toggleEditorLock}
              className={`btn btn-circle shadow-lg ${isEditorLocked ? "btn-outline bg-base-100" : "btn-warning"}`}
            >
              <Pencil size={20} />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Pull
            </span>
            <button
              onClick={handlePull}
              className={`btn btn-circle shadow-lg ${(gitStatusData as GitStatusExtended | undefined)?.has_remote_updates ? "btn-warning" : "btn-info"}`}
              disabled={pullMutation.isPending}
            >
              {pullMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <ArrowDown size={20} />
              )}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Create PR
            </span>
            <button
              onClick={handlePush}
              className="btn btn-circle btn-secondary shadow-lg"
              disabled={pushMutation.isPending}
            >
              {pushMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <GitPullRequestArrow size={20} />
              )}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Save
            </span>
            <button
              onClick={handleSave}
              className={`btn btn-circle shadow-lg ${isEditorLocked ? "btn-outline bg-base-100" : "btn-success"}`}
              disabled={
                !selectedFile ||
                !hasUnsavedChanges ||
                saveMutation.isPending ||
                isEditorLocked
              }
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <Save size={20} />
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
