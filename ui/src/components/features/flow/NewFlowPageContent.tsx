"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useForm, useWatch, type FieldErrors } from "react-hook-form";

import { useMutation, useQuery } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";

import { SelectedLabel } from "@/components/ui/SelectedLabel";
import { useToast } from "@/components/ui/Toast";

import type {
  FlowTemplate,
  ListTaskFileBackendsResponse,
  SaveFlowRequest,
  SaveFlowResponse,
  TaskFileBackend,
  TaskFileSettings,
} from "@/schemas";
import { isAxiosError, type AxiosResponse } from "axios";

import { useGetCurrentUser } from "@/client/auth/auth";
import { useChatDock } from "@/contexts/ChatDockContext";
import { useProject } from "@/contexts/ProjectContext";
import { useListChips } from "@/client/chip/chip";
import { getFlowTemplate, listFlowTemplates, saveFlow, useListFlows } from "@/client/flow/flow";
import {
  useFirstCalibrationJourney,
  type JourneyContext,
} from "@/components/features/first-calibration/useFirstCalibrationJourney";
import {
  flowMetadataSchema,
  type FlowMetadataFormData,
  type FlowMetadataFormInput,
} from "@/components/features/flow/flowMetadataSchema";
import { getTaskFileSettings, listTaskFileBackends } from "@/client/task-file/task-file";
import { JOURNEY_QUERY_VALUE, suggestJourneyFlowName } from "@/lib/firstCalibrationJourney";
import { formatMuxIds, summarizeFlowCode } from "@/lib/flowCodeSummary";
import { pickDefaultTemplate } from "@/lib/flowTemplates";
import { monoFontFamily, remeasureMonacoFontsWhenLoaded } from "@/lib/fonts";
import { getApiErrorMessage } from "@/lib/utils/apiError";

// Monaco Editor is only available on client side
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

/** A save as submitted, with the user and project it was submitted in. */
interface SaveSubmission {
  request: SaveFlowRequest;
  context: JourneyContext;
  /** The save was made for the first calibration guide. */
  forJourney: boolean;
}

type SaveError = { kind: "conflict"; name: string } | { kind: "failed"; message: string };

/** Metadata fields in form order, used to pick the first invalid one to reveal. */
const METADATA_FIELD_ORDER: readonly (keyof FlowMetadataFormInput)[] = [
  "name",
  "description",
  "flow_function_name",
  "username",
  "tags",
  "folder",
];

type TemplateOption = {
  value: string;
  label: string;
  description?: string;
};

/**
 * New Flow editor. It only ever creates a flow: the save is create-only, so a name that is taken,
 * also by a flow created in the meantime, is refused by the API and the user picks another name.
 *
 * Opened from the first calibration guide (`?journey=first-calibration`), it suggests a free flow
 * name and reports the saved flow to the guide; it never runs anything. A save that answers after
 * the user switched project is ignored, so it neither moves the new project's guide nor navigates.
 */
