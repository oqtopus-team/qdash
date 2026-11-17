"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useRef, useState } from "react";
import { useController, useForm, type FieldErrors } from "react-hook-form";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { GetFlowResponse, SaveFlowRequest } from "@/schemas";

import { useGetCurrentUser } from "@/client/auth/auth";
import { useListChips } from "@/client/chip/chip";
import { getFlow, getListFlowsQueryKey, saveFlow } from "@/client/flow/flow";
import type { JourneyContext } from "@/components/features/first-calibration/useFirstCalibrationJourney";
import {
  flowPropertiesSchema,
  type FlowPropertiesFormData,
  type FlowPropertiesFormInput,
} from "@/components/features/flow/flowMetadataSchema";
import { useToast } from "@/components/ui/Toast";

export type FlowPropertyField = keyof FlowPropertiesFormInput;

const EMPTY_PROPERTIES: FlowPropertiesFormInput = {
  description: "",
  flow_function_name: "",
  username: "",
  chip_id: "",
  tags: "",
  folder: "",
  default_interval: "",
};

/**
 * One workflow open in an editor pane: its saved source, the draft being edited, its
 * properties, and the save that writes them back. The workflow editor holds one per pane,
 * so each pane edits and saves its own workflow. The properties are a React Hook Form form
 * validated by `flowPropertiesSchema`.
 */
export interface FlowDocument {
  /** The workflow this document is for, or null for an empty pane. */
  name: string | null;
  /** The saved workflow, once it has loaded for `name`. */
  flow: GetFlowResponse | undefined;
  isLoading: boolean;
  error: unknown;
  /**
   * The draft and properties below belong to `name`. False while another workflow's values
   * are still in state, so nothing is shown, edited or saved under the wrong name.
   */
  isReady: boolean;
  code: string;
  setCode: (code: string) => void;
  description: string;
  setDescription: (value: string) => void;
  flowFunctionName: string;
  setFlowFunctionName: (value: string) => void;
  username: string;
  setUsername: (value: string) => void;
  chipId: string;
  setChipId: (value: string) => void;
  tags: string;
  setTags: (value: string) => void;
  folder: string;
  setFolder: (value: string) => void;
  defaultInterval: string;
  setDefaultInterval: (value: string) => void;
  /** Validation errors of the properties from the last save attempt, cleared as they are fixed. */
  propertyErrors: FieldErrors<FlowPropertiesFormInput>;
  /** The draft differs from the saved source. */
  isDirty: boolean;
  /**
   * Validate the properties and save them with the draft under `name`. Invalid properties are
   * not saved; `onInvalid` receives their errors. Does nothing while no workflow is ready.
   */
  save: (
    context: JourneyContext,
    onInvalid?: (errors: FieldErrors<FlowPropertiesFormInput>) => void,
  ) => void;
  isSaving: boolean;
  saveError: unknown;
  resetSave: () => void;
}

/** The save request for a workflow's draft and its validated properties. */
function buildSaveRequest(
  name: string,
  code: string,
  values: FlowPropertiesFormData,
): SaveFlowRequest {
  return {
    name,
    description: values.description,
    code,
    flow_function_name: values.flow_function_name,
    chip_id: values.chip_id,
    tags: values.tags,
    folder: values.folder,
    default_parameters: {
      username: values.username,
      chip_id: values.chip_id,
    },
    default_run_parameters: values.default_interval
      ? {
          interval: {
            value: values.default_interval,
            value_type: "int",
            unit: "ns",
          },
        }
      : {},
  };
}

