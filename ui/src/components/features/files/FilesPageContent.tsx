"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useMemo } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  Check,
  Database,
  GitCompareArrows,
  GitPullRequestArrow,
  PanelLeft,
  Pencil,
  Plus,
  Save,
} from "lucide-react";

import { EditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { PierreFileTree } from "@/components/ui/PierreFileTree";
import { FileDiffReviewDialog } from "@/components/ui/FileDiffReviewDialog";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import { type FileWorkspace, workspaceQueryKeys } from "@/lib/fileWorkspace";
import { getApiErrorMessage } from "@/lib/utils/apiError";

import { FilesBulkDownloadButton } from "./FilesBulkDownloadButton";
import { GitWorkspaceToolbar, PullRequestBanner } from "./GitWorkspaceToolbar";
import { useGitWorkspace } from "./useGitWorkspace";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

// Helper to check if file is a params YAML that can be imported
function parseParamsFilePath(path: string): { chipId: string; paramName: string } | null {
  // Match pattern: config/qubex/{chip_id}/params/{param_name}.yaml
  const match = path.match(/^config\/qubex\/([^/]+)\/params\/([^/]+)\.ya?ml$/);
  if (match) {
    return { chipId: match[1], paramName: match[2] };
  }
  return null;
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

/**
 * Tree editor of one git workspace (the Qubex config or the knowledge repo):
 * browse, edit with Monaco, review the saved diff, pull, and open a PR.
 * `?path=` opens a file on load.
 */
export function FilesPageContent({ workspace }: { workspace: FileWorkspace }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [selectedFile, setSelectedFile] = useState<string | null>(
    () => searchParams.get("path") || null,
  );
  const [fileContent, setFileContent] = useState("");
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [pendingFilePath, setPendingFilePath] = useState<string | null>(null);
  const [pullConfirmationOpen, setPullConfirmationOpen] = useState(false);
  const [isEditorLocked, setIsEditorLocked] = useState(true);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [isDiffPreviewOpen, setIsDiffPreviewOpen] = useState(false);
  const [importResult, setImportResult] = useState<SeedImportResponse | null>(null);

  // Check if selected file is a params YAML that can be imported
  const paramsFileInfo = useMemo(() => {
    if (!selectedFile || !workspace.seedImport) return null;
    return parseParamsFilePath(selectedFile);
  }, [selectedFile, workspace.seedImport]);

  const {
    data: fileTreeData,
    isLoading: isTreeLoading,
    error: treeError,
  } = useQuery({
    queryKey: workspaceQueryKeys.tree(workspace),
    queryFn: workspace.getTree,
  });

  const { data: savedFileContent, isLoading: isContentLoading } = useQuery({
    queryKey: workspaceQueryKeys.content(workspace, selectedFile),
    queryFn: () => workspace.getContent(selectedFile || ""),
    enabled: !!selectedFile,
  });

  const hasSavedChanges = savedFileContent?.is_saved_change === true;

  const git = useGitWorkspace(workspace, { onPulled: () => setPullConfirmationOpen(false) });

  const saveMutation = useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      workspace.saveContent(path, content),
    onSuccess: () => {
      setHasUnsavedChanges(false);
      setIsDiffPreviewOpen(false);
      toast.success("File saved successfully!");
      queryClient.invalidateQueries({
        queryKey: workspaceQueryKeys.content(workspace, selectedFile),
      });
      git.refetchStatus();
    },
    onError: (error: Error) => {
      toast.error(`Failed to save file: ${getApiErrorMessage(error, "Unknown error")}`);
    },
  });

  // Seed import mutation
  const importMutation = useMutation({
    mutationFn: async ({ chipId, paramName }: { chipId: string; paramName: string }) => {
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
        throw new Error(errorData.detail || `Import failed: ${response.status}`);
      }
      return response.json() as Promise<SeedImportResponse>;
    },
    onSuccess: (data) => {
      setImportResult(data);
      toast.success(`Imported ${data.imported_count} parameters to QDash`);
    },
    onError: (error: Error) => {
      toast.error(`Import failed: ${getApiErrorMessage(error, "Unknown error")}`);
    },
  });

  useEffect(() => {
    if (savedFileContent?.content !== undefined && savedFileContent?.content !== null) {
      setFileContent(String(savedFileContent.content));
      setHasUnsavedChanges(false);
    }
  }, [savedFileContent]);

  const selectFile = (path: string) => {
    setSelectedFile(path);
    setHasUnsavedChanges(false);
    setIsEditorLocked(true); // Lock editor when opening new file
    setImportResult(null); // Clear import result when selecting new file
  };

  const handleFileSelect = (path: string) => {
    if (hasUnsavedChanges) {
      setPendingFilePath(path);
      return;
    }
    selectFile(path);
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
      setPullConfirmationOpen(true);
      return;
    }
    git.pull();
  };

  const handlePush = () => git.push();

  const handleContentChange = (value: string | undefined) => {
    setFileContent(value || "");
    // Only flag unsaved changes when the editor is unlocked (the user can actually type).
    // @monaco-editor/react fires onChange for programmatic setValue() updates even while
    // read-only, so loading/switching a file would otherwise mark it dirty by mistake.
    if (!isEditorLocked) {
      setHasUnsavedChanges(true);
    }
  };

  const getLanguage = (filename: string): string => {
    if (filename.endsWith(".yaml") || filename.endsWith(".yml")) return "yaml";
    if (filename.endsWith(".json")) return "json";
    if (filename.endsWith(".toml")) return "toml";
    if (filename.endsWith(".md")) return "markdown";
    if (filename.endsWith(".py")) return "python";
    return "plaintext";
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
      {selectedFile && (
        <FileDiffReviewDialog
          filename={selectedFile}
          newContent={String(savedFileContent?.content ?? "")}
          oldContent={String(savedFileContent?.base_content ?? "")}
          onClose={() => setIsDiffPreviewOpen(false)}
          open={isDiffPreviewOpen}
        />
      )}
      <div className="h-[calc(100dvh-4rem)] flex flex-col bg-base-300">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0">
            <div className="flex items-center gap-1 sm:gap-2 min-w-0 overflow-hidden">
              <span className="text-sm font-medium flex-shrink-0 hidden sm:inline">
                {workspace.title}
              </span>
              {selectedFile && (
                <>
                  <span className="text-base-content/50 hidden sm:inline">/</span>
                  <span className="text-sm text-base-content/70 truncate">{selectedFile}</span>
                </>
              )}
            </div>
            {hasUnsavedChanges && <span className="text-xs text-warning flex-shrink-0">●</span>}
          </div>
          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 overflow-x-auto">
            {workspace.bulkDownload && (
              <FilesBulkDownloadButton
                disabled={!fileTreeData?.length}
                onError={(message) => toast.error(message)}
              />
            )}
            <button
              onClick={toggleEditorLock}
              className={`btn btn-sm hidden sm:flex ${isEditorLocked ? "btn-outline" : "btn-warning"}`}
              title={isEditorLocked ? "Click to edit" : "Currently editing"}
            >
              <Pencil size={16} />
              <span className="ml-1">{isEditorLocked ? "Edit" : "Editing"}</span>
            </button>
            <GitWorkspaceToolbar
              status={git.status}
              onPull={handlePull}
              onPush={handlePush}
              isPulling={git.isPulling}
              isPushing={git.isPushing}
              hideOnMobile
              pushTitle={`Create a pull request with ${workspace.key} changes`}
            />
            <button
              onClick={handleSave}
              className={`btn btn-sm hidden sm:flex ${isEditorLocked ? "btn-outline" : "btn-success"}`}
              disabled={
                !selectedFile || !hasUnsavedChanges || saveMutation.isPending || isEditorLocked
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
            <button
              onClick={() => setIsDiffPreviewOpen(true)}
              className="btn btn-sm btn-ghost hidden sm:flex"
              disabled={!selectedFile || !hasSavedChanges || hasUnsavedChanges}
              title={hasUnsavedChanges ? "Save changes before review" : "Review saved changes"}
            >
              <GitCompareArrows size={16} />
              <span className="ml-1">Review</span>
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

        <PullRequestBanner pr={git.prResult} onDismiss={git.dismissPr} />

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
              <button onClick={() => setImportResult(null)} className="btn btn-xs btn-ghost">
                ✕
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <div className="bg-base-100 border-r border-base-300 flex flex-shrink-0">
            {/* Collapsible panel */}
            <div
              className={`${isSidebarVisible ? "w-48 sm:w-64" : "w-0"} flex flex-col transition-all duration-200 overflow-hidden`}
            >
              <div className="flex min-h-0 flex-1 flex-col py-2">
                <h2 className="text-xs font-bold text-base-content/60 mb-1 px-3 tracking-wider">
                  EXPLORER
                </h2>
                <div className="text-xs text-base-content/50 px-3 mb-2 uppercase tracking-wide">
                  {workspace.title}
                </div>
                {fileTreeData && (
                  <div className="min-h-0 flex-1">
                    <PierreFileTree
                      nodes={fileTreeData}
                      onSelectFile={handleFileSelect}
                      selectedPath={selectedFile}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Toggle button - always visible */}
            <div className="flex flex-col bg-transparent">
              <button
                onClick={() => setIsSidebarVisible(!isSidebarVisible)}
                className="px-2 py-2 text-base-content/50 hover:text-base-content hover:bg-base-200 transition-colors"
                aria-label={isSidebarVisible ? "Hide sidebar" : "Show sidebar"}
                title={isSidebarVisible ? "Hide sidebar" : "Show sidebar"}
              >
                <PanelLeft size={16} />
              </button>
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

                      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
                        if (!isEditorLocked) {
                          handleSave();
                        }
                      });
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
            {selectedFile && <span>{fileContent.split("\n").length} lines</span>}
          </div>
        </div>

        {/* Mobile FAB */}
        <div className="fab fixed bottom-20 right-4 z-30 sm:hidden">
          <div tabIndex={0} role="button" className="btn btn-circle btn-primary shadow-lg">
            <Plus size={20} />
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
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">Pull</span>
            <button
              onClick={handlePull}
              className={`btn btn-circle shadow-lg ${git.status?.has_remote_updates ? "btn-warning" : "btn-info"}`}
              disabled={git.isPulling}
            >
              {git.isPulling ? (
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
              disabled={git.isPushing}
            >
              {git.isPushing ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <GitPullRequestArrow size={20} />
              )}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">Save</span>
            <button
              onClick={handleSave}
              className={`btn btn-circle shadow-lg ${isEditorLocked ? "btn-outline bg-base-100" : "btn-success"}`}
              disabled={
                !selectedFile || !hasUnsavedChanges || saveMutation.isPending || isEditorLocked
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
      <ConfirmDialog
        open={pendingFilePath !== null}
        title="Discard unsaved changes?"
        description="Your unsaved changes will be lost when you open another file."
        confirmLabel="Discard and open"
        onConfirm={() => {
          if (pendingFilePath) selectFile(pendingFilePath);
          setPendingFilePath(null);
        }}
        onOpenChange={(open) => !open && setPendingFilePath(null)}
        destructive
      />
      <ConfirmDialog
        open={pullConfirmationOpen}
        title="Discard changes and pull?"
        description="Git pull will overwrite your unsaved changes."
        confirmLabel="Discard and pull"
        onConfirm={() => git.pull()}
        onOpenChange={setPullConfirmationOpen}
        pending={git.isPulling}
        destructive
      />
    </>
  );
}