export function NewFlowPageContent() {
  const router = useRouter();
  const toast = useToast();
  const {
    control,
    register,
    handleSubmit,
    getValues,
    setValue,
    setFocus,
    formState: { errors },
  } = useForm<FlowMetadataFormInput, unknown, FlowMetadataFormData>({
    resolver: zodResolver(flowMetadataSchema),
    defaultValues: {
      name: "",
      description: "",
      flow_function_name: "",
      username: "",
      tags: "",
      folder: "",
    },
    shouldFocusError: false,
  });
  const name = useWatch({ control, name: "name" });
  const username = useWatch({ control, name: "username" });
  const [code, setCode] = useState("");
  const [chipId, setChipId] = useQueryState("chip_id", parseAsString.withDefault(""));
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [saveError, setSaveError] = useState<SaveError | null>(null);
  const pendingFieldFocus = useRef<keyof FlowMetadataFormInput | null>(null);
  const [fieldFocusRequest, setFieldFocusRequest] = useState(0);
  const nameInputId = useId();
  const nameErrorId = useId();
  const nameFieldErrorId = useId();
  const usernameInputId = useId();
  const usernameErrorId = useId();
  // Templates are listed per backend, like the task catalog on the Tasks page.
  const [selectedBackend, setSelectedBackend] = useQueryState("backend", parseAsString);
  // A link may name the template to open first, e.g. after creating a fake preset chip.
  const [requestedTemplateId] = useQueryState("template", parseAsString);
  const [journeyParam] = useQueryState("journey", parseAsString);
  const journey = useFirstCalibrationJourney();
  const journeyState = journey.state?.status === "active" ? journey.state : null;
  const fromJourney = journeyParam === JOURNEY_QUERY_VALUE && journeyState !== null;
  const journeyChipId = fromJourney ? journeyState.chipId : null;

  // The chat sidebar sees the flow being written here and can propose its code.
  const { registerPage } = useChatDock();
  const pageState = useRef({ name, chipId, code });
  // Written after each commit, never during render; the provider below reads it when a turn is sent.
  useEffect(() => {
    pageState.current = { name, chipId, code };
  });
  useEffect(
    () =>
      registerPage({
        current: () => {
          const { name, chipId, code } = pageState.current;
          return {
            path: "/workflow/new",
            title: "New workflow",
            flow: {
              name: name || "new_flow",
              chipId: chipId || undefined,
              code,
              dirty: true,
            },
          };
        },
        applyCode: setCode,
      }),
    [registerPage],
  );

  // Fetch current user
  const { data: userData } = useGetCurrentUser();

  // Fetch chips
  const { data: chipsData } = useListChips();

  // Flow names are unique per project and saving reuses a name, so the guide suggests a free one.
  const { data: flowsData } = useListFlows({ query: { enabled: fromJourney } });
  const flowNames = flowsData?.data?.flows;
  const suggestedName = useRef(false);
  useEffect(() => {
    if (!fromJourney || suggestedName.current || !flowNames) return;
    suggestedName.current = true;
    if (getValues("name")) return;
    setValue("name", suggestJourneyFlowName(flowNames.map((flow) => flow.name)));
  }, [flowNames, fromJourney, getValues, setValue]);

  const { data: settingsData, isPending: isSettingsPending } = useQuery({
    queryKey: ["taskFileSettings"],
    queryFn: () =>
      getTaskFileSettings().then((response: AxiosResponse<TaskFileSettings>) => response.data),
  });

  const { data: backendsData } = useQuery({
    queryKey: ["taskFileBackends"],
    queryFn: () =>
      listTaskFileBackends().then(
        (response: AxiosResponse<ListTaskFileBackendsResponse>) => response.data,
      ),
  });

  // Start on the configured default backend unless the URL already names one.
  useEffect(() => {
    if (isSettingsPending || !backendsData?.backends.length || selectedBackend) return;
    const configuredBackend = settingsData?.default_backend;
    const backend = backendsData.backends.find((item) => item.name === configuredBackend);
    setSelectedBackend(backend?.name ?? backendsData.backends[0].name);
  }, [
    backendsData?.backends,
    isSettingsPending,
    selectedBackend,
    setSelectedBackend,
    settingsData?.default_backend,
  ]);

  // Fetch the templates written for the selected backend
  const { data: templatesData, isLoading: isTemplatesLoading } = useQuery({
    queryKey: ["flowTemplates", selectedBackend],
    queryFn: () => listFlowTemplates({ backend: selectedBackend }),
    enabled: Boolean(selectedBackend),
  });

  const templateOptions: TemplateOption[] = useMemo(
    () =>
      (templatesData?.data ?? []).map((template: FlowTemplate) => ({
        value: template.id,
        label: template.description ? `${template.name} - ${template.description}` : template.name,
        description: template.description,
      })),
    [templatesData],
  );

  // Template select styles removed - using DaisyUI native select instead

  // The first calibration guide points at the template once its code is in the editor.
  const templateReady = selectedTemplateId !== "" && code.trim() !== "";
  // What the code in the editor runs, shown to the guide; it follows the user's edits.
  const codeSummary = useMemo(() => summarizeFlowCode(code), [code]);

  // Set default username and chip_id
  useEffect(() => {
    if (userData?.data?.username && !username) {
      setValue("username", userData.data.username);
    }
  }, [userData, username, setValue]);

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
  }, [chipsData, chipId, setChipId]);

  // Only the newest template request may touch the editor: a backend switch or a newer pick
  // retires older requests, and a source edit made while a request is in flight wins over it.
  const latestTemplateRequest = useRef(0);
  const sourceVersion = useRef(0);

  /** Loads a template's code, entrypoint and description, unless a newer pick or an edit won. */
  const loadTemplate = async (templateId: string, { notify }: { notify: boolean }) => {
    const requestId = ++latestTemplateRequest.current;
    const sourceAtRequest = sourceVersion.current;
    setSelectedTemplateId(templateId);
    const isCurrent = () =>
      requestId === latestTemplateRequest.current && sourceAtRequest === sourceVersion.current;
    try {
      const response = await getFlowTemplate(templateId);
      if (!isCurrent()) return;
      const template = response.data;

      setCode(template.code);
      setValue("flow_function_name", template.function_name);
      setValue("description", template.description);
      if (notify) toast.success("Template loaded successfully");
    } catch (error) {
      console.error("Failed to load template:", error);
      if (!isCurrent()) return;
      toast.error("Failed to load template");
      if (!notify) setCode("# Failed to load template. Please select one from the dropdown.");
    }
  };

  // Open the editor on the backend's default template once; switching the backend later only
  // changes the list, so the user's edits are never replaced without a pick.
  const hasLoadedInitialTemplate = useRef(false);
  useEffect(() => {
    if (hasLoadedInitialTemplate.current || !templatesData) return;
    hasLoadedInitialTemplate.current = true;
    const template = pickDefaultTemplate(templatesData.data, requestedTemplateId);
    if (template) {
      void loadTemplate(template.id, { notify: false });
    } else {
      setCode("# No template for this backend. Select another backend or start from scratch.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, when the first template list arrives
  }, [templatesData]);

  // Load template when selected
  const handleTemplateSelect = (templateId: string) => {
    if (!templateId) return;
    void loadTemplate(templateId, { notify: true });
  };

  const saveMutation = useMutation({
    mutationFn: ({ request }: SaveSubmission) => saveFlow(request),
    onSuccess: (
      response: AxiosResponse<SaveFlowResponse>,
      { request, context, forJourney }: SaveSubmission,
    ) => {
      // Saved in a project the user has left: nothing here speaks for it any more.
      if (!context.isCurrent()) return;
      if (forJourney) {
        context.record({
          type: "flowSaved",
          flowName: response.data.name,
          chipId: request.chip_id,
        });
      }
      router.push(`/workflow/${encodeURIComponent(response.data.name)}`);
    },
    onError: (error: unknown, { request, context }: SaveSubmission) => {
      if (!context.isCurrent()) return;
      if (isAxiosError(error) && error.response?.status === 409) {
        // The inputs stay as they are; only the name has to change.
        setSaveError({ kind: "conflict", name: request.name });
        revealField("name");
        return;
      }
      setSaveError({
        kind: "failed",
        message: getApiErrorMessage(error, "Unknown error"),
      });
    },
  });

  // A save error belongs to the project it was made in.
  const { projectId } = useProject();
  useEffect(() => {
    setSaveError(null);
  }, [projectId]);

  /** Shows the Properties panel and focuses a metadata field once the panel has rendered. */
  const revealField = (field: keyof FlowMetadataFormInput) => {
    setIsSidebarVisible(true);
    pendingFieldFocus.current = field;
    setFieldFocusRequest((request) => request + 1);
  };

  useEffect(() => {
    const field = pendingFieldFocus.current;
    if (!field) return;
    pendingFieldFocus.current = null;
    setFocus(field);
  }, [fieldFocusRequest, setFocus]);

  /** Reveals the first invalid metadata field, in form order, so a hidden panel never hides it. */
  const revealInvalidField = (fieldErrors: FieldErrors<FlowMetadataFormInput>) => {
    const field = METADATA_FIELD_ORDER.find((key) => fieldErrors[key]);
    if (field) revealField(field);
  };

  /** Submits the validated metadata with the editor code and the chip from the URL. */
  const submitFlow = (values: FlowMetadataFormData) => {
    const request: SaveFlowRequest = {
      // Creating never replaces a flow, even one created since this page opened.
      create_only: true,
      name: values.name,
      description: values.description,
      code,
      flow_function_name: values.flow_function_name,
      chip_id: chipId.trim(),
      tags: values.tags,
      folder: values.folder,
      default_parameters: {
        username: values.username,
        chip_id: chipId.trim(),
      },
    };

    setSaveError(null);
    saveMutation.mutate({
      request,
      context: journey.capture(),
      forJourney: fromJourney,
    });
  };
  const handleSave = handleSubmit(submitFlow, revealInvalidField);
  const nameConflict = saveError?.kind === "conflict";

  return (
    <>
      {/* Fills the page area under the navbar and the guide banner, whatever their height. */}
      <div className="flex h-full min-h-0 flex-col bg-base-300">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0">
            <button
              type="button"
              onClick={() => router.back()}
              className="btn btn-sm btn-ghost"
              disabled={saveMutation.isPending}
              aria-label="Back"
            >
              <span aria-hidden="true">←</span>
            </button>
            <button
              type="button"
              onClick={() => setIsSidebarVisible(!isSidebarVisible)}
              className="btn btn-sm btn-ghost sm:hidden"
              title={isSidebarVisible ? "Hide properties" : "Show properties"}
              aria-label={isSidebarVisible ? "Hide properties" : "Show properties"}
              aria-expanded={isSidebarVisible}
            >
              <span aria-hidden="true">☰</span>
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
              type="button"
              onClick={() => setIsSidebarVisible(!isSidebarVisible)}
              className="btn btn-sm btn-ghost hidden sm:flex"
              title={isSidebarVisible ? "Hide properties" : "Show properties"}
              aria-label={isSidebarVisible ? "Hide properties" : "Show properties"}
              aria-expanded={isSidebarVisible}
            >
              <span aria-hidden="true">☰</span>
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="btn btn-sm btn-primary"
              disabled={saveMutation.isPending}
              data-coachmark="flow-save"
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

        {journeyChipId && chipId.trim() !== journeyChipId && (
          <div className="alert alert-warning mx-4 mt-2" role="status">
            <span className="break-words">
              The first calibration guide follows chip {journeyChipId}. Set Chip ID back to{" "}
              {journeyChipId} to continue the guide with this flow.
            </span>
          </div>
        )}

        {saveError && (
          <div role="alert" id={nameErrorId} className="alert alert-error mx-4 mt-2">
            <span className="break-words">
              {saveError.kind === "conflict"
                ? `A flow named ${saveError.name} already exists, so nothing was saved. Enter another name in Flow Name and save again.`
                : `Failed to save flow: ${saveError.message}`}
            </span>
          </div>
        )}

        {/* Main Editor Area */}
        <div className="relative flex min-h-0 flex-1 overflow-hidden">
          {/* Editor */}
          <div className="flex-1 flex flex-col min-w-0">
            <Editor
              height="100%"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(value) => {
                sourceVersion.current += 1;
                setCode(value || "");
              }}
              onMount={(editor, monaco) => {
                remeasureMonacoFontsWhenLoaded(monaco);
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
                fontFamily: monoFontFamily,
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
              className="absolute inset-0 bg-black/50 z-10 sm:hidden"
              onClick={() => setIsSidebarVisible(false)}
            />
          )}

          {/* Right Sidebar - Metadata */}
          <div
            className={`${isSidebarVisible ? "w-72 sm:w-80" : "w-0"} bg-base-100 border-l border-base-300 overflow-x-hidden overflow-y-auto transition-all duration-200 flex-shrink-0 ${isSidebarVisible ? "absolute sm:relative right-0 top-0 h-full z-20 sm:z-auto" : ""}`}
          >
            <div className="p-4">
              {/* Mobile Close Button */}
              <div className="flex justify-between items-center mb-4 sm:hidden">
                <span className="text-sm font-medium">Properties</span>
                <button
                  type="button"
                  onClick={() => setIsSidebarVisible(false)}
                  className="btn btn-ghost btn-sm btn-square"
                  aria-label="Close properties"
                >
                  <span aria-hidden="true">✕</span>
                </button>
              </div>
              {fromJourney && templateReady && (
                <FlowCodeSummaryPanel
                  tasks={codeSummary.tasks}
                  muxIds={codeSummary.muxIds}
                  chipId={chipId.trim()}
                />
              )}

              {/* Template Selector */}
              <div
                className="mb-6"
                data-coachmark="flow-template"
                data-coachmark-ready={templateReady ? "true" : undefined}
              >
                <h2 className="text-sm font-medium mb-3">Template</h2>
                <label className="label py-1" htmlFor="template-backend">
                  <span className="label-text text-xs">Backend</span>
                </label>
                <select
                  id="template-backend"
                  className="select select-bordered select-sm w-full mb-3"
                  value={selectedBackend ?? ""}
                  onChange={(e) => {
                    latestTemplateRequest.current += 1;
                    setSelectedBackend(e.target.value);
                    setSelectedTemplateId("");
                  }}
                  disabled={!backendsData?.backends.length}
                >
                  <SelectedLabel />
                  {backendsData?.backends.map((backend: TaskFileBackend) => (
                    <option key={backend.name} value={backend.name}>
                      {backend.name}
                    </option>
                  ))}
                </select>
                <select
                  className="select select-bordered select-sm w-full"
                  aria-label="Template"
                  value={selectedTemplateId}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (!value) {
                      setSelectedTemplateId("");
                      return;
                    }
                    handleTemplateSelect(value);
                  }}
                  disabled={isTemplatesLoading || !selectedBackend}
                >
                  <SelectedLabel />
                  <option value="">Select a template...</option>
                  {templateOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                {selectedTemplateId ? (
                  <p className="text-xs text-base-content/60 mt-2">
                    Template loaded. You can modify the code as needed.
                  </p>
                ) : selectedBackend && !isTemplatesLoading && templateOptions.length === 0 ? (
                  <p className="text-xs text-base-content/60 mt-2">
                    No templates are written for the {selectedBackend} backend
                  </p>
                ) : null}
              </div>

              <h2 className="text-sm font-medium mb-4">Properties</h2>

              <div className="space-y-4">
                <div className="form-control">
                  <label className="label" htmlFor={nameInputId}>
                    <span className="label-text text-xs">Flow Name *</span>
                  </label>
                  <input
                    id={nameInputId}
                    data-coachmark="flow-name"
                    type="text"
                    placeholder="my_flow"
                    className={`input input-bordered input-sm ${errors.name || nameConflict ? "input-error" : ""}`}
                    aria-invalid={Boolean(errors.name) || nameConflict || undefined}
                    aria-describedby={
                      errors.name ? nameFieldErrorId : nameConflict ? nameErrorId : undefined
                    }
                    {...register("name", {
                      onChange: () => {
                        if (nameConflict) setSaveError(null);
                      },
                    })}
                  />
                  {errors.name && (
                    <p id={nameFieldErrorId} className="mt-1 text-xs text-error">
                      {errors.name.message}
                    </p>
                  )}
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
                    rows={3}
                    {...register("description")}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Entrypoint Function</span>
                  </label>
                  <input
                    type="text"
                    placeholder="simple_flow"
                    className="input input-bordered input-sm"
                    {...register("flow_function_name")}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      The @flow decorated function name in your code
                    </span>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label" htmlFor={usernameInputId}>
                    <span className="label-text text-xs">Username *</span>
                  </label>
                  <input
                    id={usernameInputId}
                    type="text"
                    placeholder="your_username"
                    className={`input input-bordered input-sm ${errors.username ? "input-error" : ""}`}
                    aria-invalid={Boolean(errors.username)}
                    aria-describedby={errors.username ? usernameErrorId : undefined}
                    {...register("username")}
                  />
                  {errors.username && (
                    <p id={usernameErrorId} className="mt-1 text-xs text-error">
                      {errors.username.message}
                    </p>
                  )}
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
                    {...register("tags")}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">Comma-separated</span>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-xs">Folder</span>
                  </label>
                  <input
                    type="text"
                    placeholder="daily/t1"
                    className="input input-bordered input-sm"
                    {...register("folder")}
                  />
                  <label className="label">
                    <span className="label-text-alt text-xs">
                      Where it sits in your space on the Workflow page; "/" nests
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

interface FlowCodeSummaryPanelProps {
  tasks: string[] | null;
  muxIds: number[] | null;
  chipId: string;
}

/**
 * What the code in the editor runs, for the first calibration guide: the task list and the MUX
 * targets the template declares. It only reads the code; edits in the editor update it.
 */
function FlowCodeSummaryPanel({ tasks, muxIds, chipId }: FlowCodeSummaryPanelProps) {
  return (
    <section
      className="mb-6 border-b border-base-content/10 pb-6"
      aria-labelledby="flow-code-summary-heading"
      data-coachmark="flow-summary"
      data-coachmark-ready="true"
    >
      <h2 id="flow-code-summary-heading" className="text-sm font-medium">
        What this flow runs
      </h2>
      <p className="mt-0.5 text-xs text-base-content/60">Follows the code in the editor</p>
      <dl className="mt-3 space-y-3 text-xs">
        <div>
          <dt className="font-medium text-base-content/60">Tasks, in order</dt>
          <dd className="mt-1">
            {tasks ? (
              <ol className="space-y-0.5" aria-label="Tasks in run order">
                {tasks.map((task, index) => (
                  <li key={`${task}-${index}`} className="flex gap-2">
                    <span className="w-5 shrink-0 text-right tabular-nums text-base-content/60">
                      {index + 1}.
                    </span>{" "}
                    <span className="min-w-0 break-all font-mono">{task}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <span className="text-base-content/60">Listed in the code</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-base-content/60">Targets</dt>
          <dd className="mt-1 break-words">
            {muxIds ? (
              <>
                <span className="font-mono">{formatMuxIds(muxIds)}</span>
                {chipId ? ` of ${chipId}` : ""}
                <span className="mt-0.5 block text-base-content/60">
                  Each MUX&apos;s qubits come from the chip wiring
                </span>
              </>
            ) : (
              <span className="text-base-content/60">Set in the code</span>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}
