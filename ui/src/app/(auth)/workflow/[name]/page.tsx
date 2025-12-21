"use client";

import dynamic from "next/dynamic";
import { useRouter, useParams } from "next/navigation";
import { useState, useEffect } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import type { SaveFlowRequest, ExecuteFlowResponse } from "@/schemas";
import type { AxiosResponse } from "axios";

import { useToast } from "@/components/ui/Toast";

import { useGetCurrentUser } from "@/client/auth/auth";
import { useListChips } from "@/client/chip/chip";
import { useGetExecutionLockStatus } from "@/client/execution/execution";
import {
  getFlow,
  saveFlow,
  deleteFlow,
  useExecuteFlow,
  listFlowSchedules,
} from "@/client/flow/flow";
import {
  ArrowLeft,
  Clock,
  Lock,
  Pencil,
  Play,
  Plus,
  Save,
  Settings,
  Trash2,
  X,
} from "lucide-react";

import { FlowExecuteConfirmModal } from "@/components/features/flow/FlowExecuteConfirmModal";
import { FlowImportsPanel } from "@/components/features/flow/FlowImportsPanel";
import { FlowSchedulePanel } from "@/components/features/flow/FlowSchedulePanel";
import { WorkflowEditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { formatDateTime } from "@/utils/datetime";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function EditFlowPage() {
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
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showExecuteConfirm, setShowExecuteConfirm] = useState(false);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [activeTab, setActiveTab] = useState<"code" | "helpers">("code");
  const [showPropertiesModal, setShowPropertiesModal] = useState(false);
  const [isEditorLocked, setIsEditorLocked] = useState(true);

  // Fetch current user
  const { data: userData } = useGetCurrentUser();

  // Fetch chips
  const { data: chipsData } = useListChips();

  // Fetch execution lock status (refresh every 5 seconds)
  const { data: lockStatus, isLoading: isLockStatusLoading } =
    useGetExecutionLockStatus({
      query: {
        refetchInterval: 5000,
      },
    });

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
        toast.success(
          `Flow execution started! Execution ID: ${response.data.execution_id || "N/A"}`,
        );
      },
    },
  });

  useEffect(() => {
    if (data?.data) {
      const flow = data.data;
      setDescription(flow.description);
      setCode(flow.code);
      setFlowFunctionName(flow.flow_function_name);

      // Set username from flow or fallback to current user
      const flowUsername = (flow.default_parameters?.username as string) || "";
      setUsername(flowUsername || userData?.data?.username || "");

      // Set chip_id from flow or fallback to latest chip
      setChipId(flow.chip_id);

      setTags(flow.tags?.join(", ") || "");
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
    if (
      chipsData?.data?.chips &&
      chipsData.data.chips.length > 0 &&
      !chipId &&
      !data?.data
    ) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setChipId(sortedChips[0].chip_id);
    }
  }, [chipsData, chipId, data]);

  const handleSave = () => {
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
    };

    saveMutation.mutate(request);
  };

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
        <button
          onClick={() => router.push("/workflow")}
          className="btn btn-ghost mt-4"
        >
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
              onClick={() => router.push("/workflow")}
              className="btn btn-sm btn-ghost"
              disabled={saveMutation.isPending || deleteMutation.isPending}
            >
              <ArrowLeft size={16} />
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-base-content/50">●</span>
              <span className="text-sm font-medium text-base-content truncate">
                {name}.py
              </span>
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
              onClick={() => setShowPropertiesModal(true)}
              className="btn btn-sm btn-ghost"
              title="Properties"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={() => setIsEditorLocked(!isEditorLocked)}
              className={`btn btn-sm ${isEditorLocked ? "btn-outline" : "btn-warning"}`}
              title={isEditorLocked ? "Click to edit" : "Currently editing"}
            >
              <Pencil size={16} />
              <span className="ml-1">
                {isEditorLocked ? "Edit" : "Editing"}
              </span>
            </button>
            <button
              onClick={() => setShowExecuteConfirm(true)}
              className={`btn btn-sm ${
                lockStatus?.data.lock ? "btn-disabled" : "btn-success"
              }`}
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
              <span className="ml-1">
                {lockStatus?.data.lock ? "Locked" : "Execute"}
              </span>
            </button>
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
              disabled={
                saveMutation.isPending ||
                deleteMutation.isPending ||
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

        {saveMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>
              Failed to save flow:{" "}
              {(saveMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}

        {deleteMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>
              Failed to delete flow:{" "}
              {(deleteMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}

        {executeMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>
              Failed to execute flow:{" "}
              {(executeMutation.error as Error)?.message || "Unknown error"}
            </span>
          </div>
        )}

        {/* Main Editor Area */}
        <div className="flex-1 flex overflow-hidden mb-4">
          {/* Editor with Tab Switcher */}
          <div className="flex-1 flex flex-col">
            {/* Tab Bar */}
            <div className="flex bg-base-200 border-b border-base-300">
              <button
                onClick={() => setActiveTab("code")}
                className={`px-4 py-2 text-sm font-medium flex items-center gap-2 border-r border-base-300 transition-colors ${
                  activeTab === "code"
                    ? "bg-base-300 text-base-content border-t-2 border-t-primary"
                    : "bg-base-200 text-base-content/60 hover:bg-base-300/50 border-t-2 border-t-transparent"
                }`}
              >
                <span className="text-info">py</span>
                {name}.py
              </button>
              <button
                onClick={() => setActiveTab("helpers")}
                className={`px-4 py-2 text-sm font-medium flex items-center gap-2 border-r border-base-300 transition-colors ${
                  activeTab === "helpers"
                    ? "bg-base-300 text-base-content border-t-2 border-t-primary"
                    : "bg-base-200 text-base-content/60 hover:bg-base-300/50 border-t-2 border-t-transparent"
                }`}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-secondary"
                >
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
                Helpers Reference
              </button>
            </div>

            {/* Tab Content */}
            {activeTab === "code" ? (
              <Editor
                height="100%"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(value) => setCode(value || "")}
                onMount={(editor) => {
                  editor.onDidChangeCursorPosition((e) => {
                    setCursorPosition({
                      line: e.position.lineNumber,
                      column: e.position.column,
                    });
                  });
                }}
                options={{
                  minimap: { enabled: true },
                  fontSize: 14,
                  lineNumbers: "on",
                  automaticLayout: true,
                  scrollBeyondLastLine: true,
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
            ) : (
              <FlowImportsPanel />
            )}
          </div>
        </div>

        {/* Status Bar */}
        <div className="flex items-center justify-between px-4 py-1 bg-primary text-primary-content text-xs">
          <div className="flex items-center gap-4">
            <span>
              Ln {cursorPosition.line}, Col {cursorPosition.column}
            </span>
            <span>Python</span>
            <span>UTF-8</span>
          </div>
          <div className="flex items-center gap-4">
            <span>{code.split("\n").length} lines</span>
          </div>
        </div>

        {/* Mobile FAB / Speed Dial - only visible on mobile */}
        <div className="fab fixed bottom-20 right-4 z-30 sm:hidden">
          <div
            tabIndex={0}
            role="button"
            className="btn btn-circle btn-primary shadow-lg"
          >
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
          {/* Save Button */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Save
            </span>
            <button
              onClick={handleSave}
              className={`btn btn-circle shadow-lg ${isEditorLocked ? "btn-outline bg-base-100" : "btn-success"}`}
              disabled={
                saveMutation.isPending ||
                deleteMutation.isPending ||
                isEditorLocked
              }
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
            <span className="text-sm font-medium bg-base-100 px-2 py-1 rounded shadow">
              Delete
            </span>
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
            <div
              className="modal-backdrop"
              onClick={() => setShowPropertiesModal(false)}
            />
            <div className="modal-box max-w-md">
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
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Flow Name</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm"
                    value={name}
                    disabled
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      Cannot be changed
                    </span>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Description</span>
                  </label>
                  <textarea
                    className="textarea textarea-bordered textarea-sm"
                    placeholder="Describe your flow..."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">
                      Entrypoint Function
                    </span>
                  </label>
                  <input
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

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Username *</span>
                  </label>
                  <input
                    type="text"
                    placeholder="your_username"
                    className="input input-bordered input-sm"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Chip ID *</span>
                  </label>
                  <input
                    type="text"
                    placeholder="64Qv3"
                    className="input input-bordered input-sm"
                    value={chipId}
                    onChange={(e) => setChipId(e.target.value)}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Tags</span>
                  </label>
                  <input
                    type="text"
                    placeholder="tag1, tag2, tag3"
                    className="input input-bordered input-sm"
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      Comma-separated
                    </span>
                  </label>
                </div>

                <div className="divider my-2"></div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">File Path</span>
                  </label>
                  <input
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
                <button
                  onClick={() => setShowPropertiesModal(false)}
                  className="btn"
                >
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
                Are you sure you want to delete <strong>{name}</strong>? This
                action cannot be undone.
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