export function useFlowDocument(name: string | null): FlowDocument {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: userData } = useGetCurrentUser();
  const { data: chipsData } = useListChips();

  const [loadedName, setLoadedName] = useState<string | null>(null);
  // Read by a save that answers later, to tell whether the pane still shows the saved workflow.
  const loadedNameRef = useRef<string | null>(null);
  // Counts each time a workflow is opened, so a save that answers after the pane reopened its
  // workflow does not move the new draft's baseline.
  const openCountRef = useRef(0);
  const [code, setCode] = useState("");
  const [originalCode, setOriginalCode] = useState("");

  const {
    control,
    handleSubmit,
    reset,
    setValue,
    formState: { errors: propertyErrors },
  } = useForm<FlowPropertiesFormInput, unknown, FlowPropertiesFormData>({
    resolver: zodResolver(flowPropertiesSchema),
    defaultValues: EMPTY_PROPERTIES,
    shouldFocusError: false,
  });
  const { field: descriptionField } = useController({ control, name: "description" });
  const { field: flowFunctionNameField } = useController({ control, name: "flow_function_name" });
  const { field: usernameField } = useController({ control, name: "username" });
  const { field: chipIdField } = useController({ control, name: "chip_id" });
  const { field: tagsField } = useController({ control, name: "tags" });
  const { field: folderField } = useController({ control, name: "folder" });
  const { field: defaultIntervalField } = useController({ control, name: "default_interval" });
  const username = usernameField.value;
  const chipId = chipIdField.value;

  const { data, isLoading, error } = useQuery({
    queryKey: ["flow", name],
    queryFn: () => getFlow(name as string),
    enabled: Boolean(name),
  });
  const flow = name ? data?.data : undefined;

  // The signed-in user, read when a workflow loads without a saved username.
  const currentUsername = useRef<string | undefined>(undefined);
  useEffect(() => {
    currentUsername.current = userData?.data?.username;
  });

  // Load the saved workflow into the draft only when it is opened. A refetch of the open
  // workflow, such as the one after a save, never replaces the draft, so edits made while a save
  // was pending survive. When the query drops its data (a project switch resets it), the next
  // answer opens the workflow again.
  useEffect(() => {
    if (!name || !flow) {
      if (loadedNameRef.current !== null) {
        loadedNameRef.current = null;
        setLoadedName(null);
      }
      return;
    }
    if (loadedNameRef.current === name) return;
    setCode(flow.code);
    setOriginalCode(flow.code);

    // Set username from flow or fallback to current user
    const flowUsername = (flow.default_parameters?.username as string) || "";
    const runParams = flow.default_run_parameters as
      | Record<string, { value?: string | number }>
      | undefined;
    reset({
      description: flow.description,
      flow_function_name: flow.flow_function_name,
      username: flowUsername || currentUsername.current || "",
      chip_id: flow.chip_id,
      tags: flow.tags?.join(", ") || "",
      folder: flow.folder ?? "",
      default_interval: runParams?.interval?.value != null ? String(runParams.interval.value) : "",
    });
    openCountRef.current += 1;
    loadedNameRef.current = name;
    setLoadedName(name);
  }, [name, flow, reset]);

  // Set default username if not set by flow data
  useEffect(() => {
    if (userData?.data?.username && !username && !flow) {
      setValue("username", userData.data.username);
    }
  }, [userData, username, flow, setValue]);

  // Set default chip_id if not set by flow data
  useEffect(() => {
    if (chipsData?.data?.chips && chipsData.data.chips.length > 0 && !chipId && !flow) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setValue("chip_id", sortedChips[0].chip_id);
    }
  }, [chipsData, chipId, flow, setValue]);

  const isReady = Boolean(name && flow && loadedName === name);

  // A save answers for the user and project it was submitted in; one that lands after a
  // project switch is dropped. The submitted source becomes the baseline only while the pane
  // still holds the draft it was submitted from, so edits made after submitting stay unsaved.
  const saveMutation = useMutation({
    mutationFn: ({
      request,
    }: {
      request: SaveFlowRequest;
      context: JourneyContext;
      openCount: number;
    }) => saveFlow(request),
    onSuccess: (_response, { request, context, openCount }) => {
      if (!context.isCurrent()) return;
      queryClient.invalidateQueries({ queryKey: ["flow", request.name] });
      // The Workflow page lists under ["flows"]; the editor's Explorer uses the generated key.
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: getListFlowsQueryKey() });
      queryClient.invalidateQueries({ queryKey: ["execution-availability"] });
      if (loadedNameRef.current === request.name && openCountRef.current === openCount) {
        setOriginalCode(request.code);
      }
      toast.success(`${request.name} saved successfully!`);
    },
  });
  const mutateSave = saveMutation.mutate;

  const save = useCallback(
    (
      context: JourneyContext,
      onInvalid?: (errors: FieldErrors<FlowPropertiesFormInput>) => void,
    ) => {
      if (!name || !isReady) return;
      void handleSubmit((values) => {
        mutateSave({
          request: buildSaveRequest(name, code, values),
          context,
          openCount: openCountRef.current,
        });
      }, onInvalid)();
    },
    [name, isReady, code, handleSubmit, mutateSave],
  );

  return {
    name,
    flow,
    isLoading: Boolean(name) && isLoading,
    error: name ? error : null,
    isReady,
    code,
    setCode,
    description: descriptionField.value,
    setDescription: descriptionField.onChange,
    flowFunctionName: flowFunctionNameField.value,
    setFlowFunctionName: flowFunctionNameField.onChange,
    username,
    setUsername: usernameField.onChange,
    chipId,
    setChipId: chipIdField.onChange,
    tags: tagsField.value,
    setTags: tagsField.onChange,
    folder: folderField.value,
    setFolder: folderField.onChange,
    defaultInterval: defaultIntervalField.value,
    setDefaultInterval: defaultIntervalField.onChange,
    propertyErrors,
    isDirty: isReady && code !== originalCode,
    save,
    isSaving: saveMutation.isPending,
    saveError: saveMutation.error,
    resetSave: saveMutation.reset,
  };
}
