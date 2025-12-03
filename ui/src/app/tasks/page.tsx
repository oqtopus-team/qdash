"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState, useEffect, useMemo } from "react";
import { toast } from "react-toastify";
import { ToastContainer } from "react-toastify";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  VscFolder,
  VscFolderOpened,
  VscFile,
  VscLock,
  VscUnlock,
  VscCopy,
  VscListTree,
  VscSymbolClass,
} from "react-icons/vsc";
import { SiPython } from "react-icons/si";

import {
  listTaskFileBackends,
  getTaskFileTree,
  getTaskFileContent,
  saveTaskFileContent,
  getTaskFileSettings,
  listTaskInfo,
} from "@/client/task-file/task-file";
import type {
  TaskFileTreeNode,
  SaveTaskFileRequest,
  TaskInfo,
} from "@/schemas";

import "react-toastify/dist/ReactToastify.css";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type ViewMode = "files" | "tasks";

export default function TasksPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [viewMode, setViewMode] = useState<ViewMode | null>(null);
  const [selectedBackend, setSelectedBackend] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isEditorLocked, setIsEditorLocked] = useState(true);

  // Fetch settings (including default backend)
  const { data: settingsData } = useQuery({
    queryKey: ["taskFileSettings"],
    queryFn: () => getTaskFileSettings().then((res) => res.data),
  });

  // Fetch available backends
  const {
    data: backendsData,
    isLoading: isBackendsLoading,
    error: backendsError,
  } = useQuery({
    queryKey: ["taskFileBackends"],
    queryFn: () => listTaskFileBackends().then((res) => res.data),
  });

  // Set default view mode when settings are loaded
  useEffect(() => {
    if (settingsData && viewMode === null) {
      const defaultViewMode = settingsData.default_view_mode;
      if (defaultViewMode === "files" || defaultViewMode === "tasks") {
        setViewMode(defaultViewMode);
      } else {
        setViewMode("tasks"); // Default to tasks if not specified
      }
    }
  }, [settingsData, viewMode]);

  // Set default backend when loaded (from settings or first available)
  useEffect(() => {
    if (
      backendsData?.backends &&
      backendsData.backends.length > 0 &&
      !selectedBackend
    ) {
      // Use default from settings if available and exists in backends list
      const defaultBackend = settingsData?.default_backend;
      const backendExists = backendsData.backends.some(
        (b) => b.name === defaultBackend,
      );
      if (defaultBackend && backendExists) {
        setSelectedBackend(defaultBackend);
      } else {
        setSelectedBackend(backendsData.backends[0].name);
      }
    }
  }, [backendsData, settingsData, selectedBackend]);

  // Fetch file tree for selected backend
  const {
    data: fileTreeData,
    isLoading: isTreeLoading,
    error: treeError,
  } = useQuery({
    queryKey: ["taskFileTree", selectedBackend],
    queryFn: () =>
      getTaskFileTree({ backend: selectedBackend! }).then((res) => res.data),
    enabled: !!selectedBackend,
  });

  // Fetch task list for selected backend
  const { data: taskListData, isLoading: isTaskListLoading } = useQuery({
    queryKey: ["taskList", selectedBackend, settingsData?.sort_order],
    queryFn: () =>
      listTaskInfo({
        backend: selectedBackend!,
        sort_order: settingsData?.sort_order ?? undefined,
      }).then((res) => res.data),
    enabled: !!selectedBackend,
  });

  // Fetch file content
  const { data: fileContentData, isLoading: isContentLoading } = useQuery({
    queryKey: ["taskFileContent", selectedFile],
    queryFn: () =>
      getTaskFileContent({ path: selectedFile || "" }).then((res) => res.data),
    enabled: !!selectedFile,
  });

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: (request: SaveTaskFileRequest) =>
      saveTaskFileContent(request).then((res) => res.data),
    onSuccess: () => {
      setHasUnsavedChanges(false);
      toast.success("File saved successfully!");
      queryClient.invalidateQueries({
        queryKey: ["taskFileContent", selectedFile],
      });
    },
    onError: (error: Error) => {
      toast.error(`Failed to save file: ${error.message}`);
    },
  });

  // Update file content when loaded
  useEffect(() => {
    if (
      fileContentData?.content !== undefined &&
      fileContentData?.content !== null
    ) {
      setFileContent(String(fileContentData.content));
      setHasUnsavedChanges(false);
    }
  }, [fileContentData]);

  const handleBackendChange = (backend: string) => {
    if (hasUnsavedChanges) {
      if (
        !confirm(
          "You have unsaved changes. Do you want to discard them and switch backends?",
        )
      ) {
        return;
      }
    }
    setSelectedBackend(backend);
    setSelectedFile(null);
    setFileContent("");
    setHasUnsavedChanges(false);
    setIsEditorLocked(true);
  };

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
    // Prepend backend name to get full path
    const fullPath = `${selectedBackend}/${path}`;
    setSelectedFile(fullPath);
    setHasUnsavedChanges(false);
    setIsEditorLocked(true);
  };

  const handleTaskClick = (task: TaskInfo) => {
    // Open the file containing this task
    handleFileSelect(task.file_path);
  };

  const handleCopyTaskName = async (taskName: string) => {
    try {
      await navigator.clipboard.writeText(taskName);
      toast.success(`Copied: ${taskName}`, { autoClose: 1500 });
    } catch {
      toast.error("Failed to copy to clipboard");
    }
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

  const handleContentChange = (value: string | undefined) => {
    // Only mark as changed if editor is unlocked
    if (isEditorLocked) {
      return;
    }
    setFileContent(value || "");
    setHasUnsavedChanges(true);
  };

  const getFileIcon = (node: TaskFileTreeNode, isOpen = false) => {
    if (node.type === "directory") {
      return isOpen ? (
        <VscFolderOpened className="inline-block mr-1 text-yellow-600" />
      ) : (
        <VscFolder className="inline-block mr-1 text-yellow-600" />
      );
    }

    // Python files
    if (node.name.endsWith(".py")) {
      return <SiPython className="inline-block mr-1 text-blue-400" />;
    }

    return <VscFile className="inline-block mr-1 text-gray-400" />;
  };

  const renderFileTree = (
    nodes: TaskFileTreeNode[],
    level = 0,
  ): JSX.Element[] => {
    return nodes.map((node) => (
      <div key={node.path}>
        {node.type === "directory" ? (
          <details className="group" open={level === 0}>
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
              selectedFile === `${selectedBackend}/${node.path}`
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

  // Group tasks by task_type
  const groupedTasks = useMemo(() => {
    if (!taskListData?.tasks) return {};
    return taskListData.tasks.reduce(
      (acc: Record<string, TaskInfo[]>, task) => {
        const type = task.task_type || "other";
        if (!acc[type]) {
          acc[type] = [];
        }
        acc[type].push(task);
        return acc;
      },
      {},
    );
  }, [taskListData]);

  const renderTaskList = () => {
    if (isTaskListLoading) {
      return (
        <div className="flex items-center justify-center py-4">
          <span className="loading loading-spinner loading-sm"></span>
        </div>
      );
    }

    if (!taskListData?.tasks || taskListData.tasks.length === 0) {
      return (
        <div className="text-xs text-gray-500 px-3 py-2">No tasks found</div>
      );
    }

    return (
      <div className="space-y-2">
        {Object.entries(groupedTasks).map(([taskType, tasks]) => (
          <details key={taskType} className="group" open>
            <summary className="text-xs font-semibold text-gray-400 px-3 py-1 cursor-pointer select-none hover:bg-[#2a2d2e] uppercase tracking-wider flex items-center">
              <span className="mr-1 transition-transform group-open:rotate-90">
                ▸
              </span>
              {taskType}
              <span className="ml-2 text-gray-600">({tasks.length})</span>
            </summary>
            <div className="space-y-0.5">
              {tasks.map((task) => (
                <div
                  key={`${task.file_path}-${task.name}`}
                  className="group/item flex items-center justify-between px-3 py-1 hover:bg-[#2a2d2e] cursor-pointer"
                  onClick={() => handleTaskClick(task)}
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <VscSymbolClass className="text-purple-400 flex-shrink-0" />
                    <span className="text-sm text-gray-300 truncate">
                      {task.name}
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopyTaskName(task.name);
                    }}
                    className="opacity-0 group-hover/item:opacity-100 p-1 hover:bg-[#3c3c3c] rounded transition-opacity"
                    title="Copy task name"
                  >
                    <VscCopy className="text-gray-400 hover:text-white" />
                  </button>
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    );
  };

  // Calculate line count
  const lineCount = useMemo(() => {
    return fileContent.split("\n").length;
  }, [fileContent]);

  if (isBackendsLoading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    );
  }

  if (backendsError) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <span>Failed to load backends: {backendsError.message}</span>
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
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-[#3e3e3e]">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/")}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors"
            >
              ← Back
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">Task Files</span>
              {selectedBackend && (
                <>
                  <span className="text-gray-500">/</span>
                  <span className="text-sm text-blue-400">
                    {selectedBackend}
                  </span>
                </>
              )}
              {selectedFile && (
                <>
                  <span className="text-gray-500">/</span>
                  <span className="text-sm text-gray-400">
                    {selectedFile.replace(`${selectedBackend}/`, "")}
                  </span>
                </>
              )}
            </div>
            {hasUnsavedChanges && (
              <span className="text-xs text-orange-400">Unsaved changes</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Backend selector */}
            <select
              value={selectedBackend || ""}
              onChange={(e) => handleBackendChange(e.target.value)}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors"
            >
              {backendsData?.backends?.map((backend) => (
                <option key={backend.name} value={backend.name}>
                  {backend.name}
                </option>
              ))}
            </select>
            <button
              onClick={toggleEditorLock}
              className={`px-3 py-1 text-sm text-white border rounded transition-colors ${
                isEditorLocked
                  ? "bg-[#3c3c3c] border-[#454545] hover:bg-[#505050]"
                  : "bg-[#0e639c] border-[#1177bb] hover:bg-[#1177bb]"
              }`}
              title={isEditorLocked ? "Unlock editor to edit" : "Lock editor"}
            >
              {isEditorLocked ? (
                <>
                  <VscLock className="inline-block mr-1" />
                  Locked
                </>
              ) : (
                <>
                  <VscUnlock className="inline-block mr-1" />
                  Unlocked
                </>
              )}
            </button>
            <button
              onClick={handleSave}
              className="px-3 py-1 text-sm text-white bg-[#0e639c] border border-[#1177bb] rounded hover:bg-[#1177bb] transition-colors disabled:opacity-50"
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
                "Save (Ctrl+S)"
              )}
            </button>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <div className="w-64 bg-[#252526] border-r border-[#3e3e3e] flex flex-col">
            {/* Tab buttons */}
            <div className="flex border-b border-[#3e3e3e]">
              <button
                onClick={() => setViewMode("files")}
                className={`flex-1 px-3 py-2 text-xs font-medium flex items-center justify-center gap-1 transition-colors ${
                  viewMode === "files"
                    ? "text-white bg-[#252526] border-b-2 border-blue-500"
                    : "text-gray-500 hover:text-gray-300 hover:bg-[#2a2d2e]"
                }`}
              >
                <VscListTree />
                Files
              </button>
              <button
                onClick={() => setViewMode("tasks")}
                className={`flex-1 px-3 py-2 text-xs font-medium flex items-center justify-center gap-1 transition-colors ${
                  viewMode === "tasks"
                    ? "text-white bg-[#252526] border-b-2 border-blue-500"
                    : "text-gray-500 hover:text-gray-300 hover:bg-[#2a2d2e]"
                }`}
              >
                <VscSymbolClass />
                Tasks
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto py-2">
              {viewMode === null ? (
                <div className="flex items-center justify-center py-4">
                  <span className="loading loading-spinner loading-sm"></span>
                </div>
              ) : viewMode === "files" ? (
                <>
                  <h2 className="text-xs font-bold text-gray-400 mb-1 px-3 tracking-wider">
                    EXPLORER
                  </h2>
                  <div className="text-xs text-gray-500 px-3 mb-2 uppercase tracking-wide">
                    {selectedBackend
                      ? `${selectedBackend} Tasks`
                      : "Select Backend"}
                  </div>
                  {isTreeLoading ? (
                    <div className="flex items-center justify-center py-4">
                      <span className="loading loading-spinner loading-sm"></span>
                    </div>
                  ) : treeError ? (
                    <div className="text-xs text-red-400 px-3">
                      Error loading tree
                    </div>
                  ) : (
                    fileTreeData && renderFileTree(fileTreeData)
                  )}
                </>
              ) : (
                <>
                  <h2 className="text-xs font-bold text-gray-400 mb-1 px-3 tracking-wider">
                    TASK LIST
                  </h2>
                  <div className="text-xs text-gray-500 px-3 mb-2">
                    Click to view source, copy button for Flow Editor
                  </div>
                  {renderTaskList()}
                </>
              )}
            </div>
          </div>

          {/* Editor */}
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
                    language="python"
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
                    }}
                  />
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <SiPython className="text-6xl mx-auto mb-4 text-blue-400/50" />
                  <p className="text-lg mb-2">No file selected</p>
                  <p className="text-sm">
                    Select a Python file from the tree to view or edit
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Status bar */}
        <div className="flex items-center justify-between px-4 py-1 bg-[#007acc] text-white text-xs">
          <div className="flex items-center gap-4">
            {selectedFile && (
              <>
                <span>
                  Ln {cursorPosition.line}, Col {cursorPosition.column}
                </span>
                <span>Python</span>
                <span>UTF-8</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-4">
            {selectedFile && <span>{lineCount} lines</span>}
          </div>
        </div>
      </div>
    </>
  );
}
