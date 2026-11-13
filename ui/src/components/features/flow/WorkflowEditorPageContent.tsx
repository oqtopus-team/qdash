"use client";

import type { OnMount } from "@monaco-editor/react";
import dynamic from "next/dynamic";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { useState, useEffect, useCallback, useRef } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { ExecuteFlowRequest, ExecuteFlowResponse, ExecutionResponseDetail } from "@/schemas";
import type { AxiosResponse } from "axios";

import { useChatDock } from "@/contexts/ChatDockContext";
import { useProject } from "@/contexts/ProjectContext";
import { useExecutionAvailability } from "@/hooks/useExecutionAvailability";
import { useFlowExecutionPlan } from "@/hooks/useFlowExecutionPlan";
import { useToast } from "@/components/ui/Toast";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/Command";

import { useGetCurrentUser } from "@/client/auth/auth";
import {
  getGetExecutionLockStatusQueryKey,
  useCancelExecution,
  useGetExecution,
  useGetExecutionLockStatus,
} from "@/client/execution/execution";
import {
  deleteFlow,
  executeFlow,
  getListFlowsQueryKey,
  useListFlows,
  listFlowSchedules,
} from "@/client/flow/flow";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  CircleHelp,
  Clock,
  Columns2,
  Command as CommandIcon,
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

