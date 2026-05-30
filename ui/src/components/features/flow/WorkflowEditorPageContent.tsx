"use client";

import dynamic from "next/dynamic";
import { useRouter, useParams } from "next/navigation";
import { useState, useEffect, useCallback, useRef } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import type { SaveFlowRequest, ExecuteFlowResponse } from "@/schemas";
import type { AxiosResponse } from "axios";

import { useToast } from "@/components/ui/Toast";

import { useGetCurrentUser } from "@/client/auth/auth";
import { useListChips } from "@/client/chip/chip";
import { useGetExecutionLockStatus, useCancelExecution } from "@/client/execution/execution";
import {
  getFlow,
  saveFlow,
  deleteFlow,
  useExecuteFlow,
  useListFlows,
  listFlowSchedules,
} from "@/client/flow/flow";
import {
  ArrowLeft,
  BookOpen,
  ChevronRight,
  Clock,
  Columns2,
  Command,
  FileCode,
  FilePlus2,
  FolderOpen,
  Info,
  Lock,
  Minus,
  PanelBottom,
  PanelLeft,
  Pencil,
  Play,
  Plus,
  Save,
  Search,
  Settings,
  StopCircle,
  Terminal,
  Trash2,
  WrapText,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";

import { FlowExecuteConfirmModal } from "@/components/features/flow/FlowExecuteConfirmModal";
import { FlowImportsPanel } from "@/components/features/flow/FlowImportsPanel";
import { FlowSchedulePanel } from "@/components/features/flow/FlowSchedulePanel";
import { WorkflowEditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { formatDateTime } from "@/lib/utils/datetime";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const EDITOR_OPTIONS = {
  minimap: { enabled: true, renderCharacters: false, maxColumn: 80, scale: 2 },
  fontSize: 14,
  fontFamily:
    "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, Monaco, 'Courier New', monospace",
  fontLigatures: true,
  lineNumbers: "on" as const,
  automaticLayout: true,
  scrollBeyondLastLine: true,
  padding: { top: 16, bottom: 16 },
  wordWrap: "on" as const,
  folding: true,
  foldingHighlight: true,
  renderLineHighlight: "all" as const,
  cursorStyle: "line" as const,
  cursorBlinking: "smooth" as const,
  cursorSmoothCaretAnimation: "on" as const,
  smoothScrolling: true,
  bracketPairColorization: { enabled: true },
  guides: { bracketPairs: true, indentation: true, highlightActiveIndentation: true },
  renderWhitespace: "selection" as const,
  stickyScroll: { enabled: true },
  suggest: { showKeywords: true, showSnippets: true },
  quickSuggestions: { other: true, comments: false, strings: false },
  parameterHints: { enabled: true },
  matchBrackets: "always" as const,
  occurrencesHighlight: "singleFile" as const,
  selectionHighlight: true,
  linkedEditing: true,
  colorDecorators: true,
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
};

type SidePanel = "explorer" | "properties" | "helpers";

export function WorkflowEditorPageContent() {
  const router = useRouter();
  const params = useParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const name = params.name as string;

  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [flowFunctionName, setFlowFunctionName] = useState("");
  const [username, setUsername] = useState("");
  const [chipId, setChipId] = useState("");
  const [tags, setTags] = useState("");
  const [defaultInterval, setDefaultInterval] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showExecuteConfirm, setShowExecuteConfirm] = useState(false);
  const [lastExecutionId, setLastExecutionId] = useState<string | null>(null);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [activeTab, setActiveTab] = useState<"code" | "helpers">("code");
  const [showPropertiesModal, setShowPropertiesModal] = useState(false);
  const [isEditorLocked, setIsEditorLocked] = useState(true);
  const [originalCode, setOriginalCode] = useState("");
  const [isSplitView, setIsSplitView] = useState(false);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [activeSidePanel, setActiveSidePanel] = useState<SidePanel>("explorer");
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [commandSearch, setCommandSearch] = useState("");
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [fontSize, setFontSize] = useState(14);
  const [selection, setSelection] = useState({ lines: 0, chars: 0 });
  const [isBottomPanelOpen, setIsBottomPanelOpen] = useState(false);
  const [wordWrap, setWordWrap] = useState<"on" | "off">("on");
  const commandInputRef = useRef<HTMLInputElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const editorRef = useRef<any>(null);

  // Fetch current user
  const { data: userData } = useGetCurrentUser();

  // Fetch chips
  const { data: chipsData } = useListChips();

  // Fetch execution lock status (refresh every 5 seconds)
  const { data: lockStatus, isLoading: isLockStatusLoading } = useGetExecutionLockStatus({
    query: {
      refetchInterval: 5000,
    },
  });

  // Fetch all flows for sidebar
  const { data: flowsData } = useListFlows();

  // Fetch schedules for this flow
  const { data: schedulesData } = useQuery({
    queryKey: ["flow-schedules", name],
    queryFn: () => listFlowSchedules(name),
    refetchInterval: 10000,
  });

  const activeSchedules =
    (schedulesData?.data &&
      "schedules" in schedulesData.data &&
      schedulesData.data.schedules?.filter((s) => s.active)) ||
    [];

  const { data, isLoading, error } = useQuery({
    queryKey: ["flow", name],
    queryFn: () => getFlow(name),
  });

  const saveMutation = useMutation({
    mutationFn: (request: SaveFlowRequest) => saveFlow(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", name] });
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      setOriginalCode(code);
      toast.success("Flow saved successfully!");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteFlow(name),
    onSuccess: () => {
      toast.success("Flow deleted successfully!");
      router.push("/workflow");
    },
  });

  const executeMutation = useExecuteFlow({
    mutation: {
      onSuccess: (response: AxiosResponse<ExecuteFlowResponse>) => {
        const execId = response.data.execution_id || null;
        setLastExecutionId(execId);
        toast.success(`Flow execution started! Execution ID: ${execId || "N/A"}`);
      },
    },
  });

  const cancelMutation = useCancelExecution({
    mutation: {
      onSuccess: () => {
        toast.success("Cancellation requested successfully");
        setLastExecutionId(null);
      },
      onError: (error: unknown) => {
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "Failed to cancel execution";
        toast.error(detail);
      },
    },
  });

  const canCancel = !!lastExecutionId && !!lockStatus?.data.lock;

  useEffect(() => {
    if (data?.data) {
      const flow = data.data;
      setDescription(flow.description);
      setCode(flow.code);
      setOriginalCode(flow.code);
      setFlowFunctionName(flow.flow_function_name);

      // Set username from flow or fallback to current user
      const flowUsername = (flow.default_parameters?.username as string) || "";
      setUsername(flowUsername || userData?.data?.username || "");

      // Set chip_id from flow or fallback to latest chip
      setChipId(flow.chip_id);

      setTags(flow.tags?.join(", ") || "");
      const runParams = flow.default_run_parameters as
        | Record<string, { value?: string | number }>
        | undefined;
      setDefaultInterval(
        runParams?.interval?.value != null ? String(runParams.interval.value) : "",
      );
    }
  }, [data, userData, chipsData]);

  // Set default username if not set by flow data
  useEffect(() => {
    if (userData?.data?.username && !username && !data?.data) {
      setUsername(userData.data.username);
    }
  }, [userData, username, data]);

  // Set default chip_id if not set by flow data
  useEffect(() => {
    if (chipsData?.data?.chips && chipsData.data.chips.length > 0 && !chipId && !data?.data) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setChipId(sortedChips[0].chip_id);
    }
  }, [chipsData, chipId, data]);

  const isDirty = code !== originalCode;

  const handleSave = useCallback(() => {
    if (isEditorLocked) return;
    if (!username.trim()) {
      toast.error("Please enter a username");
      return;
    }

    const request: SaveFlowRequest = {
      name,
      description: description.trim(),
      code,
      flow_function_name: flowFunctionName.trim() || undefined,
      chip_id: chipId.trim(),
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      default_parameters: {
        username: username.trim(),
        chip_id: chipId.trim(),
      },
      default_run_parameters: defaultInterval.trim()
        ? {
            interval: {
              value: defaultInterval.trim(),
              value_type: "int",
              unit: "ns",
            },
          }
        : {},
    };

    saveMutation.mutate(request);
  }, [
    isEditorLocked,
    username,
    name,
    description,
    code,
    flowFunctionName,
    chipId,
    tags,
    defaultInterval,
    saveMutation,
    toast,
  ]);

  // Keep a ref to handleSave for Monaco command (avoids stale closure)
  const handleSaveRef = useRef(handleSave);
  useEffect(() => {
    handleSaveRef.current = handleSave;
  }, [handleSave]);

  // Warn before leaving with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + Shift + P → Command Palette
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "p") {
        e.preventDefault();
        setShowCommandPalette(true);
        setCommandSearch("");
      }
      // Ctrl/Cmd + = → Zoom In
      if ((e.metaKey || e.ctrlKey) && (e.key === "=" || e.key === "+")) {
        e.preventDefault();
        setFontSize((prev) => Math.min(prev + 2, 32));
      }
      // Ctrl/Cmd + - → Zoom Out
      if ((e.metaKey || e.ctrlKey) && e.key === "-") {
        e.preventDefault();
        setFontSize((prev) => Math.max(prev - 2, 8));
      }
      // Ctrl/Cmd + 0 → Reset Zoom
      if ((e.metaKey || e.ctrlKey) && e.key === "0") {
        e.preventDefault();
        setFontSize(14);
      }
      // Ctrl/Cmd + ` → Toggle Bottom Panel
      if ((e.metaKey || e.ctrlKey) && e.key === "`") {
        e.preventDefault();
        setIsBottomPanelOpen((prev) => !prev);
      }
      // Escape → close command palette
      if (e.key === "Escape" && showCommandPalette) {
        setShowCommandPalette(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showCommandPalette]);

  // Sync fontSize and wordWrap to editor
  useEffect(() => {
    if (editorRef.current) {
      editorRef.current.updateOptions({ fontSize, wordWrap });
    }
  }, [fontSize, wordWrap]);

  // Focus command palette input when opened
  useEffect(() => {
    if (showCommandPalette) {
      requestAnimationFrame(() => commandInputRef.current?.focus());
    }
  }, [showCommandPalette]);

  // Command palette actions
  const commands = [
    {
      id: "save",
      label: "Save Flow",
      shortcut: "⌘S",
      icon: Save,
      action: () => handleSaveRef.current(),
      enabled: !isEditorLocked,
    },
    {
      id: "toggle-edit",
      label: isEditorLocked ? "Enable Editing" : "Disable Editing",
      shortcut: "",
      icon: Pencil,
      action: () => setIsEditorLocked(!isEditorLocked),
      enabled: true,
    },
    {
      id: "execute",
      label: "Execute Flow",
      shortcut: "",
      icon: Play,
      action: () => setShowExecuteConfirm(true),
      enabled: !lockStatus?.data.lock,
    },
    {
      id: "properties",
      label: "Open Properties",
      shortcut: "",
      icon: Settings,
      action: () => setShowPropertiesModal(true),
      enabled: true,
    },
    {
      id: "split-view",
      label: isSplitView ? "Close Split View" : "Open Split View",
      shortcut: "",
      icon: Columns2,
      action: () => {
        setIsSplitView(!isSplitView);
        if (!isSplitView) setActiveTab("code");
      },
      enabled: true,
    },
    {
      id: "toggle-sidebar",
      label: isSidebarVisible ? "Hide Sidebar" : "Show Sidebar",
      shortcut: "",
      icon: PanelLeft,
      action: () => setIsSidebarVisible((prev) => !prev),
      enabled: true,
    },
    {
      id: "toggle-bottom",
      label: isBottomPanelOpen ? "Hide Panel" : "Show Panel",
      shortcut: "⌘`",
      icon: PanelBottom,
      action: () => setIsBottomPanelOpen((prev) => !prev),
      enabled: true,
    },
    {
      id: "focus-explorer",
      label: "Show Explorer",
      shortcut: "",
      icon: FolderOpen,
      action: () => openSidePanel("explorer"),
      enabled: true,
    },
    {
      id: "focus-properties",
      label: "Show Properties",
      shortcut: "",
      icon: Info,
      action: () => openSidePanel("properties"),
      enabled: true,
    },
    {
      id: "focus-helpers",
      label: "Show Helpers",
      shortcut: "",
      icon: BookOpen,
      action: () => openSidePanel("helpers"),
      enabled: true,
    },
    {
      id: "toggle-minimap",
      label: "Toggle Minimap",
      shortcut: "",
      icon: FileCode,
      action: () => {
        const ed = editorRef.current;
        if (ed) {
          const current = ed.getOption(72);
          ed.updateOptions({ minimap: { enabled: !current?.enabled } });
        }
      },
      enabled: true,
    },
    {
      id: "toggle-wordwrap",
      label: wordWrap === "on" ? "Disable Word Wrap" : "Enable Word Wrap",
      shortcut: "⌥Z",
      icon: WrapText,
      action: () => setWordWrap((prev) => (prev === "on" ? "off" : "on")),
      enabled: true,
    },
    {
      id: "zoom-in",
      label: "Zoom In",
      shortcut: "⌘+",
      icon: ZoomIn,
      action: () => setFontSize((prev) => Math.min(prev + 2, 32)),
      enabled: true,
    },
    {
      id: "zoom-out",
      label: "Zoom Out",
      shortcut: "⌘-",
      icon: ZoomOut,
      action: () => setFontSize((prev) => Math.max(prev - 2, 8)),
      enabled: true,
    },
    {
      id: "zoom-reset",
      label: "Reset Zoom",
      shortcut: "⌘0",
      icon: Minus,
      action: () => setFontSize(14),
      enabled: true,
    },
    {
      id: "go-to-line",
      label: "Go to Line...",
      shortcut: "⌘G",
      icon: ChevronRight,
      action: () => {
        editorRef.current?.focus();
        editorRef.current?.getAction("editor.action.gotoLine")?.run();
      },
      enabled: true,
    },
    {
      id: "find",
      label: "Find and Replace",
      shortcut: "⌘F",
      icon: Search,
      action: () => {
        editorRef.current?.focus();
        editorRef.current?.getAction("actions.find")?.run();
      },
      enabled: true,
    },
    {
      id: "format",
      label: "Format Document",
      shortcut: "⇧⌥F",
      icon: FileCode,
      action: () => {
        editorRef.current?.focus();
        editorRef.current?.getAction("editor.action.formatDocument")?.run();
      },
      enabled: true,
    },
  ];

  const filteredCommands = commands.filter((cmd) =>
    cmd.label.toLowerCase().includes(commandSearch.toLowerCase()),
  );

  useEffect(() => {
    setSelectedCommandIndex(0);
  }, [commandSearch, showCommandPalette]);

  const executeCommand = (cmd: (typeof commands)[0]) => {
    if (!cmd.enabled) return;
    setShowCommandPalette(false);
    cmd.action();
  };

  const filteredFlows =
    flowsData?.data?.flows
      ?.filter((f) =>
        sidebarSearch ? f.name.toLowerCase().includes(sidebarSearch.toLowerCase()) : true,
      )
      .sort((a, b) => a.name.localeCompare(b.name)) ?? [];

  const sidePanelItems = [
    {
      id: "explorer" as const,
      label: "Explorer",
      icon: FolderOpen,
      count: flowsData?.data?.flows?.length ?? 0,
    },
    {
      id: "properties" as const,
      label: "Properties",
      icon: Info,
      count: activeSchedules.length,
    },
    {
      id: "helpers" as const,
      label: "Helpers",
      icon: BookOpen,
    },
  ];

  const openSidePanel = (panel: SidePanel) => {
    setActiveSidePanel(panel);
    setIsSidebarVisible(true);
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEditorMount = useCallback((editor: any, monaco: any) => {
    editorRef.current = editor;
    editor.onDidChangeCursorPosition((e: { position: { lineNumber: number; column: number } }) => {
      setCursorPosition({
        line: e.position.lineNumber,
        column: e.position.column,
      });
    });
    editor.onDidChangeCursorSelection(
      (e: {
        selection: {
          startLineNumber: number;
          endLineNumber: number;
          startColumn: number;
          endColumn: number;
        };
      }) => {
        const sel = e.selection;
        if (sel.startLineNumber === sel.endLineNumber && sel.startColumn === sel.endColumn) {
          setSelection({ lines: 0, chars: 0 });
        } else {
          const model = editor.getModel();
          if (model) {
            const text = model.getValueInRange(sel);
            const lines = sel.endLineNumber - sel.startLineNumber + 1;
            setSelection({ lines, chars: text.length });
          }
        }
      },
    );
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => handleSaveRef.current());
    // Alt+Z → toggle word wrap
    editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyZ, () =>
      setWordWrap((prev) => (prev === "on" ? "off" : "on")),
    );
  }, []);

  const handleDelete = () => {
    deleteMutation.mutate();
  };

  if (isLoading) {
    return <WorkflowEditorPageSkeleton />;
  }

  if (error) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <span>Failed to load flow: {(error as Error)?.message}</span>
        </div>
        <button onClick={() => router.push("/workflow")} className="btn btn-ghost mt-4">
          ← Back to Flows
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="h-screen flex flex-col bg-base-300">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsSidebarVisible((prev) => !prev);
              }}
              className="btn btn-sm btn-ghost max-sm:hidden"
              title={isSidebarVisible ? "Hide sidebar" : "Show sidebar"}
              aria-label={isSidebarVisible ? "Hide sidebar" : "Show sidebar"}
            >
              <PanelLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => router.push("/workflow")}
              className="btn btn-sm btn-ghost"
              disabled={saveMutation.isPending || deleteMutation.isPending}
              title="Back to workflows"
              aria-label="Back to workflows"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-base-content/50">●</span>
              <span className="text-sm font-medium text-base-content truncate">{name}.py</span>
              {activeSchedules.length > 0 && (
                <span
                  className="badge badge-sm badge-info gap-1"
                  title={`${activeSchedules.length} active schedule(s)`}
                >
                  <Clock size={12} />
                  {activeSchedules.length}
                </span>
              )}
            </div>
            {data?.data?.updated_at && (
              <span className="text-xs text-base-content/50 hidden lg:inline">
                Updated: {formatDateTime(data.data.updated_at)}
              </span>
            )}
          </div>
          {/* Desktop action buttons - hidden on mobile, use FAB instead */}
          <div className="hidden sm:flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={() => setShowPropertiesModal(true)}
              className="btn btn-sm btn-ghost"
              title="Properties"
              aria-label="Properties"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={() => setIsEditorLocked(!isEditorLocked)}
              className={`btn btn-sm ${isEditorLocked ? "btn-outline" : "btn-warning"}`}
              title={isEditorLocked ? "Click to edit" : "Currently editing"}
            >
              <Pencil size={16} />
              <span className="ml-1">{isEditorLocked ? "Edit" : "Editing"}</span>
            </button>
            <button
              onClick={() => setShowExecuteConfirm(true)}
              className={`btn btn-sm ${lockStatus?.data.lock ? "btn-disabled" : "btn-success"}`}
              disabled={
                saveMutation.isPending ||
                deleteMutation.isPending ||
                executeMutation.isPending ||
                isLockStatusLoading
              }
              title={
                lockStatus?.data.lock
                  ? "Execution locked - another calibration is running"
                  : "Execute Flow"
              }
            >
              {executeMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : lockStatus?.data.lock ? (
                <Lock size={16} />
              ) : (
                <Play size={16} />
              )}
              <span className="ml-1">{lockStatus?.data.lock ? "Locked" : "Execute"}</span>
            </button>
            {canCancel && (
              <button
                onClick={() =>
                  lastExecutionId && cancelMutation.mutate({ flowRunId: lastExecutionId })
                }
                className="btn btn-sm btn-error btn-outline"
                disabled={cancelMutation.isPending}
                title="Cancel the running execution"
              >
                {cancelMutation.isPending ? (
                  <span className="loading loading-spinner loading-xs"></span>
                ) : (
                  <StopCircle size={16} />
                )}
                <span className="ml-1">Cancel</span>
              </button>
            )}
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="btn btn-sm btn-error"
              disabled={saveMutation.isPending || deleteMutation.isPending}
            >
              <Trash2 size={16} />
              <span className="ml-1">Delete</span>
            </button>
            <button
              onClick={handleSave}
              className={`btn btn-sm ${isEditorLocked ? "btn-outline" : "btn-success"}`}
              disabled={saveMutation.isPending || deleteMutation.isPending || isEditorLocked}
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

        {saveMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>
              Failed to save flow: {(saveMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}

        {deleteMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>
              Failed to delete flow: {(deleteMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}

        {executeMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>
              Failed to execute flow: {(executeMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}

        {/* Main Editor Area */}
        <div className="flex-1 flex overflow-hidden mb-4">
          {/* Activity Bar */}
          <div className="max-sm:hidden flex w-12 flex-col items-center border-r border-base-300 bg-base-200">
            <div className="flex flex-1 flex-col items-center gap-1 py-2">
              {sidePanelItems.map((item) => {
                const Icon = item.icon;
                const isActive = isSidebarVisible && activeSidePanel === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      if (isActive) {
                        setIsSidebarVisible(false);
                      } else {
                        openSidePanel(item.id);
                      }
                    }}
                    className={`btn btn-ghost btn-sm btn-square relative rounded-sm ${
                      isActive ? "bg-base-300 text-primary" : "text-base-content/60"
                    }`}
                    title={item.label}
                    aria-label={item.label}
                  >
                    <Icon size={18} />
                    {item.count ? (
                      <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-[10px] leading-4 text-primary-content">
                        {item.count > 99 ? "99+" : item.count}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
            <div className="flex flex-col items-center gap-1 py-2">
              <button
                type="button"
                onClick={() => {
                  setShowCommandPalette(true);
                  setCommandSearch("");
                }}
                className="btn btn-ghost btn-sm btn-square rounded-sm text-base-content/60"
                title="Command Palette"
                aria-label="Command Palette"
              >
                <Command size={18} />
              </button>
            </div>
          </div>

          {/* Side Panel */}
          {isSidebarVisible && (
            <div className="max-sm:hidden flex w-72 min-w-72 flex-col border-r border-base-300 bg-base-200">
              <div className="flex h-9 items-center justify-between border-b border-base-300 px-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-base-content/60">
                  {sidePanelItems.find((item) => item.id === activeSidePanel)?.label}
                </span>
                <button
                  type="button"
                  onClick={() => setIsSidebarVisible(false)}
                  className="btn btn-ghost btn-xs btn-square"
                  title="Close panel"
                  aria-label="Close panel"
                >
                  <X size={12} />
                </button>
              </div>

              {activeSidePanel === "explorer" && (
                <>
                  <div className="border-b border-base-300 px-2 py-2">
                    <div className="relative">
                      <Search
                        size={12}
                        className="absolute left-2 top-1/2 -translate-y-1/2 text-base-content/40"
                      />
                      <input
                        id="flow-explorer-filter"
                        name="flowExplorerFilter"
                        type="text"
                        placeholder="Filter flows..."
                        className="input input-xs w-full border-base-300 bg-base-300 pl-6 focus:border-primary/50 focus:outline-none"
                        value={sidebarSearch}
                        onChange={(e) => setSidebarSearch(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto py-1">
                    {filteredFlows.map((flow) => (
                      <button
                        key={flow.name}
                        type="button"
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors ${
                          flow.name === name
                            ? "bg-primary/15 text-base-content"
                            : "text-base-content/70 hover:bg-base-300"
                        }`}
                        onClick={() => {
                          if (flow.name !== name) {
                            router.push(`/workflow/${encodeURIComponent(flow.name)}`);
                          }
                        }}
                        title={flow.description || flow.name}
                      >
                        <FileCode
                          size={14}
                          className={`shrink-0 ${flow.name === name ? "text-primary" : "text-info/60"}`}
                        />
                        <span className="min-w-0 flex-1 truncate font-mono text-xs">
                          {flow.name}.py
                        </span>
                        {flow.name === name && isDirty ? (
                          <span
                            className="h-2 w-2 rounded-full bg-warning"
                            title="Unsaved changes"
                          />
                        ) : null}
                      </button>
                    ))}
                    {filteredFlows.length === 0 && (
                      <div className="px-3 py-6 text-center text-xs text-base-content/40">
                        No flows match the filter.
                      </div>
                    )}
                  </div>
                  <div className="border-t border-base-300 p-2">
                    <button
                      type="button"
                      onClick={() => router.push("/workflow/new")}
                      className="btn btn-primary btn-xs w-full gap-1"
                    >
                      <FilePlus2 size={13} />
                      New Flow
                    </button>
                  </div>
                </>
              )}

              {activeSidePanel === "properties" && (
                <div className="flex-1 overflow-y-auto p-3">
                  <div className="mb-3 rounded border border-base-300 bg-base-100 p-3">
                    <div className="flex items-center gap-2">
                      <FileCode size={16} className="text-primary" />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold">{name}.py</div>
                        <div className="truncate text-xs text-base-content/50">
                          {flowFunctionName ? `${flowFunctionName}()` : "No entrypoint set"}
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1">
                      <span className="badge badge-xs badge-outline">{chipId || "No chip"}</span>
                      <span className="badge badge-xs badge-outline">
                        {activeSchedules.length} schedules
                      </span>
                      <span
                        className={`badge badge-xs ${isEditorLocked ? "badge-ghost" : "badge-warning"}`}
                      >
                        {isEditorLocked ? "Read-only" : "Editing"}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <label className="form-control">
                      <span className="label py-1">
                        <span className="label-text text-xs">Description</span>
                      </span>
                      <textarea
                        id="flow-side-description"
                        name="flowDescription"
                        className="textarea textarea-bordered textarea-sm min-h-20"
                        placeholder="Describe your flow..."
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                      />
                    </label>
                    <label className="form-control">
                      <span className="label py-1">
                        <span className="label-text text-xs">Entrypoint Function</span>
                      </span>
                      <input
                        id="flow-side-entrypoint"
                        name="flowEntrypoint"
                        type="text"
                        placeholder="simple_flow"
                        className="input input-bordered input-sm"
                        value={flowFunctionName}
                        onChange={(e) => setFlowFunctionName(e.target.value)}
                      />
                    </label>
                    <label className="form-control">
                      <span className="label py-1">
                        <span className="label-text text-xs">Username *</span>
                      </span>
                      <input
                        id="flow-side-username"
                        name="flowUsername"
                        type="text"
                        placeholder="your_username"
                        className="input input-bordered input-sm"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                      />
                    </label>
                    <label className="form-control">
                      <span className="label py-1">
                        <span className="label-text text-xs">Chip ID *</span>
                      </span>
                      <input
                        id="flow-side-chip-id"
                        name="flowChipId"
                        type="text"
                        placeholder="64Qv3"
                        className="input input-bordered input-sm"
                        value={chipId}
                        onChange={(e) => setChipId(e.target.value)}
                      />
                    </label>
                    <label className="form-control">
                      <span className="label py-1">
                        <span className="label-text text-xs">Tags</span>
                      </span>
                      <input
                        id="flow-side-tags"
                        name="flowTags"
                        type="text"
                        placeholder="tag1, tag2, tag3"
                        className="input input-bordered input-sm"
                        value={tags}
                        onChange={(e) => setTags(e.target.value)}
                      />
                    </label>
                    <label className="form-control">
                      <span className="label py-1">
                        <span className="label-text text-xs">Default Interval (ns)</span>
                      </span>
                      <input
                        id="flow-side-default-interval"
                        name="flowDefaultInterval"
                        type="text"
                        placeholder="150 * 1024"
                        className="input input-bordered input-sm"
                        value={defaultInterval}
                        onChange={(e) => setDefaultInterval(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => setShowPropertiesModal(true)}
                      className="btn btn-outline btn-xs w-full gap-1"
                    >
                      <Settings size={13} />
                      Advanced Settings
                    </button>
                  </div>
                </div>
              )}

              {activeSidePanel === "helpers" && (
                <div className="flex-1 overflow-hidden">
                  <FlowImportsPanel compact />
                </div>
              )}
            </div>
          )}
          {/* Editor with Tab Switcher */}
          <div className="flex-1 flex flex-col">
            {/* Tab Bar */}
            <div className="flex items-end bg-base-200 border-b border-base-300 h-9">
              <button
                type="button"
                onClick={() => setActiveTab("code")}
                className={`h-full px-4 text-sm font-medium flex items-center gap-2 border-r border-base-300 transition-colors relative ${
                  activeTab === "code" || isSplitView
                    ? "bg-base-300 text-base-content"
                    : "bg-base-200 text-base-content/50 hover:text-base-content/80"
                }`}
              >
                {(activeTab === "code" || isSplitView) && (
                  <span className="absolute top-0 left-0 right-0 h-0.5 bg-primary" />
                )}
                <span className="text-info">py</span>
                {name}.py
                {isDirty && (
                  <span
                    className="w-2 h-2 rounded-full bg-base-content/60"
                    title="Unsaved changes"
                  />
                )}
              </button>
              {!isSplitView && (
                <button
                  type="button"
                  onClick={() => setActiveTab("helpers")}
                  className={`h-full px-4 text-sm font-medium flex items-center gap-2 border-r border-base-300 transition-colors relative ${
                    activeTab === "helpers"
                      ? "bg-base-300 text-base-content"
                      : "bg-base-200 text-base-content/50 hover:text-base-content/80"
                  }`}
                >
                  {activeTab === "helpers" && (
                    <span className="absolute top-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                  <BookOpen size={14} className="text-secondary" />
                  Helpers
                </button>
              )}
              {/* Split View Toggle */}
              <div className="ml-auto flex items-center px-2 h-full">
                <button
                  type="button"
                  onClick={() => {
                    setIsSplitView(!isSplitView);
                    if (!isSplitView) setActiveTab("code");
                  }}
                  className={`btn btn-xs btn-ghost ${isSplitView ? "text-primary" : "text-base-content/50"}`}
                  title={isSplitView ? "Single view" : "Split view"}
                >
                  <Columns2 size={14} />
                </button>
              </div>
            </div>

            {/* Breadcrumbs */}
            <div className="flex items-center gap-1 px-3 py-1 bg-base-300/50 border-b border-base-300 text-xs text-base-content/50">
              <span
                className="hover:text-base-content cursor-pointer"
                onClick={() => router.push("/workflow")}
              >
                workflows
              </span>
              <ChevronRight size={10} />
              <span
                className="hover:text-base-content cursor-pointer"
                onClick={() => setShowPropertiesModal(true)}
              >
                {chipId || "chip"}
              </span>
              <ChevronRight size={10} />
              <span className="text-base-content/80">{name}.py</span>
              {flowFunctionName && (
                <>
                  <ChevronRight size={10} />
                  <span className="text-base-content/60">{flowFunctionName}()</span>
                </>
              )}
            </div>

            {/* Tab Content */}
            {isSplitView ? (
              <PanelGroup orientation="horizontal" style={{ flex: 1, overflow: "hidden" }}>
                <Panel defaultSize="60%" minSize="20%" style={{ overflow: "hidden" }}>
                  <Editor
                    height="100%"
                    language="python"
                    theme="vs-dark"
                    value={code}
                    onChange={(value) => setCode(value || "")}
                    onMount={handleEditorMount}
                    options={{
                      ...EDITOR_OPTIONS,
                      fontSize,
                      wordWrap,
                      readOnly: isEditorLocked,
                      domReadOnly: isEditorLocked,
                    }}
                  />
                </Panel>
                <PanelResizeHandle className="w-1 bg-base-300 hover:bg-primary/50 transition-colors cursor-col-resize" />
                <Panel defaultSize="40%" minSize="15%" style={{ overflow: "hidden" }}>
                  <FlowImportsPanel />
                </Panel>
              </PanelGroup>
            ) : activeTab === "code" ? (
              <Editor
                height="100%"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(value) => setCode(value || "")}
                onMount={handleEditorMount}
                options={{
                  ...EDITOR_OPTIONS,
                  fontSize,
                  wordWrap,
                  readOnly: isEditorLocked,
                  domReadOnly: isEditorLocked,
                }}
              />
            ) : (
              <FlowImportsPanel />
            )}
          </div>
        </div>

        {/* Bottom Panel */}
        {isBottomPanelOpen && (
          <div
            className="flex flex-col border-t border-base-300 bg-base-200"
            style={{ height: "200px" }}
          >
            <div className="flex items-center justify-between px-3 py-1 border-b border-base-300">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className="text-xs font-medium text-base-content flex items-center gap-1.5 px-2 py-0.5 bg-base-300 rounded"
                >
                  <Terminal size={12} />
                  Output
                </button>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setIsBottomPanelOpen(false)}
                  className="btn btn-ghost btn-xs btn-square"
                >
                  <X size={12} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-base-content/70 bg-base-300">
              {lastExecutionId ? (
                <div className="space-y-1">
                  <div className="text-base-content/40">
                    <span className="text-info">[info]</span> Flow: {name}
                  </div>
                  <div className="text-base-content/40">
                    <span className="text-info">[info]</span> Execution ID: {lastExecutionId}
                  </div>
                  <div className="text-base-content/40">
                    <span className="text-info">[info]</span> Chip: {chipId} | User: {username}
                  </div>
                  {lockStatus?.data.lock ? (
                    <div>
                      <span className="text-warning">[running]</span> Execution in progress...
                    </div>
                  ) : (
                    <div>
                      <span className="text-success">[done]</span> Execution completed.
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-base-content/30">
                  <div className="text-center">
                    <Terminal size={24} className="mx-auto mb-2 opacity-50" />
                    <div>No execution output yet.</div>
                    <div className="text-xs mt-1">Execute a flow to see output here.</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Status Bar */}
        <div className="flex items-center justify-between px-2 py-1 bg-primary text-primary-content text-xs select-none">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => {
                editorRef.current?.focus();
                editorRef.current?.getAction("editor.action.gotoLine")?.run();
              }}
              className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer"
              title="Go to Line (⌘G)"
            >
              Ln {cursorPosition.line}, Col {cursorPosition.column}
            </button>
            {selection.chars > 0 && (
              <span className="px-1.5 py-0.5 bg-primary-content/10 rounded">
                {selection.lines > 1 ? `${selection.lines} lines, ` : ""}
                {selection.chars} selected
              </span>
            )}
            <span className="px-1.5 py-0.5">Spaces: 4</span>
            <span className="px-1.5 py-0.5">Python</span>
            <span className="px-1.5 py-0.5">UTF-8</span>
            {isDirty && <span className="px-1.5 py-0.5 opacity-80">● Modified</span>}
          </div>
          <div className="flex items-center gap-1">
            <span className="px-1.5 py-0.5">{code.split("\n").length} lines</span>
            <button
              type="button"
              onClick={() => setWordWrap((prev) => (prev === "on" ? "off" : "on"))}
              className={`hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1 ${wordWrap === "off" ? "opacity-50" : ""}`}
              title="Toggle Word Wrap (⌥Z)"
            >
              <WrapText size={10} />
            </button>
            <button
              type="button"
              onClick={() => setIsBottomPanelOpen((prev) => !prev)}
              className={`hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1 ${isBottomPanelOpen ? "" : "opacity-60"}`}
              title="Toggle Panel (⌘`)"
            >
              <Terminal size={10} />
            </button>
            {fontSize !== 14 && (
              <button
                type="button"
                onClick={() => setFontSize(14)}
                className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer"
                title="Reset Zoom (⌘0)"
              >
                {Math.round((fontSize / 14) * 100)}%
              </button>
            )}
            {isEditorLocked ? (
              <button
                type="button"
                onClick={() => setIsEditorLocked(false)}
                className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1 opacity-80"
                title="Click to enable editing"
              >
                <Lock size={10} /> Read-only
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setIsEditorLocked(true)}
                className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1"
                title="Click to lock editor"
              >
                <Pencil size={10} /> Editing
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setShowCommandPalette(true);
                setCommandSearch("");
              }}
              className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1 opacity-70 hover:opacity-100"
              title="Command Palette"
            >
              <Command size={10} />
              <span>⌘⇧P</span>
            </button>
          </div>
        </div>

        {/* Command Palette */}
        {showCommandPalette && (
          <div
            className="fixed inset-0 z-50 flex justify-center pt-[15vh]"
            onClick={() => setShowCommandPalette(false)}
          >
            <div className="absolute inset-0 bg-black/50" />
            <div
              className="relative w-full max-w-lg h-fit bg-base-200 rounded-lg shadow-2xl border border-base-300 overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-2 px-3 py-2 border-b border-base-300">
                <Search size={14} className="text-base-content/40 shrink-0" />
                <input
                  id="workflow-command-palette-search"
                  name="workflowCommandPaletteSearch"
                  ref={commandInputRef}
                  type="text"
                  placeholder="Type a command..."
                  className="flex-1 bg-transparent text-sm text-base-content outline-none placeholder:text-base-content/40"
                  value={commandSearch}
                  onChange={(e) => setCommandSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      if (filteredCommands.length === 0) return;
                      setSelectedCommandIndex((prev) =>
                        Math.min(prev + 1, filteredCommands.length - 1),
                      );
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      if (filteredCommands.length === 0) return;
                      setSelectedCommandIndex((prev) => Math.max(prev - 1, 0));
                    }
                    if (e.key === "Enter" && filteredCommands.length > 0) {
                      executeCommand(filteredCommands[selectedCommandIndex] || filteredCommands[0]);
                    }
                    if (e.key === "Escape") {
                      setShowCommandPalette(false);
                    }
                  }}
                />
              </div>
              <div className="max-h-64 overflow-y-auto py-1">
                {filteredCommands.map((cmd) => (
                  <button
                    key={cmd.id}
                    type="button"
                    onClick={() => executeCommand(cmd)}
                    disabled={!cmd.enabled}
                    onMouseEnter={() =>
                      setSelectedCommandIndex(
                        filteredCommands.findIndex((command) => command.id === cmd.id),
                      )
                    }
                    className={`w-full flex items-center gap-3 px-3 py-2 text-sm text-left transition-colors ${
                      cmd.enabled
                        ? "text-base-content hover:bg-base-300 cursor-pointer"
                        : "text-base-content/30 cursor-not-allowed"
                    } ${
                      filteredCommands[selectedCommandIndex]?.id === cmd.id ? "bg-base-300" : ""
                    }`}
                  >
                    <cmd.icon size={14} className="shrink-0 opacity-60" />
                    <span className="flex-1">{cmd.label}</span>
                    {cmd.shortcut && (
                      <kbd className="text-xs text-base-content/40 bg-base-300 px-1.5 py-0.5 rounded">
                        {cmd.shortcut}
                      </kbd>
                    )}
                  </button>
                ))}
                {filteredCommands.length === 0 && (
                  <div className="px-3 py-4 text-sm text-base-content/40 text-center">
                    No matching commands
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Mobile FAB / Speed Dial - only visible on mobile */}
        <div className="fab fixed bottom-20 right-4 z-30 sm:hidden">
          <div tabIndex={0} role="button" className="btn btn-circle btn-primary shadow-lg">
            <Plus size={20} />
          </div>
          {/* Properties Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Properties
            </span>
            <button
              onClick={() => setShowPropertiesModal(true)}
              className="btn btn-circle btn-outline bg-base-100 shadow-lg"
            >
              <Settings size={20} />
            </button>
          </div>
          {/* Editor Lock Toggle Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              {isEditorLocked ? "Edit" : "Editing"}
            </span>
            <button
              onClick={() => setIsEditorLocked(!isEditorLocked)}
              className={`btn btn-circle shadow-lg ${isEditorLocked ? "btn-outline bg-base-100" : "btn-warning"}`}
            >
              <Pencil size={20} />
            </button>
          </div>
          {/* Execute Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              {lockStatus?.data.lock ? "Locked" : "Execute"}
            </span>
            <button
              onClick={() => setShowExecuteConfirm(true)}
              className={`btn btn-circle shadow-lg ${
                lockStatus?.data.lock ? "btn-disabled" : "btn-success"
              }`}
              disabled={
                saveMutation.isPending ||
                deleteMutation.isPending ||
                executeMutation.isPending ||
                isLockStatusLoading
              }
            >
              {executeMutation.isPending ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : lockStatus?.data.lock ? (
                <Lock size={20} />
              ) : (
                <Play size={20} />
              )}
            </button>
          </div>
          {/* Cancel Button (mobile) */}
          {canCancel && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
                Cancel
              </span>
              <button
                onClick={() =>
                  lastExecutionId && cancelMutation.mutate({ flowRunId: lastExecutionId })
                }
                className="btn btn-circle btn-error btn-outline shadow-lg"
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm"></span>
                ) : (
                  <StopCircle size={20} />
                )}
              </button>
            </div>
          )}
          {/* Save Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">Save</span>
            <button
              onClick={handleSave}
              className={`btn btn-circle shadow-lg ${isEditorLocked ? "btn-outline bg-base-100" : "btn-success"}`}
              disabled={saveMutation.isPending || deleteMutation.isPending || isEditorLocked}
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : (
                <Save size={20} />
              )}
            </button>
          </div>
          {/* Delete Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">Delete</span>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="btn btn-circle btn-error shadow-lg"
              disabled={saveMutation.isPending || deleteMutation.isPending}
            >
              <Trash2 size={20} />
            </button>
          </div>
        </div>

        {/* Properties Modal */}
        {showPropertiesModal && (
          <div className="modal modal-open">
            <div className="modal-backdrop" onClick={() => setShowPropertiesModal(false)} />
            <div className="modal-box max-w-md max-h-[calc(100vh-8rem)]">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-bold text-lg">Properties</h3>
                <button
                  onClick={() => setShowPropertiesModal(false)}
                  className="btn btn-ghost btn-sm btn-square"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-4">
                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-name" className="label">
                    <span className="label-text text-xs">Flow Name</span>
                  </label>
                  <input
                    id="flow-name"
                    type="text"
                    className="input input-bordered input-sm"
                    value={name}
                    disabled
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">Cannot be changed</span>
                  </label>
                </div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-description" className="label">
                    <span className="label-text text-xs">Description</span>
                  </label>
                  <textarea
                    id="flow-description"
                    className="textarea textarea-bordered textarea-sm"
                    placeholder="Describe your flow..."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                  />
                </div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-entrypoint" className="label">
                    <span className="label-text text-xs">Entrypoint Function</span>
                  </label>
                  <input
                    id="flow-entrypoint"
                    type="text"
                    placeholder="simple_flow"
                    className="input input-bordered input-sm"
                    value={flowFunctionName}
                    onChange={(e) => setFlowFunctionName(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      The @flow decorated function name in your code
                    </span>
                  </label>
                </div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-username" className="label">
                    <span className="label-text text-xs">Username *</span>
                  </label>
                  <input
                    id="flow-username"
                    type="text"
                    placeholder="your_username"
                    className="input input-bordered input-sm"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-chip-id" className="label">
                    <span className="label-text text-xs">Chip ID *</span>
                  </label>
                  <input
                    id="flow-chip-id"
                    type="text"
                    placeholder="64Qv3"
                    className="input input-bordered input-sm"
                    value={chipId}
                    onChange={(e) => setChipId(e.target.value)}
                  />
                </div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-tags" className="label">
                    <span className="label-text text-xs">Tags</span>
                  </label>
                  <input
                    id="flow-tags"
                    type="text"
                    placeholder="tag1, tag2, tag3"
                    className="input input-bordered input-sm"
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">Comma-separated</span>
                  </label>
                </div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-interval" className="label">
                    <span className="label-text text-xs">Default Interval (ns)</span>
                  </label>
                  <input
                    id="flow-interval"
                    type="text"
                    placeholder="150 * 1024"
                    className="input input-bordered input-sm"
                    value={defaultInterval}
                    onChange={(e) => setDefaultInterval(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      Default: 150 * 1024 (153600 ns). Expression format supported.
                    </span>
                  </label>
                </div>

                <div className="divider my-2"></div>

                <div className="form-control flex flex-col gap-1">
                  <label htmlFor="flow-file-path" className="label">
                    <span className="label-text text-xs">File Path</span>
                  </label>
                  <input
                    id="flow-file-path"
                    type="text"
                    className="input input-bordered input-sm text-xs"
                    value={data?.data?.file_path || ""}
                    disabled
                  />
                </div>

                {/* Flow Schedules Section */}
                <div className="divider my-2"></div>
                <FlowSchedulePanel flowName={name} />
              </div>

              <div className="modal-action">
                <button onClick={() => setShowPropertiesModal(false)} className="btn">
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="modal modal-open">
            <div className="modal-box">
              <h3 className="font-bold text-lg">Delete Flow</h3>
              <p className="py-4">
                Are you sure you want to delete <strong>{name}</strong>? This action cannot be
                undone.
              </p>
              <div className="modal-action">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="btn btn-ghost"
                  disabled={deleteMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowDeleteConfirm(false);
                    handleDelete();
                  }}
                  className="btn btn-error"
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? (
                    <span className="loading loading-spinner"></span>
                  ) : (
                    "Delete"
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Execute Confirmation Modal */}
        {showExecuteConfirm && (
          <FlowExecuteConfirmModal
            flowName={name}
            username={username}
            chipId={chipId}
            description={description}
            tags={tags}
            isLocked={lockStatus?.data.lock ?? false}
            isLockStatusLoading={isLockStatusLoading}
            onConfirm={() => {
              setShowExecuteConfirm(false);
              executeMutation.mutate({
                name,
                data: {
                  parameters: {
                    username: username,
                    chip_id: chipId,
                  },
                },
              });
            }}
            onClose={() => setShowExecuteConfirm(false)}
          />
        )}
      </div>
    </>
  );
}
