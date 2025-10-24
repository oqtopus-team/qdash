"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getFlow,
  saveFlow,
  deleteFlow,
  useExecuteFlow,
} from "@/client/flow/flow";
import { useListChips } from "@/client/chip/chip";
import { useAuthReadUsersMe } from "@/client/auth/auth";
import { useFetchExecutionLockStatus } from "@/client/execution/execution";
import type { SaveFlowRequest } from "@/schemas";
import dynamic from "next/dynamic";
import { toast } from "react-toastify";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function EditFlowPage() {
  const router = useRouter();
  const params = useParams();
  const queryClient = useQueryClient();
  const name = params.name as string;

  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [flowFunctionName, setFlowFunctionName] = useState("");
  const [username, setUsername] = useState("");
  const [chipId, setChipId] = useState("");
  const [tags, setTags] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });

  // Fetch current user
  const { data: userData } = useAuthReadUsersMe();

  // Fetch chips
  const { data: chipsData } = useListChips();

  // Fetch execution lock status (refresh every 5 seconds)
  const { data: lockStatus, isLoading: isLockStatusLoading } =
    useFetchExecutionLockStatus({
      query: {
        refetchInterval: 5000,
      },
    });

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
      router.push("/flow");
    },
  });

  const executeMutation = useExecuteFlow({
    mutation: {
      onSuccess: (response) => {
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
      chipsData?.data &&
      chipsData.data.length > 0 &&
      !chipId &&
      !data?.data
    ) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data].sort((a, b) => {
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
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <span>Failed to load flow: {error.message}</span>
        </div>
        <button
          onClick={() => router.push("/flow")}
          className="btn btn-ghost mt-4"
        >
          ← Back to Flows
        </button>
      </div>
    );
  }

  return (
    <>
      <ToastContainer position="top-right" autoClose={3000} />
      <div className="h-screen flex flex-col bg-[#1e1e1e]">
        {/* VSCode-style Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-[#3e3e3e]">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/flow")}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors"
              disabled={saveMutation.isPending || deleteMutation.isPending}
            >
              ← Back
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">●</span>
              <span className="text-sm font-medium text-white">{name}.py</span>
            </div>
            {data?.data?.updated_at && (
              <span className="text-xs text-gray-500">
                Updated: {new Date(data.data.updated_at).toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() =>
                executeMutation.mutate({
                  name,
                  data: {
                    parameters: {
                      username: username,
                      chip_id: chipId,
                    },
                  },
                })
              }
              className={`px-3 py-1 text-sm text-white border rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                lockStatus?.data.lock
                  ? "bg-gray-600 border-gray-700"
                  : "bg-[#16825d] border-[#1a9870] hover:bg-[#1a9870]"
              }`}
              disabled={
                saveMutation.isPending ||
                deleteMutation.isPending ||
                executeMutation.isPending ||
                lockStatus?.data.lock ||
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
                "🔒 Locked"
              ) : (
                "▶ Execute"
              )}
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="px-3 py-1 text-sm text-white bg-[#c72e2e] border border-[#d73737] rounded hover:bg-[#d73737] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={saveMutation.isPending || deleteMutation.isPending}
            >
              Delete
            </button>
            <button
              onClick={handleSave}
              className="px-3 py-1 text-sm text-white bg-[#0e639c] border border-[#1177bb] rounded hover:bg-[#1177bb] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={saveMutation.isPending || deleteMutation.isPending}
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </div>

        {saveMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>Failed to save flow: {saveMutation.error.message}</span>
          </div>
        )}

        {deleteMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>Failed to delete flow: {deleteMutation.error.message}</span>
          </div>
        )}

        {executeMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>Failed to execute flow: {executeMutation.error.message}</span>
          </div>
        )}

        {/* Main Editor Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Editor */}
          <div className="flex-1 flex flex-col">
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
                scrollBeyondLastLine: false,
                wordWrap: "on",
                folding: true,
                renderLineHighlight: "all",
                cursorStyle: "line",
                cursorBlinking: "blink",
              }}
            />
          </div>

          {/* Right Sidebar - Metadata */}
          <div className="w-80 bg-[#252526] border-l border-[#3e3e3e] overflow-y-auto">
            <div className="p-4">
              <h2 className="text-sm font-semibold text-white mb-4">
                PROPERTIES
              </h2>

              <div className="space-y-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Flow Name
                    </span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-gray-500"
                    value={name}
                    disabled
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs text-gray-500">
                      Cannot be changed
                    </span>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Description
                    </span>
                  </label>
                  <textarea
                    className="textarea textarea-bordered textarea-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
                    placeholder="Describe your flow..."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Entrypoint Function
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder="simple_flow"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
                    value={flowFunctionName}
                    onChange={(e) => setFlowFunctionName(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs text-gray-500">
                      The @flow decorated function name in your code
                    </span>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Username *
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder="your_username"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Chip ID *
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder="64Qv3"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
                    value={chipId}
                    onChange={(e) => setChipId(e.target.value)}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Tags
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder="tag1, tag2, tag3"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs text-gray-500">
                      Comma-separated
                    </span>
                  </label>
                </div>

                <div className="divider my-2"></div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      File Path
                    </span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-gray-500 text-xs"
                    value={data?.data?.file_path || ""}
                    disabled
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* VSCode-style Status Bar */}
        <div className="flex items-center justify-between px-4 py-1 bg-[#007acc] text-white text-xs">
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
      </div>
    </>
  );
}
