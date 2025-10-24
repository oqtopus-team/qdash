"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  saveFlow,
  listFlowTemplates,
  getFlowTemplate,
} from "@/client/flow/flow";
import { useListChips } from "@/client/chip/chip";
import { useAuthReadUsersMe } from "@/client/auth/auth";
import type { SaveFlowRequest } from "@/schemas";
import dynamic from "next/dynamic";
import { toast } from "react-toastify";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function NewFlowPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [flowFunctionName, setFlowFunctionName] = useState("");
  const [username, setUsername] = useState("");
  const [chipId, setChipId] = useState("");
  const [tags, setTags] = useState("");
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");

  // Fetch current user
  const { data: userData } = useAuthReadUsersMe();

  // Fetch chips
  const { data: chipsData } = useListChips();

  // Fetch templates
  const { data: templatesData } = useQuery({
    queryKey: ["flowTemplates"],
    queryFn: () => listFlowTemplates(),
  });

  const templates = templatesData?.data || [];

  // Set default username and chip_id
  useEffect(() => {
    if (userData?.data?.username && !username) {
      setUsername(userData.data.username);
    }
  }, [userData, username]);

  useEffect(() => {
    if (chipsData?.data && chipsData.data.length > 0 && !chipId) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setChipId(sortedChips[0].chip_id);
    }
  }, [chipsData, chipId]);

  // Load default template (simple) on mount
  useEffect(() => {
    const loadDefaultTemplate = async () => {
      try {
        const response = await getFlowTemplate("simple");
        const template = response.data;

        setCode(template.code);
        setFlowFunctionName(template.function_name);
        setDescription(template.description);
        setSelectedTemplateId("simple");
      } catch (error) {
        console.error("Failed to load default template:", error);
        toast.error("Failed to load default template");
        // Set a minimal fallback template if loading fails
        setCode(
          "# Failed to load template. Please select one from the dropdown.",
        );
      }
    };

    loadDefaultTemplate();
  }, []);

  // Load template when selected
  const handleTemplateSelect = async (templateId: string) => {
    if (!templateId) return;

    setSelectedTemplateId(templateId);

    try {
      const response = await getFlowTemplate(templateId);
      const template = response.data;

      setCode(template.code);
      setFlowFunctionName(template.function_name);
      setDescription(template.description);
      toast.success("Template loaded successfully");
    } catch (error) {
      console.error("Failed to load template:", error);
      toast.error("Failed to load template");
    }
  };

  const saveMutation = useMutation({
    mutationFn: (request: SaveFlowRequest) => saveFlow(request),
    onSuccess: (response) => {
      router.push(`/flow/${response.data.name}`);
    },
  });

  const handleSave = () => {
    if (!name.trim()) {
      toast.error("Please enter a flow name");
      return;
    }

    if (!/^[a-zA-Z0-9_]+$/.test(name)) {
      toast.error(
        "Flow name must contain only alphanumeric characters and underscores",
      );
      return;
    }

    if (!username.trim()) {
      toast.error("Please enter a username");
      return;
    }

    const request: SaveFlowRequest = {
      name: name.trim(),
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

  return (
    <>
      <ToastContainer position="top-right" autoClose={3000} />
      <div className="h-screen flex flex-col bg-[#1e1e1e]">
        {/* VSCode-style Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-[#3e3e3e]">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.back()}
              className="px-3 py-1 text-sm text-white bg-[#3c3c3c] border border-[#454545] rounded hover:bg-[#505050] transition-colors"
              disabled={saveMutation.isPending}
            >
              ← Back
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">●</span>
              <span className="text-sm font-medium text-white">
                {name || "new_flow"}.py
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              className="px-3 py-1 text-sm text-white bg-[#0e639c] border border-[#1177bb] rounded hover:bg-[#1177bb] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                "Save Flow"
              )}
            </button>
          </div>
        </div>

        {saveMutation.isError && (
          <div className="alert alert-error mx-4 mt-2">
            <span>Failed to save flow: {saveMutation.error.message}</span>
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
              {/* Template Selector */}
              <div className="mb-6">
                <h2 className="text-sm font-semibold text-white mb-3">
                  TEMPLATE
                </h2>
                <select
                  value={selectedTemplateId}
                  onChange={(e) => handleTemplateSelect(e.target.value)}
                  className="w-full px-3 py-2 bg-[#3c3c3c] text-white text-sm border border-[#454545] rounded focus:outline-none focus:border-[#007acc]"
                >
                  <option value="">Select a template...</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name} - {template.description}
                    </option>
                  ))}
                </select>
                {selectedTemplateId && (
                  <p className="text-xs text-gray-400 mt-2">
                    Template loaded. You can modify the code as needed.
                  </p>
                )}
              </div>

              <h2 className="text-sm font-semibold text-white mb-4">
                PROPERTIES
              </h2>

              <div className="space-y-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs text-gray-400">
                      Flow Name *
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder="my_flow"
                    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs text-gray-500">
                      Alphanumeric and underscores only
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
      </div>
    </>
  );
}
