"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  File,
  FileJson,
  Folder,
  FolderOpen,
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

export default function FilesEditorPage() {
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
    onError: (error: any) => {
      toast.error(`Failed to save file: ${(error as Error)?.message}`);
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
    onError: (error: any) => {
      toast.error(`Git pull failed: ${(error as Error)?.message}`);
    },
  });

  const pushMutation = useMutation({
    mutationFn: (message: string) =>
      gitPushConfig({ commit_message: message }).then(
        (res: AxiosResponse<GitPushConfig200>) => res.data,
      ),
    onSuccess: (data: GitPushConfig200) => {
      if (data.commit) {
        toast.success(`Git push successful! Commit: ${data.commit}`);
      } else {
        toast.info(String(data.message) || "No changes to commit");
      }
      setCommitMessage("");
      refetchGitStatus();
    },
    onError: (error: any) => {
      toast.error(`Git push failed: ${(error as Error)?.message}`);
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
            {(gitStatusData as any)?.is_git_repo && (
              <div className="hidden md:flex items-center gap-2 px-2 sm:px-3 py-1 text-xs bg-base-100 border border-base-300 rounded">
                <span className="text-base-content/70">
                  {(gitStatusData as any).branch || "main"}
                </span>
                <span className="text-base-content/50">@</span>
                <span className="text-info">
                  {(gitStatusData as any).commit || "unknown"}
                </span>
                {(gitStatusData as any).is_dirty && (
                  <span className="text-warning">●</span>
                )}
              </div>
            )}
            <button
              onClick={handlePull}
              className="btn btn-sm btn-info hidden sm:flex"
              disabled={pullMutation.isPending}
              title="Pull latest changes from Git repository"
            >
              {pullMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <ArrowDown size={16} />
              )}
              <span className="ml-1">Pull</span>
            </button>
            <button
              onClick={handlePush}
              className="btn btn-sm btn-secondary hidden sm:flex"
              disabled={pushMutation.isPending}
              title="Push changes to Git repository"
            >
              {pushMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <ArrowUp size={16} />
              )}
              <span className="ml-1">Push</span>
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
          </div>
        </div>

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
              className="btn btn-circle btn-info shadow-lg"
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
              Push
            </span>
            <button
              onClick={handlePush}
              className="btn btn-circle btn-secondary shadow-lg"
              disabled={pushMutation.isPending}
            >
              {pushMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <ArrowUp size={20} />
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
