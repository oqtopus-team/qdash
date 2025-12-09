"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useMutation, useQuery } from "@tanstack/react-query";

import { useToast } from "@/components/ui/Toast";

import type {
  SaveFlowRequest,
  FlowTemplate,
  SaveFlowResponse,
} from "@/schemas";
import type { AxiosResponse } from "axios";

import { useGetCurrentUser } from "@/client/auth/auth";
import { useListChips } from "@/client/chip/chip";
import {
  getFlowTemplate,
  listFlowTemplates,
  saveFlow,
} from "@/client/flow/flow";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type TemplateOption = {
  value: string;
  label: string;
  description?: string;
};

export default function NewFlowPage() {
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [flowFunctionName, setFlowFunctionName] = useState("");
  const [username, setUsername] = useState("");
  const [chipId, setChipId] = useState("");
  const [tags, setTags] = useState("");
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);

  // Fetch current user
  const { data: userData } = useGetCurrentUser();

  // Fetch chips
  const { data: chipsData } = useListChips();

  // Fetch templates
  const { data: templatesData, isLoading: isTemplatesLoading } = useQuery({
    queryKey: ["flowTemplates"],
    queryFn: () => listFlowTemplates(),
  });

  const templateOptions: TemplateOption[] = useMemo(
    () =>
      (templatesData?.data ?? []).map((template: FlowTemplate) => ({
        value: template.id,
        label: template.description
          ? `${template.name} - ${template.description}`
          : template.name,
        description: template.description,
      })),
    [templatesData],
  );

  // Template select styles removed - using DaisyUI native select instead

  // Set default username and chip_id
  useEffect(() => {
    if (userData?.data?.username && !username) {
      setUsername(userData.data.username);
    }
  }, [userData, username]);

  useEffect(() => {
    if (chipsData?.data?.chips && chipsData.data.chips.length > 0 && !chipId) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toast is a singleton from sonner, doesn't need to be a dependency
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
    onSuccess: (response: AxiosResponse<SaveFlowResponse>) => {
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
      <div className="h-screen flex flex-col bg-base-300">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0">
            <button
              onClick={() => router.back()}
              className="btn btn-sm btn-ghost"
              disabled={saveMutation.isPending}
            >
              ←
            </button>
            <button
              onClick={() => setIsSidebarVisible(!isSidebarVisible)}
              className="btn btn-sm btn-ghost sm:hidden"
              title={isSidebarVisible ? "Hide properties" : "Show properties"}
            >
              ☰
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-base-content/50">●</span>
              <span className="text-sm font-medium text-base-content truncate">
                {name || "new_flow"}.py
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => setIsSidebarVisible(!isSidebarVisible)}
              className="btn btn-sm btn-ghost hidden sm:flex"
              title={isSidebarVisible ? "Hide properties" : "Show properties"}
            >
              ☰
            </button>
            <button
              onClick={handleSave}
              className="btn btn-sm btn-primary"
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <>
                  <span className="hidden sm:inline">Save Flow</span>
                  <span className="sm:hidden">Save</span>
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

          {/* Mobile Sidebar Overlay */}
          {isSidebarVisible && (
            <div
              className="fixed inset-0 bg-black/50 z-10 sm:hidden"
              onClick={() => setIsSidebarVisible(false)}
            />
          )}

          {/* Right Sidebar - Metadata */}
          <div
            className={`${isSidebarVisible ? "w-72 sm:w-80" : "w-0"} bg-base-100 border-l border-base-300 overflow-y-auto transition-all duration-200 overflow-hidden flex-shrink-0 ${isSidebarVisible ? "fixed sm:relative right-0 top-0 h-full z-20 sm:z-auto" : ""}`}
          >
            <div className="p-4">
              {/* Mobile Close Button */}
              <div className="flex justify-between items-center mb-4 sm:hidden">
                <span className="text-sm font-semibold">Properties</span>
                <button
                  onClick={() => setIsSidebarVisible(false)}
                  className="btn btn-ghost btn-sm btn-square"
                >
                  ✕
                </button>
              </div>
              {/* Template Selector */}
              <div className="mb-6">
                <h2 className="text-sm font-semibold mb-3">TEMPLATE</h2>
                <select
                  className="select select-bordered select-sm w-full"
                  value={selectedTemplateId}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (!value) {
                      setSelectedTemplateId("");
                      return;
                    }
                    handleTemplateSelect(value);
                  }}
                  disabled={isTemplatesLoading}
                >
                  <option value="">Select a template...</option>
                  {templateOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                {selectedTemplateId && (
                  <p className="text-xs text-base-content/60 mt-2">
                    Template loaded. You can modify the code as needed.
                  </p>
                )}
              </div>

              <h2 className="text-sm font-semibold mb-4">PROPERTIES</h2>

              <div className="space-y-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Flow Name *</span>
                  </label>
                  <input
                    type="text"
                    placeholder="my_flow"
                    className="input input-bordered input-sm"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      Alphanumeric and underscores only
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
              </div>
            </div>
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
      </div>
    </>
  );
}