import {
  useFirstCalibrationJourney,
  type JourneyContext,
} from "@/components/features/first-calibration/useFirstCalibrationJourney";
import { executionHref } from "@/components/features/first-calibration/journeyProgress";
import { FlowExecuteConfirmModal } from "@/components/features/flow/FlowExecuteConfirmModal";
import { FlowExplorer } from "@/components/features/flow/FlowExplorer";
import { FlowSchedulePanel } from "@/components/features/flow/FlowSchedulePanel";
import { type FlowDocument, useFlowDocument } from "@/components/features/flow/useFlowDocument";
import { WorkflowExecutionHelpDialog } from "@/components/features/flow/WorkflowExecutionHelpDialog";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { WorkflowEditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { isExecutionTerminal } from "@/lib/executionStatus";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";
import { monoFontFamily, remeasureMonacoFontsWhenLoaded } from "@/lib/fonts";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const EDITOR_OPTIONS = {
  minimap: { enabled: true, renderCharacters: false, maxColumn: 80, scale: 2 },
  fontSize: 14,
  fontFamily: monoFontFamily,
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
  guides: {
    bracketPairs: true,
    indentation: true,
    highlightActiveIndentation: true,
  },
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

type SidePanel = "explorer" | "properties";
/** The left pane shows the page's workflow (the URL); the right pane, in split view, another. */
type Pane = "primary" | "secondary";

/** Workflows whose unsaved drafts an action would drop, and the action to run once confirmed. */
interface DiscardPrompt {
  names: string[];
  action: () => void;
}

const PANE_LABEL: Record<Pane, string> = { primary: "Left", secondary: "Right" };

export function WorkflowEditorPageContent() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  // `?space=<creator>`: the Workflow page opened this editor to browse that creator's tree.
  const initialSpace = searchParams.get("space");
  // `?split=<name>`: the right pane's workflow, carried over when the left pane opens another.
  const initialSplit = searchParams.get("split");
  const queryClient = useQueryClient();
  const toast = useToast();
  const routeName = params.name as string;
  const { capture: captureJourneyContext } = useFirstCalibrationJourney();

  const [deleteTarget, setDeleteTarget] = useState<Pane | null>(null);
  const [executeTarget, setExecuteTarget] = useState<Pane | null>(null);
  const [lastExecutionId, setLastExecutionId] = useState<string | null>(null);
  const [lastFlowRunId, setLastFlowRunId] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<{
    flowName: string;
    chipId: string;
    username: string;
  } | null>(null);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [showPropertiesModal, setShowPropertiesModal] = useState(false);
  const [showExecutionHelp, setShowExecutionHelp] = useState(false);
  const [isEditorLocked, setIsEditorLocked] = useState(true);
  const [isSplitView, setIsSplitView] = useState(Boolean(initialSplit));
  const [splitName, setSplitName] = useState<string | null>(
    initialSplit && initialSplit !== routeName ? initialSplit : null,
  );
  const [activePane, setActivePane] = useState<Pane>("primary");
  const [discardPrompt, setDiscardPrompt] = useState<DiscardPrompt | null>(null);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [activeSidePanel, setActiveSidePanel] = useState<SidePanel>("explorer");
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [fontSize, setFontSize] = useState(14);
  const [selection, setSelection] = useState({ lines: 0, chars: 0 });
  const [isBottomPanelOpen, setIsBottomPanelOpen] = useState(false);
  const [wordWrap, setWordWrap] = useState<"on" | "off">("on");
  const reportedTerminalExecution = useRef<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const editorRefs = useRef<Record<Pane, any>>({ primary: null, secondary: null });

  // Each pane edits and saves its own workflow.
  const primary = useFlowDocument(routeName);
  const secondary = useFlowDocument(isSplitView ? splitName : null);
  const docs: Record<Pane, FlowDocument> = { primary, secondary };
  // The pane that header actions, Properties, the status bar and the Explorer act on.
  const currentPane: Pane = isSplitView && activePane === "secondary" ? "secondary" : "primary";
  const active = docs[currentPane];
  const ready = active.isReady;
  const name = active.name ?? "";
  const {
    code,
    setCode,
    description,
    setDescription,
    flowFunctionName,
    setFlowFunctionName,
    username,
    setUsername,
    chipId,
    setChipId,
    tags,
    setTags,
    folder,
    setFolder,
    defaultInterval,
    setDefaultInterval,
    isDirty,
  } = active;
  const flow = active.flow;
  // The run being confirmed belongs to the pane it was opened from.
  const execDoc = executeTarget ? docs[executeTarget] : active;

  // Fetch current user
  const { data: userData } = useGetCurrentUser();

  // Fetch execution lock status (refresh every 5 seconds)
  const { data: lockStatus } = useGetExecutionLockStatus({
    query: {
      refetchInterval: 5000,
    },
  });

  const { data: executionResponse } = useGetExecution(lastExecutionId ?? "", {
    query: {
      enabled: Boolean(lastExecutionId),
      refetchInterval: (query) => {
        const status = (query.state.data?.data as ExecutionResponseDetail | undefined)?.status;
        return isExecutionTerminal(status) ? false : 2000;
      },
      refetchIntervalInBackground: true,
    },
  });
  const latestExecution = executionResponse?.data as ExecutionResponseDetail | undefined;

  useEffect(() => {
    if (!lastExecutionId || !latestExecution) return;
    if (!["failed", "cancelled"].includes(latestExecution.status)) return;
    if (reportedTerminalExecution.current === lastExecutionId) return;

    reportedTerminalExecution.current = lastExecutionId;
    const message = latestExecution.message || `Flow execution ${latestExecution.status}`;
    toast.error(message);
    setIsBottomPanelOpen(true);
  }, [lastExecutionId, latestExecution, toast]);

  // Fetch all flows for sidebar
  const { data: flowsData } = useListFlows();

  // Fetch schedules for the active workflow
  const { data: schedulesData } = useQuery({
    queryKey: ["flow-schedules", name],
    queryFn: () => listFlowSchedules(name),
    refetchInterval: 10000,
    enabled: Boolean(name),
  });

  const activeSchedules =
    (ready &&
      schedulesData?.data &&
      "schedules" in schedulesData.data &&
      schedulesData.data.schedules?.filter((s) => s.active)) ||
    [];

  // The preview reads the saved source, which is what Execute runs.
  const executionPlan = useFlowExecutionPlan({
    flowName: execDoc.name ?? "",
    chipId: execDoc.chipId,
    sourceVersion: execDoc.flow?.updated_at,
    enabled: executeTarget !== null && execDoc.isReady,
  });

  const availability = useExecutionAvailability(
    { flow_name: execDoc.name ?? "", parameters: { chip_id: execDoc.chipId } },
    Boolean(execDoc.isReady && execDoc.chipId),
  );

  const deleteMutation = useMutation({
    mutationFn: (flowName: string) => deleteFlow(flowName),
    onSuccess: (_response, flowName) => {
      toast.success(`${flowName} deleted successfully!`);
      if (flowName === routeName) {
        router.push("/workflow");
        return;
      }
      // The right pane's workflow is gone; the left pane stays open.
      queryClient.invalidateQueries({ queryKey: getListFlowsQueryKey() });
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      setSplitName((current) => (current === flowName ? null : current));
    },
  });

  // Run answers are checked against the user and project they were submitted in; one that
  // lands after a project switch is dropped instead of updating this page or the guide.
  const executeMutation = useMutation({
    mutationFn: ({
      name: flowName,
      data: request,
    }: {
      name: string;
      data: ExecuteFlowRequest;
      context: JourneyContext;
    }) => executeFlow(flowName, request),
    onSuccess: (response: AxiosResponse<ExecuteFlowResponse>, variables) => {
      if (!variables.context.isCurrent()) return;
      const execId = response.data.execution_id || null;
      const runChipId = variables.data.parameters?.chip_id;
      // The first calibration guide follows this run when it is the guide's flow and chip.
      let followedByJourney = false;
      if (execId && typeof runChipId === "string") {
        // Checked before recording: a guide paused or restarted during the request stays put.
        const follows = variables.context.followsSubmittedJourney();
        const journeyAfter = variables.context.record({
          type: "runStarted",
          flowName: variables.name,
          chipId: runChipId,
          executionId: execId,
        });
        followedByJourney =
          follows &&
          journeyAfter?.executionId === execId &&
          journeyAfter.flowName === variables.name &&
          journeyAfter.chipId === runChipId;
      }
      setLastExecutionId(execId);
      setLastFlowRunId(response.data.flow_run_id || null);
      setLastRun({
        flowName: variables.name,
        chipId: typeof runChipId === "string" ? runChipId : "",
        username: String(variables.data.parameters?.username ?? ""),
      });
      toast.success(`Flow execution started! Execution ID: ${execId || "N/A"}`);
      // The guide's run opens on its execution page, where the guide follows its progress.
      if (followedByJourney && execId && typeof runChipId === "string") {
        router.push(executionHref(runChipId, execId));
      }
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: getGetExecutionLockStatusQueryKey(),
        }),
        queryClient.invalidateQueries({ queryKey: ["execution-availability"] }),
      ]),
  });

  // Errors shown on this page belong to the project they were made in.
  const { projectId } = useProject();
  const resetPrimarySave = primary.resetSave;
  const resetSecondarySave = secondary.resetSave;
  const resetExecute = executeMutation.reset;
  const previousProjectId = useRef(projectId);
  useEffect(() => {
    if (previousProjectId.current === projectId) return;
    previousProjectId.current = projectId;
    resetPrimarySave();
    resetSecondarySave();
    resetExecute();
  }, [projectId, resetPrimarySave, resetSecondarySave, resetExecute]);

  const cancelMutation = useCancelExecution({
    mutation: {
      onSuccess: () => {
        toast.success("Cancellation requested successfully");
      },
      onError: (error: unknown) => {
        toast.error(getApiErrorMessage(error, "Failed to cancel execution"));
      },
    },
  });

  const executeDisabledReason = !execDoc.isReady
    ? execDoc.name
      ? "Loading this workflow…"
      : "Open a workflow in this pane to run it."
    : execDoc.isSaving || deleteMutation.isPending
      ? "Wait for the current operation to finish."
      : executeMutation.isPending
        ? "Starting this flow…"
        : availability.disabledReason;

  const canCancel =
    !!lastFlowRunId &&
    !!lockStatus?.data.lock &&
    latestExecution?.status !== "cancelling" &&
    !isExecutionTerminal(latestExecution?.status);
  const executeErrorMessage = getApiErrorMessage(executeMutation.error, "Unknown error");

  // Tell the chat sidebar what is open here: the active pane's flow and its current text, read
  // when a turn is sent; a proposed edit for that flow lands in the same pane, unlocked.
  const { registerPage } = useChatDock();
  const pageState = useRef({ routeName, name, ready, chipId, code, isDirty, setCode });
  // Written after each commit, never during render; the provider below reads it when a turn is sent.
  useEffect(() => {
    pageState.current = { routeName, name, ready, chipId, code, isDirty, setCode };
  });
  useEffect(
    () =>
      registerPage({
        current: () => {
          const { routeName, name, ready, chipId, code, isDirty } = pageState.current;
          return {
            path: `/workflow/${routeName}`,
            title: `Workflow editor: ${name || routeName}`,
            flow: ready ? { name, chipId: chipId || undefined, code, dirty: isDirty } : undefined,
          };
        },
        applyCode: (next) => {
          if (!pageState.current.ready) return;
          pageState.current.setCode(next);
          setIsEditorLocked(false);
        },
      }),
    [registerPage],
  );

  // Save the given pane's workflow; Save buttons and the palette use the active pane.
  const savePane = (pane: Pane) => {
    if (isEditorLocked) return;
    docs[pane].save(captureJourneyContext());
  };
  const handleSave = () => savePane(currentPane);

  // Keep a ref to savePane for Monaco commands (avoids stale closure)
  const savePaneRef = useRef(savePane);
  useEffect(() => {
    savePaneRef.current = savePane;
  });

  // Warn before leaving with unsaved changes in either pane
  const hasUnsavedChanges = primary.isDirty || secondary.isDirty;
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [hasUnsavedChanges]);

  /** Run `action`, first asking to discard any unsaved draft among `candidates`. */
  const confirmDiscard = (candidates: FlowDocument[], action: () => void) => {
    const names = candidates
      .filter((doc) => doc.isDirty && doc.name)
      .map((doc) => doc.name as string);
    if (names.length === 0) {
      action();
      return;
    }
    setDiscardPrompt({ names, action });
  };

  const leaveEditor = () => confirmDiscard([primary, secondary], () => router.push("/workflow"));

  // Open a workflow from the Explorer in the active pane.
  const openFlow = (flowName: string) => {
    const target = currentPane;
    const other: Pane = target === "primary" ? "secondary" : "primary";
    // A workflow already open in the other pane is focused there, never opened twice.
    if (isSplitView && docs[other].name === flowName) {
      setActivePane(other);
      return;
    }
    if (docs[target].name === flowName) return;
    if (target === "secondary") {
      confirmDiscard([secondary], () => setSplitName(flowName));
      return;
    }
    // The left pane is the page's workflow: opening another navigates, keeping the right pane's
    // workflow open; the page reloads both, so either pane's draft is confirmed first.
    confirmDiscard(isSplitView ? [primary, secondary] : [primary], () => {
      const split = isSplitView && splitName ? `?split=${encodeURIComponent(splitName)}` : "";
      router.push(`/workflow/${encodeURIComponent(flowName)}${split}`);
    });
  };

  const toggleSplit = () => {
    if (!isSplitView) {
      // The new right pane waits for a workflow picked in the Explorer.
      setIsSplitView(true);
      setActivePane("secondary");
      setActiveSidePanel("explorer");
      setIsSidebarVisible(true);
      return;
    }
    confirmDiscard([secondary], () => {
      setIsSplitView(false);
      setSplitName(null);
      setActivePane("primary");
    });
  };

  const openExecute = () => {
    if (executeDisabledReason) return;
    setExecuteTarget(currentPane);
  };

  const activeEditor = () => editorRefs.current[currentPane];

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + Shift + P → Command Palette
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "p") {
        e.preventDefault();
        setShowCommandPalette(true);
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
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Sync fontSize and wordWrap to both editors
  useEffect(() => {
    for (const editor of Object.values(editorRefs.current)) {
      editor?.updateOptions({ fontSize, wordWrap });
    }
  }, [fontSize, wordWrap]);

  // The status bar follows the active pane's cursor.
  const activePaneRef = useRef<Pane>(currentPane);
  useEffect(() => {
    activePaneRef.current = currentPane;
    const position = editorRefs.current[currentPane]?.getPosition?.();
    setCursorPosition(
      position ? { line: position.lineNumber, column: position.column } : { line: 1, column: 1 },
    );
    setSelection({ lines: 0, chars: 0 });
  }, [currentPane]);

  // Command palette actions
  const commands = [
    {
      id: "save",
      label: "Save Flow",
      shortcut: "⌘S",
      icon: Save,
      action: () => savePaneRef.current(currentPane),
      enabled: !isEditorLocked && ready,
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
      action: openExecute,
      enabled: !executeDisabledReason,
    },
    {
      id: "properties",
      label: "Open Properties",
      shortcut: "",
      icon: Settings,
      action: () => setShowPropertiesModal(true),
      enabled: ready,
    },
    {
      id: "split-view",
      label: isSplitView ? "Close Split Editor" : "Open Split Editor",
      shortcut: "",
      icon: Columns2,
      action: toggleSplit,
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
      id: "toggle-minimap",
      label: "Toggle Minimap",
      shortcut: "",
      icon: FileCode,
      action: () => {
        const ed = activeEditor();
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
        activeEditor()?.focus();
        activeEditor()?.getAction("editor.action.gotoLine")?.run();
      },
      enabled: true,
    },
    {
      id: "find",
      label: "Find and Replace",
      shortcut: "⌘F",
      icon: Search,
      action: () => {
        activeEditor()?.focus();
        activeEditor()?.getAction("actions.find")?.run();
      },
      enabled: true,
    },
    {
      id: "format",
      label: "Format Document",
      shortcut: "⇧⌥F",
      icon: FileCode,
      action: () => {
        activeEditor()?.focus();
        activeEditor()?.getAction("editor.action.formatDocument")?.run();
      },
      enabled: true,
    },
  ];

  const executeCommand = (cmd: (typeof commands)[0]) => {
    if (!cmd.enabled) return;
    setShowCommandPalette(false);
    cmd.action();
  };

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
  ];

  const openSidePanel = (panel: SidePanel) => {
    setActiveSidePanel(panel);
    setIsSidebarVisible(true);
  };

  const mountEditor = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (pane: Pane, editor: any, monaco: any) => {
      editorRefs.current[pane] = editor;
      // A pane that opens another workflow remounts its editor; forget the disposed one.
      editor.onDidDispose(() => {
        if (editorRefs.current[pane] === editor) editorRefs.current[pane] = null;
      });
      remeasureMonacoFontsWhenLoaded(monaco);
      editor.onDidChangeCursorPosition(
        (e: { position: { lineNumber: number; column: number } }) => {
          if (activePaneRef.current !== pane) return;
          setCursorPosition({
            line: e.position.lineNumber,
            column: e.position.column,
          });
        },
      );
      editor.onDidChangeCursorSelection(
        (e: {
          selection: {
            startLineNumber: number;
            endLineNumber: number;
            startColumn: number;
            endColumn: number;
          };
        }) => {
          if (activePaneRef.current !== pane) return;
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
      // Cmd/Ctrl+S saves the workflow of the pane it was pressed in.
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () =>
        savePaneRef.current(pane),
      );
      // Alt+Z → toggle word wrap
      editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyZ, () =>
        setWordWrap((prev) => (prev === "on" ? "off" : "on")),
      );
    },
    [],
  );
  // Each pane's editor reports to its own pane.
  const handlePrimaryMount = useCallback<OnMount>(
    (editor, monaco) => mountEditor("primary", editor, monaco),
    [mountEditor],
  );
  const handleSecondaryMount = useCallback<OnMount>(
    (editor, monaco) => mountEditor("secondary", editor, monaco),
    [mountEditor],
  );

  const deleteDoc = deleteTarget ? docs[deleteTarget] : null;
  const showDeleteConfirm = deleteTarget !== null;
  const handleDelete = () => {
    const pane = deleteTarget;
    setDeleteTarget(null);
    if (pane === "secondary") {
      if (secondary.name) deleteMutation.mutate(secondary.name);
      return;
    }
    // Deleting the left pane's workflow leaves the editor, so a right-pane draft is confirmed.
    confirmDiscard(isSplitView ? [secondary] : [], () => deleteMutation.mutate(routeName));
  };

  // Unsaved draft confirmation before a pane's workflow is replaced, closed or deleted. Both the
  // editor and the load-error view render it, since either can defer an action behind it.
  const discardDialog = (
    <ConfirmDialog
      open={discardPrompt !== null}
      title="Discard unsaved changes?"
      description={
        <>
          Unsaved changes to{" "}
          {discardPrompt?.names.map((draft, index) => (
            <span key={draft}>
              {index > 0 && " and "}
              <strong>{draft}.py</strong>
            </span>
          ))}{" "}
          will be lost. Save first to keep them.
        </>
      }
      confirmLabel="Discard changes"
      destructive
      onConfirm={() => {
        const action = discardPrompt?.action;
        setDiscardPrompt(null);
        action?.();
      }}
      onOpenChange={(open) => !open && setDiscardPrompt(null)}
    />
  );

  if (primary.isLoading) {
    return <WorkflowEditorPageSkeleton />;
  }

  if (primary.error) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <AlertTriangle className="h-5 w-5" />
          <div>
            <div className="font-medium">Failed to load flow</div>
            <div className="text-sm">{(primary.error as Error)?.message}</div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={() => router.push("/workflow")} className="btn btn-ghost">
            ← Back to Flows
          </button>
          <button
            onClick={() => setDeleteTarget("primary")}
            className="btn btn-error"
            disabled={deleteMutation.isPending}
          >
            <Trash2 size={16} />
            Delete Flow Metadata
          </button>
        </div>
        {deleteMutation.isError && (
          <div className="alert alert-error mt-4">
            <span>
              Failed to delete flow: {(deleteMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}
        {showDeleteConfirm && (
          <Dialog
            open
            onOpenChange={(open) => !open && !deleteMutation.isPending && setDeleteTarget(null)}
          >
            <DialogContent>
              <DialogTitle>Delete Flow</DialogTitle>
              <DialogDescription className="py-4">
                Are you sure you want to delete <strong>{routeName}</strong>? The source file could
                not be loaded, so this will remove the remaining flow metadata.
              </DialogDescription>
              <div className="modal-action">
                <button
                  type="button"
                  onClick={() => setDeleteTarget(null)}
                  className="btn btn-ghost"
                  disabled={deleteMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
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
            </DialogContent>
          </Dialog>
        )}
        {discardDialog}
      </div>
    );
  }

  // One Monaco editor per pane, each bound to its own workflow's draft.
  const renderEditor = (pane: Pane) => {
    const doc = docs[pane];
    return (
      <Editor
        // A new workflow in the pane gets a fresh editor, so undo never reaches another's text.
        key={`${pane}:${doc.name}`}
        height="100%"
        language="python"
        theme="vs-dark"
        value={doc.code}
        onChange={(value) => doc.setCode(value || "")}
        onMount={pane === "primary" ? handlePrimaryMount : handleSecondaryMount}
        options={{
          ...EDITOR_OPTIONS,
          fontSize,
          wordWrap,
          readOnly: isEditorLocked,
          domReadOnly: isEditorLocked,
        }}
      />
    );
  };

  const renderPaneBody = (pane: Pane) => {
    const doc = docs[pane];
    if (doc.isReady) return renderEditor(pane);
    if (doc.error) {
      return (
        <div className="p-4">
          <div className="alert alert-error">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            <span>
              Failed to load {doc.name}: {(doc.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        </div>
      );
    }
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-base-content/60">
        {doc.name ? (
          <span className="flex items-center gap-2">
            <span className="loading loading-spinner loading-sm" aria-hidden="true" />
            Loading {doc.name}.py…
          </span>
        ) : (
          <div>
            <FolderOpen size={24} className="mx-auto mb-2 opacity-60" aria-hidden="true" />
            <p>Select a workflow in the Explorer to open it in this pane.</p>
          </div>
        )}
      </div>
    );
  };

  // A split pane: a header naming its workflow, then its editor. Clicking or focusing a pane
  // makes it the one that Save, Execute, Properties and the Explorer act on.
  const renderPane = (pane: Pane) => {
    const doc = docs[pane];
    const isActive = currentPane === pane;
    const fileName = doc.name ? `${doc.name}.py` : "No workflow";
    return (
      <section
        className="flex h-full min-w-0 flex-col"
        aria-label={`${PANE_LABEL[pane]} editor: ${fileName}`}
        onMouseDownCapture={() => setActivePane(pane)}
        onFocusCapture={() => setActivePane(pane)}
      >
        <button
          type="button"
          onClick={() => setActivePane(pane)}
          aria-pressed={isActive}
          title={
            isActive
              ? `${PANE_LABEL[pane]} pane (active)`
              : `Activate ${PANE_LABEL[pane].toLowerCase()} pane`
          }
          className={`relative flex h-8 shrink-0 items-center gap-2 border-b border-base-300 px-3 text-left text-xs ${
            isActive ? "bg-base-300 text-base-content" : "bg-base-200 text-base-content/60"
          }`}
        >
          {isActive && <span className="absolute inset-x-0 top-0 h-0.5 bg-primary" />}
          <span className="text-info">py</span>
          <span className="truncate font-medium">{fileName}</span>
          {doc.isDirty && (
            <span
              className="h-2 w-2 shrink-0 rounded-full bg-base-content/60"
              title="Unsaved changes"
            />
          )}
        </button>
        <div className="min-h-0 flex-1">{renderPaneBody(pane)}</div>
      </section>
    );
  };

  return (
    <>
      {/* Fills the page area under the navbar and the guide banner, whatever their height. */}
      <div className="flex h-full min-h-0 flex-col bg-base-300">
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
              onClick={leaveEditor}
              className="btn btn-sm btn-ghost"
              disabled={active.isSaving || deleteMutation.isPending}
              title="Back to workflows"
              aria-label="Back to workflows"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-base-content/50">●</span>
              <span className="text-sm font-medium text-base-content truncate">
                {name ? `${name}.py` : "No workflow"}
              </span>
              {isSplitView && (
                <span className="badge badge-sm badge-ghost">{PANE_LABEL[currentPane]} pane</span>
              )}
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
            {ready && flow?.updated_at && (
              <span className="text-xs text-base-content/50 hidden lg:inline">
                Updated: {formatDateTime(flow.updated_at)}
              </span>
            )}
          </div>
          {/* Desktop action buttons - hidden on mobile, use FAB instead */}
          <div className="hidden sm:flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={() => setShowExecutionHelp(true)}
              className="btn btn-sm btn-ghost"
              title="Execution help"
              aria-label="Execution help"
            >
              <CircleHelp size={16} />
              <span className="ml-1 hidden md:inline">Execution help</span>
            </button>
            <button
              type="button"
              onClick={() => setShowPropertiesModal(true)}
              className="btn btn-sm btn-ghost"
              disabled={!ready}
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
              onClick={openExecute}
              className="btn btn-sm btn-success"
              data-coachmark="flow-execute"
              data-coachmark-ready={executeDisabledReason ? undefined : "true"}
              disabled={Boolean(executeDisabledReason)}
              aria-describedby={executeDisabledReason ? "flow-execution-availability" : undefined}
              title={executeDisabledReason ?? "Execute Flow"}
            >
              {executeMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <Play size={16} />
              )}
              <span className="ml-1">Execute</span>
            </button>
            {canCancel && (
              <button
                onClick={() => lastFlowRunId && cancelMutation.mutate({ flowRunId: lastFlowRunId })}
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
              onClick={() => setDeleteTarget(currentPane)}
              className="btn btn-sm btn-error"
              disabled={active.isSaving || deleteMutation.isPending || !ready}
            >
              <Trash2 size={16} />
              <span className="ml-1">Delete</span>
            </button>
            <button
              onClick={handleSave}
              className={`btn btn-sm ${isEditorLocked ? "btn-outline" : "btn-success"}`}
              disabled={active.isSaving || deleteMutation.isPending || isEditorLocked || !ready}
            >
              {active.isSaving ? (
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

        {[primary, secondary].map((doc) =>
          doc.saveError && doc.name ? (
            <div key={doc.name} className="alert alert-error mx-4 mt-2">
              <span>
                Failed to save {doc.name}: {(doc.saveError as Error)?.message || "Unknown error"}
              </span>
            </div>
          ) : null,
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
            <span>Failed to execute flow: {executeErrorMessage}</span>
          </div>
        )}

        {executeDisabledReason && (
          <div
            id="flow-execution-availability"
            className="alert mx-4 mt-2 gap-2 border-base-content/10! px-3 py-1.5 text-base-content/70"
            role="status"
          >
            <Info size={16} className="shrink-0 text-base-content/60" aria-hidden="true" />
            <span className="min-w-0">{executeDisabledReason}</span>
          </div>
        )}

        {/* Main Editor Area */}
        <div className="flex min-h-0 flex-1 overflow-hidden mb-4">
          {/* Activity Bar */}
          <div className="flex w-12 flex-col items-center border-r border-base-300 bg-base-200">
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
                    className={`btn btn-ghost btn-sm btn-square relative h-9 w-9 rounded-sm ${
                      isActive ? "bg-base-300 text-primary" : "text-base-content/60"
                    }`}
                    title={item.label}
                    aria-label={item.label}
                  >
                    <Icon size={18} />
                    {item.count ? (
                      <span className="absolute right-0 top-0 min-w-4 rounded-full bg-primary px-1 text-xs leading-4 text-primary-content">
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
                onClick={() => setShowCommandPalette(true)}
                className="btn btn-ghost btn-sm btn-square h-9 w-9 rounded-sm text-base-content/60"
                title="Command Palette"
                aria-label="Command Palette"
              >
                <CommandIcon size={18} />
              </button>
            </div>
          </div>

          {/* Side Panel */}
          <div
            className={`flex flex-col overflow-hidden bg-base-200 transition-colors duration-200 ${
              isSidebarVisible
                ? "w-56 min-w-56 border-r border-base-300 sm:w-72 sm:min-w-72"
                : "w-0 min-w-0"
            }`}
          >
            <div className="flex h-full w-56 min-w-56 flex-col sm:w-72 sm:min-w-72">
              <div className="flex h-9 items-center justify-between border-b border-base-300 px-3">
                <span className="text-xs font-medium text-base-content/60">
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
                  {isSplitView && (
                    <p
                      className="border-b border-base-300 px-3 py-1.5 text-xs text-base-content/60"
                      role="status"
                    >
                      Opens in the{" "}
                      <span className="font-medium text-base-content">
                        {PANE_LABEL[currentPane].toLowerCase()} pane
                      </span>
                    </p>
                  )}
                  <div className="min-h-0 flex-1 py-1">
                    <FlowExplorer
                      flows={flowsData?.data?.flows ?? []}
                      username={userData?.data?.username}
                      currentName={name}
                      isDirty={isDirty}
                      filter={sidebarSearch}
                      initialSpace={initialSpace}
                      onOpen={openFlow}
                    />
                  </div>
                  <div className="border-t border-base-300 p-2">
                    <button
                      type="button"
                      onClick={() =>
                        confirmDiscard([primary, secondary], () => router.push("/workflow/new"))
                      }
                      className="btn btn-primary btn-xs w-full gap-1"
                    >
                      <FilePlus2 size={13} />
                      New Flow
                    </button>
                  </div>
                </>
              )}

              {activeSidePanel === "properties" && !ready && (
                <div className="flex-1 p-3 text-sm text-base-content/60">
                  {name
                    ? `Loading ${name}.py…`
                    : "Open a workflow in this pane to see its properties."}
                </div>
              )}

              {activeSidePanel === "properties" && ready && (
                <div className="flex-1 overflow-y-auto p-3">
                  <div className="mb-3 rounded border border-base-300 bg-base-100 p-3">
                    <div className="flex items-center gap-2">
                      <FileCode size={16} className="text-primary" />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{name}.py</div>
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
                    <label className="form-control flex flex-col gap-1">
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
                    <label className="form-control flex flex-col gap-1">
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
                    <label className="form-control flex flex-col gap-1">
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
                    <label className="form-control flex flex-col gap-1">
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
                    <label className="form-control flex flex-col gap-1">
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
                    <label className="form-control flex flex-col gap-1">
                      <span className="label py-1">
                        <span className="label-text text-xs">Folder</span>
                      </span>
                      <input
                        id="flow-side-folder"
                        name="flowFolder"
                        type="text"
                        placeholder="daily/t1"
                        className="input input-bordered input-sm"
                        value={folder}
                        onChange={(e) => setFolder(e.target.value)}
                      />
                    </label>
                    <label className="form-control flex flex-col gap-1">
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

                    <div className="divider my-1"></div>
                    <FlowSchedulePanel flowName={name} />
                    <div className="divider my-1"></div>

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
            </div>
          </div>
          {/* Editor with Tab Switcher */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Tab Bar */}
            <div className="flex items-end bg-base-200 border-b border-base-300 h-9">
              {!isSplitView && (
                <div className="h-full px-4 text-sm font-medium flex items-center gap-2 border-r border-base-300 bg-base-300 text-base-content relative">
                  <span className="absolute top-0 left-0 right-0 h-0.5 bg-primary" />
                  <span className="text-info">py</span>
                  {name}.py
                  {isDirty && (
                    <span
                      className="w-2 h-2 rounded-full bg-base-content/60"
                      title="Unsaved changes"
                    />
                  )}
                </div>
              )}
              {/* Split View Toggle */}
              <div className="ml-auto flex items-center px-2 h-full">
                <button
                  type="button"
                  onClick={toggleSplit}
                  className={`btn btn-xs btn-ghost ${isSplitView ? "text-primary" : "text-base-content/50"}`}
                  title={isSplitView ? "Close split editor" : "Open split editor"}
                  aria-label={isSplitView ? "Close split editor" : "Open split editor"}
                >
                  <Columns2 size={14} />
                </button>
              </div>
            </div>

            {/* Breadcrumbs: the active pane's workflow */}
            <div className="flex items-center gap-1 px-3 py-1 bg-base-300/50 border-b border-base-300 text-xs text-base-content/50">
              <span className="hover:text-base-content cursor-pointer" onClick={leaveEditor}>
                workflows
              </span>
              <ChevronRight size={10} />
              <span
                className="hover:text-base-content cursor-pointer"
                onClick={() => ready && setShowPropertiesModal(true)}
              >
                {(ready && chipId) || "chip"}
              </span>
              <ChevronRight size={10} />
              <span className="text-base-content/80">{name ? `${name}.py` : "No workflow"}</span>
              {ready && flowFunctionName && (
                <>
                  <ChevronRight size={10} />
                  <span className="text-base-content/60">{flowFunctionName}()</span>
                </>
              )}
            </div>

            {/* Tab Content */}
            {isSplitView ? (
              <PanelGroup
                orientation="horizontal"
                style={{ flex: 1, minWidth: 0, overflow: "hidden" }}
              >
                <Panel defaultSize="50%" minSize="20%" style={{ overflow: "hidden", minWidth: 0 }}>
                  {renderPane("primary")}
                </Panel>
                <PanelResizeHandle className="w-1 bg-base-300 hover:bg-primary/50 transition-colors cursor-col-resize" />
                <Panel defaultSize="50%" minSize="20%" style={{ overflow: "hidden", minWidth: 0 }}>
                  {renderPane("secondary")}
                </Panel>
              </PanelGroup>
            ) : (
              renderEditor("primary")
            )}
          </div>
        </div>

        {/* Bottom Panel */}
        {isBottomPanelOpen && (
          <div className="h-48 shrink-0 border-t border-base-300 bg-base-100 flex flex-col">
            <div className="flex items-center justify-between border-b border-base-300 px-3 py-1">
              <div className="flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium">
                <Terminal size={12} />
                Output
              </div>
              <button
                type="button"
                onClick={() => setIsBottomPanelOpen(false)}
                className="btn btn-ghost btn-xs btn-square"
              >
                <X size={12} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto bg-base-300 p-3 font-mono text-xs text-base-content/70">
              {lastExecutionId ? (
                <div className="space-y-1">
                  <div className="text-base-content/40">
                    <span className="text-info">[info]</span> Flow: {lastRun?.flowName}
                  </div>
                  <div className="text-base-content/40">
                    <span className="text-info">[info]</span> Execution ID: {lastExecutionId}
                  </div>
                  <div className="text-base-content/40">
                    <span className="text-info">[info]</span> Chip: {lastRun?.chipId} | User:{" "}
                    {lastRun?.username}
                  </div>
                  {latestExecution?.status === "failed" ? (
                    <div className="space-y-1 text-error">
                      <div>[failed] Execution failed.</div>
                      {latestExecution.message && <div>{latestExecution.message}</div>}
                    </div>
                  ) : latestExecution?.status === "cancelled" ? (
                    <div className="space-y-1 text-warning">
                      <div>[cancelled] Execution was cancelled.</div>
                      {latestExecution.message && <div>{latestExecution.message}</div>}
                    </div>
                  ) : latestExecution?.status === "completed" ? (
                    <div>
                      <span className="text-success">[done]</span> Execution completed.
                    </div>
                  ) : latestExecution?.status === "cancelling" ? (
                    <div>
                      <span className="text-warning">[cancelling]</span> Cancelling execution...
                    </div>
                  ) : lockStatus?.data.lock ? (
                    <div>
                      <span className="text-warning">[running]</span> Execution in progress...
                    </div>
                  ) : (
                    <div>
                      <span className="text-info">[pending]</span> Waiting for execution status...
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex h-full items-center justify-center text-base-content/30">
                  <div className="text-center">
                    <Terminal size={24} className="mx-auto mb-2 opacity-50" />
                    <div>No execution output yet.</div>
                    <div className="mt-1 text-xs">Execute a flow to see output here.</div>
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
                activeEditor()?.focus();
                activeEditor()?.getAction("editor.action.gotoLine")?.run();
              }}
              className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer"
              title="Go to Line (⌘G)"
            >
              Ln {cursorPosition.line}, Col {cursorPosition.column}
            </button>
            {selection.chars > 0 && (
              <span className="hidden sm:inline-block px-1.5 py-0.5 bg-primary-content/10 rounded">
                {selection.lines > 1 ? `${selection.lines} lines, ` : ""}
                {selection.chars} selected
              </span>
            )}
            <span className="hidden sm:inline-block px-1.5 py-0.5">Spaces: 4</span>
            <span className="px-1.5 py-0.5">Python</span>
            <span className="px-1.5 py-0.5">UTF-8</span>
            {isDirty && (
              <span className="hidden sm:inline-block px-1.5 py-0.5 opacity-80">● Modified</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <span className="px-1.5 py-0.5">{ready ? code.split("\n").length : 0} lines</span>
            <button
              type="button"
              onClick={() => setWordWrap((prev) => (prev === "on" ? "off" : "on"))}
              className={`hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer hidden sm:flex items-center gap-1 ${wordWrap === "off" ? "opacity-50" : ""}`}
              title="Toggle Word Wrap (⌥Z)"
            >
              <WrapText size={10} />
            </button>
            <button
              type="button"
              onClick={() => setIsBottomPanelOpen((prev) => !prev)}
              className={`hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer hidden sm:flex items-center gap-1 ${isBottomPanelOpen ? "" : "opacity-60"}`}
              title="Toggle Panel (⌘`)"
            >
              <Terminal size={10} />
            </button>
            {fontSize !== 14 && (
              <button
                type="button"
                onClick={() => setFontSize(14)}
                className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer hidden sm:block"
                title="Reset Zoom (⌘0)"
              >
                {Math.round((fontSize / 14) * 100)}%
              </button>
            )}
            {isEditorLocked ? (
              <button
                type="button"
                onClick={() => setIsEditorLocked(false)}
                className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer hidden sm:flex items-center gap-1 opacity-80"
                title="Click to enable editing"
              >
                <Lock size={10} /> Read-only
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setIsEditorLocked(true)}
                className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer hidden sm:flex items-center gap-1"
                title="Click to lock editor"
              >
                <Pencil size={10} /> Editing
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setShowCommandPalette(true);
              }}
              className="hover:bg-primary-content/20 px-1.5 py-0.5 rounded transition-colors cursor-pointer hidden sm:flex items-center gap-1 opacity-70 hover:opacity-100"
              title="Command Palette"
            >
              <CommandIcon size={10} />
              <span>⌘⇧P</span>
            </button>
          </div>
        </div>

        {/* Command Palette */}
        <CommandDialog
          open={showCommandPalette}
          onOpenChange={setShowCommandPalette}
          title="Command Palette"
          description="Search for an editor command, then press Enter to run it."
        >
          <Command loop label="Workflow commands">
            <CommandInput
              id="workflow-command-palette-search"
              name="workflowCommandPaletteSearch"
              placeholder="Type a command..."
            />
            <CommandList>
              <CommandEmpty>No matching commands</CommandEmpty>
              {commands.map((cmd) => (
                <CommandItem
                  key={cmd.id}
                  value={cmd.label}
                  keywords={[cmd.id]}
                  disabled={!cmd.enabled}
                  onSelect={() => executeCommand(cmd)}
                >
                  <cmd.icon size={14} className="shrink-0 opacity-60" aria-hidden="true" />
                  <span className="flex-1">{cmd.label}</span>
                  {cmd.shortcut && (
                    <kbd className="rounded bg-base-300 px-1.5 py-0.5 text-xs text-base-content/40">
                      {cmd.shortcut}
                    </kbd>
                  )}
                </CommandItem>
              ))}
            </CommandList>
          </Command>
        </CommandDialog>

        {/* Mobile FAB / Speed Dial - only visible on mobile */}
        <div className="fab fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] right-4 z-30 sm:hidden">
          <div tabIndex={0} role="button" className="btn btn-circle btn-primary shadow-lg">
            <Plus size={20} />
          </div>
          {/* Execution Help Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Execution help
            </span>
            <button
              type="button"
              onClick={() => setShowExecutionHelp(true)}
              className="btn btn-circle btn-outline bg-base-100 shadow-lg"
              aria-label="Execution help"
            >
              <CircleHelp size={20} />
            </button>
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
              Execute
            </span>
            <button
              onClick={openExecute}
              className="btn btn-circle btn-success shadow-lg"
              data-coachmark="flow-execute"
              data-coachmark-ready={executeDisabledReason ? undefined : "true"}
              disabled={Boolean(executeDisabledReason)}
              aria-describedby={executeDisabledReason ? "flow-execution-availability" : undefined}
            >
              {executeMutation.isPending ? (
                <span className="loading loading-spinner loading-sm"></span>
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
                onClick={() => lastFlowRunId && cancelMutation.mutate({ flowRunId: lastFlowRunId })}
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
              disabled={active.isSaving || deleteMutation.isPending || isEditorLocked || !ready}
            >
              {active.isSaving ? (
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
              onClick={() => setDeleteTarget(currentPane)}
              className="btn btn-circle btn-error shadow-lg"
              disabled={active.isSaving || deleteMutation.isPending || !ready}
            >
              <Trash2 size={20} />
            </button>
          </div>
        </div>

        <WorkflowExecutionHelpDialog open={showExecutionHelp} onOpenChange={setShowExecutionHelp} />

        {/* Properties Modal */}
        {showPropertiesModal && ready && (
          <Dialog open onOpenChange={(open) => !open && setShowPropertiesModal(false)}>
            <DialogContent className="max-w-md max-h-[calc(100vh-8rem)]">
              <div className="flex justify-between items-center mb-4">
                <DialogTitle>Properties</DialogTitle>
                <button
                  onClick={() => setShowPropertiesModal(false)}
                  className="btn btn-ghost btn-sm btn-square"
                >
                  <X size={16} />
                </button>
              </div>
              <DialogDescription className="sr-only">
                View and edit workflow metadata and schedules.
              </DialogDescription>

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
                  <label htmlFor="flow-folder" className="label">
                    <span className="label-text text-xs">Folder</span>
                  </label>
                  <input
                    id="flow-folder"
                    type="text"
                    placeholder="daily/t1"
                    className="input input-bordered input-sm"
                    value={folder}
                    onChange={(e) => setFolder(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      Where it sits in your space on the Workflow page; "/" nests
                    </span>
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
                    value={flow?.file_path || ""}
                    disabled
                  />
                </div>

                {/* Flow Schedules Section */}
                <div className="divider my-2"></div>
                <FlowSchedulePanel flowName={name} />
              </div>

              <div className="modal-action">
                <button type="button" onClick={() => setShowPropertiesModal(false)} className="btn">
                  Close
                </button>
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <Dialog
            open
            onOpenChange={(open) => !open && !deleteMutation.isPending && setDeleteTarget(null)}
          >
            <DialogContent>
              <DialogTitle>Delete Flow</DialogTitle>
              <DialogDescription className="py-4">
                Are you sure you want to delete <strong>{deleteDoc?.name}</strong>? This action
                cannot be undone.
              </DialogDescription>
              <div className="modal-action">
                <button
                  type="button"
                  onClick={() => setDeleteTarget(null)}
                  className="btn btn-ghost"
                  disabled={deleteMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
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
            </DialogContent>
          </Dialog>
        )}

        {/* Execute Confirmation Modal: runs the workflow of the pane it was opened from */}
        {executeTarget && execDoc.name && (
          <FlowExecuteConfirmModal
            flowName={execDoc.name}
            username={execDoc.username}
            chipId={execDoc.chipId}
            description={execDoc.description}
            tags={execDoc.tags}
            targetDefaults={execDoc.flow?.target_defaults}
            targetModes={execDoc.flow?.target_modes}
            plan={executionPlan}
            hasUnsavedChanges={execDoc.isDirty}
            disabledReason={executeDisabledReason}
            onConfirm={(targetOverride) => {
              if (executeDisabledReason || !execDoc.name) return;
              setExecuteTarget(null);
              executeMutation.mutate({
                name: execDoc.name,
                context: captureJourneyContext(),
                data: {
                  target_override: targetOverride,
                  parameters: {
                    username: execDoc.username,
                    chip_id: execDoc.chipId,
                    tags: execDoc.tags
                      .split(",")
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  },
                },
              });
            }}
            onClose={() => setExecuteTarget(null)}
          />
        )}

        {discardDialog}
      </div>
    </>
  );
}
