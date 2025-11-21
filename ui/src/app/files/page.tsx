"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { toast } from "react-toastify";
import { ToastContainer } from "react-toastify";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { VscFolder, VscFolderOpened, VscFile, VscJson } from "react-icons/vsc";

import {
  getFileTree,
  getFileContent,
  saveFileContent,
  getGitStatus,
  gitPullConfig,
  gitPushConfig,
} from "@/client/file/file";
import type { FileTreeNode, SaveFileRequest } from "@/schemas";

import "react-toastify/dist/ReactToastify.css";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function FilesEditorPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");

  const {
    data: fileTreeData,
    isLoading: isTreeLoading,
    error: treeError,
  } = useQuery({
    queryKey: ["fileTree"],
    queryFn: () => getFileTree().then((res) => res.data),
  });

  const { data: fileContentData, isLoading: isContentLoading } = useQuery({
    queryKey: ["fileContent", selectedFile],
    queryFn: () =>
      getFileContent({ path: selectedFile || "" }).then((res) => res.data),
    enabled: !!selectedFile,
  });

  const { data: gitStatusData, refetch: refetchGitStatus } = useQuery({
    queryKey: ["gitStatus"],
    queryFn: () => getGitStatus().then((res) => res.data),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const saveMutation = useMutation({
    mutationFn: (request: SaveFileRequest) =>
      saveFileContent(request).then((res) => res.data),
    onSuccess: () => {
      setHasUnsavedChanges(false);
      toast.success("File saved successfully!");
      queryClient.invalidateQueries({
        queryKey: ["fileContent", selectedFile],
      });
      refetchGitStatus();
    },
    onError: (error: any) => {
      toast.error(`Failed to save file: ${error.message}`);
    },
  });

  const pullMutation = useMutation({
    mutationFn: () => gitPullConfig().then((res) => res.data),
    onSuccess: (data) => {
      toast.success(
        `Git pull successful! Updated to commit: ${data.commit || "unknown"}`,
      );
      queryClient.invalidateQueries({ queryKey: ["fileTree"] });
      queryClient.invalidateQueries({ queryKey: ["fileContent"] });
      refetchGitStatus();
    },
    onError: (error: any) => {
      toast.error(`Git pull failed: ${error.message}`);
    },
  });

  const pushMutation = useMutation({
    mutationFn: (message: string) =>
      gitPushConfig({ commit_message: message }).then((res) => res.data),
    onSuccess: (data: any) => {
      if (data.commit) {
        toast.success(`Git push successful! Commit: ${data.commit}`);
      } else {
        toast.info(data.message || "No changes to commit");
      }
      setCommitMessage("");
      refetchGitStatus();
    },
    onError: (error: any) => {
      toast.error(`Git push failed: ${error.message}`);
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
        <VscFolderOpened className="inline-block mr-1 text-yellow-600" />
      ) : (
        <VscFolder className="inline-block mr-1 text-yellow-600" />
      );
    }

    // File type specific icons
    if (node.name.endsWith(".json")) {
      return <VscJson className="inline-block mr-1 text-yellow-500" />;
    }
    if (node.name.endsWith(".yaml") || node.name.endsWith(".yml")) {
      return <VscFile className="inline-block mr-1 text-red-400" />;
    }
    if (node.name.endsWith(".toml")) {
      return <VscFile className="inline-block mr-1 text-purple-400" />;
    }

    return <VscFile className="inline-block mr-1 text-gray-400" />;
  };

  const renderFileTree = (nodes: FileTreeNode[], level = 0): JSX.Element[] => {
    return nodes.map((node) => (
      <div key={node.path}>
        {node.type === "directory" ? (
          <details open className="group">
            <summary
              className="text-sm text-gray-300 hover:bg-[#2a2d2e] px-2 py-0.5 cursor-pointer select-none flex items-center list-none"
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
                ? "bg-[#37373d] text-white"
                : "text-gray-300 hover:bg-[#2a2d2e]"
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
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    );
  }

  if (treeError) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <span>Failed to load file tree: {treeError.message}</span>
        </div>
        <button onClick={() => router.push("/")} className="btn btn-ghost mt-4">
          ← Back to Home
        </button>
      </div>
    );
  }

  return (
    <>
      <ToastContainer position="top-right" autoClose={3000} />
      <div className="h-screen flex flex-col bg-[#1e1e1e]">
        <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-[#3e3e3e]">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/")}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors"
            >
              ← Back
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">
                Config Files
              </span>
              {selectedFile && (
                <>
                  <span className="text-gray-500">/</span>
                  <span className="text-sm text-gray-400">{selectedFile}</span>
                </>
              )}
            </div>
            {hasUnsavedChanges && (
              <span className="text-xs text-orange-400">● Unsaved changes</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {(gitStatusData as any)?.is_git_repo && (
              <div className="flex items-center gap-2 px-3 py-1 text-xs bg-[#3c3c3c] border border-[#454545] rounded">
                <span className="text-gray-400">
                  {(gitStatusData as any).branch || "main"}
                </span>
                <span className="text-gray-500">@</span>
                <span className="text-blue-400">
                  {(gitStatusData as any).commit || "unknown"}
                </span>
                {(gitStatusData as any).is_dirty && (
                  <span className="text-orange-400">● Modified</span>
                )}
              </div>
            )}
            <button
              onClick={handlePull}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors disabled:opacity-50"
              disabled={pullMutation.isPending}
              title="Pull latest changes from Git repository"
            >
              {pullMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                "↓ Pull"
              )}
            </button>
            <button
              onClick={handlePush}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors disabled:opacity-50"
              disabled={pushMutation.isPending}
              title="Push changes to Git repository"
            >
              {pushMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                "↑ Push"
              )}
            </button>
            <button
              onClick={handleSave}
              className="px-3 py-1 text-sm text-white bg-[#0e639c] border border-[#1177bb] rounded hover:bg-[#1177bb] transition-colors disabled:opacity-50"
              disabled={
                !selectedFile || !hasUnsavedChanges || saveMutation.isPending
              }
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                "Save (Ctrl+S)"
              )}
            </button>
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          <div className="w-64 bg-[#252526] border-r border-[#3e3e3e] overflow-y-auto">
            <div className="py-2">
              <h2 className="text-xs font-bold text-gray-400 mb-1 px-3 tracking-wider">
                EXPLORER
              </h2>
              <div className="text-xs text-gray-500 px-3 mb-2 uppercase tracking-wide">
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
                          handleSave();
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
                    }}
                  />
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <p className="text-lg mb-2">No file selected</p>
                  <p className="text-sm">Select a file from the tree to edit</p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between px-4 py-1 bg-[#007acc] text-white text-xs">
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
      </div>
    </>
  );
}
